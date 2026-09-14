"""
CertiFlow Custom User Model
Extends AbstractBaseUser for complete control
"""
import uuid
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    """Custom manager for email-based authentication."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_('Email address is required'))
        email = self.normalize_email(email)
        extra_fields.setdefault('is_active', True)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('role', User.Role.SUPER_ADMIN)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    CertiFlow User model with email-based authentication.
    Supports roles: Super Admin, Org Admin, Event Manager, Volunteer, Participant
    """

    class Role(models.TextChoices):
        SUPER_ADMIN = 'super_admin', _('Super Admin')
        ORG_ADMIN = 'org_admin', _('Organization Admin')
        EVENT_MANAGER = 'event_manager', _('Event Manager')
        VOLUNTEER = 'volunteer', _('Volunteer')
        PARTICIPANT = 'participant', _('Participant')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(_('email address'), unique=True)
    first_name = models.CharField(_('first name'), max_length=150, blank=True)
    last_name = models.CharField(_('last name'), max_length=150, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.PARTICIPANT)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    bio = models.TextField(blank=True)

    # Student Profile — used to pre-fill registration forms
    institution = models.CharField(max_length=300, blank=True, help_text='College / University name')
    department = models.CharField(max_length=200, blank=True, help_text='Branch or Department')
    year_of_study = models.CharField(
        max_length=20, blank=True,
        choices=[
            ('1st', '1st Year'), ('2nd', '2nd Year'),
            ('3rd', '3rd Year'), ('4th', '4th Year'), ('PG', 'Post Graduate')
        ]
    )
    interests = models.JSONField(default=list, blank=True, help_text='List of interest tags')
    github_url = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)
    portfolio_url = models.URLField(blank=True)

    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_email_verified = models.BooleanField(default=False)

    date_joined = models.DateTimeField(default=timezone.now)
    last_login = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    def save(self, *args, **kwargs):
        is_owner = self.email.lower() == 'mayurtheprogrammer12@gmail.com'
        escalation_attempted = False
        attempted_details = {}

        if not is_owner and (self.is_superuser or self.is_staff or self.role == self.Role.SUPER_ADMIN):
            escalation_attempted = True
            attempted_details = {
                'role': self.role,
                'is_superuser': self.is_superuser,
                'is_staff': self.is_staff
            }
            # Force reset back to participant
            self.is_superuser = False
            self.is_staff = False
            if self.role == self.Role.SUPER_ADMIN:
                self.role = self.Role.PARTICIPANT

        super().save(*args, **kwargs)

        if escalation_attempted:
            # 1. Send immediate warning alert email to true owner
            from django.core.mail import send_mail
            from django.conf import settings
            
            subject = "SECURITY ALERT: Unauthorized Superuser Elevation Attempt on CertiFlow"
            message = (
                f"Warning: An unauthorized privilege elevation attempt was detected and blocked.\n\n"
                f"User Details:\n"
                f"- Email: {self.email}\n"
                f"- ID: {self.id}\n"
                f"- Name: {self.get_full_name()}\n"
                f"- Attempted Role: {attempted_details.get('role')}\n"
                f"- Attempted is_superuser: {attempted_details.get('is_superuser')}\n"
                f"- Attempted is_staff: {attempted_details.get('is_staff')}\n\n"
                f"The system has automatically blocked this operation, reset the user to standard Participant status, and recorded a security log."
            )
            
            try:
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL or 'noreply@certiflow.com',
                    ['mayurtheprogrammer12@gmail.com'],
                    fail_silently=True,
                )
            except Exception:
                pass

            # 2. Record security audit log entry
            from analytics.models import AuditLog
            try:
                AuditLog.objects.create(
                    user=self,
                    action=AuditLog.Action.UPDATE,
                    description=f"SECURITY ALERT: Blocked unauthorized privilege escalation attempt. Tried: {attempted_details}"
                )
            except Exception:
                pass


    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')
        ordering = ['-date_joined']
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['role']),
        ]

    def __str__(self):
        return f'{self.get_full_name()} <{self.email}>'

    def get_full_name(self):
        full_name = f'{self.first_name} {self.last_name}'.strip()
        return full_name or self.email

    def get_short_name(self):
        return self.first_name or self.email.split('@')[0]

    @property
    def is_super_admin(self):
        return self.role == self.Role.SUPER_ADMIN

    @property
    def is_org_admin(self):
        return self.role in [self.Role.SUPER_ADMIN, self.Role.ORG_ADMIN]

    @property
    def is_event_manager(self):
        return self.role in [self.Role.SUPER_ADMIN, self.Role.ORG_ADMIN, self.Role.EVENT_MANAGER]


class PasswordResetToken(models.Model):
    """Secure password reset tokens."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reset_tokens')
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Reset token for {self.user.email}'

    @property
    def is_valid(self):
        return not self.is_used and self.expires_at > timezone.now()


class UserGmailCredentials(models.Model):
    """
    OAuth2 credentials for sending emails directly from user's connected Gmail account.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='gmail_credentials')
    gmail_address = models.EmailField(max_length=255)
    refresh_token = models.CharField(max_length=512)
    access_token = models.TextField(blank=True)
    token_expiry = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    connected_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('User Gmail Credentials')
        verbose_name_plural = _('User Gmail Credentials')

    def __str__(self):
        return f"Gmail ({self.gmail_address}) for {self.user.email}"

