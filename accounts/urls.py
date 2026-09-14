from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from . import gmail_views

app_name = 'accounts'

urlpatterns = [
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='accounts:login'), name='logout'),
    path('profile/', views.profile_view, name='profile'),

    # Google OAuth 2.0 Gmail Connection Endpoints
    path('google/gmail/connect/', gmail_views.gmail_connect, name='gmail_connect'),
    path('google/gmail/callback/', gmail_views.gmail_callback, name='gmail_callback'),
    path('google/gmail/disconnect/', gmail_views.gmail_disconnect, name='gmail_disconnect'),
]

