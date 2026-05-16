"""Pull Google Calendar events from a given time window."""

import base64
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def get_service():
    creds = None
    token_env = os.getenv("GOOGLE_OAUTH_TOKEN_JSON")

    if token_env:
        info = json.loads(base64.b64decode(token_env))
        creds = Credentials.from_authorized_user_info(info, SCOPES)
    elif Path("token.json").exists():
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif Path("credentials.json").exists():
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
            Path("token.json").write_text(creds.to_json())
        else:
            raise RuntimeError("No credentials. See docs/setup.md")

    return build("calendar", "v3", credentials=creds)


def pull_calendar_activity(
    start: datetime,
    end: datetime,
    ignore_patterns: List[str] = None,
) -> List[Dict]:
    svc = get_service()
    ignore_patterns = ignore_patterns or []

    events = svc.events().list(
        calendarId="primary",
        timeMin=start.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute().get("items", [])

    items: List[Dict] = []
    for e in events:
        summary = e.get("summary", "(no title)")
        if any(p.lower() in summary.lower() for p in ignore_patterns):
            continue

        start_t = e["start"].get("dateTime") or e["start"].get("date")
        end_t = e["end"].get("dateTime") or e["end"].get("date")
        items.append({
            "type": "meeting",
            "summary": summary,
            "start": start_t,
            "end": end_t,
            "duration_min": _duration_min(start_t, end_t),
            "attendees": len(e.get("attendees", [])) or 1,
            "self_organized": e.get("organizer", {}).get("self", False),
            "url": e.get("htmlLink"),
        })
    return items


def _duration_min(start_str, end_str):
    try:
        s = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
        e = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
        return int((e - s).total_seconds() / 60)
    except (ValueError, AttributeError):
        return None
