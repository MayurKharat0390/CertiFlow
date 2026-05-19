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
]
