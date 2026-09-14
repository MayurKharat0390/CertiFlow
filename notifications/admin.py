from django.contrib import admin
from .models import EmailLog, Notification

@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ('subject', 'recipient_email', 'status', 'email_type', 'sent_at')
    list_filter = ('status', 'email_type', 'organization')
    search_fields = ('subject', 'recipient_email', 'body_text')
    ordering = ('-sent_at',)

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'is_read', 'created_at')
    list_filter = ('is_read',)
    search_fields = ('title', 'message', 'user__email')
    ordering = ('-created_at',)
