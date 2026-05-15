from celery import shared_task
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone
from .models import EmailLog

@shared_task
def send_queued_emails(limit=100):
    """Celery task to send queued emails"""
    pending_emails = EmailLog.objects.filter(
        status=EmailLog.Status.QUEUED
    ).order_by('id')[:limit]
    
    count = 0
    for email_log in pending_emails:
        try:
            msg = EmailMultiAlternatives(
                subject=email_log.subject,
                body=email_log.body_text,
                from_email=None,
                to=[email_log.recipient_email]
            )
            if email_log.body_html:
                msg.attach_alternative(email_log.body_html, "text/html")
            
            if email_log.attachment:
                msg.attach_file(email_log.attachment.path)
            
            msg.send()
            
            email_log.status = EmailLog.Status.SENT
            email_log.sent_at = timezone.now()
            email_log.save()
            count += 1
        except Exception as e:
            email_log.status = EmailLog.Status.FAILED
            email_log.error_message = str(e)
            email_log.save()
            
    return f"Sent {count} emails"
