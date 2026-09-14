from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .models import Event, EventManager
from .forms import EventForm
from registrations.models import Registration, RegistrationForm as RegFormField
from analytics.models import AuditLog

@login_required
def dashboard(request):
    """
    Main dashboard view showing role-tailored stats and active events.
    """
    from certificates.models import Certificate
    from django.db.models import Count, Q
    
    if request.user.role == 'participant':
        user_regs = Registration.objects.filter(
            user=request.user
        ).select_related('event', 'event__organization').order_by('event__start_datetime')
        
        events = [reg.event for reg in user_regs if reg.event.status in ['published', 'ongoing']][:6]
        upcoming_count = len([reg for reg in user_regs if reg.event.start_datetime and reg.event.start_datetime > timezone.now()])
        certs_count = Certificate.objects.filter(registration__user=request.user, status='completed').count()
        total_registrations = user_regs.count()
        attendance_rate = "100%" if upcoming_count == 0 and total_registrations > 0 else "0%"
        total_certificates = certs_count
    else:
        # Organizer / Staff / Superuser dashboard
        if request.user.is_superuser or request.user.role in ['super_admin', 'org_admin']:
            base_events = Event.objects.all()
        else:
            user_orgs = request.user.memberships.values_list('organization_id', flat=True)
            base_events = Event.objects.filter(
                Q(organization_id__in=user_orgs) | Q(event_managers__user=request.user) | Q(created_by=request.user)
            ).distinct()

        events = base_events.filter(
            status__in=['published', 'ongoing']
        ).order_by('start_datetime').select_related('organization')[:6]
        
        upcoming_count = base_events.filter(start_datetime__gt=timezone.now(), status='published').count()
        
        event_ids = base_events.values_list('id', flat=True)
        confirmed_count = Registration.objects.filter(event_id__in=event_ids, status='confirmed').count()
        attended_count = Registration.objects.filter(event_id__in=event_ids, status='attended').count()
        total_registrations = confirmed_count + attended_count
        
        attendance_rate = f"{round((attended_count / total_registrations * 100))}%" if total_registrations > 0 else "0%"
        total_certificates = Certificate.objects.filter(registration__event_id__in=event_ids, status='completed').count()
        certs_count = total_certificates
    
    # Activity logs — prefetch user to avoid N+1
    activity_logs = AuditLog.objects.select_related('user').order_by('-timestamp')[:5]
    
    context = {
        'events': events,
        'upcoming_count': upcoming_count,
        'certs_count': certs_count,
        'total_registrations': total_registrations,
        'attendance_rate': attendance_rate,
        'total_certificates': total_certificates,
        'activity_logs': activity_logs,
    }
    return render(request, 'dashboard.html', context)

@login_required
def event_list(request):
    """
    Events directory with status filtering, live tab counts, and multi-attribute search.
    """
    from django.db.models import Q
    
    status_filter = request.GET.get('status', 'all').strip().lower()
    search_query = request.GET.get('search', '').strip()
    
    if request.user.is_superuser or request.user.role in ['super_admin', 'org_admin']:
        base_qs = Event.objects.all()
    elif request.user.role == 'participant':
        base_qs = Event.objects.filter(status='published')
    else:
        user_orgs = request.user.memberships.values_list('organization_id', flat=True)
        base_qs = Event.objects.filter(
            Q(organization_id__in=user_orgs) | Q(event_managers__user=request.user) | Q(created_by=request.user)
        ).distinct()
    
    base_qs = base_qs.select_related('organization')
    
    # Calculate counts before applying current status/search filters
    all_count = base_qs.count()
    active_count = base_qs.filter(status__in=['published', 'ongoing']).count()
    past_count = base_qs.filter(Q(status='completed') | Q(end_datetime__lt=timezone.now())).count()
    draft_count = base_qs.filter(status='draft').count()
    
    qs = base_qs
    if status_filter in ['published', 'active']:
        qs = qs.filter(status__in=['published', 'ongoing'])
    elif status_filter in ['completed', 'past']:
        qs = qs.filter(Q(status='completed') | Q(end_datetime__lt=timezone.now()))
    elif status_filter == 'draft':
        qs = qs.filter(status='draft')
        
    if search_query:
        qs = qs.filter(
            Q(title__icontains=search_query) |
            Q(venue_name__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(organization__name__icontains=search_query)
        )
        
    events = qs.order_by('-start_datetime')
    
    context = {
        'events': events,
        'current_status': status_filter if status_filter in ['published', 'active', 'completed', 'past', 'draft'] else 'all',
        'search_query': search_query,
        'all_count': all_count,
        'active_count': active_count,
        'past_count': past_count,
        'draft_count': draft_count,
    }
    return render(request, 'events/event_list.html', context)

@login_required
def event_detail(request, pk):
    from certificates.models import Certificate
    from django.db.models import Sum, Q, Count
    
    event = get_object_or_404(Event.objects.select_related('organization'), id=pk)
    registrations = event.registrations.select_related('user').order_by('-registration_date')
    
    search_query = request.GET.get('search', '').strip()
    if search_query:
        registrations = registrations.filter(
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(participant_id__icontains=search_query)
        )
    else:
        registrations = registrations[:50]
    
    # Certificate Stats — single query with aggregate
    cert_stats_agg = Certificate.objects.filter(registration__event=event).aggregate(
        total_issued=Count('id'),
        total_views=Sum('view_count'),
        total_downloads=Sum('download_count'),
    )
    cert_stats = {
        'total_issued': cert_stats_agg['total_issued'] or 0,
        'total_views': cert_stats_agg['total_views'] or 0,
        'total_downloads': cert_stats_agg['total_downloads'] or 0,
    }
    
    user_registration = None
    is_manager = False
    is_org_admin = False
    volunteer_status = None
    is_approved_volunteer = False
    
    if request.user.is_authenticated:
        user_registration = event.registrations.filter(user=request.user).first()
        
        # Check manager authorization
        if request.user.is_superuser or request.user.email.lower() == 'mayurtheprogrammer12@gmail.com':
            is_manager = True
            is_org_admin = True
        elif request.user.role in ['super_admin', 'org_admin']:
            is_manager = True
            is_org_admin = True
        elif event.organization.memberships.filter(user=request.user, role__in=['owner', 'admin']).exists():
            is_manager = True
            is_org_admin = True
        elif event.event_managers.filter(user=request.user).exists():
            is_manager = True
            
        # Check volunteer status
        from events.models import EventVolunteer
        user_volunteer = event.event_volunteers.filter(user=request.user).first()
        if user_volunteer:
            volunteer_status = user_volunteer.status
            is_approved_volunteer = (user_volunteer.status == EventVolunteer.Status.APPROVED)
    
    return render(request, 'events/event_detail.html', {
        'event': event,
        'registrations': registrations,
        'cert_stats': cert_stats,
        'search_query': search_query,
        'user_registration': user_registration,
        'is_manager': is_manager,
        'is_org_admin': is_org_admin,
        'volunteer_status': volunteer_status,
        'is_approved_volunteer': is_approved_volunteer,
    })


@login_required
def event_create(request):
    if request.method == 'POST':
        form = EventForm(request.POST, request.FILES)
        if form.is_valid():
            event = form.save(commit=False)
            # Link to first organization for now
            # Link to organization
            membership = request.user.memberships.first()
            if membership:
                event.organization = membership.organization
            elif request.user.is_superuser:
                # Fallback for superuser
                from organizations.models import Organization
                event.organization = Organization.objects.first()
                if not event.organization:
                    messages.error(request, "No organizations exist in the system.")
                    return redirect('events:event_list')
            else:
                messages.error(request, "You are not a member of any organization.")
                return redirect('events:event_list')
            
            event.created_by = request.user
            event.save()
            
            # Create Audit Log
            AuditLog.objects.create(
                user=request.user,
                organization=event.organization,
                action=AuditLog.Action.CREATE,
                description=f"Created event: {event.title}",
                content_object=event
            )
            
            messages.success(request, f"Event '{event.title}' created successfully!")
            return redirect('events:event_detail', pk=event.id)
    else:
        form = EventForm()
    
    return render(request, 'events/event_form.html', {'form': form, 'title': 'Create Event'})

@login_required
def event_update(request, pk):
    event = get_object_or_404(Event, id=pk)
    if request.method == 'POST':
        form = EventForm(request.POST, request.FILES, instance=event)
        if form.is_valid():
            event = form.save()
            
            # Create Audit Log
            AuditLog.objects.create(
                user=request.user,
                organization=event.organization,
                action=AuditLog.Action.UPDATE,
                description=f"Updated event: {event.title}",
                content_object=event
            )
            
            messages.success(request, f"Event '{event.title}' updated successfully!")
            return redirect('events:event_detail', pk=event.id)
    else:
        form = EventForm(instance=event)
    
    return render(request, 'events/event_form.html', {'form': form, 'title': f'Edit {event.title}', 'event': event})

@login_required
def export_registrations_csv(request, pk):
    """
    Renders customizable export control center dashboard or downloads generated CSV.
    """
    import csv
    import json
    from django.http import HttpResponse, JsonResponse
    from django.contrib import messages
    from registrations.models import RegistrationForm as RegFormField
    
    event = get_object_or_404(Event, id=pk)
    
    # Check manager authorization
    is_manager = False
    if request.user.is_superuser or request.user.email.lower() == 'mayurtheprogrammer12@gmail.com':
        is_manager = True
    elif request.user.role in ['super_admin', 'org_admin']:
        is_manager = True
    elif event.event_managers.filter(user=request.user).exists():
        is_manager = True
        
    if not is_manager:
        messages.error(request, "You do not have permission to export rosters for this event.")
        return redirect('events:event_detail', pk=pk)
        
    custom_fields = RegFormField.objects.filter(event=event).order_by('order')
    
    # Field definitions
    field_groups = {
        'personal': [
            ('first_name', 'First Name'),
            ('last_name', 'Last Name'),
            ('email', 'Email Address'),
            ('phone', 'Phone Number'),
        ],
        'academic': [
            ('institution', 'Institution / College'),
            ('department', 'Department / Branch'),
            ('year_of_study', 'Year of Study'),
        ],
        'professional': [
            ('github_url', 'GitHub URL'),
            ('linkedin_url', 'LinkedIn URL'),
            ('portfolio_url', 'Portfolio URL'),
        ],
        'registration': [
            ('registration_date', 'Registration Date'),
            ('status', 'Registration Status'),
            ('participant_id', 'Participant ID'),
        ],
        'credentials': [
            ('certificate_status', 'Certificate Status'),
            ('certificate_id', 'Certificate ID'),
        ]
    }
    
    # Map from field ID to human label
    all_fields_map = {}
    for group, fields in field_groups.items():
        for fid, label in fields:
            all_fields_map[fid] = label
    for cf in custom_fields:
        all_fields_map[f'custom_{cf.field_name}'] = cf.label
        
    # Check for CSV download request
    if request.GET.get('format') == 'csv':
        fields_param = request.GET.get('fields', '')
        selected_fields = [f.strip() for f in fields_param.split(',') if f.strip()]
        if not selected_fields:
            # Safe defaults
            selected_fields = ['first_name', 'last_name', 'email', 'status']
            
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{event.slug}_custom_roster.csv"'
        
        writer = csv.writer(response)
        
        # Write Header
        header = [all_fields_map.get(fid, fid) for fid in selected_fields]
        writer.writerow(header)
        
        # Prefetch user and certificates
        registrations = event.registrations.select_related('user').prefetch_related('certificates').all()
        
        for reg in registrations:
            row = []
            cert = reg.certificates.first()
            
            for fid in selected_fields:
                if fid == 'first_name':
                    row.append(reg.user.first_name)
                elif fid == 'last_name':
                    row.append(reg.user.last_name)
                elif fid == 'email':
                    row.append(reg.user.email)
                elif fid == 'phone':
                    row.append(reg.user.phone)
                elif fid == 'institution':
                    row.append(reg.user.institution)
                elif fid == 'department':
                    row.append(reg.user.department)
                elif fid == 'year_of_study':
                    row.append(reg.user.get_year_of_study_display() if hasattr(reg.user, 'get_year_of_study_display') else reg.user.year_of_study)
                elif fid == 'github_url':
                    row.append(reg.user.github_url)
                elif fid == 'linkedin_url':
                    row.append(reg.user.linkedin_url)
                elif fid == 'portfolio_url':
                    row.append(reg.user.portfolio_url)
                elif fid == 'registration_date':
                    row.append(reg.registration_date.strftime('%Y-%m-%d %H:%M:%S'))
                elif fid == 'status':
                    row.append(reg.get_status_display())
                elif fid == 'participant_id':
                    row.append(reg.participant_id)
                elif fid == 'certificate_status':
                    row.append(cert.get_status_display() if cert else 'Not Issued')
                elif fid == 'certificate_id':
                    row.append(cert.certificate_id if cert else 'N/A')
                elif fid.startswith('custom_'):
                    cf_slug = fid.replace('custom_', '', 1)
                    row.append(reg.custom_data.get(cf_slug, ''))
                else:
                    row.append('')
            writer.writerow(row)
            
        return response

    # Fetch first 5 registrations for preview
    preview_regs = event.registrations.select_related('user').prefetch_related('certificates').all()[:5]
    preview_data = []
    
    for reg in preview_regs:
        cert = reg.certificates.first()
        record = {
            'first_name': reg.user.first_name,
            'last_name': reg.user.last_name,
            'email': reg.user.email,
            'phone': reg.user.phone,
            'institution': reg.user.institution,
            'department': reg.user.department,
            'year_of_study': reg.user.get_year_of_study_display() if hasattr(reg.user, 'get_year_of_study_display') else reg.user.year_of_study,
            'github_url': reg.user.github_url,
            'linkedin_url': reg.user.linkedin_url,
            'portfolio_url': reg.user.portfolio_url,
            'registration_date': reg.registration_date.strftime('%Y-%m-%d %H:%M:%S'),
            'status': reg.get_status_display(),
            'participant_id': reg.participant_id,
            'certificate_status': cert.get_status_display() if cert else 'Not Issued',
            'certificate_id': cert.certificate_id if cert else 'N/A',
        }
        # Add custom data fields
        for cf in custom_fields:
            record[f'custom_{cf.field_name}'] = reg.custom_data.get(cf.field_name, '')
            
        preview_data.append(record)
        
    return render(request, 'events/export.html', {
        'event': event,
        'field_groups': field_groups,
        'custom_fields': custom_fields,
        'preview_data_json': json.dumps(preview_data),
    })

@login_required
def email_participants(request, pk):
    from config.task_utils import trigger_background_tasks
    from notifications.models import EmailLog
    from certificates.models import Certificate
    
    event = get_object_or_404(Event, id=pk)
    registrations = event.registrations.filter(status='confirmed').select_related('user')
    
    if request.method == 'POST':
        subject_template = request.POST.get('subject')
        message_template = request.POST.get('message')
        attach_cert = request.POST.get('attach_certificate') == 'on'
        
        # Pre-fetch certificates for all registrations to avoid per-user queries
        if attach_cert:
            cert_map = {
                c.registration_id: c
                for c in Certificate.objects.filter(
                    registration__in=registrations, status='completed'
                ).exclude(pdf_file='').select_related('registration')
            }
        
        import re
        email_logs = []
        pattern = re.compile(r'\{\{\s*name\s*\}\}|\{\s*name\s*\}', re.IGNORECASE)
        for reg in registrations:
            name = reg.user.get_full_name()
            subject = pattern.sub(name, subject_template)
            body_text = pattern.sub(name, message_template)
            
            attachment = None
            if attach_cert:
                cert = cert_map.get(reg.id)
                if cert and cert.pdf_file:
                    attachment = cert.pdf_file
            
            email_logs.append(EmailLog(
                organization=event.organization,
                sender_user=request.user,
                recipient_user=reg.user,
                recipient_email=reg.user.email,
                subject=subject,
                body_text=body_text,
                attachment=attachment,
                email_type='event_update'
            ))
        
        EmailLog.objects.bulk_create(email_logs)
        count = len(email_logs)
            
        trigger_background_tasks()
        messages.success(request, f"Custom emails successfully queued for {count} participants.")
        return redirect('events:event_detail', pk=event.id)
        
    return render(request, 'events/email_compose.html', {
        'event': event,
        'recipient_count': registrations.count()
    })

@login_required
def reset_event_certificates(request, pk):
    from certificates.models import Certificate
    event = get_object_or_404(Event, id=pk)
    
    if request.user.role not in ['admin', 'event_manager', 'super_admin']:
        messages.error(request, "You do not have permission to reset certificates.")
        return redirect('events:event_detail', pk=pk)
        
    deleted_count, _ = Certificate.objects.filter(registration__event=event).delete()
    messages.success(request, f"Successfully cleared {deleted_count} certificates. You can now re-issue them.")
    return redirect('events:event_detail', pk=pk)

@login_required
def import_participants(request, pk):
    import csv
    from accounts.models import User
    from registrations.models import Registration
    
    event = get_object_or_404(Event, id=pk)
    
    if request.method == 'POST':
        csv_file = request.FILES.get('csv_file')
        if not csv_file:
            messages.error(request, "Please upload a CSV file.")
            return redirect('events:import_participants', pk=pk)
            
        try:
            decoded_file = csv_file.read().decode('utf-8').splitlines()
            reader = csv.DictReader(decoded_file)
            
            created_count = 0
            for row in reader:
                # Normalize keys by stripping spaces to handle spaces around column names
                normalized_row = {k.strip() if k else '': v for k, v in row.items()}
                
                # Look for common name headers
                full_name = normalized_row.get('Full Name') or normalized_row.get('Name') or normalized_row.get('Student Name') or normalized_row.get('Participant') or ''
                full_name = full_name.strip()
                
                # Look for common email headers
                email = normalized_row.get('Email') or normalized_row.get('Email Address') or normalized_row.get('Student Email') or ''
                email = email.strip().lower()
                
                if not email:
                    continue
                    
                # Parse first and last name
                first_name = full_name.split(' ')[0] if ' ' in full_name else full_name
                last_name = ' '.join(full_name.split(' ')[1:]) if ' ' in full_name else ''
                
                user, u_created = User.objects.get_or_create(
                    email=email,
                    defaults={
                        'first_name': first_name,
                        'last_name': last_name,
                        'role': User.Role.PARTICIPANT
                    }
                )
                if u_created:
                    user.set_unusable_password()
                    user.save()
                elif full_name:
                    # Update existing user's name if they were imported previously without one
                    # or if the CSV is providing a more accurate name for this event.
                    user.first_name = first_name
                    user.last_name = last_name
                    user.save()
                
                # Capture all other columns as custom data
                custom_data = {}
                known_keys = {'full name', 'name', 'student name', 'participant', 'email', 'email address', 'student email'}
                for k, v in normalized_row.items():
                    if k and k.lower() not in known_keys:
                        custom_data[k] = v
                
                # Create or update Registration
                reg, r_created = Registration.objects.get_or_create(
                    event=event,
                    user=user,
                    defaults={
                        'status': Registration.Status.CONFIRMED,
                        'is_eligible_for_certificate': True,
                        'custom_data': custom_data
                    }
                )
                if not r_created:
                    # Update status, eligibility, and custom data for existing registrations
                    if not reg.custom_data:
                        reg.custom_data = {}
                    reg.custom_data.update(custom_data)
                    if reg.status != Registration.Status.CONFIRMED or not reg.is_eligible_for_certificate:
                        reg.status = Registration.Status.CONFIRMED
                        reg.is_eligible_for_certificate = True
                    reg.save()
                
                created_count += 1
                    
            messages.success(request, f"Successfully imported {created_count} participants.")
            return redirect('events:event_detail', pk=pk)
            
        except Exception as e:
            messages.error(request, f"Error processing CSV: {str(e)}")
            return redirect('events:import_participants', pk=pk)
            
    return render(request, 'events/import_participants.html', {'event': event})

@login_required
def remove_participant(request, event_id, reg_id):
    from registrations.models import Registration
    event = get_object_or_404(Event, id=event_id)
    registration = get_object_or_404(Registration, id=reg_id, event=event)
    
    if request.user.role not in ['admin', 'event_manager', 'super_admin', 'org_admin']:
        messages.error(request, "Permission denied.")
        return redirect('events:event_detail', pk=event.id)
        
    registration.delete()
    messages.success(request, "Participant removed successfully.")
    return redirect('events:event_detail', pk=event.id)

@login_required
def email_single_participant(request, event_id, reg_id):
    from registrations.models import Registration
    from notifications.models import EmailLog
    from certificates.models import Certificate
    from config.task_utils import trigger_background_tasks
    
    event = get_object_or_404(Event, id=event_id)
    registration = get_object_or_404(Registration, id=reg_id, event=event)
    
    if request.user.role not in ['admin', 'event_manager', 'super_admin', 'org_admin']:
        messages.error(request, "Permission denied.")
        return redirect('events:event_detail', pk=event.id)
        
    if request.method == 'POST':
        subject_template = request.POST.get('subject')
        message_template = request.POST.get('message')
        attach_cert = request.POST.get('attach_certificate') == 'on'
        
        import re
        name = registration.user.get_full_name()
        pattern = re.compile(r'\{\{\s*name\s*\}\}|\{\s*name\s*\}', re.IGNORECASE)
        subject = pattern.sub(name, subject_template)
        body_text = pattern.sub(name, message_template)
        
        attachment = None
        if attach_cert:
            cert = Certificate.objects.filter(registration=registration, status='completed').first()
            if cert and cert.pdf_file:
                attachment = cert.pdf_file
        
        EmailLog.objects.create(
            organization=event.organization,
            sender_user=request.user,
            recipient_user=registration.user,
            recipient_email=registration.user.email,
            subject=subject,
            body_text=body_text,
            attachment=attachment,
            email_type='event_update'
        )
        
        trigger_background_tasks()
        messages.success(request, f"Email queued for {name}.")
        return redirect('events:event_detail', pk=event.id)
        
    return render(request, 'events/email_compose.html', {
        'event': event,
        'recipient_count': 1,
        'single_registration': registration
    })

@login_required
def issue_single_certificate(request, event_id, reg_id):
    from registrations.models import Registration
    from certificates.models import Certificate
    from config.task_utils import trigger_background_tasks
    
    event = get_object_or_404(Event, id=event_id)
    registration = get_object_or_404(Registration, id=reg_id, event=event)
    
    if request.user.role not in ['admin', 'event_manager', 'super_admin', 'org_admin']:
        messages.error(request, "Permission denied.")
        return redirect('events:event_detail', pk=event.id)
    
    # Issue certificate
    template = event.certificate_templates.filter(is_active=True).first()
    if not template:
        messages.error(request, "No active certificate template found for this event. Please create and design one first.")
        return redirect('events:event_detail', pk=event.id)
        
    cert, created = Certificate.objects.get_or_create(
        registration=registration,
        template=template,
        defaults={'status': 'pending'}
    )
    
    # Reset status to pending if previously failed or revoked
    if not created and cert.status in ['failed', 'revoked']:
        cert.status = 'pending'
        cert.save()
    
    trigger_background_tasks()
    messages.success(request, f"Certificate generation queued for {registration.user.get_full_name()}.")
    return redirect('events:event_detail', pk=event.id)


# ─────────────────────────────────────────────────────────────
#  FORM BUILDER
# ─────────────────────────────────────────────────────────────

@login_required
def form_builder(request, pk):
    """
    Renders the visual registration form builder for an event.
    Organizers add field types, configure each field, and set conditional logic.
    """
    import json
    event = get_object_or_404(Event, id=pk)
    existing_fields = RegFormField.objects.filter(event=event).order_by('order')

    fields_data = []
    for f in existing_fields:
        fields_data.append({
            'id': str(f.id),
            'label': f.label,
            'field_name': f.field_name,
            'field_type': f.field_type,
            'options': f.options,
            'is_required': f.is_required,
            'order': f.order,
            'step_number': f.step_number,
            'placeholder': f.placeholder,
            'help_text_extra': f.help_text_extra,
            'conditional_logic': f.conditional_logic,
            'prefill_from': f.prefill_from,
        })

    return render(request, 'events/form_builder.html', {
        'event': event,
        'fields_json': json.dumps(fields_data),
        'field_types': RegFormField.FieldType.choices,
        'prefill_options': [
            ('', '— None —'),
            ('first_name', 'First Name'),
            ('last_name', 'Last Name'),
            ('email', 'Email Address'),
            ('phone', 'Phone Number'),
            ('institution', 'Institution / College'),
            ('department', 'Department / Branch'),
            ('year_of_study', 'Year of Study'),
            ('github_url', 'GitHub URL'),
            ('linkedin_url', 'LinkedIn URL'),
            ('portfolio_url', 'Portfolio URL'),
        ],
    })





@login_required
def save_form_schema(request, pk):
    """
    Receives form schema JSON from the builder and saves/updates
    RegistrationForm records for this event. Replaces all existing fields.
    """
    import json
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    event = get_object_or_404(Event, id=pk)

    try:
        data = json.loads(request.body)
        fields = data.get('fields', [])

        # Wipe existing fields and rebuild from submitted schema
        RegFormField.objects.filter(event=event).delete()

        created = 0
        for idx, field in enumerate(fields):
            field_name = field.get('field_name', '').strip()
            label = field.get('label', '').strip()
            if not field_name or not label:
                continue

            RegFormField.objects.create(
                event=event,
                label=label,
                field_name=field_name,
                field_type=field.get('field_type', 'text'),
                options=field.get('options', ''),
                is_required=field.get('is_required', True),
                order=idx,
                step_number=field.get('step_number', 1),
                placeholder=field.get('placeholder', ''),
                help_text_extra=field.get('help_text_extra', ''),
                conditional_logic=field.get('conditional_logic', {}),
                prefill_from=field.get('prefill_from', ''),
            )
            created += 1

        event.registration_form_enabled = created > 0
        event.save(update_fields=['registration_form_enabled'])

        return JsonResponse({'success': True, 'field_count': created})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)



# ─────────────────────────────────────────────────────────────
#  ATTENDANCE WINDOW CONTROL (Mode B)
# ─────────────────────────────────────────────────────────────

@login_required
def toggle_attendance_window(request, pk):
    """
    Opens or closes the Mode B scanning window.
    When open, participants can scan the rolling event QR to mark themselves attended.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    event = get_object_or_404(Event, id=pk)

    allowed_roles = ['admin', 'event_manager', 'super_admin', 'org_admin']
    if request.user.role not in allowed_roles and not request.user.is_superuser:
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    event.attendance_window_open = not event.attendance_window_open
    event.save(update_fields=['attendance_window_open'])

    AuditLog.objects.create(
        user=request.user,
        organization=event.organization,
        action=AuditLog.Action.UPDATE,
        description=f"Attendance window {'opened' if event.attendance_window_open else 'closed'} for: {event.title}",
    )

    return JsonResponse({
        'success': True,
        'window_open': event.attendance_window_open,
        'message': 'Scanning opened — participants can now scan' if event.attendance_window_open else 'Scanning closed',
    })


# ─────────────────────────────────────────────────────────────
#  VOLUNTEER RECRUITMENT & APPROVALS (Phase 2)
# ─────────────────────────────────────────────────────────────

@login_required
@require_POST
def volunteer_apply(request, pk):
    """
    POST handler allowing registered students to submit a volunteer request.
    """
    event = get_object_or_404(Event, id=pk)
    
    # Check if they are registered for the event
    is_registered = event.registrations.filter(user=request.user, status='confirmed').exists()
    if not is_registered:
        messages.error(request, "You must register as a participant first before applying as a volunteer.")
        return redirect('events:event_detail', pk=pk)

    # Check if volunteer record already exists
    from events.models import EventVolunteer
    volunteer, created = EventVolunteer.objects.get_or_create(
        event=event,
        user=request.user,
        defaults={'status': EventVolunteer.Status.PENDING}
    )
    
    if created:
        messages.success(request, "Your application to volunteer has been submitted successfully!")
    else:
        if volunteer.status == EventVolunteer.Status.PENDING:
            messages.info(request, "Your volunteer application is already pending approval.")
        elif volunteer.status == EventVolunteer.Status.APPROVED:
            messages.info(request, "You are already an approved volunteer for this event.")
        elif volunteer.status == EventVolunteer.Status.REJECTED:
            volunteer.status = EventVolunteer.Status.PENDING
            volunteer.save()
            messages.success(request, "Your volunteer application has been re-submitted!")
            
    return redirect('events:event_detail', pk=pk)


@login_required
def manage_volunteers(request, pk):
    """
    Organizer dashboard view to manage event volunteers.
    """
    event = get_object_or_404(Event, id=pk)
    
    # Check if active user is event manager / superuser / owner
    is_manager = False
    if request.user.is_superuser or request.user.email.lower() == 'mayurtheprogrammer12@gmail.com':
        is_manager = True
    elif request.user.role in ['super_admin', 'org_admin']:
        is_manager = True
    elif event.event_managers.filter(user=request.user).exists():
        is_manager = True
        
    if not is_manager:
        messages.error(request, "You do not have permission to manage volunteers for this event.")
        return redirect('events:event_detail', pk=pk)
        
    from events.models import EventVolunteer
    from accounts.models import User
    
    volunteers = event.event_volunteers.select_related('user', 'approved_by').order_by('-assigned_at')
    
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        if email:
            try:
                invite_user = User.objects.get(email__iexact=email)
                vol, created = EventVolunteer.objects.get_or_create(
                    event=event,
                    user=invite_user,
                    defaults={
                        'status': EventVolunteer.Status.APPROVED,
                        'approved_by': request.user
                    }
                )
                if not created:
                    vol.status = EventVolunteer.Status.APPROVED
                    vol.approved_by = request.user
                    vol.save()
                    messages.success(request, f"User {invite_user.get_full_name()} has been successfully invited and approved as a volunteer!")
                else:
                    messages.success(request, f"User {invite_user.get_full_name()} has been added and approved as a volunteer!")
                
                AuditLog.objects.create(
                    user=request.user,
                    organization=event.organization,
                    action=AuditLog.Action.CREATE,
                    description=f"Directly invited and approved volunteer {invite_user.email} for event {event.title}"
                )
            except User.DoesNotExist:
                messages.error(request, f"No registered user found with the email '{email}'. They must sign up first.")
        else:
            messages.error(request, "Please provide a valid email address.")
            
        return redirect('events:manage_volunteers', pk=pk)
        
    return render(request, 'events/volunteers.html', {
        'event': event,
        'volunteers': volunteers,
    })


@login_required
@require_POST
def approve_volunteer(request, pk, volunteer_id):
    """
    Action to approve a pending volunteer application.
    """
    event = get_object_or_404(Event, id=pk)
    
    is_manager = False
    if request.user.is_superuser or request.user.email.lower() == 'mayurtheprogrammer12@gmail.com':
        is_manager = True
    elif request.user.role in ['super_admin', 'org_admin']:
        is_manager = True
    elif event.event_managers.filter(user=request.user).exists():
        is_manager = True
        
    if not is_manager:
        messages.error(request, "You do not have permission to approve volunteers.")
        return redirect('events:event_detail', pk=pk)
        
    from events.models import EventVolunteer
    volunteer = get_object_or_404(EventVolunteer, id=volunteer_id, event=event)
    volunteer.status = EventVolunteer.Status.APPROVED
    volunteer.approved_by = request.user
    volunteer.save()
    
    AuditLog.objects.create(
        user=request.user,
        organization=event.organization,
        action=AuditLog.Action.UPDATE,
        description=f"Approved volunteer application for {volunteer.user.email} on event {event.title}"
    )
    
    messages.success(request, f"Approved {volunteer.user.get_full_name()} as a volunteer!")
    return redirect('events:manage_volunteers', pk=pk)


@login_required
@require_POST
def reject_volunteer(request, pk, volunteer_id):
    """
    Action to reject or revoke a volunteer application.
    """
    event = get_object_or_404(Event, id=pk)
    
    is_manager = False
    if request.user.is_superuser or request.user.email.lower() == 'mayurtheprogrammer12@gmail.com':
        is_manager = True
    elif request.user.role in ['super_admin', 'org_admin']:
        is_manager = True
    elif event.event_managers.filter(user=request.user).exists():
        is_manager = True
        
    if not is_manager:
        messages.error(request, "You do not have permission to reject/revoke volunteers.")
        return redirect('events:event_detail', pk=pk)
        
    from events.models import EventVolunteer
    volunteer = get_object_or_404(EventVolunteer, id=volunteer_id, event=event)
    volunteer.status = EventVolunteer.Status.REJECTED
    volunteer.save()
    
    AuditLog.objects.create(
        user=request.user,
        organization=event.organization,
        action=AuditLog.Action.UPDATE,
        description=f"Rejected/revoked volunteer application for {volunteer.user.email} on event {event.title}"
    )
    
    messages.success(request, f"Rejected/revoked volunteer status for {volunteer.user.get_full_name()}.")
    return redirect('events:manage_volunteers', pk=pk)


@login_required
def manage_coordinators(request, pk):
    """
    Organization/Superadmin dashboard view to manage event coordinators (EventManagers).
    """
    event = get_object_or_404(Event, id=pk)
    
    # Check if active user is organization admin/owner / superuser / platform owner
    is_org_admin = False
    if request.user.is_superuser or request.user.email.lower() == 'mayurtheprogrammer12@gmail.com':
        is_org_admin = True
    elif request.user.role in ['super_admin', 'org_admin']:
        is_org_admin = True
    elif event.organization.memberships.filter(user=request.user, role__in=['owner', 'admin']).exists():
        is_org_admin = True
        
    if not is_org_admin:
        messages.error(request, "You do not have permission to manage coordinators for this event.")
        return redirect('events:event_detail', pk=pk)
        
    from events.models import EventManager
    from accounts.models import User
    
    coordinators = event.event_managers.select_related('user').order_by('-assigned_at')
    
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        can_issue = request.POST.get('can_issue_certificates') == 'on'
        can_scan = request.POST.get('can_scan_attendance') != 'off' # default True
        
        if email:
            try:
                invite_user = User.objects.get(email__iexact=email)
                
                # Check if user is already a manager for this event
                manager, created = EventManager.objects.get_or_create(
                    event=event,
                    user=invite_user,
                    defaults={
                        'can_scan_attendance': can_scan,
                        'can_issue_certificates': can_issue
                    }
                )
                if not created:
                    manager.can_scan_attendance = can_scan
                    manager.can_issue_certificates = can_issue
                    manager.save()
                    messages.success(request, f"Updated permissions for coordinator {invite_user.get_full_name()}!")
                else:
                    messages.success(request, f"User {invite_user.get_full_name()} has been successfully assigned as a coordinator for this event!")
                
                AuditLog.objects.create(
                    user=request.user,
                    organization=event.organization,
                    action=AuditLog.Action.CREATE,
                    description=f"Assigned coordinator {invite_user.email} for event {event.title} (Can scan: {can_scan}, Can issue certs: {can_issue})"
                )
            except User.DoesNotExist:
                messages.error(request, f"No registered user found with the email '{email}'. They must sign up first.")
        else:
            messages.error(request, "Please provide a valid email address.")
            
        return redirect('events:manage_coordinators', pk=pk)
        
    return render(request, 'events/coordinators.html', {
        'event': event,
        'coordinators': coordinators,
    })


@login_required
@require_POST
def remove_coordinator(request, pk, coordinator_id):
    """
    Action to revoke/remove a coordinator from an event.
    """
    event = get_object_or_404(Event, id=pk)
    
    # Check permission
    is_org_admin = False
    if request.user.is_superuser or request.user.email.lower() == 'mayurtheprogrammer12@gmail.com':
        is_org_admin = True
    elif request.user.role in ['super_admin', 'org_admin']:
        is_org_admin = True
    elif event.organization.memberships.filter(user=request.user, role__in=['owner', 'admin']).exists():
        is_org_admin = True
        
    if not is_org_admin:
        messages.error(request, "You do not have permission to remove coordinators.")
        return redirect('events:event_detail', pk=pk)
        
    from events.models import EventManager
    coordinator = get_object_or_404(EventManager, id=coordinator_id, event=event)
    coord_email = coordinator.user.email
    coord_name = coordinator.user.get_full_name()
    coordinator.delete()
    
    AuditLog.objects.create(
        user=request.user,
        organization=event.organization,
        action=AuditLog.Action.DELETE,
        description=f"Removed coordinator {coord_email} from event {event.title}"
    )
    
    messages.success(request, f"Successfully removed coordinator {coord_name} from this event.")
    return redirect('events:manage_coordinators', pk=pk)
