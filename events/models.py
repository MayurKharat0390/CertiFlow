"""
Event models for CertiFlow
"""
import uuid
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from accounts.models import User
from organizations.models import Organization


class Event(models.Model):
    """
    Campus event with full lifecycle management.
    """
    class Status(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        PUBLISHED = 'published', _('Published')
        REGISTRATION_CLOSED = 'registration_closed', _('Registration Closed')
        ONGOING = 'ongoing', _('Ongoing')
        COMPLETED = 'completed', _('Completed')
        CANCELLED = 'cancelled', _('Cancelled')

    class EventType(models.TextChoices):
        WORKSHOP = 'workshop', _('Workshop')
        SEMINAR = 'seminar', _('Seminar')
        CONFERENCE = 'conference', _('Conference')
        HACKATHON = 'hackathon', _('Hackathon')
        WEBINAR = 'webinar', _('Webinar')
        COMPETITION = 'competition', _('Competition')
        SOCIAL = 'social', _('Social Event')
        OTHER = 'other', _('Other')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='events')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_events')

    title = models.CharField(max_length=300)
    slug = models.SlugField(max_length=300)
    description = models.TextField()
    event_type = models.CharField(max_length=20, choices=EventType.choices, default=EventType.WORKSHOP)
    banner_image = models.ImageField(upload_to='event_banners/', null=True, blank=True)
    tags = models.CharField(max_length=500, blank=True, help_text='Comma-separated tags')

    # Location
    venue_name = models.CharField(max_length=300, blank=True)
    venue_address = models.TextField(blank=True)
    is_online = models.BooleanField(default=False)
    online_link = models.URLField(blank=True)

    # Timing
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    registration_deadline = models.DateTimeField(null=True, blank=True)

    # Attendance window (when QR codes are valid)
    attendance_start = models.DateTimeField(null=True, blank=True)
    attendance_end = models.DateTimeField(null=True, blank=True)

    # Capacity
    max_capacity = models.PositiveIntegerField(null=True, blank=True, help_text='Leave blank for unlimited')
    is_waitlist_enabled = models.BooleanField(default=False)

    # Certificate eligibility
    certificate_eligibility_min_attendance_minutes = models.PositiveIntegerField(
        default=0, help_text='Minimum attendance minutes for certificate eligibility'
    )
    certificate_eligible_all = models.BooleanField(
        default=True, help_text='All registered participants get certificate'
    )

    status = models.CharField(max_length=30, choices=Status.choices, default=Status.DRAFT)
    is_featured = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('organization', 'slug')
        ordering = ['-start_datetime']
        indexes = [
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['start_datetime']),
            models.Index(fields=['slug']),
        ]

    def __str__(self):
        return f'{self.title} ({self.organization.name})'

    @property
    def is_registration_open(self):
        now = timezone.now()
        if self.status != self.Status.PUBLISHED:
            return False
        if self.registration_deadline and now > self.registration_deadline:
            return False
        if self.max_capacity:
            return self.registrations.filter(status='confirmed').count() < self.max_capacity
        return True

    @property
    def is_attendance_window_active(self):
        now = timezone.now()
        if self.attendance_start and self.attendance_end:
            return self.attendance_start <= now <= self.attendance_end
        return self.start_datetime <= now <= self.end_datetime

    @property
    def registered_count(self):
        return self.registrations.filter(status='confirmed').count()

    @property
    def attended_count(self):
        return self.attendances.filter(check_in_time__isnull=False).count()


class CertificateCategory(models.Model):
    """
    Multiple certificate categories per event (e.g., Participant, Winner, Speaker).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='certificate_categories')
    name = models.CharField(max_length=200)
    description = models.CharField(max_length=500, blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        unique_together = ('event', 'name')
        ordering = ['name']

    def __str__(self):
        return f'{self.name} - {self.event.title}'


class EventManager(models.Model):
    """
    Users assigned as managers for specific events.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='event_managers')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='managed_events')
    can_scan_attendance = models.BooleanField(default=True)
    can_issue_certificates = models.BooleanField(default=False)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('event', 'user')

    def __str__(self):
        return f'{self.user.get_full_name()} manages {self.event.title}'
