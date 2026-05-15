from django.core.management.base import BaseCommand
from notifications.tasks import send_queued_emails
from certificates.tasks import generate_pending_certificates

class Command(BaseCommand):
    help = 'Process pending emails and certificates'

    def handle(self, *args, **options):
        self.stdout.write('Starting background task processing...')
        
        # 1. Generate Certificates
        self.stdout.write('Generating certificates...')
        cert_result = generate_pending_certificates()
        self.stdout.write(self.style.SUCCESS(f'Certificates: {cert_result}'))
        
        # 2. Send Emails
        self.stdout.write('Sending emails...')
        email_result = send_queued_emails()
        self.stdout.write(self.style.SUCCESS(f'Emails: {email_result}'))
        
        self.stdout.write('Processing complete.')
