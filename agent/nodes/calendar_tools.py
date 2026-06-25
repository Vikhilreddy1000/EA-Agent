from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from zoneinfo import ZoneInfo
from googleapiclient.errors import HttpError
import os
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pickle
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
import pytz
import logging

logger = logging.getLogger(__name__)


    
def to_iso(dt_str):
    return datetime.strptime(dt_str, "%Y-%m-%d %H:%M").isoformat() + "+05:30"

def _ensure_iso(dt_str: str) -> str:
    """Accept either 'YYYY-MM-DD HH:MM' or an already-formed ISO string."""
    if not dt_str:
        return dt_str
    try:
        return datetime.strptime(dt_str, "%Y-%m-%d %H:%M").isoformat() + "+05:30"
    except ValueError:
        return dt_str  # already ISO — pass through unchanged


load_dotenv()
SCOPES = ["https://www.googleapis.com/auth/calendar"]
GOOGLE_CLIENT_SECRET_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE")


class GoogleCalendarService:
    def __init__(self):
        self.credentials = None
        self.token_path = 'token.pickle'
        self.service = None
        self.redirect_uri = os.getenv("OAUTH_REDIRECT_URI")
    
    def get_auth_url(self):
        """Generate and return the Google OAuth authorization URL."""
        flow = Flow.from_client_secrets_file(
            os.getenv("GOOGLE_CREDENTIALS_FILE"),
            scopes=SCOPES,
            redirect_uri=self.redirect_uri
        )

        auth_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='false',
            prompt='consent'
        )

        with open("oauth_state.txt", "w") as f:
            f.write(state)

        with open("code_verifier.txt", "w") as f:
            f.write(flow.code_verifier)

        return auth_url


    async def handle_oauth_callback(self, request: Request):
        code = request.query_params.get('code')
        state = request.query_params.get('state')

        if not code or not state:
            raise HTTPException(status_code=400, detail="Missing code or state")

        # LOAD SAVED STATE + VERIFIER
        with open("oauth_state.txt", "r") as f:
            saved_state = f.read()

        with open("code_verifier.txt", "r") as f:
            code_verifier = f.read()

        if state != saved_state:
            raise HTTPException(status_code=400, detail="Invalid state")
        try:
            # RECREATE FLOW PROPERLY
            flow = Flow.from_client_secrets_file(
                os.getenv("GOOGLE_CREDENTIALS_FILE"),
                scopes=SCOPES,
                redirect_uri=self.redirect_uri
            )

            flow.code_verifier = code_verifier

            flow.fetch_token(code=code)

            self.credentials = flow.credentials

            # SAVE TOKEN
            with open(self.token_path, "wb") as token:
                pickle.dump(self.credentials, token)

            self.service = build("calendar", "v3", credentials=self.credentials)

            return HTMLResponse("<h2>Auth successful. You can close this tab.</h2>")

        except Exception as e:
            logger.error(f"Error during token exchange: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def get_calendar_service(self):
            """Get an authenticated Google Calendar service."""
            if self.service:
                logger.info("Using existing service instance.")
                return self.service

            # Load existing credentials if available
            if os.path.exists(self.token_path):
                try:
                    with open(self.token_path, 'rb') as token:
                        self.credentials = pickle.load(token)
                except Exception as e:
                    logger.info(f"Error loading credentials: {e}")
                    if os.path.exists(self.token_path): 
                        os.remove(self.token_path)
                    return None  # Force re-authentication

            # If credentials are valid, use them
            if self.credentials and self.credentials.valid:
                logger.info("Loaded valid credentials.")
                self.service = build('calendar', 'v3', credentials=self.credentials)
                return self.service

            # If credentials are expired but refreshable, refresh them
            if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                try:
                    logger.info("Refreshing expired credentials...")
                    self.credentials.refresh(Request())
                    with open(self.token_path, 'wb') as token:
                        pickle.dump(self.credentials, token)
                    logger.info("Credentials refreshed successfully.")
                    self.service = build('calendar', 'v3', credentials=self.credentials)
                    return self.service
                except Exception as e:
                    logger.info(f"Failed to refresh credentials: {e}")
                    if os.path.exists(self.token_path):
                        os.remove(self.token_path)  # Remove invalid credentials
                    return None

            # If no valid credentials are found, require authentication
            logger.info("No valid credentials found. User must reauthenticate.")
            return None
        
    def is_authenticated(self):
        """Check if the user is authenticated"""
        return self.get_calendar_service() is not None

    def get_user_timezone(self):
        """Fetch the user's time zone from Google Calendar settings."""
        service = self.get_calendar_service()
        if not service:
            return 'UTC'  # Default to UTC if authentication fails

        try:
            settings = service.settings().get(setting='timezone').execute()
            return settings.get('value', 'UTC')
        except Exception as e:
            logger.info(f"Failed to retrieve user time zone: {e}")
            return 'UTC'
        

    def create_event(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a calendar event.

        params keys:
            title          (str)             event summary
            start          (ISO datetime)    e.g. "2025-04-10T15:00:00+05:30"
            end            (ISO datetime)    e.g. "2025-04-10T15:30:00+05:30"
            attendees      (list[str])       email addresses
            description    (str, optional)
            timezone       (str)             default "Asia/Kolkata"
            add_meet_link  (bool)            default True
        """
        service = self.get_calendar_service()
        tz = params.get("timezone", "Asia/Kolkata")

        if not service:
            raise Exception("AUTH_REQUIRED")

        attendees = params.get("attendees", [])
        if isinstance(attendees, str):
            attendees = [a.strip() for a in attendees.split(",")]

        body: Dict[str, Any] = {
            "summary":     params["title"],
            "description": params.get("description", ""),
            "start":       {"dateTime": _ensure_iso(params["start"]), "timeZone": tz},
            "end":         {"dateTime": _ensure_iso(params["end"]),  "timeZone": tz},
            "attendees":   [{"email": e} for e in attendees],
            "reminders":   {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 10},
                    {"method": "email", "minutes": 60},
                ],
            },
        }

        if params.get("add_meet_link", True):
            body["conferenceData"] = {
                "createRequest": {
                    "requestId": f"ea-{datetime.utcnow().timestamp()}",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            }

        event = service.events().insert(
            calendarId="primary",
            body=body,
            conferenceDataVersion=1,
            sendUpdates="all",
        ).execute()

        meet_link = (
            event.get("conferenceData", {})
            .get("entryPoints", [{}])[0]
            .get("uri", "")
        )
        return {
            "action":    "created",
            "event_id":  event["id"],
            "html_link": event.get("htmlLink"),
            "meet_link": meet_link,
            "title":     event.get("summary"),
            "start":     event["start"].get("dateTime"),
            "end":       event["end"].get("dateTime"),
        }


    def update_event(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing calendar event (patch — only changed fields).

        params keys:
            event_id    (str)            required
            title       (str, optional)
            start       (ISO datetime, optional)
            end         (ISO datetime, optional)
            attendees   (list[str], optional)
            description (str, optional)
            timezone    (str)            default "Asia/Kolkata"
        """
        service = self.get_calendar_service()
        if not service:
            raise Exception("AUTH_REQUIRED")
        event_id = params["event_id"]
        tz = params.get("timezone", "Asia/Kolkata")

        # Fetch current state first
        existing = service.events().get(calendarId="primary", eventId=event_id).execute()

        patch_body: Dict[str, Any] = {}
        if "title"       in params: patch_body["summary"]     = params["title"]
        if "description" in params: patch_body["description"] = params["description"]
        if "start"       in params: patch_body["start"]       = {"dateTime": _ensure_iso(params["start"]), "timeZone": tz}
        if "end"         in params: patch_body["end"]         = {"dateTime": _ensure_iso(params["end"]),   "timeZone": tz}
        if "attendees"   in params:
            attendees = params["attendees"]

            # 🔥 FIX: normalize string → list
            if isinstance(attendees, str):
                attendees = [a.strip() for a in attendees.split(",") if a.strip()]

            patch_body["attendees"] = [{"email": e} for e in attendees]
            # patch_body["attendees"] = [{"email": e} for e in params["attendees"]]

        updated = service.events().patch(
            calendarId="primary",
            eventId=event_id,
            body=patch_body,
            sendUpdates="all",
        ).execute()

        return {
            "action":    "updated",
            "event_id":  updated["id"],
            "html_link": updated.get("htmlLink"),
            "title":     updated.get("summary"),
            "start":     updated["start"].get("dateTime"),
            "end":       updated["end"].get("dateTime"),
            "changes":   list(patch_body.keys()),
        }


    def delete_event(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Delete (cancel) a calendar event and notify attendees.

        params keys:
            event_id  (str)   required
        """
        service = self.get_calendar_service()
        if not service:
            raise Exception("AUTH_REQUIRED")
        event_id = params["event_id"]

        # Fetch title before deleting for confirmation message
        try:
            event = service.events().get(calendarId="primary", eventId=event_id).execute()
            title = event.get("summary", "Unknown event")
        except HttpError:
            title = "Unknown event"

        service.events().delete(
            calendarId="primary",
            eventId=event_id,
            sendUpdates="all",
        ).execute()

        return {
            "action":   "deleted",
            "event_id": event_id,
            "title":    title,
            "message":  f"'{title}' cancelled and all attendees notified.",
        }


    def get_events(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get calendar events for a time window.

        params keys:
            time_min   (ISO datetime, optional)  default = now
            time_max   (ISO datetime, optional)  default = +7 days
            timezone   (str)                     default "Asia/Kolkata"
            max_results (int)                    default 20
            query      (str, optional)           text search
        """
        service = self.get_calendar_service()
        if not service:
            raise Exception("AUTH_REQUIRED")
        tz_str = params.get("timezone", "Asia/Kolkata")
        now = datetime.now()

        time_min = _ensure_iso(params.get("time_min"))
        time_max = _ensure_iso(params.get("time_max"))


        kwargs: Dict[str, Any] = dict(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            maxResults=params.get("max_results", 20),
            singleEvents=True,
            orderBy="startTime",
        )
        if params.get("query"):
            kwargs["q"] = params["query"]

        result = service.events().list(**kwargs).execute()
        events = []
        for e in result.get("items", []):
            events.append({
                "event_id":  e["id"],
                "title":     e.get("summary", "No title"),
                "start":     e["start"].get("dateTime", e["start"].get("date")),
                "end":       e["end"].get("dateTime",   e["end"].get("date")),
                "attendees": [a["email"] for a in e.get("attendees", [])],
                "meet_link": e.get("hangoutLink"),
                "status":    e.get("status"),
                "html_link": e.get("htmlLink"),
            })
        return events


    def check_availability(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Check for scheduling conflicts in a proposed time window.

        params keys:
            start         (ISO datetime)   proposed slot start
            end           (ISO datetime)   proposed slot end
            attendee_emails (list[str])    check their free/busy too
            timezone      (str)            default "Asia/Kolkata"

        Returns a list of conflicting events (empty = no conflicts).
        """
        service = self.get_calendar_service()
        if not service:
            raise Exception("AUTH_REQUIRED")
        tz_str = params.get("timezone", "Asia/Kolkata")
        # IST = ZoneInfo("Asia/Kolkata")

        # proposed_start = datetime.strptime(params["start"], "%Y-%m-%d %H:%M").replace(tzinfo=IST)
        # proposed_end = datetime.strptime(params["end"], "%Y-%m-%d %H:%M").replace(tzinfo=IST)

        IST = pytz.timezone("Asia/Kolkata")

        # ✅ Convert to datetime
        proposed_start = IST.localize(
            datetime.strptime(params["start"], "%Y-%m-%d %H:%M")
        )
        proposed_end = IST.localize(
            datetime.strptime(params["end"], "%Y-%m-%d %H:%M")
        )

        proposed_start_iso = proposed_start.isoformat()
        proposed_end_iso   = proposed_end.isoformat()

        # 1. Free/busy query across all attendees
        freebusy_items = [{"id": "primary"}] + [
            {"id": e} for e in params.get("attendee_emails", [])
        ]
        fb_result = service.freebusy().query(body={
            "timeMin":   proposed_start_iso,
            "timeMax":   proposed_end_iso,
            "timeZone":  "UTC",
            "items":     freebusy_items,
        }).execute()

        calendars = fb_result.get("calendars", {})

        # 2. Collect overlapping blocks
        conflicts: List[Dict[str, Any]] = []
        for calendar_id, data in calendars.items():
            for busy in data.get("busy", []):
                busy_start = datetime.fromisoformat(busy["start"].replace("Z", "+00:00")).astimezone(IST)
                busy_end   = datetime.fromisoformat(busy["end"].replace("Z", "+00:00")).astimezone(IST)

                # Overlap condition
                if busy_start < proposed_end and busy_end > proposed_start:
                    conflicts.append({
                        "calendar":    calendar_id,
                        "busy_start":  busy_start.isoformat(),
                        "busy_end":    busy_end.isoformat(),
                        "overlap_minutes": int(
                            (min(proposed_end, busy_end) - max(proposed_start, busy_start))
                            .total_seconds() / 60
                        ),
                    })

        # 3. Also list own events in that window for details
        own_events = self.get_events({
            "time_min":    proposed_start_iso,
            "time_max":    proposed_end_iso,
            "timezone":    tz_str,
            "max_results": 10,
        })

        return {
            "proposed_start":    proposed_start_iso,
            "proposed_end":      proposed_end_iso,
            "has_conflicts":     len(conflicts) > 0,
            "conflict_count":    len(conflicts),
            "conflicts":         conflicts,
            "events_in_window":  own_events,
            "recommendation":    (
                "Slot is FREE — safe to book."
                if not conflicts else
                f"CONFLICT: {len(conflicts)} overlap(s) found. "
                "Consider a different time."
            ),
        }
