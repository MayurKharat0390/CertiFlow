from django.core.management.base import BaseCommand
from notifications.tasks import send_queued_emails
from certificates.tasks import generate_pending_certificates

class Command(BaseCommand):
    help = 'Process pending emails and certificates'

    def handle(self, *args, **options):
        import time
        self.stdout.write(self.style.SUCCESS('--- Background Worker Started ---'))
        
        while True:
            try:
                # 1. Generate Certificates
                self.stdout.write('Checking for certificates...')
                cert_result = generate_pending_certificates()
                if "Generated 0" not in str(cert_result):
                    self.stdout.write(self.style.SUCCESS(f'Certificates: {cert_result}'))
                
                # 2. Send Emails
                self.stdout.write('Checking for queued emails...')
                email_result = send_queued_emails()
                if "Sent 0" not in str(email_result):
                    self.stdout.write(self.style.SUCCESS(f'Emails: {email_result}'))
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error in worker loop: {str(e)}'))
            
            time.sleep(10) # Wait 10 seconds before checking again
