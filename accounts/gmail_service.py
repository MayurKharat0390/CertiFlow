"""
Google OAuth 2.0 and Gmail API integration service for CertiFlow.
Allows event organizers to connect their personal or organization Gmail account
with 1 click and send emails/certificates directly from their account.
"""
import base64
import json
import logging
import mimetypes
import os
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders

from django.conf import settings
from django.utils import timezone
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from accounts.models import User, UserGmailCredentials

logger = logging.getLogger('certiflow')

# Scopes required: Send email, view email address, openid profile
GMAIL_SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/userinfo.email',
    'openid',
]

def get_client_config():
    """Returns Google client config dict from settings."""
    client_id = getattr(settings, 'GOOGLE_CLIENT_ID', '')
    client_secret = getattr(settings, 'GOOGLE_CLIENT_SECRET', '')
    if not client_id or not client_secret:
        raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be configured in settings.")
    
    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        }
    }


def create_oauth_flow(redirect_uri, state=None):
    """Creates a google_auth_oauthlib Flow instance."""
    config = get_client_config()
    flow = Flow.from_client_config(
        config,
        scopes=GMAIL_SCOPES,
        redirect_uri=redirect_uri,
        state=state
    )
    return flow


def get_authorization_url(redirect_uri):
    """
    Generates the Google OAuth authorization URL and state token.
    Forces offline access to ensure we get a refresh_token.
    """
    flow = create_oauth_flow(redirect_uri)
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    return authorization_url, state


def exchange_code_and_save_credentials(user, code, redirect_uri):
    """
    Exchanges authorization code for credentials and saves to UserGmailCredentials.
    """
    flow = create_oauth_flow(redirect_uri)
    flow.fetch_token(code=code)
    creds = flow.credentials

    # Fetch user's Gmail address from userinfo endpoint
    userinfo_service = build('oauth2', 'v2', credentials=creds)
    user_info = userinfo_service.userinfo().get().execute()
    gmail_address = user_info.get('email', '')

    if not gmail_address:
        raise ValueError("Could not retrieve email address from Google account.")

    # Save or update UserGmailCredentials
    gmail_cred, created = UserGmailCredentials.objects.update_or_create(
        user=user,
        defaults={
            'gmail_address': gmail_address,
            'refresh_token': creds.refresh_token or '',
            'access_token': creds.token or '',
            'token_expiry': creds.expiry,
            'is_active': True,
        }
    )

    if not creds.refresh_token and not created:
        logger.info(f"Preserved existing refresh token for {user.email}")

    logger.info(f"Successfully connected Gmail {gmail_address} for user {user.email}")
    return gmail_cred


def get_gmail_service_for_user(user):
    """
    Builds and returns an authorized Google API Gmail service client for the user.
    Automatically refreshes access token if expired using the stored refresh_token.
    """
    try:
        cred_model = user.gmail_credentials
    except (UserGmailCredentials.DoesNotExist, AttributeError):
        return None

    if not cred_model or not cred_model.is_active or not cred_model.refresh_token:
        return None

    client_id = getattr(settings, 'GOOGLE_CLIENT_ID', '')
    client_secret = getattr(settings, 'GOOGLE_CLIENT_SECRET', '')

    creds = Credentials(
        token=cred_model.access_token,
        refresh_token=cred_model.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=GMAIL_SCOPES
    )

    service = build('gmail', 'v1', credentials=creds)
    return service, cred_model.gmail_address


def send_email_via_gmail_api(sender_user, email_log):
    """
    Sends an EmailLog instance using the sender_user's connected Gmail API account.
    Returns True if sent successfully, False otherwise.
    """
    result = get_gmail_service_for_user(sender_user)
    if not result:
        return False

    service, sender_gmail = result

    try:
        message = MIMEMultipart('mixed')
        message['To'] = email_log.recipient_email
        org_name = email_log.organization.name if email_log.organization else 'CertiFlow'
        message['From'] = f"{org_name} <{sender_gmail}>"
        message['Subject'] = email_log.subject

        msg_alternative = MIMEMultipart('alternative')
        if email_log.body_text:
            msg_alternative.attach(MIMEText(email_log.body_text, 'plain', 'utf-8'))
        if email_log.body_html:
            msg_alternative.attach(MIMEText(email_log.body_html, 'html', 'utf-8'))
        elif email_log.body_text:
            msg_alternative.attach(MIMEText(f"<pre style='font-family:sans-serif;'>{email_log.body_text}</pre>", 'html', 'utf-8'))

        message.attach(msg_alternative)

        if email_log.attachment and email_log.attachment.name:
            file_path = email_log.attachment.path
            if os.path.exists(file_path):
                content_type, encoding = mimetypes.guess_type(file_path)
                if content_type is None or encoding is not None:
                    content_type = 'application/octet-stream'
                main_type, sub_type = content_type.split('/', 1)

                with open(file_path, 'rb') as f:
                    part = MIMEBase(main_type, sub_type)
                    part.set_payload(f.read())

                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename="{os.path.basename(file_path)}"')
                message.attach(part)

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

        sent_response = service.users().messages().send(
            userId='me',
            body={'raw': raw_message}
        ).execute()

        email_log.status = email_log.Status.SENT
        email_log.sent_at = timezone.now()
        email_log.error_message = f"Sent via Gmail API (Message ID: {sent_response.get('id', '')})"
        email_log.save()

        logger.info(f"SUCCESS: Sent email via Gmail API from {sender_gmail} to {email_log.recipient_email}")
        return True

    except Exception as e:
        logger.error(f"Gmail API send failed for {email_log.recipient_email}: {str(e)}")
        email_log.error_message = f"Gmail API error: {str(e)}"
        email_log.save()
        return False
