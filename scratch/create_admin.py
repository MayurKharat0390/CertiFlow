import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from accounts.models import User

if not User.objects.filter(email='admin@certiflow.com').exists():
    User.objects.create_superuser('admin@certiflow.com', 'admin123', first_name='Admin', last_name='User')
    print("Superuser created successfully")
else:
    print("Superuser already exists")
