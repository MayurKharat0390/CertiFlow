"""
CertiFlow Attendance Utilities
-------------------------------
Two QR systems:
  Mode A — Volunteer Scans Participant:
      Static, permanent HMAC-signed token tied to the registration.
      Cannot expire — participant can screenshot/print it.
      Security is enforced on the scanner side (role-based access).

  Mode B — Participant Scans Event QR:
      Rolling HMAC-signed token displayed on the organizer's screen.
      Refresh interval is configurable by the manager (30s – 5min).
      Participant must be logged in and registered to process the scan.
      Anti-cheat: one scan per window per participant + anomaly flagging.
"""
import time
import hmac
import hashlib
import json
import base64
from django.conf import settings
from django.utils import timezone


# ─────────────────────────────────────────────────────────────
#  MODE A  —  Static Participant Pass Token
# ─────────────────────────────────────────────────────────────

def generate_static_pass_token(registration_id, event_id):
    """
    Generates a permanent HMAC-signed token for a participant's QR pass.
    This token never expires and encodes the registration + event identity.
    The QR encodes the check-in URL:
        /attendance/pass/<token>/
    """
    secret = settings.CERT_SECRET_KEY.encode()
    payload = {
        'reg_id': str(registration_id),
        'event_id': str(event_id),
        'type': 'static_pass',
    }
    payload_json = json.dumps(payload, sort_keys=True)
    signature = hmac.new(secret, payload_json.encode(), hashlib.sha256).hexdigest()

    token_data = {'p': payload, 's': signature}
    token_b64 = base64.urlsafe_b64encode(
        json.dumps(token_data).encode()
    ).decode()
    return token_b64


def verify_static_pass_token(token_b64):
    """
    Verifies a static participant pass token.
    Returns (payload, None) on success or (None, error_string) on failure.
    """
    try:
        token_json = base64.urlsafe_b64decode(token_b64.encode()).decode()
        token_data = json.loads(token_json)
        payload = token_data.get('p')
        signature = token_data.get('s')

        if not payload or not signature:
            return None, 'Invalid token format'

        if payload.get('type') != 'static_pass':
            return None, 'Wrong token type'

        secret = settings.CERT_SECRET_KEY.encode()
        payload_json = json.dumps(payload, sort_keys=True)
        expected = hmac.new(secret, payload_json.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(signature, expected):
            return None, 'Invalid signature'

        return payload, None
    except Exception as e:
        return None, str(e)


# ─────────────────────────────────────────────────────────────
#  MODE B  —  Rolling Event QR Token (Participant Scans Screen)
# ─────────────────────────────────────────────────────────────

def get_current_window(roll_interval_seconds):
    """
    Returns the current window number based on the configured interval.
    Window changes every `roll_interval_seconds` seconds.
    """
    return int(time.time()) // roll_interval_seconds


def generate_room_qr_token(event_id, roll_interval_seconds):
    """
    Generates a rolling HMAC-signed token for Mode B (event QR shown on screen).
    The token is tied to the current time window.
    Organizer's screen auto-refreshes the QR every `roll_interval_seconds`.
    """
    secret = settings.CERT_SECRET_KEY.encode()
    window = get_current_window(roll_interval_seconds)

    payload = {
        'event_id': str(event_id),
        'window': window,
        'interval': roll_interval_seconds,
        'type': 'room_qr',
    }
    payload_json = json.dumps(payload, sort_keys=True)
    signature = hmac.new(secret, payload_json.encode(), hashlib.sha256).hexdigest()

    token_data = {'p': payload, 's': signature}
    token_b64 = base64.urlsafe_b64encode(
        json.dumps(token_data).encode()
    ).decode()
    return token_b64, window


def verify_room_qr_token(token_b64, event_id):
    """
    Verifies a Mode B rolling event QR token.
    Accepts the current window and the previous window (for scan latency tolerance).
    Returns (payload, window_number, None) on success or (None, None, error_string).
    """
    try:
        token_json = base64.urlsafe_b64decode(token_b64.encode()).decode()
        token_data = json.loads(token_json)
        payload = token_data.get('p')
        signature = token_data.get('s')

        if not payload or not signature:
            return None, None, 'Invalid token format'

        if payload.get('type') != 'room_qr':
            return None, None, 'Wrong token type'

        if str(payload.get('event_id')) != str(event_id):
            return None, None, 'Token is for a different event'

        secret = settings.CERT_SECRET_KEY.encode()
        payload_json = json.dumps(payload, sort_keys=True)
        expected = hmac.new(secret, payload_json.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(signature, expected):
            return None, None, 'Invalid signature'

        # Verify the token belongs to the current or previous window
        interval = payload.get('interval', 60)
        current_window = get_current_window(interval)
        token_window = payload.get('window')

        if token_window not in [current_window, current_window - 1]:
            return None, None, 'QR code has expired — please scan the current one on screen'

        return payload, token_window, None
    except Exception as e:
        return None, None, str(e)


# ─────────────────────────────────────────────────────────────
#  ANTI-CHEAT  —  Suspicious Scan Detection (Mode B)
# ─────────────────────────────────────────────────────────────

def get_client_ip(request):
    """Extracts the real client IP, handling proxies."""
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def get_device_fingerprint(request):
    """
    Creates a lightweight device fingerprint from request headers.
    Not perfect but good enough to detect same-device multi-account scans.
    """
    ua = request.META.get('HTTP_USER_AGENT', '')
    lang = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
    encoding = request.META.get('HTTP_ACCEPT_ENCODING', '')
    raw = f"{ua}|{lang}|{encoding}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def detect_suspicious_scan(registration, request, window_number, event):
    """
    Runs anti-cheat checks against a Mode B scan attempt.
    Returns a flag string if suspicious, or '' if clean.

    Flags:
        'device_sharing'  — same device fingerprint, different account scanned this window
        'suspicious_burst'— this participant attempted >3 windows in <2 minutes
        'ghost_account'   — account was created very recently (< 24 hours ago)
    """
    from .models import ParticipantScanRecord
    from django.utils import timezone as tz
    from datetime import timedelta

    ip = get_client_ip(request)
    fingerprint = get_device_fingerprint(request)

    # Check 1: Same device fingerprint used by a DIFFERENT registration this window
    same_device_different_user = ParticipantScanRecord.objects.filter(
        event=event,
        window_number=window_number,
        device_fingerprint=fingerprint,
        is_accepted=True,
    ).exclude(registration=registration).exists()

    if same_device_different_user:
        return 'device_sharing'

    # Check 2: This participant has scanned more than 3 different windows in 2 minutes
    two_min_ago = tz.now() - timedelta(minutes=2)
    recent_scan_count = ParticipantScanRecord.objects.filter(
        registration=registration,
        scan_time__gte=two_min_ago,
    ).count()

    if recent_scan_count > 3:
        return 'suspicious_burst'

    # Check 3: Account was created in the last 24 hours (possible throwaway)
    user = registration.user
    if tz.now() - user.date_joined < timedelta(hours=24):
        return 'ghost_account'

    return ''  # Clean scan


# ─────────────────────────────────────────────────────────────
#  LEGACY  —  Kept for backward compatibility during transition
# ─────────────────────────────────────────────────────────────

def generate_attendance_token(registration_id, event_id):
    """Legacy rotating token — replaced by generate_static_pass_token for Mode A."""
    return generate_static_pass_token(registration_id, event_id)


def verify_attendance_token(token_b64):
    """Legacy verifier — delegates to static pass verifier."""
    payload, error = verify_static_pass_token(token_b64)
    return payload, error
