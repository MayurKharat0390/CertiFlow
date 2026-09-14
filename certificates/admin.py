from django.contrib import admin
from .models import CertificateTemplate, Certificate, VerificationLog

@admin.register(CertificateTemplate)
class CertificateTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'event', 'category', 'is_active', 'created_at')
    list_filter = ('category', 'is_active', 'event')
    search_fields = ('name', 'event__title')

@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ('certificate_id', 'registration', 'template', 'status', 'issue_date', 'is_revoked')
    list_filter = ('status', 'is_revoked', 'template__event')
    search_fields = ('certificate_id', 'registration__user__email', 'registration__user__first_name')

@admin.register(VerificationLog)
class VerificationLogAdmin(admin.ModelAdmin):
    list_display = ('certificate', 'verification_time', 'ip_address', 'is_success')
    list_filter = ('is_success',)
    search_fields = ('certificate__certificate_id', 'ip_address')
