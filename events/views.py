from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.conf import settings
from .models import Event, EventManager
from .forms import EventForm
from registrations.models import Registration
from analytics.models import AuditLog

@login_required
def dashboard(request):
    """
    Main dashboard view showing stats and upcoming events.
    """
    from django.db.models import Count
    events = Event.objects.filter(
        status__in=['published', 'ongoing']
    ).order_by('start_datetime').select_related('organization')[:5]
    
    # Stats
    upcoming_count = Event.objects.filter(start_datetime__gt=timezone.now(), status='published').count()
    total_registrations = Registration.objects.filter(status='confirmed').count()
    
    # Activity logs — prefetch user to avoid N+1
    activity_logs = AuditLog.objects.select_related('user').order_by('-timestamp')[:5]
    
    context = {
        'events': events,
        'upcoming_count': upcoming_count,
        'total_registrations': total_registrations,
        'activity_logs': activity_logs,
    }
    return render(request, 'dashboard.html', context)

@login_required
def event_list(request):
    events = Event.objects.all().order_by('-start_datetime')
    return render(request, 'events/event_list.html', {'events': events})

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
    
    return render(request, 'events/event_detail.html', {
        'event': event,
        'registrations': registrations,
        'cert_stats': cert_stats,
        'search_query': search_query
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
    import csv
    from django.http import HttpResponse
    
    event = get_object_or_404(Event, id=pk)
    registrations = event.registrations.all()
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{event.slug}_registrations.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Name', 'Email', 'Status', 'Registration Date', 'Attendance'])
    
    for reg in registrations:
        attendance = "Yes" if hasattr(reg, 'attendance_record') and reg.attendance_record.is_present else "No"
        writer.writerow([
            reg.user.get_full_name(),
            reg.user.email,
            reg.get_status_display(),
            reg.registration_date.strftime('%Y-%m-%d'),
            attendance
        ])
    
    return response

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
        
        email_logs = []
        for reg in registrations:
            name = reg.user.get_full_name()
            subject = subject_template.replace('{{ name }}', name)
            body_text = message_template.replace('{{ name }}', name)
            
            attachment = None
            if attach_cert:
                cert = cert_map.get(reg.id)
                if cert and cert.pdf_file:
                    attachment = cert.pdf_file
            
            email_logs.append(EmailLog(
                organization=event.organization,
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
                # Look for common name headers
                full_name = row.get('Full Name') or row.get('Name') or row.get('Student Name') or row.get('Participant') or ''
                full_name = full_name.strip()
                
                # Look for common email headers
                email = row.get('Email') or row.get('Email Address') or row.get('Student Email') or ''
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
                
                # Create Registration
                reg, r_created = Registration.objects.get_or_create(
                    event=event,
                    user=user,
                    defaults={
                        'status': Registration.Status.CONFIRMED,
                        'is_eligible_for_certificate': True
                    }
                )
                if r_created:
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
        
        name = registration.user.get_full_name()
        subject = subject_template.replace('{{ name }}', name)
        body_text = message_template.replace('{{ name }}', name)
        
        attachment = None
        if attach_cert:
            cert = Certificate.objects.filter(registration=registration, status='completed').first()
            if cert and cert.pdf_file:
                attachment = cert.pdf_file
        
        EmailLog.objects.create(
            organization=event.organization,
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
    from certificates.tasks import generate_certificate_task
    
    event = get_object_or_404(Event, id=event_id)
    registration = get_object_or_404(Registration, id=reg_id, event=event)
    
    if request.user.role not in ['admin', 'event_manager', 'super_admin', 'org_admin']:
        messages.error(request, "Permission denied.")
        return redirect('events:event_detail', pk=event.id)
    
    # Issue certificate
    template = event.organization.certificatetemplate_set.filter(is_active=True).first()
    if not template:
        messages.error(request, "No active certificate template found for this organization.")
        return redirect('events:event_detail', pk=event.id)
        
    cert, created = Certificate.objects.get_or_create(
        registration=registration,
        template=template,
        defaults={'status': 'pending'}
    )
    
    generate_certificate_task.delay(cert.id)
    messages.success(request, f"Certificate generation queued for {registration.user.get_full_name()}.")
    return redirect('events:event_detail', pk=event.id)

