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
    # Filter events based on organization context (simplified for now)
    events = Event.objects.filter(status__in=['published', 'ongoing']).order_by('start_datetime')[:5]
    
    # Stats
    upcoming_count = Event.objects.filter(start_datetime__gt=timezone.now(), status='published').count()
    total_registrations = Registration.objects.filter(status='confirmed').count()
    
    # Activity logs
    activity_logs = AuditLog.objects.all().order_by('-timestamp')[:5]
    
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
    event = get_object_or_404(Event, id=pk)
    registrations = event.registrations.all().order_by('-registration_date')[:10]
    return render(request, 'events/event_detail.html', {
        'event': event,
        'registrations': registrations
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
    registrations = event.registrations.filter(status='confirmed')
    
    if request.method == 'POST':
        subject_template = request.POST.get('subject')
        message_template = request.POST.get('message')
        attach_cert = request.POST.get('attach_certificate') == 'on'
        
        count = 0
        for reg in registrations:
            # Personalize
            name = reg.user.get_full_name()
            subject = subject_template.replace('{{ name }}', name)
            body_text = message_template.replace('{{ name }}', name)
            
            # Handle certificate attachment
            attachment = None
            if attach_cert:
                cert = Certificate.objects.filter(registration=reg, status='completed').first()
                if cert and cert.pdf_file:
                    attachment = cert.pdf_file
            
            EmailLog.objects.create(
                organization=event.organization,
                recipient_user=reg.user,
                recipient_email=reg.user.email,
                subject=subject,
                body_text=body_text,
                attachment=attachment,
                email_type='event_update'
            )
            count += 1
            
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
                # Expected headers: 'Full Name', 'Email'
                full_name = row.get('Full Name', '').strip()
                email = row.get('Email', '').strip().lower()
                
                if not email:
                    continue
                    
                # Create user if doesn't exist
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
