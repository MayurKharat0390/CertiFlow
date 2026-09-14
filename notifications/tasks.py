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
            # 1. Try sending natively via Organizer's Connected Gmail API
            from accounts.gmail_service import send_email_via_gmail_api
            sender_user = email_log.sender_user
            if not sender_user and email_log.organization:
                owner_membership = email_log.organization.memberships.filter(role='owner').first()
                if owner_membership:
                    sender_user = owner_membership.user

            if sender_user and hasattr(sender_user, 'gmail_credentials') and sender_user.gmail_credentials.is_active:
                sent = send_email_via_gmail_api(sender_user, email_log)
                if sent:
                    print(f"SUCCESS: Email sent via Gmail API to {email_log.recipient_email}")
                    count += 1
                    continue

            # 2. Fallback to Standard Django SMTP
            from django.conf import settings
            
            # Use the organization's name if available, otherwise default to settings.DEFAULT_FROM_EMAIL
            if email_log.organization:
                from_email = f"{email_log.organization.name} <{settings.EMAIL_HOST_USER}>"
            else:
                from_email = settings.DEFAULT_FROM_EMAIL or f"CertiFlow <{settings.EMAIL_HOST_USER}>"

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
