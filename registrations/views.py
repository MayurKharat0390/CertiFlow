"""
Registration views for CertiFlow
Supports both logged-in users AND guests (email-only).
Guests get an account auto-created on registration submission.
"""
import json
import secrets
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import login
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from events.models import Event
from .models import Registration, RegistrationForm as RegFormField
from config.task_utils import trigger_background_tasks


# ─────────────────────────────────────────────────────────────
#  PUBLIC EVENT LIST
# ─────────────────────────────────────────────────────────────

def public_event_list(request):
    """Public listing of all published events open for registration."""
    from django.db.models import Q, Count
    now = timezone.now()
    events = (
        Event.objects
        .filter(
            Q(status__in=[Event.Status.PUBLISHED, Event.Status.ONGOING]) &
            (Q(registration_deadline__isnull=True) | Q(registration_deadline__gte=now))
        )
        .select_related('organization')
        .annotate(confirmed_count=Count('registrations', filter=Q(registrations__status='confirmed')))
        .order_by('start_datetime')
    )

    context = {
        'events': events,
        'event_types': Event.EventType.choices,
        'total_events_count': events.count(),
    }
    return render(request, 'registrations/public_list.html', context)


# ─────────────────────────────────────────────────────────────
#  FORM SCHEMA API  (consumed by the JS wizard)
# ─────────────────────────────────────────────────────────────

def get_form_schema(request, event_id):
    """
    Returns the registration form schema for an event as JSON.
    Used by the multi-step wizard JS to render fields dynamically.
    Also returns the current user's profile data for pre-filling.
    """
    event = get_object_or_404(Event, id=event_id)
    fields = RegFormField.objects.filter(event=event).order_by('order')

    schema = []
    for f in fields:
        schema.append({
            'id': str(f.id),
            'label': f.label,
            'field_name': f.field_name,
            'field_type': f.field_type,
            'options': [o.strip() for o in f.options.split(',') if o.strip()],
            'is_required': f.is_required,
            'step_number': f.step_number,
            'placeholder': f.placeholder,
            'help_text': f.help_text_extra,
            'conditional_logic': f.conditional_logic,
            'prefill_from': f.prefill_from,
        })

    # Build prefill data from user profile if authenticated
    prefill = {}
    if request.user.is_authenticated:
        u = request.user
        prefill = {
            'first_name': u.first_name,
            'last_name': u.last_name,
            'email': u.email,
            'phone': u.phone,
            'institution': u.institution,
            'department': u.department,
            'year_of_study': u.year_of_study,
            'github_url': u.github_url,
            'linkedin_url': u.linkedin_url,
            'portfolio_url': u.portfolio_url,
        }

    return JsonResponse({
        'schema': schema,
        'prefill': prefill,
        'event': {
            'title': event.title,
            'registration_form_enabled': event.registration_form_enabled,
            'spots_left': (event.max_capacity - event.registered_count) if event.max_capacity else None,
            'deadline': event.registration_deadline.isoformat() if event.registration_deadline else None,
        }
    })


# ─────────────────────────────────────────────────────────────
#  SMART REGISTRATION  (Guest + Logged-in)
# ─────────────────────────────────────────────────────────────

def smart_register(request, event_id):
    """
    Main registration view — serves the multi-step wizard page.
    Works for both logged-in users and guests.
    On POST submission, handles account creation for guests.
    """
    from accounts.models import User
    from notifications.models import EmailLog

    event = get_object_or_404(Event, id=event_id)

    if not event.is_registration_open:
        messages.error(request, 'Registration is currently closed for this event.')
        return redirect('registrations:public_list')

    # If user is logged in and already registered, redirect to their pass
    if request.user.is_authenticated:
        existing = Registration.objects.filter(event=event, user=request.user).first()
        if existing:
            messages.info(request, 'You are already registered for this event.')
            return redirect('attendance:participant_pass', event_id=event.id)

    if request.method == 'POST':
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, Exception):
            body = request.POST.dict()

        # ── Resolve / create user account ──────────────────────
        user = request.user if request.user.is_authenticated else None

        if not user:
            email = body.get('email', '').strip().lower()
            first_name = body.get('first_name', '').strip()
            last_name = body.get('last_name', '').strip()

            if not email:
                return JsonResponse({'success': False, 'error': 'Email is required'}, status=400)

            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'first_name': first_name,
                    'last_name': last_name,
                    'role': User.Role.PARTICIPANT,
                    'institution': body.get('institution', ''),
                    'department': body.get('department', ''),
                    'year_of_study': body.get('year_of_study', ''),
                    'github_url': body.get('github_url', ''),
                    'linkedin_url': body.get('linkedin_url', ''),
                    'portfolio_url': body.get('portfolio_url', ''),
                }
            )

            if created:
                # Generate a temporary password and email it
                temp_password = secrets.token_urlsafe(10)
                user.set_password(temp_password)
                user.save()

                # Queue welcome email with credentials
                EmailLog.objects.create(
                    organization=event.organization,
                    recipient_email=email,
                    recipient_user=user,
                    subject='Welcome to CertiFlow — Your Account Details',
                    body_text=(
                        f"Hi {first_name or email},\n\n"
                        f"Your CertiFlow account has been created automatically "
                        f"when you registered for '{event.title}'.\n\n"
                        f"Email: {email}\n"
                        f"Temporary Password: {temp_password}\n\n"
                        f"Please log in and change your password at your earliest convenience.\n\n"
                        f"— CertiFlow Team"
                    ),
                    email_type='account_created',
                )
            else:
                # Update profile fields if they've changed
                update_fields = []
                profile_map = {
                    'institution': 'institution', 'department': 'department',
                    'year_of_study': 'year_of_study', 'github_url': 'github_url',
                    'linkedin_url': 'linkedin_url', 'portfolio_url': 'portfolio_url',
                }
                for body_key, model_field in profile_map.items():
                    val = body.get(body_key, '').strip()
                    if val and not getattr(user, model_field):
                        setattr(user, model_field, val)
                        update_fields.append(model_field)
                if update_fields:
                    user.save(update_fields=update_fields)

            # Auto-login the guest after account creation/retrieval
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')

        # ── Check for duplicate registration ───────────────────
        if Registration.objects.filter(event=event, user=user).exists():
            return JsonResponse({
                'success': False,
                'error': 'You are already registered for this event.',
                'redirect': str(event.id),
            }, status=409)

        # ── Collect custom form data ───────────────────────────
        custom_data = {}
        form_fields = RegFormField.objects.filter(event=event)
        for field in form_fields:
            value = body.get(field.field_name)
            if value is not None:
                custom_data[field.field_name] = value

        # ── Create registration ────────────────────────────────
        registration = Registration.objects.create(
            event=event,
            user=user,
            status=Registration.Status.CONFIRMED,
            custom_data=custom_data,
        )

        # ── Send confirmation email ────────────────────────────
        EmailLog.objects.create(
            organization=event.organization,
            recipient_email=user.email,
            recipient_user=user,
            subject=f'Registration Confirmed: {event.title}',
            body_text=(
                f"Hi {user.first_name or user.email},\n\n"
                f"You're registered for '{event.title}'!\n\n"
                f"Participant ID: {registration.participant_id}\n"
                f"Date: {event.start_datetime.strftime('%B %d, %Y at %I:%M %p')}\n"
                f"Venue: {event.venue_name or 'Online'}\n\n"
                f"Show your digital pass at the event entrance.\n\n"
                f"— {event.organization.name}"
            ),
            email_type='registration_confirmation',
            related_object_id=registration.id,
        )
        trigger_background_tasks()

        return JsonResponse({
            'success': True,
            'participant_id': registration.participant_id,
            'registration_id': str(registration.id),
            'event_id': str(event.id),
            'redirect_pass': True,
        })

    # GET — serve the wizard page
    return render(request, 'registrations/smart_register.html', {
        'event': event,
        'user_authenticated': request.user.is_authenticated,
    })
