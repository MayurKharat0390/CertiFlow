from django.urls import path
from . import views

app_name = 'certificates'

urlpatterns = [
    path('', views.certificate_list, name='certificate_list'),
    path('templates/create/', views.template_create, name='template_create'),
    path('templates/<uuid:pk>/edit/', views.template_update, name='template_update'),
    path('issue-bulk/<uuid:event_id>/', views.issue_bulk_certificates, name='issue_bulk'),
]
