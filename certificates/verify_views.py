from django.shortcuts import render, get_object_or_404
from .models import Certificate, VerificationLog

def verify_certificate(request, certificate_id):
    """
    Public view to verify a certificate's authenticity.
    """
    certificate = get_object_or_404(Certificate, certificate_id=certificate_id)
    
    # Log the verification attempt
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
        
    VerificationLog.objects.create(
        certificate=certificate,
        ip_address=ip,
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        is_success=not certificate.is_revoked
    )
    
    return render(request, 'certificates/verify.html', {
        'certificate': certificate,
        'event': certificate.registration.event,
        'participant': certificate.registration.user
    })
