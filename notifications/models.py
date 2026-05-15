"""
Notification models for CertiFlow
"""
import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from accounts.models import User
from organizations.models import Organization


class EmailLog(models.Model):
    """
    Tracks emails sent by the system (registrations, certificates, etc.)
    """
    class Status(models.TextChoices):
        QUEUED = 'queued', _('Queued')
        SENT = 'sent', _('Sent')
        FAILED = 'failed', _('Failed')
        OPENED = 'opened', _('Opened')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='email_logs')
    recipient_email = models.EmailField()
    recipient_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='received_emails')
    
    subject = models.CharField(max_length=255)
    body_text = models.TextField()
    body_html = models.TextField(blank=True)
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    sent_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    
    # Metadata to track what this email was for
    email_type = models.CharField(max_length=50, help_text='e.g., registration_confirmation, certificate_delivery')
    related_object_id = models.UUIDField(null=True, blank=True)
    attachment = models.FileField(upload_to="email_attachments/", null=True, blank=True)
    
    class Meta:
        ordering = ['-sent_at', 'id']
        indexes = [
            models.Index(fields=['recipient_email']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f'{self.subject} to {self.recipient_email}'


class Notification(models.Model):
    """
    In-app notifications for users.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    link = models.URLField(blank=True)
    
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.title} for {self.user.get_full_name()}'
