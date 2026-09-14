from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from organizations.models import Organization
from events.models import Event

class ProfileViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='teststudent@example.com',
            password='securepassword123',
            first_name='OriginalFirst',
            last_name='OriginalLast',
            phone='1234567890',
            institution='Original University',
            department='Original Dept',
            year_of_study='2nd',
            github_url='https://github.com/original',
            linkedin_url='https://linkedin.com/in/original',
            portfolio_url='https://original.me'
        )
        self.profile_url = reverse('accounts:profile')

    def test_profile_view_redirects_unauthenticated(self):
        """GET request to profile page when not logged in redirects to login view."""
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('accounts:login'), response.url)

    def test_profile_view_loads_for_authenticated_user(self):
        """GET request to profile page when logged in works and displays form and memberships."""
        self.client.login(email='teststudent@example.com', password='securepassword123')
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/profile.html')
        self.assertIn('form', response.context)
        self.assertIn('memberships', response.context)
        self.assertEqual(response.context['user'], self.user)

    def test_profile_update_successful(self):
        """POST request with valid profile data updates user details and redirects to profile."""
        self.client.login(email='teststudent@example.com', password='securepassword123')
        post_data = {
            'first_name': 'UpdatedFirst',
            'last_name': 'UpdatedLast',
            'phone': '+91 99999 88888',
            'institution': 'Elite Tech Institute',
            'department': 'Computer Science Engineering',
            'year_of_study': '3rd',
            'github_url': 'https://github.com/updatedstudent',
            'linkedin_url': 'https://linkedin.com/in/updatedstudent',
            'portfolio_url': 'https://updatedstudent.github.io'
        }
        response = self.client.post(self.profile_url, post_data)
        
        # Verify redirect
        self.assertRedirects(response, self.profile_url)
        
        # Reload user from DB
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'UpdatedFirst')
        self.assertEqual(self.user.last_name, 'UpdatedLast')
        self.assertEqual(self.user.phone, '+91 99999 88888')
        self.assertEqual(self.user.institution, 'Elite Tech Institute')
        self.assertEqual(self.user.department, 'Computer Science Engineering')
        self.assertEqual(self.user.year_of_study, '3rd')
        self.assertEqual(self.user.github_url, 'https://github.com/updatedstudent')
        self.assertEqual(self.user.linkedin_url, 'https://linkedin.com/in/updatedstudent')
        self.assertEqual(self.user.portfolio_url, 'https://updatedstudent.github.io')

    def test_profile_update_invalid_url(self):
        """POST request with invalid URL field outputs validation error and keeps original values."""
        self.client.login(email='teststudent@example.com', password='securepassword123')
        post_data = {
            'first_name': 'UpdatedFirst',
            'last_name': 'UpdatedLast',
            'phone': '+91 99999 88888',
            'institution': 'Elite Tech Institute',
            'department': 'Computer Science Engineering',
            'year_of_study': '3rd',
            'github_url': 'invalid-url-format',
            'linkedin_url': 'https://linkedin.com/in/updatedstudent',
            'portfolio_url': 'https://updatedstudent.github.io'
        }
        response = self.client.post(self.profile_url, post_data)
        self.assertEqual(response.status_code, 200) # Form re-rendered with errors
        self.assertFalse(response.context['form'].is_valid())
        self.assertIn('github_url', response.context['form'].errors)

        # Reload user from DB and assert original github_url is preserved
        self.user.refresh_from_db()
        self.assertEqual(self.user.github_url, 'https://github.com/original')

    def test_prefill_parameters_integration(self):
        """User profile updates are reflected in the smart registration pre-fill data endpoint."""
        self.client.login(email='teststudent@example.com', password='securepassword123')
        
        # Update profile first
        post_data = {
            'first_name': 'PreFilledName',
            'last_name': 'PreFilledLast',
            'phone': '9876543210',
            'institution': 'Prefill Tech',
            'department': 'IT',
            'year_of_study': '4th',
            'github_url': 'https://github.com/prefill',
            'linkedin_url': 'https://linkedin.com/in/prefill',
            'portfolio_url': 'https://prefill.me'
        }
        self.client.post(self.profile_url, post_data)

        # Create dummy Organization and Event to query the schema prefill endpoint
        org = Organization.objects.create(name='Test Org', slug='test-org')
        event = Event.objects.create(
            organization=org,
            created_by=self.user,
            title='Test Tech Summit',
            slug='test-tech-summit',
            description='Test event description',
            start_datetime=timezone.now() + timezone.timedelta(days=1),
            end_datetime=timezone.now() + timezone.timedelta(days=1, hours=2),
            status=Event.Status.PUBLISHED
        )

        schema_url = reverse('registrations:form_schema', kwargs={'event_id': event.id})
        response = self.client.get(schema_url)
        self.assertEqual(response.status_code, 200)

        json_data = response.json()
        self.assertIn('prefill', json_data)
        prefill = json_data['prefill']
        
        # Verify that all updated profile parameters are fully integrated into prefill logic
        self.assertEqual(prefill['first_name'], 'PreFilledName')
        self.assertEqual(prefill['last_name'], 'PreFilledLast')
        self.assertEqual(prefill['phone'], '9876543210')
        self.assertEqual(prefill['institution'], 'Prefill Tech')
        self.assertEqual(prefill['department'], 'IT')
        self.assertEqual(prefill['year_of_study'], '4th')
        self.assertEqual(prefill['github_url'], 'https://github.com/prefill')
        self.assertEqual(prefill['linkedin_url'], 'https://linkedin.com/in/prefill')
        self.assertEqual(prefill['portfolio_url'], 'https://prefill.me')


class SecurityLockTests(TestCase):
    def test_unauthorized_superuser_escalation_blocked(self):
        """Saving a non-owner user as superuser, staff, or super admin automatically resets them and alerts."""
        user = User.objects.create_user(
            email='malicious@example.com',
            password='maliciouspassword123',
            first_name='Malicious',
            last_name='User'
        )
        
        # Attempt to escalate
        user.is_superuser = True
        user.is_staff = True
        user.role = User.Role.SUPER_ADMIN
        user.save()

        # Check fields were reset
        user.refresh_from_db()
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)
        self.assertEqual(user.role, User.Role.PARTICIPANT)

        # Check AuditLog entry exists
        from analytics.models import AuditLog
        audit_log = AuditLog.objects.filter(user=user, action=AuditLog.Action.UPDATE).first()
        self.assertIsNotNone(audit_log)
        self.assertIn("SECURITY ALERT: Blocked unauthorized privilege escalation attempt", audit_log.description)

    def test_authorized_owner_escalation_allowed(self):
        """Saving the true owner as superuser, staff, and super admin is fully allowed."""
        owner = User.objects.create_user(
            email='mayurtheprogrammer12@gmail.com',
            password='ownerpassword123',
            first_name='Mayur',
            last_name='Kharat'
        )
        
        # Escalate
        owner.is_superuser = True
        owner.is_staff = True
        owner.role = User.Role.SUPER_ADMIN
        owner.save()

        # Check fields are retained
        owner.refresh_from_db()
        self.assertTrue(owner.is_superuser)
        self.assertTrue(owner.is_staff)
        self.assertEqual(owner.role, User.Role.SUPER_ADMIN)

