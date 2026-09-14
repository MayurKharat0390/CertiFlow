"""
Views for connecting and managing Google OAuth 2.0 Gmail account in CertiFlow.
"""
import logging
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from accounts.gmail_service import get_authorization_url, exchange_code_and_save_credentials
from accounts.models import UserGmailCredentials

logger = logging.getLogger('certiflow')

@login_required
def gmail_connect(request):
    """
    Initiates Google OAuth 2.0 consent flow.
    Redirects organizer to Google authorization URL.
    """
    redirect_uri = request.build_absolute_uri(reverse('accounts:gmail_callback'))
    # In local development if using 127.0.0.1, ensure URI matches registered redirect URI exactly
    if 'localhost' in redirect_uri:
        redirect_uri = redirect_uri.replace('localhost', '127.0.0.1')

    try:
        auth_url, state = get_authorization_url(redirect_uri)
        request.session['gmail_oauth_state'] = state
        request.session['gmail_oauth_next'] = request.META.get('HTTP_REFERER', reverse('accounts:profile'))
        return redirect(auth_url)
    except Exception as e:
        logger.error(f"Failed to generate Google OAuth URL: {str(e)}")
        messages.error(request, f"Could not connect to Google: {str(e)}")
        return redirect('accounts:profile')


@login_required
def gmail_callback(request):
    """
    Handles redirect callback from Google OAuth 2.0.
    Exchanges code for tokens and saves to UserGmailCredentials.
    """
    code = request.GET.get('code')
    error = request.GET.get('error')
    next_url = request.session.pop('gmail_oauth_next', reverse('accounts:profile'))

    if error:
        messages.error(request, f"Google authorization was cancelled or failed: {error}")
        return redirect(next_url)

    if not code:
        messages.error(request, "Invalid response from Google (no authorization code received).")
        return redirect(next_url)

    redirect_uri = request.build_absolute_uri(reverse('accounts:gmail_callback'))
    if 'localhost' in redirect_uri:
        redirect_uri = redirect_uri.replace('localhost', '127.0.0.1')

    try:
        gmail_cred = exchange_code_and_save_credentials(request.user, code, redirect_uri)
        messages.success(request, f"Successfully connected your Gmail account ({gmail_cred.gmail_address})! Your certificates and passes will now be sent directly from your Gmail.")
    except Exception as e:
        logger.error(f"OAuth code exchange failed: {str(e)}")
        messages.error(request, f"Failed to complete Google authentication: {str(e)}")

    return redirect(next_url)


@login_required
def gmail_disconnect(request):
    """
    Disconnects and removes stored Gmail credentials for the current user.
    """
    next_url = request.META.get('HTTP_REFERER', reverse('accounts:profile'))
    try:
        cred = UserGmailCredentials.objects.get(user=request.user)
        email_addr = cred.gmail_address
        cred.delete()
        messages.success(request, f"Disconnected Gmail account ({email_addr}). Emails will now send via default mail server.")
    except UserGmailCredentials.DoesNotExist:
        messages.info(request, "No connected Gmail account found.")

    return redirect(next_url)
