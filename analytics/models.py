"""
Analytics and Audit models for CertiFlow
"""
import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from accounts.models import User
from organizations.models import Organization


class AuditLog(models.Model):
    """
    Tracks sensitive actions in the system.
    """
    class Action(models.TextChoices):
        CREATE = 'create', _('Create')
        UPDATE = 'update', _('Update')
        DELETE = 'delete', _('Delete')
        LOGIN = 'login', _('Login')
        LOGOUT = 'logout', _('Logout')
        SCAN = 'scan', _('Attendance Scan')
        ISSUE_CERT = 'issue_cert', _('Issue Certificate')
        SEND_EMAIL = 'send_email', _('Send Email')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='audit_logs', null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='audit_logs')
    
    action = models.CharField(max_length=20, choices=Action.choices)
    description = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    # Generic relation to log any object
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.UUIDField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Changes in JSON format
    changes = models.JSONField(null=True, blank=True)
    
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['action']),
            models.Index(fields=['timestamp']),
        ]

    def __str__(self):
        return f'{self.user} performed {self.action} at {self.timestamp}'


class EventAnalytics(models.Model):
    """
    Cached analytics for an event to avoid expensive queries on dashboard.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_id = models.UUIDField(unique=True) # Linking by ID to avoid cascading delete issues during analysis
    
    total_registrations = models.PositiveIntegerField(default=0)
    total_confirmed = models.PositiveIntegerField(default=0)
    total_attended = models.PositiveIntegerField(default=0)
    total_certificates_issued = models.PositiveIntegerField(default=0)
    
    attendance_rate = models.FloatField(default=0.0) # Percentage
    
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Analytics for Event {self.event_id}'
