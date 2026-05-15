import logging
from django.core.management.base import BaseCommand
from certificates.models import Certificate
from certificates.utils import generate_certificate_pdf

logger = logging.getLogger('certiflow')

class Command(BaseCommand):
    help = 'Processes the certificate generation queue'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=20,
            help='Limit the number of certificates to generate in one run'
        )

    def handle(self, *args, **options):
        limit = options['limit']
        
        pending_certs = Certificate.objects.filter(
            status=Certificate.Status.PENDING
        ).order_by('id')[:limit]
        
        if not pending_certs:
            self.stdout.write(self.style.SUCCESS('No pending certificates found.'))
            return

        self.stdout.write(f'Generating {len(pending_certs)} certificates...')
        
        success_count = 0
        fail_count = 0
        
        for cert in pending_certs:
            try:
                # Mark as generating
                cert.status = Certificate.Status.GENERATING
                cert.save()
                
                # Call utility
                generate_certificate_pdf(cert.id)
                
                # Mark as completed
                cert.status = Certificate.Status.COMPLETED
                cert.save()
                
                success_count += 1
                self.stdout.write(self.style.SUCCESS(f'Successfully generated: {cert.certificate_id}'))
                
            except Exception as e:
                fail_count += 1
                cert.status = Certificate.Status.FAILED
                cert.revocation_reason = f"Generation error: {str(e)}"
                cert.save()
                self.stdout.write(self.style.ERROR(f'Failed for {cert.certificate_id}: {str(e)}'))
                logger.error(f'Certificate generation error for {cert.certificate_id}: {str(e)}')

        self.stdout.write(self.style.SUCCESS(
            f'Certificate generation complete. Success: {success_count}, Failed: {fail_count}'
        ))
