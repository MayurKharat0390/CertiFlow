"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/wsgi/
"""

import os
from pathlib import Path

# Default to production on Render, otherwise config.settings
if os.getenv('RENDER'):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
else:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Ensure staticfiles directory exists so WhiteNoise doesn't warn
BASE_DIR = Path(__file__).resolve().parent.parent
(BASE_DIR / 'staticfiles').mkdir(exist_ok=True)

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()

# Auto-run migrations on Render / production container startup
if os.getenv('RENDER') or os.getenv('AUTO_MIGRATE', 'false').lower() == 'true':
    try:
        from django.core.management import call_command
        call_command('migrate', interactive=False)

        # Create initial admin if no superuser exists yet
        from django.contrib.auth import get_user_model
        User = get_user_model()
        admin_email = os.getenv('ADMIN_EMAIL', 'admin@certiflow.com')
        admin_password = os.getenv('ADMIN_PASSWORD', 'Admin@12345')
        if not User.objects.filter(is_superuser=True).exists() and not User.objects.filter(email=admin_email).exists():
            User.objects.create_superuser(
                email=admin_email,
                password=admin_password,
                first_name='Admin',
                last_name='CertiFlow'
            )
    except Exception as e:
        import logging
        logging.getLogger('django').warning(f"Auto startup setup: {e}")
