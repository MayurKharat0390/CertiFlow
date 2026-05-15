"""
Certificate models for CertiFlow
"""
import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from accounts.models import User
from events.models import Event, CertificateCategory
from registrations.models import Registration


class CertificateTemplate(models.Model):
    """
    Template for certificate generation.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='certificate_templates')
    category = models.ForeignKey(CertificateCategory, on_delete=models.CASCADE, related_name='templates')
    
    name = models.CharField(max_length=200)
    background_image = models.ImageField(upload_to='cert_templates/')
    
    # Designer data (JSON storing positions of dynamic fields like { "name": {"x": 100, "y": 200, "font_size": 24}, ... })
    layout_config = models.JSONField(default=dict)
    
    # CSS for the PDF generation (if using WeasyPrint) or styles for ReportLab
    custom_styles = models.TextField(blank=True)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.name} ({self.event.title})'


class Certificate(models.Model):
    """
    Issued certificate record.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    registration = models.ForeignKey(Registration, on_delete=models.CASCADE, related_name='certificates')
    template = models.ForeignKey(CertificateTemplate, on_delete=models.CASCADE, related_name='issued_certificates')
    
    # Unique Certificate ID for verification
    # Format: CERT-YEAR-RANDOM
    certificate_id = models.CharField(max_length=50, unique=True)
    
    issue_date = models.DateTimeField(auto_now_add=True)
    issued_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='certificates_issued')
    
    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending')
        GENERATING = 'generating', _('Generating')
        COMPLETED = 'completed', _('Completed')
        FAILED = 'failed', _('Failed')

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    pdf_file = models.FileField(upload_to='certificates/', null=True, blank=True)
    
    # Verification QR code (link to verification portal)
    verification_qr = models.ImageField(upload_to='cert_qrs/', null=True, blank=True)
    
    is_revoked = models.BooleanField(default=False)
    revocation_reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-issue_date']
        indexes = [
            models.Index(fields=['certificate_id']),
        ]

    def __str__(self):
        return f'{self.certificate_id} - {self.registration.user.get_full_name()}'

    def save(self, *args, **kwargs):
        if not self.certificate_id:
            import random
            import string
            from django.utils import timezone
            year = timezone.now().year
            random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
            self.certificate_id = f"CERT-{year}-{random_part}"
        super().save(*args, **kwargs)


class VerificationLog(models.Model):
    """
    Logs every time a certificate is verified via the public portal.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    certificate = models.ForeignKey(Certificate, on_delete=models.CASCADE, related_name='verification_logs')
    verification_time = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    is_success = models.BooleanField(default=True)

    class Meta:
        ordering = ['-verification_time']

    def __str__(self):
        return f'Verification for {self.certificate.certificate_id} at {self.verification_time}'
