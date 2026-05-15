from django.urls import path
from . import views

app_name = 'registrations'

urlpatterns = [
    path('browse/', views.public_event_list, name='public_list'),
    path('register/<uuid:event_id>/', views.register_for_event, name='register'),
]
