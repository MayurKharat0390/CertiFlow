from django.urls import path
from . import views

app_name = 'registrations'

urlpatterns = [
    path('browse/', views.public_event_list, name='public_list'),

    # Smart registration wizard (replaces old register_confirm)
    path('register/<uuid:event_id>/', views.smart_register, name='register'),

    # JSON schema endpoint used by the wizard JS
    path('register/<uuid:event_id>/schema/', views.get_form_schema, name='form_schema'),
]
