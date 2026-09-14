"""
CertiFlow Production Settings
Uses PostgreSQL - ready for scale
"""
from .base import *
from decouple import config

import dj_database_url

DEBUG = False

# Allowed hosts for production
allowed_hosts_env = config('ALLOWED_HOSTS', default='*')
if allowed_hosts_env == '*':
    ALLOWED_HOSTS = ['*']
else:
    ALLOWED_HOSTS = [h.strip() for h in allowed_hosts_env.split(',') if h.strip()]

# Production Database - PostgreSQL (fallback to SQLite if DATABASE_URL not yet configured)
database_url = config('DATABASE_URL', default='')
if database_url:
    DATABASES = {
        'default': dj_database_url.config(
            default=database_url,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Security settings for production
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

SESSION_COOKIE_SECURE = True
import os

csrf_trusted = config('CSRF_TRUSTED_ORIGINS', default='')
if csrf_trusted:
    CSRF_TRUSTED_ORIGINS = [s.strip() for s in csrf_trusted.split(',') if s.strip()]
else:
    CSRF_TRUSTED_ORIGINS = ['https://*.onrender.com']

# Cache (Redis if REDIS_URL provided, else in-memory cache)
redis_url = config('REDIS_URL', default='')
if redis_url:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': redis_url,
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    }

# Static files served by CDN/WhiteNoise
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Email (production SMTP)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='CertiFlow <noreply@certiflow.com>')

# Ensure logs directory exists
os.makedirs(BASE_DIR / 'logs', exist_ok=True)

# Logging to file in production
LOGGING['handlers']['file'] = {
    'class': 'logging.handlers.RotatingFileHandler',
    'filename': BASE_DIR / 'logs' / 'certiflow.log',
    'maxBytes': 10 * 1024 * 1024,  # 10 MB
    'backupCount': 5,
    'formatter': 'verbose',
}
LOGGING['root']['handlers'] = ['console', 'file']
