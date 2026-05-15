"""
Organization models for CertiFlow multi-tenancy
"""
import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from accounts.models import User


class Organization(models.Model):
    """
    Multi-tenant organization. All data is scoped per organization.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, max_length=100)
    description = models.TextField(blank=True)
    logo = models.ImageField(upload_to='org_logos/', null=True, blank=True)
    website = models.URLField(blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)

    # Settings
    is_active = models.BooleanField(default=True)
    allow_public_registration = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='created_organizations'
    )

    class Meta:
        verbose_name = _('organization')
        verbose_name_plural = _('organizations')
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_member_count(self):
        return self.memberships.filter(is_active=True).count()


class Membership(models.Model):
    """
    User membership in an organization with role assignment.
    """
    class Role(models.TextChoices):
        OWNER = 'owner', _('Owner')
        ADMIN = 'admin', _('Admin')
        EVENT_MANAGER = 'event_manager', _('Event Manager')
        VOLUNTEER = 'volunteer', _('Volunteer')
        MEMBER = 'member', _('Member')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='memberships')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    invited_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sent_invitations'
    )

    class Meta:
        unique_together = ('user', 'organization')
        ordering = ['-joined_at']

    def __str__(self):
        return f'{self.user.get_full_name()} @ {self.organization.name} ({self.role})'

    @property
    def is_admin(self):
        return self.role in [self.Role.OWNER, self.Role.ADMIN]

    @property
    def can_manage_events(self):
        return self.role in [self.Role.OWNER, self.Role.ADMIN, self.Role.EVENT_MANAGER]


class Invitation(models.Model):
    """
    Pending invitations to join an organization.
    """
    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending')
        ACCEPTED = 'accepted', _('Accepted')
        DECLINED = 'declined', _('Declined')
        EXPIRED = 'expired', _('Expired')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='invitations')
    email = models.EmailField()
    role = models.CharField(max_length=20, choices=Membership.Role.choices, default=Membership.Role.MEMBER)
    token = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    invited_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='invitations_sent')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Invitation for {self.email} to {self.organization.name}'
