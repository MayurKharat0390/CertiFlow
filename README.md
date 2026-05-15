# CertiFlow - Campus Event Management & Certificate Automation

CertiFlow is a production-ready, multi-tenant platform designed for educational institutions to manage events, track attendance using dynamic QR codes, and automate certificate generation and delivery.

## Key Features

- **Multi-Tenant Architecture**: Support for multiple organizations with data isolation.
- **Event Lifecycle Management**: Create, publish, and manage campus events with capacity limits.
- **Dynamic QR Attendance**: Security-focused QR codes that refresh every 20 seconds using HMAC-signed tokens to prevent duplication and spoofing.
- **Volunteer Scanner**: Mobile-friendly scanning interface for real-time attendance validation.
- **Automated Certificates**: Generate personalized PDF certificates with unique IDs and verification QR codes.
- **Verification Portal**: Public-facing portal to verify the authenticity of issued certificates.
- **Real-time Analytics**: Dashboards for tracking registrations, attendance rates, and certificate issuance.

## Tech Stack

- **Backend**: Python 3.10+, Django 4.2+, Django REST Framework
- **Database**: SQLite (Development), PostgreSQL (Production-ready)
- **Frontend**: Tailwind CSS, Vanilla JavaScript, Lucide Icons
- **PDF Generation**: ReportLab
- **QR Codes**: python-qrcode, html5-qrcode (JS)
- **Authentication**: Custom User Model, Django Allauth (Social/OAuth ready)

## Project Structure

```text
certiflow/
├── accounts/        # Custom User, Auth, Roles
├── organizations/   # Multi-tenancy, Memberships
├── events/          # Event management, categories
├── registrations/   # Participant tracking, custom forms
├── attendance/      # Dynamic QR logic, Scanners
├── certificates/    # PDF Generation, Templates, Verification
├── notifications/   # Email logs, In-app notifications
├── analytics/       # Audit logs, performance metrics
├── api/             # REST API endpoints
├── config/          # Project settings (modular)
├── templates/       # Premium UI templates
└── static/          # CSS, JS, Images
```

## Setup Instructions

### 1. Prerequisites
- Python 3.10+
- pip

### 2. Installation
```bash
# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.example` to `.env` and update the values:
```bash
cp .env.example .env
```

### 4. Database Setup
```bash
# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Create initial admin user
# (Default development credentials: admin@certiflow.com / admin123)
python manage.py createsuperuser
```

### 5. Running the Application
```bash
python manage.py runserver
```

Access the dashboard at `http://localhost:8000/dashboard/`.

## Deployment

The project is architected for seamless migration to production:
- **Database**: Change `DJANGO_SETTINGS_MODULE` to `config.settings.production` to use PostgreSQL.
- **Static Files**: Uses WhiteNoise for efficient serving of static assets.
- **Media**: Configured for local storage; easily switchable to S3/Cloudinary.
- **Tasks**: Ready for Celery/Redis integration for bulk certificate generation.

## License
MIT
