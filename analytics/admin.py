from django.contrib import admin
from .models import AuditLog, EventAnalytics

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'description', 'ip_address', 'timestamp')
    list_filter = ('action', 'organization')
    search_fields = ('description', 'user__email', 'ip_address')
    ordering = ('-timestamp',)

@admin.register(EventAnalytics)
class EventAnalyticsAdmin(admin.ModelAdmin):
    list_display = ('event_id', 'total_registrations', 'total_confirmed', 'total_attended', 'total_certificates_issued', 'attendance_rate', 'last_updated')
    ordering = ('-last_updated',)
