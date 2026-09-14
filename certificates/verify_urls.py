from django.urls import path
from . import verify_views

app_name = 'verify'

urlpatterns = [
    path('<str:certificate_id>/', verify_views.verify_certificate, name='certificate'),
    path('<str:certificate_id>/image/', verify_views.certificate_image_view, name='certificate_image'),
]

