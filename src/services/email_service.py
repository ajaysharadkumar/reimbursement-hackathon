import os
import base64
from email.mime.text import MIMEText

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src import config


def _get_email_body(msg_payload):
    """Recursively searches payload parts for the plain text body."""
    if 'parts' in msg_payload:
        for part in msg_payload['parts']:
            if part['mimeType'] == 'text/plain':
                if 'data' in part['body']:
                    data = part['body']['data']
                    return base64.urlsafe_b64decode(data.encode('UTF-8')).decode('UTF-8')
            elif 'parts' in part:
                # Recursive call for nested multipart
                body = _get_email_body(part)
                if body:
                    return body
    elif msg_payload['mimeType'] == 'text/plain':
        if 'data' in msg_payload['body']:
            data = msg_payload['body']['data']
            return base64.urlsafe_b64decode(data.encode('UTF-8')).decode('UTF-8')
    return None  # No plain text body found


def get_gmail_service():
    """Authenticates and returns a Gmail API service object."""
    creds = None
    if os.path.exists(config.TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(config.TOKEN_FILE, config.GMAIL_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(config.CREDENTIALS_FILE, config.GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(config.TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def read_unread_emails():
    """Reads the first unread email from Gmail and extracts receipt attachments."""
    try:
        service = get_gmail_service()
        query = f'is:unread to:{config.TARGET_EMAIL}'
        results = service.users().messages().list(userId="me", q=query).execute()
        messages = results.get("messages", [])

        if not messages:
            return None

        msg_id = messages[0]["id"]
        msg = service.users().messages().get(userId="me", id=msg_id).execute()

        sender_email = ""
        for header in msg['payload']['headers']:
            if header['name'].lower() == 'from':
                sender_email = header['value']
                break

        email_content = _get_email_body(msg['payload'])
        if not email_content:
            print("Warning: Could not extract plain text body from email.")
            email_content = msg.get("snippet", "")  # Fallback to snippet

        for part in msg["payload"]["parts"]:
            if part.get("filename"):
                if "data" in part["body"]:
                    data = part["body"]["data"]
                else:
                    att_id = part["body"]["attachmentId"]
                    att = service.users().messages().attachments().get(
                        userId="me", messageId=msg_id, id=att_id
                    ).execute()
                    data = att["data"]

                file_data = base64.urlsafe_b64decode(data.encode("UTF-8"))

                if not os.path.exists(config.RECEIPT_DIR):
                    os.makedirs(config.RECEIPT_DIR)

                path = os.path.join(config.RECEIPT_DIR, part["filename"])
                with open(path, "wb") as f:
                    f.write(file_data)

                service.users().messages().modify(
                    userId="me", id=msg_id, body={'removeLabelIds': ['UNREAD']}
                ).execute()

                return {
                    "receipt_path": path,
                    "sender_email": sender_email,
                    "email_content": email_content
                }
        return None

    except HttpError as error:
        print(f"An error occurred: {error}")
        return None


def send_email(recipient_email, subject, body):
    """Sends an email using the Gmail API."""
    try:
        service = get_gmail_service()
        message = MIMEText(body)
        message['to'] = recipient_email
        message['subject'] = subject
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

        service.users().messages().send(
            userId='me',
            body={'raw': raw_message}
        ).execute()
        print(f"Email sent successfully to {recipient_email}")
    except HttpError as error:
        print(f"Failed to send email. Error: {error}")