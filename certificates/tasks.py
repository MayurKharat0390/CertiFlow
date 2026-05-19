from celery import shared_task
from .models import Certificate
from .utils import generate_certificate_pdf
from notifications.models import EmailLog

@shared_task
def generate_pending_certificates(limit=500):
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
            
            # Email notification removed: Manager will manually send emails via Outreach.
            
            count += 1
        except Exception as e:
            cert.status = Certificate.Status.FAILED
            cert.revocation_reason = f"Generation error: {str(e)}"
            cert.save()
            
    return f"Generated {count} certificates"
