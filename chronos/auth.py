"""OAuth2 authentication for Google Calendar API."""

import os
import json
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

TOKEN_PATH = Path(__file__).parent.parent / "token.json"
CREDENTIALS_PATH = Path(__file__).parent.parent / "credentials.json"


def get_credentials() -> Credentials:
    """Obtain valid Google OAuth2 credentials.

    Uses stored token if available and valid, otherwise initiates
    the OAuth2 authorization flow.

    Returns:
        Valid Google OAuth2 credentials.
    """
    creds = None

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_token(creds)
    elif not creds or not creds.valid:
        if not CREDENTIALS_PATH.exists():
            _generate_credentials_file()

        flow = InstalledAppFlow.from_client_secrets_file(
            str(CREDENTIALS_PATH), SCOPES
        )
        creds = flow.run_local_server(port=0)
        _save_token(creds)

    return creds


def _save_token(creds: Credentials) -> None:
    """Persist credentials token to disk."""
    TOKEN_PATH.write_text(creds.to_json())


def _generate_credentials_file() -> None:
    """Generate credentials.json from environment variables."""
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise RuntimeError(
            "No credentials.json found and GOOGLE_CLIENT_ID / "
            "GOOGLE_CLIENT_SECRET environment variables are not set. "
            "Provide either a credentials.json file or set both env vars."
        )

    credentials_data = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    CREDENTIALS_PATH.write_text(json.dumps(credentials_data, indent=2))
