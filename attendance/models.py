"""
Attendance models for CertiFlow
"""
import uuid
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from accounts.models import User
from events.models import Event
from registrations.models import Registration


class Attendance(models.Model):
    """
    Main attendance record for a participant in an event.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    registration = models.OneToOneField(Registration, on_delete=models.CASCADE, related_name='attendance_record')
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='attendances')
    
    check_in_time = models.DateTimeField(null=True, blank=True)
    check_out_time = models.DateTimeField(null=True, blank=True)
    
    # Total time spent in minutes
    total_minutes = models.PositiveIntegerField(default=0)
    
    is_present = models.BooleanField(default=False)
    
    class Meta:
        verbose_name_plural = _('Attendance')
        indexes = [
            models.Index(fields=['event', 'is_present']),
        ]

    def __str__(self):
        return f'{self.registration.user.get_full_name()} - {self.event.title}'

    def update_duration(self):
        if self.check_in_time and self.check_out_time:
            delta = self.check_out_time - self.check_in_time
            self.total_minutes = int(delta.total_seconds() / 60)
            self.save()


class ScanLog(models.Model):
    """
    Logs every time a QR code is scanned. Useful for audit and check-in/out tracking.
    """
    class ScanType(models.TextChoices):
        CHECK_IN = 'check_in', _('Check-in')
        CHECK_OUT = 'check_out', _('Check-out')
        VERIFICATION = 'verification', _('Verification Only')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attendance = models.ForeignKey(Attendance, on_delete=models.CASCADE, related_name='scan_logs')
    scanned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='scans_performed')
    scan_time = models.DateTimeField(default=timezone.now)
    scan_type = models.CharField(max_length=20, choices=ScanType.choices, default=ScanType.CHECK_IN)
    
    # Device/Location info
    device_info = models.TextField(blank=True)
    location_data = models.JSONField(null=True, blank=True)

    # Verification token used for this scan
    token_used = models.TextField(blank=True)

    # Action performed after scan (Mode A volunteer scanner)
    action_performed = models.CharField(
        max_length=50, blank=True,
        help_text='e.g. mark_attended, mark_absent, issued_cert, verify_only'
    )

    # Anti-cheat flagging (Mode B participant scans)
    is_flagged = models.BooleanField(default=False)
    scan_flag = models.CharField(
        max_length=50, blank=True,
        help_text='geo_anomaly | suspicious_burst | device_sharing | ghost_account'
    )
    flag_reviewed = models.BooleanField(default=False)

    class Meta:
        ordering = ['-scan_time']

    def __str__(self):
        return f'{self.scan_type} at {self.scan_time}'


class ParticipantScanRecord(models.Model):
    """
    Tracks Mode B attendance: participant scans the event's rolling QR.
    Each record represents one participant's scan attempt, including
    anti-cheat metadata for the organizer's review panel.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    registration = models.ForeignKey(
        Registration, on_delete=models.CASCADE,
        related_name='self_scan_records'
    )
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE,
        related_name='participant_scan_records'
    )
    scan_time = models.DateTimeField(default=timezone.now)

    # The QR window number that was scanned
    window_number = models.PositiveIntegerField()

    # Whether this scan was accepted and attendance marked
    is_accepted = models.BooleanField(default=True)
    rejection_reason = models.CharField(max_length=100, blank=True)

    # Anti-cheat metadata
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    device_fingerprint = models.CharField(max_length=255, blank=True)
    is_flagged = models.BooleanField(default=False)
    scan_flag = models.CharField(
        max_length=50, blank=True,
        help_text='geo_anomaly | suspicious_burst | device_sharing | ghost_account'
    )
    flag_reviewed = models.BooleanField(default=False)
    flag_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-scan_time']
        indexes = [
            models.Index(fields=['event', 'window_number']),
            models.Index(fields=['registration', 'window_number']),
            models.Index(fields=['is_flagged', 'flag_reviewed']),
        ]

    def __str__(self):
        status = 'ACCEPTED' if self.is_accepted else 'REJECTED'
        flag = f' [{self.scan_flag}]' if self.is_flagged else ''
        return f'{self.registration.user.get_full_name()} - {status}{flag}'
