"""
Attendance views for CertiFlow — Dual Mode System

Mode A — Volunteer Scans Participant:
    Volunteer opens scanner, points at participant's static QR.
    Action panel slides up with participant info and actions.

Mode B — Participant Scans Event QR:
    Organizer displays a rolling QR on their screen.
    Participants scan it with their phones to mark themselves attended.
    QR roll interval is configurable by the manager.
    Anti-cheat: one scan per window per participant + anomaly flagging.
"""
import io
import json
import base64
import qrcode
from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.contrib import messages
from django.views.decorators.http import require_POST

from .models import Attendance, ScanLog, ParticipantScanRecord
from .utils import (
    generate_static_pass_token, verify_static_pass_token,
    generate_room_qr_token, verify_room_qr_token,
    detect_suspicious_scan, get_client_ip, get_device_fingerprint,
    get_current_window,
)
from registrations.models import Registration
from events.models import Event


# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────

def _make_qr_base64(data: str, box_size=10, border=4) -> str:
    """Generates a QR code and returns it as a base64 PNG data URI."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color='#0f172a', back_color='white')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()


def _is_event_manager(user, event=None):
    # 1. Superuser or owner email
    if user.is_superuser or user.email.lower() == 'mayurtheprogrammer12@gmail.com':
        return True
    
    # 2. General admins
    if getattr(user, 'role', '') in ['super_admin', 'org_admin']:
        return True

    # 3. If there is event context, check specific management or volunteer permissions
    if event:
        # Check if user is an assigned manager for this event
        if event.event_managers.filter(user=user).exists():
            return True
        
        # Check if user is an approved volunteer for this event
        from events.models import EventVolunteer
        if EventVolunteer.objects.filter(event=event, user=user, status=EventVolunteer.Status.APPROVED).exists():
            return True
            
        return False

    # 4. Fallback if no event context: check role
    allowed = ['admin', 'event_manager', 'super_admin', 'org_admin', 'volunteer']
    return getattr(user, 'role', '') in allowed



# ─────────────────────────────────────────────────────────────
#  PARTICIPANT PASS  (replaces old rotating QR page)
# ─────────────────────────────────────────────────────────────

@login_required
def participant_pass(request, event_id):
    """
    Static identity QR pass for the participant.
    The QR encodes a permanent signed token — participants can screenshot/print it.
    """
    event = get_object_or_404(Event, id=event_id)
    registration = get_object_or_404(Registration, event=event, user=request.user)

    token = generate_static_pass_token(registration.id, event.id)
    qr_data_uri = _make_qr_base64(token, box_size=8, border=3)

    # Get attendance status
    attendance = Attendance.objects.filter(registration=registration).first()

    return render(request, 'attendance/participant_pass.html', {
        'event': event,
        'registration': registration,
        'qr_data_uri': qr_data_uri,
        'attendance': attendance,
    })


# Keep legacy URL working during transition
@login_required
def participant_qr(request, event_id):
    return redirect('attendance:participant_pass', event_id=event_id)


# ─────────────────────────────────────────────────────────────
#  MODE A — VOLUNTEER SCANNER (Volunteer Scans Participant QR)
# ─────────────────────────────────────────────────────────────

@login_required
def volunteer_scanner(request, event_id):
    """Mode A scanner page — volunteer scans each participant's static QR pass."""
    event = get_object_or_404(Event, id=event_id)
    if not _is_event_manager(request.user, event):
        messages.error(request, 'You do not have permission to scan attendance.')
        return redirect('events:event_detail', pk=event_id)
    return render(request, 'attendance/scanner.html', {
        'event': event,
        'mode': 'volunteer_scans',
    })


@login_required
def process_scan(request):
    """
    API — processes a scanned participant pass token (Mode A).
    Returns full participant context to power the scanner action panel.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    try:
        body = json.loads(request.body)
    except Exception:
        body = request.POST.dict()

    token = body.get('token', '')
    event_id = body.get('event_id', '')

    if not token or not event_id:
        return JsonResponse({'success': False, 'error': 'Missing parameters'}, status=400)

    payload, error = verify_static_pass_token(token)
    if error:
        return JsonResponse({'success': False, 'error': error})

    if str(payload.get('event_id')) != str(event_id):
        return JsonResponse({'success': False, 'error': 'This pass is for a different event'})

    registration = get_object_or_404(Registration, id=payload['reg_id'])
    user = registration.user

    attendance = Attendance.objects.filter(registration=registration).first()

    # Build certificate status
    from certificates.models import Certificate
    cert = Certificate.objects.filter(registration=registration, status='completed').first()

    return JsonResponse({
        'success': True,
        'participant': {
            'name': user.get_full_name(),
            'email': user.email,
            'id': registration.participant_id,
            'department': user.department,
            'year': user.year_of_study,
            'institution': user.institution,
            'initials': (user.first_name[:1] + user.last_name[:1]).upper() if user.first_name else user.email[:2].upper(),
            'registration_id': str(registration.id),
        },
        'attendance': {
            'is_present': attendance.is_present if attendance else False,
            'check_in_time': attendance.check_in_time.strftime('%H:%M') if attendance and attendance.check_in_time else None,
            'check_out_time': attendance.check_out_time.strftime('%H:%M') if attendance and attendance.check_out_time else None,
        },
        'certificate': {
            'issued': bool(cert),
            'cert_id': str(cert.id) if cert else None,
        },
    })


@login_required
def perform_scan_action(request):
    """
    API — performs a post-scan action from the Mode A volunteer scanner action panel.
    Actions: mark_attended, mark_absent, undo_checkin, issue_cert
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    try:
        body = json.loads(request.body)
    except Exception:
        body = request.POST.dict()

    registration_id = body.get('registration_id')
    action = body.get('action')

    if not registration_id or not action:
        return JsonResponse({'success': False, 'error': 'Missing parameters'}, status=400)

    registration = get_object_or_404(Registration, id=registration_id)

    if action == 'mark_attended':
        attendance, created = Attendance.objects.get_or_create(
            registration=registration,
            event=registration.event,
            defaults={'is_present': True, 'check_in_time': timezone.now()}
        )
        if not created:
            attendance.is_present = True
            if not attendance.check_in_time:
                attendance.check_in_time = timezone.now()
            attendance.save()

        ScanLog.objects.create(
            attendance=attendance,
            scanned_by=request.user,
            scan_type=ScanLog.ScanType.CHECK_IN,
            action_performed='mark_attended',
        )

        # Mark registration status as attended
        registration.status = Registration.Status.ATTENDED
        registration.is_eligible_for_certificate = True
        registration.save(update_fields=['status', 'is_eligible_for_certificate'])

        return JsonResponse({'success': True, 'message': f'{registration.user.get_full_name()} marked as attended'})

    elif action == 'mark_absent':
        attendance = Attendance.objects.filter(registration=registration).first()
        if attendance:
            attendance.is_present = False
            attendance.save()
            ScanLog.objects.create(
                attendance=attendance,
                scanned_by=request.user,
                scan_type=ScanLog.ScanType.VERIFICATION,
                action_performed='mark_absent',
            )
        return JsonResponse({'success': True, 'message': f'{registration.user.get_full_name()} marked as absent'})

    elif action == 'undo_checkin':
        attendance = Attendance.objects.filter(registration=registration).first()
        if attendance:
            attendance.is_present = False
            attendance.check_in_time = None
            attendance.save()
        registration.status = Registration.Status.CONFIRMED
        registration.save(update_fields=['status'])
        return JsonResponse({'success': True, 'message': 'Check-in undone'})

    elif action == 'issue_cert':
        from certificates.models import Certificate
        from config.task_utils import trigger_background_tasks
        
        template = registration.event.certificate_templates.filter(is_active=True).first()
        if not template:
            return JsonResponse({'success': False, 'error': 'No active certificate template found for this event'})
            
        cert, created = Certificate.objects.get_or_create(
            registration=registration,
            template=template,
            defaults={'status': 'pending'}
        )
        
        if not created and cert.status in ['failed', 'revoked']:
            cert.status = 'pending'
            cert.save()
            created = True
            
        if created:
            trigger_background_tasks()
            return JsonResponse({'success': True, 'message': 'Certificate generation queued'})
        return JsonResponse({'success': True, 'message': 'Certificate already exists'})

    return JsonResponse({'success': False, 'error': f'Unknown action: {action}'}, status=400)


# ─────────────────────────────────────────────────────────────
#  MODE B — ROOM QR DISPLAY (Organizer's Screen)
# ─────────────────────────────────────────────────────────────

@login_required
def room_qr_display(request, event_id):
    """
    Mode B organizer view — displays the rolling event QR on their screen/projector.
    The QR refreshes automatically based on the event's qr_roll_interval.
    """
    event = get_object_or_404(Event, id=event_id)
    if not _is_event_manager(request.user, event):
        messages.error(request, 'You do not have permission to manage attendance.')
        return redirect('events:event_detail', pk=event_id)

    scan_count = ParticipantScanRecord.objects.filter(event=event, is_accepted=True).count()
    flagged_count = ParticipantScanRecord.objects.filter(event=event, is_flagged=True, flag_reviewed=False).count()

    return render(request, 'attendance/room_qr.html', {
        'event': event,
        'scan_count': scan_count,
        'flagged_count': flagged_count,
    })


@login_required
def get_room_qr_token(request, event_id):
    """API — returns the current rolling room QR token + base64 image for Mode B display."""
    event = get_object_or_404(Event, id=event_id)
    if not _is_event_manager(request.user, event):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    token, window = generate_room_qr_token(event.id, event.qr_roll_interval)
    qr_data_uri = _make_qr_base64(token, box_size=12, border=4)

    # seconds remaining in this window
    import time
    elapsed = int(time.time()) % event.qr_roll_interval
    seconds_left = event.qr_roll_interval - elapsed

    scan_count = ParticipantScanRecord.objects.filter(event=event, is_accepted=True).count()
    flagged_count = ParticipantScanRecord.objects.filter(event=event, is_flagged=True, flag_reviewed=False).count()

    return JsonResponse({
        'success': True,
        'qr_image': qr_data_uri,
        'window': window,
        'seconds_left': seconds_left,
        'roll_interval': event.qr_roll_interval,
        'window_open': event.attendance_window_open,
        'scan_count': scan_count,
        'flagged_count': flagged_count,
    })


# ─────────────────────────────────────────────────────────────
#  MODE B — PARTICIPANT SCAN (Student Scans Event QR)
# ─────────────────────────────────────────────────────────────

@login_required
def participant_scan_page(request, event_id):
    """
    Mode B participant page — shown after student scans the room QR.
    Handles the confirmation and attendance marking.
    """
    event = get_object_or_404(Event, id=event_id)
    token = request.GET.get('token', '')

    if not token:
        messages.error(request, 'Invalid scan link.')
        return redirect('registrations:public_list')

    registration = Registration.objects.filter(event=event, user=request.user).first()
    if not registration:
        messages.error(request, 'You are not registered for this event.')
        return redirect('registrations:public_list')

    # Verify the token
    payload, window_number, error = verify_room_qr_token(token, event_id)

    context = {
        'event': event,
        'registration': registration,
        'token': token,
        'error': error,
        'already_attended': False,
    }

    if not error:
        # Check if already scanned this window
        already = ParticipantScanRecord.objects.filter(
            registration=registration,
            event=event,
            window_number=window_number,
            is_accepted=True,
        ).exists()
        if already:
            context['already_attended'] = True

    return render(request, 'attendance/participant_scan.html', context)


@login_required
def process_participant_scan(request):
    """
    API — processes a Mode B participant self-scan.
    Verifies the rolling token, runs anti-cheat checks, marks attendance.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    try:
        body = json.loads(request.body)
    except Exception:
        body = request.POST.dict()

    token = body.get('token', '')
    event_id = body.get('event_id', '')

    if not token or not event_id:
        return JsonResponse({'success': False, 'error': 'Missing parameters'}, status=400)

    event = get_object_or_404(Event, id=event_id)

    # Check attendance window is open
    if not event.attendance_window_open:
        return JsonResponse({'success': False, 'error': 'Attendance scanning is not currently open for this event.'})

    # Verify the rolling token
    payload, window_number, error = verify_room_qr_token(token, event_id)
    if error:
        return JsonResponse({'success': False, 'error': error})

    # Check participant is registered
    registration = Registration.objects.filter(event=event, user=request.user).first()
    if not registration:
        return JsonResponse({'success': False, 'error': 'You are not registered for this event.'})

    # Check already scanned this window
    already = ParticipantScanRecord.objects.filter(
        registration=registration,
        event=event,
        window_number=window_number,
        is_accepted=True,
    ).exists()
    if already:
        return JsonResponse({'success': False, 'error': 'You have already scanned for this window. Your attendance is recorded.'})

    # Run anti-cheat detection
    flag = detect_suspicious_scan(registration, request, window_number, event)

    # Record the scan
    scan_record = ParticipantScanRecord.objects.create(
        registration=registration,
        event=event,
        window_number=window_number,
        is_accepted=True,
        ip_address=get_client_ip(request),
        device_fingerprint=get_device_fingerprint(request),
        is_flagged=bool(flag),
        scan_flag=flag,
    )

    # Mark attendance
    attendance, created = Attendance.objects.get_or_create(
        registration=registration,
        event=event,
        defaults={'is_present': True, 'check_in_time': timezone.now()}
    )
    if not created and not attendance.is_present:
        attendance.is_present = True
        attendance.check_in_time = timezone.now()
        attendance.save()

    registration.status = Registration.Status.ATTENDED
    registration.is_eligible_for_certificate = True
    registration.save(update_fields=['status', 'is_eligible_for_certificate'])

    return JsonResponse({
        'success': True,
        'flagged': bool(flag),
        'message': '✅ Attendance marked! See you at the event.' if not flag else '✅ Attendance recorded (pending verification).',
        'participant_id': registration.participant_id,
    })


# ─────────────────────────────────────────────────────────────
#  FLAGGED SCANS REVIEW PANEL
# ─────────────────────────────────────────────────────────────

@login_required
def flagged_scans_review(request, event_id):
    """Organizer review panel for flagged Mode B scans."""
    event = get_object_or_404(Event, id=event_id)
    if not _is_event_manager(request.user, event):
        messages.error(request, 'Permission denied.')
        return redirect('events:event_detail', pk=event_id)

    flagged = ParticipantScanRecord.objects.filter(
        event=event, is_flagged=True
    ).select_related('registration__user').order_by('-scan_time')

    if request.method == 'POST':
        scan_id = request.POST.get('scan_id')
        action = request.POST.get('action')  # 'approve' or 'reject'
        scan = get_object_or_404(ParticipantScanRecord, id=scan_id, event=event)
        scan.flag_reviewed = True
        if action == 'reject':
            scan.is_accepted = False
            # Reverse attendance if this was their only scan
            other_accepted = ParticipantScanRecord.objects.filter(
                registration=scan.registration, event=event, is_accepted=True
            ).exclude(id=scan.id).exists()
            if not other_accepted:
                Attendance.objects.filter(registration=scan.registration).update(is_present=False)
                scan.registration.status = Registration.Status.CONFIRMED
                scan.registration.save(update_fields=['status'])
        scan.save()
        messages.success(request, f'Scan {"approved" if action == "approve" else "rejected"}.')
        return redirect('attendance:flagged_scans', event_id=event_id)

    return render(request, 'attendance/flagged_scans.html', {
        'event': event,
        'flagged_scans': flagged,
    })


# Legacy token endpoint — kept for any code still referencing it
@login_required
def get_new_token(request, registration_id):
    registration = get_object_or_404(Registration, id=registration_id, user=request.user)
    token = generate_static_pass_token(registration.id, registration.event.id)
    qr_data_uri = _make_qr_base64(token)
    return JsonResponse({'token': token, 'qr_image': qr_data_uri})
