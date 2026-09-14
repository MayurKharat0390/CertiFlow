from django.contrib import admin
from .models import Registration, RegistrationForm

@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ('user', 'event', 'status', 'participant_id', 'is_eligible_for_certificate', 'registration_date')
    list_filter = ('status', 'is_eligible_for_certificate', 'event')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'participant_id')

@admin.register(RegistrationForm)
class RegistrationFormAdmin(admin.ModelAdmin):
    list_display = ('label', 'field_name', 'field_type', 'event', 'is_required', 'order')
    list_filter = ('field_type', 'is_required', 'event')
    search_fields = ('label', 'field_name', 'event__title')
