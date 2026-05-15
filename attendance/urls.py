from django.urls import path
from . import views

app_name = 'attendance'

urlpatterns = [
    path('event/<uuid:event_id>/qr/', views.participant_qr, name='participant_qr'),
    path('event/<uuid:event_id>/scanner/', views.volunteer_scanner, name='volunteer_scanner'),
    
    # API endpoints
    path('api/token/<uuid:registration_id>/', views.get_new_token, name='get_new_token'),
    path('api/process-scan/', views.process_scan, name='process_scan'),
]
