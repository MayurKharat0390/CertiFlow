"""
Registration models for CertiFlow
"""
import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from accounts.models import User
from events.models import Event


class Registration(models.Model):
    """
    Participant registration for an event.
    """
    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending')
        CONFIRMED = 'confirmed', _('Confirmed')
        CANCELLED = 'cancelled', _('Cancelled')
        WAITLISTED = 'waitlisted', _('Waitlisted')
        ATTENDED = 'attended', _('Attended')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='registrations')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='registrations')
    
    # Registration details
    registration_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CONFIRMED)
    
    # Participant unique ID for this specific event
    participant_id = models.CharField(max_length=50, blank=True, unique=True)
    
    # Additional data captured during registration (JSON for flexibility)
    custom_data = models.JSONField(default=dict, blank=True)
    
    # Eligibility for certificate (calculated based on attendance)
    is_eligible_for_certificate = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ('event', 'user')
        ordering = ['-registration_date']
        indexes = [
            models.Index(fields=['event', 'status']),
            models.Index(fields=['participant_id']),
        ]

    def __str__(self):
        return f'{self.user.get_full_name()} - {self.event.title}'

    def save(self, *args, **kwargs):
        if not self.participant_id:
            # Generate a unique participant ID if not provided
            # Format: CF-EVENT_SLUG[:4]-RANDOM[:6]
            import random
            import string
            slug_part = self.event.slug[:4].upper()
            random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            self.participant_id = f"CF-{slug_part}-{random_part}"
        super().save(*args, **kwargs)


class RegistrationForm(models.Model):
    """
    Custom fields for event registration.
    """
    class FieldType(models.TextChoices):
        TEXT = 'text', _('Short Text')
        TEXTAREA = 'textarea', _('Long Text')
        SELECT = 'select', _('Dropdown')
        CHECKBOX = 'checkbox', _('Checkbox')
        NUMBER = 'number', _('Number')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='custom_form_fields')
    label = models.CharField(max_length=200)
    field_name = models.SlugField(max_length=50) # Key in the JSON data
    field_type = models.CharField(max_length=20, choices=FieldType.choices, default=FieldType.TEXT)
    options = models.TextField(blank=True, help_text='Comma-separated for dropdowns')
    is_required = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('event', 'field_name')
        ordering = ['order']

    def __str__(self):
        return f'{self.label} ({self.event.title})'
