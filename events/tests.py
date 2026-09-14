from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.core import mail
from accounts.models import User
from organizations.models import Organization
from events.models import Event, EventVolunteer
from registrations.models import Registration, RegistrationForm

class EventVolunteerTests(TestCase):
    def setUp(self):
        # Create an organization
        self.org = Organization.objects.create(name='Test Org', slug='test-org')
        
        # Create an owner
        self.owner = User.objects.create_user(
            email='mayurtheprogrammer12@gmail.com',
            password='ownerpassword123',
            first_name='Mayur',
            last_name='Kharat'
        )
        self.owner.is_superuser = True
        self.owner.is_staff = True
        self.owner.role = User.Role.SUPER_ADMIN
        self.owner.save()
        
        # Create a manager
        self.manager = User.objects.create_user(
            email='manager@example.com',
            password='managerpassword123',
            first_name='Event',
            last_name='Manager',
            role=User.Role.EVENT_MANAGER
        )
        
        # Create some students/participants
        self.student1 = User.objects.create_user(
            email='student1@example.com',
            password='studentpassword123',
            first_name='Student',
            last_name='One'
        )
        
        self.student2 = User.objects.create_user(
            email='student2@example.com',
            password='studentpassword123',
            first_name='Student',
            last_name='Two'
        )
        
        # Create an event
        self.event = Event.objects.create(
            organization=self.org,
            created_by=self.owner,
            title='Annual Hackathon',
            slug='annual-hackathon',
            description='Code all night!',
            start_datetime=timezone.now() + timezone.timedelta(days=1),
            end_datetime=timezone.now() + timezone.timedelta(days=1, hours=10),
            status=Event.Status.PUBLISHED,
            attendance_mode=Event.AttendanceMode.VOLUNTEER_SCANS
        )
        
        # Assign manager to event
        from events.models import EventManager
        EventManager.objects.create(event=self.event, user=self.manager)
        
        # Register student1 to event
        self.reg1 = Registration.objects.create(
            event=self.event,
            user=self.student1,
            status=Registration.Status.CONFIRMED
        )

    def test_volunteer_apply_registered_participant(self):
        """A confirmed participant can apply to volunteer for the event."""
        self.client.login(email='student1@example.com', password='studentpassword123')
        url = reverse('events:volunteer_apply', kwargs={'pk': self.event.id})
        
        response = self.client.post(url)
        self.assertRedirects(response, reverse('events:event_detail', kwargs={'pk': self.event.id}))
        
        # Verify EventVolunteer record
        vol = EventVolunteer.objects.get(event=self.event, user=self.student1)
        self.assertEqual(vol.status, EventVolunteer.Status.PENDING)

    def test_volunteer_apply_unregistered_participant(self):
        """An unregistered user cannot apply to volunteer."""
        self.client.login(email='student2@example.com', password='studentpassword123')
        url = reverse('events:volunteer_apply', kwargs={'pk': self.event.id})
        
        response = self.client.post(url)
        self.assertRedirects(response, reverse('events:event_detail', kwargs={'pk': self.event.id}))
        
        # Verify no EventVolunteer record is created
        self.assertFalse(EventVolunteer.objects.filter(event=self.event, user=self.student2).exists())

    def test_manage_volunteers_permission(self):
        """Only event managers/admins/superusers can manage volunteers."""
        # Unprivileged student
        self.client.login(email='student1@example.com', password='studentpassword123')
        url = reverse('events:manage_volunteers', kwargs={'pk': self.event.id})
        response = self.client.get(url)
        self.assertRedirects(response, reverse('events:event_detail', kwargs={'pk': self.event.id}))

        # Event Manager
        self.client.login(email='manager@example.com', password='managerpassword123')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'events/volunteers.html')

    def test_manage_volunteers_invite_success(self):
        """Event manager can recruit/invite a volunteer directly by email."""
        self.client.login(email='manager@example.com', password='managerpassword123')
        url = reverse('events:manage_volunteers', kwargs={'pk': self.event.id})
        
        # Invite student2 (who is not yet a volunteer)
        response = self.client.post(url, {'email': 'student2@example.com'})
        self.assertRedirects(response, url)
        
        # Verify they are directly approved as a volunteer
        vol = EventVolunteer.objects.get(event=self.event, user=self.student2)
        self.assertEqual(vol.status, EventVolunteer.Status.APPROVED)
        self.assertEqual(vol.approved_by, self.manager)

    def test_approve_reject_volunteer_flow(self):
        """Event manager can approve and reject/revoke pending volunteer requests."""
        # Create a pending volunteer application for student1
        vol = EventVolunteer.objects.create(
            event=self.event,
            user=self.student1,
            status=EventVolunteer.Status.PENDING
        )
        
        self.client.login(email='manager@example.com', password='managerpassword123')
        
        # Approve the application
        approve_url = reverse('events:approve_volunteer', kwargs={'pk': self.event.id, 'volunteer_id': vol.id})
        response = self.client.post(approve_url)
        self.assertRedirects(response, reverse('events:manage_volunteers', kwargs={'pk': self.event.id}))
        
        vol.refresh_from_db()
        self.assertEqual(vol.status, EventVolunteer.Status.APPROVED)
        self.assertEqual(vol.approved_by, self.manager)
        
        # Reject/revoke the volunteer
        reject_url = reverse('events:reject_volunteer', kwargs={'pk': self.event.id, 'volunteer_id': vol.id})
        response = self.client.post(reject_url)
        self.assertRedirects(response, reverse('events:manage_volunteers', kwargs={'pk': self.event.id}))
        
        vol.refresh_from_db()
        self.assertEqual(vol.status, EventVolunteer.Status.REJECTED)

    def test_volunteer_scanner_permission_transition(self):
        """Approved volunteers get access to volunteer_scanner, pending/rejected are denied."""
        vol = EventVolunteer.objects.create(
            event=self.event,
            user=self.student1,
            status=EventVolunteer.Status.PENDING
        )
        
        scanner_url = reverse('attendance:volunteer_scanner', kwargs={'event_id': self.event.id})
        
        # Logged in as student1 (PENDING volunteer)
        self.client.login(email='student1@example.com', password='studentpassword123')
        response = self.client.get(scanner_url)
        self.assertRedirects(response, reverse('events:event_detail', kwargs={'pk': self.event.id}))
        
        # Approve student1
        vol.status = EventVolunteer.Status.APPROVED
        vol.save()
        
        # Logged in as student1 (APPROVED volunteer)
        response = self.client.get(scanner_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'attendance/scanner.html')
        
        # Reject student1
        vol.status = EventVolunteer.Status.REJECTED
        vol.save()
        
        # Logged in as student1 (REJECTED volunteer)
        response = self.client.get(scanner_url)
        self.assertRedirects(response, reverse('events:event_detail', kwargs={'pk': self.event.id}))


class ExportRosterTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Test Org', slug='test-org')
        
        self.owner = User.objects.create_user(
            email='mayurtheprogrammer12@gmail.com',
            password='ownerpassword123',
            first_name='Mayur',
            last_name='Kharat'
        )
        self.owner.is_superuser = True
        self.owner.is_staff = True
        self.owner.role = User.Role.SUPER_ADMIN
        self.owner.save()
        
        self.event = Event.objects.create(
            organization=self.org,
            created_by=self.owner,
            title='Annual Hackathon',
            slug='annual-hackathon',
            description='Code all night!',
            start_datetime=timezone.now() + timezone.timedelta(days=1),
            end_datetime=timezone.now() + timezone.timedelta(days=1, hours=10),
            status=Event.Status.PUBLISHED
        )
        
        # Create a dynamic form field
        self.custom_field = RegistrationForm.objects.create(
            event=self.event,
            label='T-Shirt Size',
            field_name='tshirt_size',
            field_type=RegistrationForm.FieldType.SELECT,
            options='S,M,L,XL',
            is_required=True,
            order=1
        )
        
        # Create a student with filled details and dynamic response
        self.student = User.objects.create_user(
            email='student@example.com',
            password='studentpassword123',
            first_name='Alice',
            last_name='Smith',
            phone='9999999999',
            institution='MIT',
            department='EECS',
            year_of_study='3rd'
        )
        
        self.registration = Registration.objects.create(
            event=self.event,
            user=self.student,
            status=Registration.Status.CONFIRMED,
            custom_data={'tshirt_size': 'XL'}
        )

    def test_export_roster_get_dashboard(self):
        """Event manager loading the export url via GET is presented with the customization dashboard and live preview payload."""
        self.client.login(email='mayurtheprogrammer12@gmail.com', password='ownerpassword123')
        url = reverse('events:event_export', kwargs={'pk': self.event.id})
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'events/export.html')
        self.assertIn('event', response.context)
        self.assertIn('field_groups', response.context)
        self.assertIn('custom_fields', response.context)
        self.assertIn('preview_data_json', response.context)
        
        # Check preview data payload contains Alice Smith and her custom field answer
        import json
        preview_data = json.loads(response.context['preview_data_json'])
        self.assertEqual(len(preview_data), 1)
        self.assertEqual(preview_data[0]['first_name'], 'Alice')
        self.assertEqual(preview_data[0]['custom_tshirt_size'], 'XL')

    def test_export_roster_csv_custom_fields(self):
        """Requesting CSV download with custom fields format returns exactly specified columns and rows."""
        self.client.login(email='mayurtheprogrammer12@gmail.com', password='ownerpassword123')
        
        # Request standard + custom field columns
        url = reverse('events:event_export', kwargs={'pk': self.event.id})
        response = self.client.get(url, {
            'format': 'csv',
            'fields': 'first_name,email,institution,custom_tshirt_size,status'
        })
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('attachment', response['Content-Disposition'])
        
        # Parse CSV output
        import csv
        content = response.content.decode('utf-8')
        lines = content.splitlines()
        reader = list(csv.reader(lines))
        
        # Assert Header row
        self.assertEqual(len(reader), 2)  # Header + 1 record
        header = reader[0]
        self.assertEqual(header, ['First Name', 'Email Address', 'Institution / College', 'T-Shirt Size', 'Registration Status'])
        
        # Assert Data row
        data_row = reader[1]
        self.assertEqual(data_row, ['Alice', 'student@example.com', 'MIT', 'XL', 'Confirmed'])


class EventCoordinatorTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='GDGC Org', slug='gdgc-org')
        
        self.owner = User.objects.create_user(
            email='mayurtheprogrammer12@gmail.com',
            password='ownerpassword123',
            first_name='Mayur',
            last_name='Kharat'
        )
        self.owner.is_superuser = True
        self.owner.is_staff = True
        self.owner.role = User.Role.SUPER_ADMIN
        self.owner.save()
        
        self.coordinator_user = User.objects.create_user(
            email='coordinator@example.com',
            password='coordpassword123',
            first_name='John',
            last_name='Doe'
        )
        
        self.student = User.objects.create_user(
            email='student@example.com',
            password='studentpassword123',
            first_name='Alice',
            last_name='Smith'
        )
        
        self.event = Event.objects.create(
            organization=self.org,
            created_by=self.owner,
            title='GDGC Tech Fest 2026',
            slug='gdgc-tech-fest',
            description='Tech Fest by GDGC',
            start_datetime=timezone.now() + timezone.timedelta(days=1),
            end_datetime=timezone.now() + timezone.timedelta(days=1, hours=10),
            status=Event.Status.PUBLISHED
        )

    def test_manage_coordinators_permission_restricted(self):
        """Standard student should not be able to manage coordinators."""
        self.client.login(email='student@example.com', password='studentpassword123')
        url = reverse('events:manage_coordinators', kwargs={'pk': self.event.id})
        response = self.client.get(url)
        self.assertRedirects(response, reverse('events:event_detail', kwargs={'pk': self.event.id}))

    def test_manage_coordinators_permission_granted(self):
        """Owner/Superadmin can view the manage coordinators dashboard."""
        self.client.login(email='mayurtheprogrammer12@gmail.com', password='ownerpassword123')
        url = reverse('events:manage_coordinators', kwargs={'pk': self.event.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'events/coordinators.html')

    def test_add_coordinator_success(self):
        """Owner can successfully appoint a coordinator to the event."""
        self.client.login(email='mayurtheprogrammer12@gmail.com', password='ownerpassword123')
        url = reverse('events:manage_coordinators', kwargs={'pk': self.event.id})
        
        response = self.client.post(url, {
            'email': 'coordinator@example.com',
            'can_scan_attendance': 'on',
            'can_issue_certificates': 'on'
        })
        self.assertRedirects(response, url)
        
        from events.models import EventManager
        # Verify EventManager record is created
        manager = EventManager.objects.get(event=self.event, user=self.coordinator_user)
        self.assertTrue(manager.can_scan_attendance)
        self.assertTrue(manager.can_issue_certificates)

    def test_remove_coordinator_success(self):
        """Owner can successfully revoke a coordinator's permissions."""
        from events.models import EventManager
        manager = EventManager.objects.create(
            event=self.event,
            user=self.coordinator_user,
            can_scan_attendance=True,
            can_issue_certificates=True
        )
        
        self.client.login(email='mayurtheprogrammer12@gmail.com', password='ownerpassword123')
        remove_url = reverse('events:remove_coordinator', kwargs={'pk': self.event.id, 'coordinator_id': manager.id})
        
        response = self.client.post(remove_url)
        self.assertRedirects(response, reverse('events:manage_coordinators', kwargs={'pk': self.event.id}))
        
        self.assertFalse(EventManager.objects.filter(event=self.event, user=self.coordinator_user).exists())
