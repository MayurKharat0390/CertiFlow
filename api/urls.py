from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'events', views.EventViewSet)
router.register(r'registrations', views.RegistrationViewSet)
router.register(r'attendance', views.AttendanceViewSet)
router.register(r'certificates', views.CertificateViewSet)

app_name = 'api'

urlpatterns = [
    path('', include(router.urls)),
]
