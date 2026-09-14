from django.urls import path
from . import views

app_name = 'events'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('list/', views.event_list, name='event_list'),
    path('create/', views.event_create, name='event_create'),
    path('<uuid:pk>/', views.event_detail, name='event_detail'),
    path('<uuid:pk>/edit/', views.event_update, name='event_edit'),
    path('<uuid:pk>/export/', views.export_registrations_csv, name='event_export'),
    path('<uuid:pk>/email/', views.email_participants, name='event_email'),
    path('<uuid:event_id>/email/<uuid:reg_id>/', views.email_single_participant, name='email_single_participant'),
    path('<uuid:event_id>/remove/<uuid:reg_id>/', views.remove_participant, name='remove_participant'),
    path('<uuid:event_id>/issue-cert/<uuid:reg_id>/', views.issue_single_certificate, name='issue_single_certificate'),
    path('<uuid:pk>/reset-certificates/', views.reset_event_certificates, name='reset_certificates'),
    path('<uuid:pk>/import-participants/', views.import_participants, name='import_participants'),

    # Form Builder
    path('<uuid:pk>/form-builder/', views.form_builder, name='form_builder'),
    path('<uuid:pk>/form-builder/save/', views.save_form_schema, name='save_form_schema'),

    # Attendance mode management
    path('<uuid:pk>/attendance/toggle-window/', views.toggle_attendance_window, name='toggle_attendance_window'),

    # Volunteers management
    path('<uuid:pk>/volunteer/apply/', views.volunteer_apply, name='volunteer_apply'),
    path('<uuid:pk>/volunteers/', views.manage_volunteers, name='manage_volunteers'),
    path('<uuid:pk>/volunteers/approve/<uuid:volunteer_id>/', views.approve_volunteer, name='approve_volunteer'),
    path('<uuid:pk>/volunteers/reject/<uuid:volunteer_id>/', views.reject_volunteer, name='reject_volunteer'),

    # Coordinators management
    path('<uuid:pk>/coordinators/', views.manage_coordinators, name='manage_coordinators'),
    path('<uuid:pk>/coordinators/remove/<uuid:coordinator_id>/', views.remove_coordinator, name='remove_coordinator'),
]

