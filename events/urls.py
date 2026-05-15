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
    path('<uuid:pk>/reset-certificates/', views.reset_event_certificates, name='reset_certificates'),
    path('<uuid:pk>/import-participants/', views.import_participants, name='import_participants'),
]
