from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.contrib import messages
from .models import Attendance, ScanLog
from .utils import generate_attendance_token, verify_attendance_token
from registrations.models import Registration
from events.models import Event
import qrcode
import io
import base64

@login_required
def participant_qr(request, event_id):
    """
    View for participants to see their refreshing QR code.
    """
    event = get_object_or_404(Event, id=event_id)
    registration = get_object_or_404(Registration, event=event, user=request.user)
    
    # Check if event is active for attendance
    if not event.is_attendance_window_active:
        return render(request, 'attendance/not_active.html', {'event': event})
        
    return render(request, 'attendance/qr_display.html', {
        'event': event,
        'registration': registration,
        'refresh_interval': getattr(settings, 'QR_REFRESH_INTERVAL', 20)
    })

@login_required
def get_new_token(request, registration_id):
    """
    API endpoint to get a fresh token for the QR code.
    """
    registration = get_object_or_404(Registration, id=registration_id, user=request.user)
    token = generate_attendance_token(registration.id, registration.event.id)
    
    # Generate QR code image as base64
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(token)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    return JsonResponse({
        'token': token,
        'qr_image': f"data:image/png;base64,{img_str}"
    })

@login_required
def volunteer_scanner(request, event_id):
    """
    View for volunteers/admins to scan QR codes.
    """
    event = get_object_or_404(Event, id=event_id)
    
    # Check permissions (must be admin or event manager/volunteer)
    # For now, just check if they are authenticated
    
    return render(request, 'attendance/scanner.html', {'event': event})

@login_required
def process_scan(request):
    """
    API endpoint to process a scanned token.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)
        
    token = request.POST.get('token')
    event_id = request.POST.get('event_id')
    
    if not token or not event_id:
        return JsonResponse({'success': False, 'error': 'Missing parameters'}, status=400)
        
    payload, error = verify_attendance_token(token)
    
    if error:
        return JsonResponse({'success': False, 'error': error})
        
    # Verify event match
    if str(payload['event_id']) != str(event_id):
        return JsonResponse({'success': False, 'error': 'Token is for a different event'})
        
    # Process attendance
    registration = get_object_or_404(Registration, id=payload['reg_id'])
    
    attendance, created = Attendance.objects.get_or_create(
        registration=registration,
        event_id=event_id,
        defaults={'is_present': True, 'check_in_time': timezone.now()}
    )
    
    if not created:
        # If already checked in, this could be a check-out or just a re-scan
        if not attendance.check_out_time:
            attendance.check_out_time = timezone.now()
            attendance.update_duration()
            scan_type = ScanLog.ScanType.CHECK_OUT
        else:
            # Already checked out? Maybe re-check in
            attendance.check_out_time = None
            attendance.check_in_time = timezone.now()
            scan_type = ScanLog.ScanType.CHECK_IN
    else:
        scan_type = ScanLog.ScanType.CHECK_IN
        
    attendance.is_present = True
    attendance.save()
    
    # Create Scan Log
    ScanLog.objects.create(
        attendance=attendance,
        scanned_by=request.user,
        scan_type=scan_type,
        token_used=token
    )
    
    return JsonResponse({
        'success': True,
        'participant': registration.user.get_full_name(),
        'scan_type': scan_type,
        'time': timezone.now().strftime('%H:%M:%S')
    })
