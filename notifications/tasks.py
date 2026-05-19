from celery import shared_task
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone
from .models import EmailLog

@shared_task
def send_queued_emails(limit=500):
    """Celery task to send queued emails"""
    pending_emails = EmailLog.objects.filter(
        status=EmailLog.Status.QUEUED
    ).order_by('id')[:limit]
    
    count = 0
    for email_log in pending_emails:
        try:
            from django.conf import settings
            
            # Set sender name to the requested GDGC PCCOE
            sender_name = "GDGC PCCOE"
            from_email = f"{sender_name} <{settings.EMAIL_HOST_USER}>"

            msg = EmailMultiAlternatives(
                subject=email_log.subject,
                body=email_log.body_text,
                from_email=from_email,
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
            print(f"SUCCESS: Email sent to {email_log.recipient_email}")
            count += 1
        except Exception as e:
            print(f"FAILED to send email to {email_log.recipient_email}: {str(e)}")
            email_log.status = EmailLog.Status.FAILED
            email_log.error_message = str(e)
            email_log.save()
            
    return f"Sent {count} emails"
