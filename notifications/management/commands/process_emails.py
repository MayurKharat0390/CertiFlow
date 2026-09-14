import time
import logging
from django.core.management.base import BaseCommand
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone
from notifications.models import EmailLog

logger = logging.getLogger('certiflow')

class Command(BaseCommand):
    help = 'Processes the email queue and sends pending emails'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Limit the number of emails to process in one run'
        )
        parser.add_argument(
            '--sleep',
            type=float,
            default=1.0,
            help='Seconds to sleep between emails to avoid rate limits'
        )

    def handle(self, *args, **options):
        limit = options['limit']
        sleep_time = options['sleep']
        
        pending_emails = EmailLog.objects.filter(
            status=EmailLog.Status.QUEUED
        ).order_by('id')[:limit]
        
        if not pending_emails:
            self.stdout.write(self.style.SUCCESS('No pending emails found.'))
            return

        self.stdout.write(f'Processing {len(pending_emails)} emails...')
        
        success_count = 0
        fail_count = 0
        
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
                        success_count += 1
                        self.stdout.write(self.style.SUCCESS(f'Successfully sent via Gmail API to {email_log.recipient_email}'))
                        continue

                # 2. Fallback to Standard Django SMTP
                from django.conf import settings
                
                # Use the organization's name if available, otherwise default to settings.DEFAULT_FROM_EMAIL
                if email_log.organization:
                    from_email = f"{email_log.organization.name} <{settings.EMAIL_HOST_USER}>"
                else:
                    from_email = settings.DEFAULT_FROM_EMAIL or f"CertiFlow <{settings.EMAIL_HOST_USER}>"

                # Prepare email
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
                
                # Send
                msg.send()
                
                # Update log
                email_log.status = EmailLog.Status.SENT
                email_log.sent_at = timezone.now()
                email_log.save()
                
                success_count += 1
                self.stdout.write(self.style.SUCCESS(f'Successfully sent to {email_log.recipient_email}'))
                
                # Throttle
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    
            except Exception as e:
                fail_count += 1
                email_log.status = EmailLog.Status.FAILED
                email_log.error_message = str(e)
                email_log.save()
                self.stdout.write(self.style.ERROR(f'Failed to send to {email_log.recipient_email}: {str(e)}'))
                logger.error(f'Email send error: {str(e)}')

        self.stdout.write(self.style.SUCCESS(
            f'Email processing complete. Success: {success_count}, Failed: {fail_count}'
        ))
