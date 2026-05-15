from celery import shared_task
from .models import Certificate
from .utils import generate_certificate_pdf
from notifications.models import EmailLog

@shared_task
def generate_pending_certificates(limit=50):
    """Celery task to generate pending certificates"""
    pending_certs = Certificate.objects.filter(
        status=Certificate.Status.PENDING
    ).order_by('id')[:limit]
    
    count = 0
    for cert in pending_certs:
        try:
            cert.status = Certificate.Status.GENERATING
            cert.save()
            
            generate_certificate_pdf(cert.id)
            cert.refresh_from_db()
            
            # Queue Email Notification
            EmailLog.objects.create(
                organization=cert.registration.event.organization,
                recipient_user=cert.registration.user,
                recipient_email=cert.registration.user.email,
                subject=f"Certificate Issued: {cert.registration.event.title}",
                body_text=f"Congratulations! Your certificate for {cert.registration.event.title} is now available.",
                body_html=f"<h3>Congratulations!</h3><p>Your certificate for <b>{cert.registration.event.title}</b> has been issued. You can download it from your dashboard.</p>",
                email_type='certificate_delivery'
            )
            
            count += 1
        except Exception as e:
            cert.status = Certificate.Status.FAILED
            cert.revocation_reason = f"Generation error: {str(e)}"
            cert.save()
            
    return f"Generated {count} certificates"
