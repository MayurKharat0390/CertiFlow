from django.contrib import admin
from .models import Event, CertificateCategory, EventManager, EventVolunteer

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'organization', 'event_type', 'status', 'start_datetime', 'end_datetime')
    list_filter = ('event_type', 'status', 'organization')
    search_fields = ('title', 'slug', 'description')
    prepopulated_fields = {'slug': ('title',)}

@admin.register(CertificateCategory)
class CertificateCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'event', 'is_default')
    list_filter = ('is_default', 'event__organization')
    search_fields = ('name', 'event__title')

@admin.register(EventManager)
class EventManagerAdmin(admin.ModelAdmin):
    list_display = ('event', 'user', 'can_scan_attendance', 'can_issue_certificates', 'assigned_at')
    list_filter = ('can_scan_attendance', 'can_issue_certificates', 'event__organization')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'event__title')

@admin.register(EventVolunteer)
class EventVolunteerAdmin(admin.ModelAdmin):
    list_display = ('event', 'user', 'status', 'assigned_at')
    list_filter = ('status', 'event__organization')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'event__title')
