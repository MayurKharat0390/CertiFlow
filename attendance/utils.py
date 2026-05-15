import time
import hmac
import hashlib
import json
import base64
from django.conf import settings
from django.utils import timezone

def generate_attendance_token(registration_id, event_id):
    """
    Generates a signed attendance token valid for the current time window.
    Window changes every settings.QR_REFRESH_INTERVAL seconds.
    """
    secret = settings.CERT_SECRET_KEY.encode()
    interval = getattr(settings, 'QR_REFRESH_INTERVAL', 20)
    
    # Calculate current window
    timestamp = int(time.time())
    window = timestamp // interval
    
    payload = {
        'reg_id': str(registration_id),
        'event_id': str(event_id),
        'window': window
    }
    
    payload_json = json.dumps(payload, sort_keys=True)
    signature = hmac.new(secret, payload_json.encode(), hashlib.sha256).hexdigest()
    
    # Combine payload and signature then base64 encode
    token_data = {
        'p': payload,
        's': signature
    }
    
    token_json = json.dumps(token_data)
    token_b64 = base64.urlsafe_b64encode(token_json.encode()).decode()
    
    return token_b64

def verify_attendance_token(token_b64):
    """
    Verifies a token and returns the payload if valid.
    Checks the current window and the previous window to account for network latency/timing.
    """
    try:
        token_json = base64.urlsafe_b64decode(token_b64.encode()).decode()
        token_data = json.loads(token_json)
        
        payload = token_data.get('p')
        signature = token_data.get('s')
        
        if not payload or not signature:
            return None, "Invalid token format"
            
        # Re-verify signature
        secret = settings.CERT_SECRET_KEY.encode()
        payload_json = json.dumps(payload, sort_keys=True)
        expected_signature = hmac.new(secret, payload_json.encode(), hashlib.sha256).hexdigest()
        
        if not hmac.compare_digest(signature, expected_signature):
            return None, "Invalid signature"
            
        # Verify time window
        interval = getattr(settings, 'QR_REFRESH_INTERVAL', 20)
        timestamp = int(time.time())
        current_window = timestamp // interval
        token_window = payload.get('window')
        
        # Allow current window or previous window
        if token_window not in [current_window, current_window - 1]:
            return None, "Token expired"
            
        return payload, None
        
    except Exception as e:
        return None, str(e)
