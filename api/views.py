from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .serializers import *
from events.models import Event
from registrations.models import Registration
from attendance.models import Attendance
from certificates.models import Certificate
from attendance.utils import verify_attendance_token

class EventViewSet(viewsets.ModelViewSet):
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Filter by organization if user is not super_admin
        if self.request.user.is_superuser:
            return Event.objects.all()
        return Event.objects.filter(organization__memberships__user=self.request.user)

class RegistrationViewSet(viewsets.ModelViewSet):
    queryset = Registration.objects.all()
    serializer_class = RegistrationSerializer
    permission_classes = [permissions.IsAuthenticated]

class AttendanceViewSet(viewsets.ModelViewSet):
    queryset = Attendance.objects.all()
    serializer_class = AttendanceSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['post'])
    def scan(self, request):
        token = request.data.get('token')
        event_id = request.data.get('event_id')
        
        payload, error = verify_attendance_token(token)
        if error:
            return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)
            
        # Business logic for attendance check-in (already implemented in attendance.views)
        # Here we could call a service function or trigger an async task
        return Response({'success': True, 'participant': payload['reg_id']})

class CertificateViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Certificate.objects.all()
    serializer_class = CertificateSerializer
    permission_classes = [permissions.IsAuthenticated]
