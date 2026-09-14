from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, Http404
from django.utils.text import slugify
from .models import Certificate, VerificationLog
from .utils import generate_certificate_image

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
    
    # Increment view count
    certificate.view_count += 1
    certificate.save(update_fields=['view_count'])
    
    return render(request, 'certificates/verify.html', {
        'certificate': certificate,
        'event': certificate.registration.event,
        'participant': certificate.registration.user
    })


def certificate_image_view(request, certificate_id):
    """
    Renders the certificate as a crisp, ultra high-resolution PNG image.
    Supports inline preview (e.g. for img tags) or attachment download (?download=1).
    """
    certificate = get_object_or_404(Certificate, certificate_id=certificate_id)
    if certificate.is_revoked:
        raise Http404("Certificate has been revoked.")
        
    # Default to 300 DPI for download, or 150 DPI for inline web preview
    is_download = request.GET.get('download') == '1'
    dpi = 300 if is_download else int(request.GET.get('dpi', 150))
    # Cap DPI safely between 72 and 300
    dpi = max(72, min(dpi, 300))
    
    try:
        img_bytes = generate_certificate_image(certificate.id, dpi=dpi)
    except Exception as e:
        raise Http404(f"Error rendering certificate image: {str(e)}")
        
    response = HttpResponse(img_bytes, content_type='image/png')
    if is_download:
        certificate.download_count += 1
        certificate.save(update_fields=['download_count'])
        
        user_name = slugify(certificate.registration.user.get_full_name()) or 'participant'
        event_name = slugify(certificate.registration.event.title) or 'event'
        filename = f"{user_name}-{event_name}-certificate.png"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
    else:
        # Cache for inline preview efficiency
        response['Cache-Control'] = 'public, max-age=3600'
        
    return response

