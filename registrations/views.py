from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from events.models import Event
from .models import Registration
from config.task_utils import trigger_background_tasks

def public_event_list(request):
    """
    Public listing of all published events.
    """
    events = Event.objects.filter(status='published', registration_deadline__gte=timezone.now()).order_by('start_datetime')
    return render(request, 'registrations/public_list.html', {'events': events})

@login_required
def register_for_event(request, event_id):
    """
    Handle user registration for an event.
    """
    event = get_object_or_404(Event, id=event_id)
    
    if not event.is_registration_open:
        messages.error(request, "Registration is currently closed for this event.")
        return redirect('registrations:public_list')
        
    # Check if already registered
    if Registration.objects.filter(event=event, user=request.user).exists():
        messages.info(request, "You are already registered for this event.")
        return redirect('events:dashboard')
        
    if request.method == 'POST':
        # In a real app, handle dynamic form fields here
        registration = Registration.objects.create(
            event=event,
            user=request.user,
            status=Registration.Status.CONFIRMED
        )
        
        # Create Email Log for confirmation
        from notifications.models import EmailLog
        EmailLog.objects.create(
            organization=event.organization,
            recipient_email=request.user.email,
            recipient_user=request.user,
            subject=f"Registration Confirmed: {event.title}",
            body_text=f"Hi {request.user.first_name}, your registration for {event.title} is confirmed!",
            email_type='registration_confirmation',
            related_object_id=registration.id
        )
        
        messages.success(request, f"Successfully registered for {event.title}!")
        trigger_background_tasks() # Automatically process the confirmation email
        return redirect('attendance:participant_qr', event_id=event.id)
        
    return render(request, 'registrations/register_confirm.html', {'event': event})
