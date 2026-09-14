from django.urls import path
from . import views

app_name = 'attendance'

urlpatterns = [
    # ── Participant Pass (static identity QR) ──────────────────
    path('event/<uuid:event_id>/pass/', views.participant_pass, name='participant_pass'),
    path('event/<uuid:event_id>/qr/',  views.participant_qr,   name='participant_qr'),   # legacy redirect

    # ── Mode A — Volunteer Scans Participant ────────────────────
    path('event/<uuid:event_id>/scanner/', views.volunteer_scanner, name='volunteer_scanner'),

    # ── Mode B — Participant Scans Event QR ────────────────────
    path('event/<uuid:event_id>/room-qr/',      views.room_qr_display,       name='room_qr'),
    path('event/<uuid:event_id>/scan/',         views.participant_scan_page,  name='participant_scan'),
    path('event/<uuid:event_id>/flagged/',      views.flagged_scans_review,   name='flagged_scans'),

    # ── API endpoints ──────────────────────────────────────────
    path('api/token/<uuid:registration_id>/',   views.get_new_token,          name='get_new_token'),
    path('api/process-scan/',                   views.process_scan,           name='process_scan'),
    path('api/action/',                         views.perform_scan_action,    name='scan_action'),
    path('api/room-qr-token/<uuid:event_id>/',  views.get_room_qr_token,      name='room_qr_token'),
    path('api/participant-scan/',               views.process_participant_scan, name='process_participant_scan'),
]
