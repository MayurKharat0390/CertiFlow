"""
CertiFlow URL Configuration
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),

    # Redirect root to dashboard
    path('', RedirectView.as_view(url='/dashboard/', permanent=False)),

    # Authentication
    path('accounts/', include('accounts.urls')),
    path('accounts/', include('allauth.urls')),

    # Main Application
    path('dashboard/', include('events.urls')),
    path('organizations/', include('organizations.urls')),
    path('registrations/', include('registrations.urls')),
    path('attendance/', include('attendance.urls')),
    path('certificates/', include('certificates.urls')),
    path('analytics/', include('analytics.urls')),
    path('notifications/', include('notifications.urls')),

    # Public verification portal (no auth required)
    path('verify/', include('certificates.verify_urls')),

    # REST API
    path('api/v1/', include('api.urls')),
    path('api-auth/', include('rest_framework.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Custom admin site branding
admin.site.site_header = 'CertiFlow Administration'
admin.site.site_title = 'CertiFlow Admin'
admin.site.index_title = 'Campus Event Management Platform'
