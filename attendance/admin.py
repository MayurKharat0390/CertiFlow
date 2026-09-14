from django.contrib import admin
from .models import Attendance, ScanLog, ParticipantScanRecord

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('registration', 'event', 'is_present', 'check_in_time', 'check_out_time', 'total_minutes')
    list_filter = ('is_present', 'event')
    search_fields = ('registration__user__email', 'registration__user__first_name', 'registration__user__last_name', 'event__title')

@admin.register(ScanLog)
class ScanLogAdmin(admin.ModelAdmin):
    list_display = ('attendance', 'scanned_by', 'scan_type', 'scan_time', 'action_performed', 'is_flagged')
    list_filter = ('scan_type', 'is_flagged', 'scan_flag')
    search_fields = ('attendance__registration__user__email', 'scanned_by__email')

@admin.register(ParticipantScanRecord)
class ParticipantScanRecordAdmin(admin.ModelAdmin):
    list_display = ('registration', 'event', 'scan_time', 'window_number', 'is_accepted', 'is_flagged')
    list_filter = ('is_accepted', 'is_flagged', 'scan_flag')
    search_fields = ('registration__user__email', 'event__title')
