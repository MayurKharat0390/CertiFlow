import os
import django
from datetime import timedelta
from django.utils import timezone

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from accounts.models import User
from organizations.models import Organization, Membership
from events.models import Event, CertificateCategory
from registrations.models import Registration
from attendance.models import Attendance, ScanLog
from certificates.models import CertificateTemplate, Certificate

def create_full_demo_data():
    # 1. Create Organization
    org, _ = Organization.objects.get_or_create(
        slug='tech-institute',
        defaults={
            'name': 'Tech Institute of Excellence',
            'description': 'A premier campus for innovation and technology demo.'
        }
    )

    # 2. Ensure Users
    admin_email = 'admin@certiflow.com'
    admin, created = User.objects.get_or_create(
        email=admin_email,
        defaults={
            'first_name': 'Super',
            'last_name': 'Admin',
            'role': User.Role.SUPER_ADMIN,
            'is_staff': True,
            'is_superuser': True
        }
    )
    if created:
        admin.set_password('admin123')
        admin.save()
    Membership.objects.get_or_create(user=admin, organization=org, defaults={'role': Membership.Role.ADMIN})

    manager, created = User.objects.get_or_create(
        email='manager@certiflow.com',
        defaults={'first_name': 'Event', 'last_name': 'Manager', 'role': User.Role.EVENT_MANAGER}
    )
    if created:
        manager.set_password('manager123')
        manager.save()
    Membership.objects.get_or_create(user=manager, organization=org, defaults={'role': Membership.Role.EVENT_MANAGER})

    volunteer, created = User.objects.get_or_create(
        email='volunteer@certiflow.com',
        defaults={'first_name': 'Campus', 'last_name': 'Volunteer', 'role': User.Role.VOLUNTEER}
    )
    if created:
        volunteer.set_password('volunteer123')
        volunteer.save()
    Membership.objects.get_or_create(user=volunteer, organization=org, defaults={'role': Membership.Role.VOLUNTEER})

    # 3. Create an Event
    start_time = timezone.now() + timedelta(days=2)
    event, created = Event.objects.get_or_create(
        slug='annual-tech-summit-2026',
        defaults={
            'organization': org,
            'created_by': manager,
            'title': 'Annual Tech Summit 2026',
            'description': 'The biggest tech gathering on campus. Join us for keynote sessions, workshops, and networking.',
            'event_type': 'conference',
            'venue_name': 'Main Auditorium',
            'venue_address': 'Building 4, Sector A',
            'start_datetime': start_time,
            'end_datetime': start_time + timedelta(hours=6),
            'attendance_start': timezone.now() - timedelta(hours=1),
            'attendance_end': timezone.now() + timedelta(hours=24),
            'registration_deadline': start_time - timedelta(days=1),
            'max_capacity': 100,
            'status': 'published',
            'certificate_eligible_all': True
        }
    )

    # 4. Create Certificate Category
    category, _ = CertificateCategory.objects.get_or_create(
        event=event,
        name='Participation',
        defaults={'description': 'General participation certificate', 'is_default': True}
    )

    # 5. Create Certificate Template
    template, _ = CertificateTemplate.objects.get_or_create(
        event=event,
        category=category,
        name='Default Participation Template',
        defaults={
            'layout_config': {
                "fields": [
                    {"type": "participant_name", "x": 500, "y": 500, "font": "Helvetica-Bold", "size": 48, "align": "center", "color": "#1e1b4b"},
                    {"type": "event_name", "x": 500, "y": 400, "font": "Helvetica", "size": 24, "align": "center", "color": "#4338ca"}
                ]
            }
        }
    )

    # 6. Create Dummy Participants & Registrations
    students_data = [
        ('alice@example.com', 'Alice', 'Johnson'),
        ('bob@example.com', 'Bob', 'Smith'),
        ('charlie@example.com', 'Charlie', 'Davis'),
        ('diana@example.com', 'Diana', 'Prince'),
        ('ethan@example.com', 'Ethan', 'Hunt'),
    ]

    for email, fname, lname in students_data:
        student, created = User.objects.get_or_create(
            email=email,
            defaults={'first_name': fname, 'last_name': lname, 'role': User.Role.PARTICIPANT}
        )
        if created:
            student.set_password('student123')
            student.save()
            Membership.objects.get_or_create(user=student, organization=org)

        # Register them
        reg, r_created = Registration.objects.get_or_create(
            event=event,
            user=student,
            defaults={'status': Registration.Status.CONFIRMED, 'is_eligible_for_certificate': True}
        )
        
        # Force a pending certificate for each
        Certificate.objects.get_or_create(
            registration=reg,
            template=template,
            defaults={'status': Certificate.Status.PENDING, 'issued_by': manager}
        )
        
        if r_created and email in ['alice@example.com', 'bob@example.com']:
            # Simulate attendance for Alice and Bob
            att, _ = Attendance.objects.get_or_create(
                registration=reg,
                defaults={'event': event, 'check_in_time': timezone.now(), 'is_present': True}
            )
            ScanLog.objects.create(
                attendance=att, 
                scan_type=ScanLog.ScanType.CHECK_IN,
                scanned_by=volunteer,
                token_used='DEMO_TOKEN_123'
            )

    print(f"Demo Data Setup Complete:")
    print(f"- Organization: {org.name}")
    print(f"- Event: {event.title}")
    print(f"- Registrations: 5 students")
    print(f"- Pending Certificates: 5 created")
    print(f"- Simulation: Attendance recorded for 2 students")

if __name__ == "__main__":
    create_full_demo_data()
