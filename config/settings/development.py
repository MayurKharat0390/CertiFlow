"""
CertiFlow Development Settings
"""
from .base import *

DEBUG = True

# Development Database - SQLite
# Easy to switch to PostgreSQL by changing settings in production.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Development Email - Defaults to console, but can be overridden in .env
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')

# Allow all hosts in development
ALLOWED_HOSTS = ['*']

# Django Debug Toolbar (optional, uncomment to use)
# INSTALLED_APPS += ['debug_toolbar']
# MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']
# INTERNAL_IPS = ['127.0.0.1']

# Relax security for development
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False

# WhiteNoise in development
WHITENOISE_AUTOREFRESH = True

# Logging level for development
LOGGING['root']['level'] = 'DEBUG'
