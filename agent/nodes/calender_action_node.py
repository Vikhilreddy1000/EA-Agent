from agent.nodes.calendar_tools import GoogleCalendarService
from datetime import datetime, timedelta
from agent.nodes.llm import build_llm
from langchain_core.messages import SystemMessage, HumanMessage
from agent.services.mom_service import MOMService


service = GoogleCalendarService()
IST = "+05:30"
GENERIC_DELETE_TITLES = {
    "",
    "event",
    "meeting",
    "meet",
    "call",
    "calendar event",
    "appointment",
    "interview",
}
MEETING_KEYWORDS = (
    "meeting",
    "meet",
    "call",
    "sync",
    "standup",
    "discussion",
    "interview",
    "screening",
)


def to_iso(dt_str):
    return datetime.strptime(dt_str, "%Y-%m-%d %H:%M").isoformat() + "+05:30"


def is_generic_delete_title(title: str) -> bool:
    return (title or "").strip().lower() in GENERIC_DELETE_TITLES


def event_match_score(event: dict, requested_title: str) -> int:
    title = (event.get("title") or "").lower()
    requested = (requested_title or "").strip().lower()
    score = 0

    if requested and requested not in GENERIC_DELETE_TITLES:
        if requested == title:
            score += 100
        elif requested in title:
            score += 60

    if requested == "interview" and "interview" in title:
        score += 50

    if any(keyword in title for keyword in MEETING_KEYWORDS):
        score += 20

    if event.get("meet_link"):
        score += 15

    if event.get("attendees"):
        score += 10

    return score


def format_event_options(events):
    return "\n".join(
        [f"{i + 1}. {event['title']} at {event['start']}" for i, event in enumerate(events)]
    )


def resolve_date_range(date_filter: str):
    now = datetime.now()
    label = (date_filter or "").strip().lower()
 
    if label in ("today", ""):
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end   = start + timedelta(days=1)
    elif label == "tomorrow":
        start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end   = start + timedelta(days=1)
    elif label in ("this week", "week"):
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end   = start + timedelta(days=7)
    elif label == "next week":
        start = (now + timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        end   = start + timedelta(days=7)
    else:
        try:
            start = datetime.strptime(label, "%Y-%m-%d")
            end   = start + timedelta(days=1)
        except ValueError:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end   = start + timedelta(days=1)
 
    return start.isoformat() + IST, end.isoformat() + IST
 

class CalendarActionNode:
    """
    Validates extracted params and executes the calendar tool.
    Equivalent role to BDDGenerationNode (takes structured input → produces output artifact).
    """

    REQUIRED_FIELDS = {
        "create":             ["title", "start", "end"],
        "update":             ["title"],
        "delete":             [],
        "check_availability": ["start", "end"],
        "get":                [],   # no required fields
        "extract_mom":        ["meeting_notes"]
    }

    async def __call__(self, state):
        print("------111")
        # Skip execution if clarification is still pending
        if state.response_message:
            return state
        print(state.response_message,"----")
        intent = state.intent
        params = state.action_params or {}
        print(intent, params,"-------")

        # Validate required fields
        missing = [
            field for field in self.REQUIRED_FIELDS.get(intent, [])
            if not params.get(field)
        ]
        if missing:
            state.response_message = (
                f"I need a bit more info to {intent} the event. "
                f"Could you provide: {', '.join(missing)}?"
            )
            return state

        # Route to correct tool
        try:
            print("------22222")
            if intent == "create":
                result = service.create_event({
                    "title":       params.get("title", ""),
                    "start":       params.get("start", ""),
                    "end":         params.get("end", ""),
                    "attendees":   params.get("attendees", ""),
                    "description": params.get("description", "")
                })
                print(result, "----create")

            elif intent == "get":
                start = params.get("start")
                end = params.get("end")

                # 🔥 fallback using date_filter
                if not start or not end:
                    start, end = resolve_date_range(params.get("date_filter"))
                result = service.get_events({
                    "time_min":    start,
                    "time_max":    end,
                    "query": params.get("title", "")
                })
                print(result, "----get")

            elif intent == "update":
                print("hsjdsjd")
                event_id = params.get("event_id", "")
 
                # If no event_id provided, look the event up by title
                if not event_id:
                    title = params.get("title", "")
                    if not title:
                        state.response_message = (
                            "I couldn't identify which event to update. "
                            "Could you tell me the name of the event?"
                        )
                        return state
                    time_min, time_max = resolve_date_range(params.get("date_filter"))
                    matched = service.get_events({
                            "time_min":    time_min,
                            "time_max":    time_max,
                            "query":       title,
                            "max_results": 10,
                        })
                    print(matched,"------")
                    if not matched:
                        state.response_message = (
                            f"I couldn't find an event called \"{title}\" in your calendar. "
                            "Could you double-check the name or date?"
                        )
                        return state
                    # Handle multiple matches
                    if len(matched) > 1:
                        options = "\n".join(
                            [f"{i+1}. {e['title']} at {e['start']}" for i, e in enumerate(matched)]
                        )
                        state.response_message = (
                            f"I found multiple events named \"{title}\":\n{options}\n"
                            "Which one should I update?"
                        )
                        return state

                    event_id = matched[0]["event_id"]

 
                update_params = {"event_id": event_id}
                # Only forward fields the user actually wants to change
                for field in ("title", "start", "end", "attendees", "description"):
                    if params.get(field):
                        update_params[field] = params[field]
 
                result = service.update_event(update_params)

            elif intent == "delete":
                event_id = params.get("event_id", "")

                # If no event_id → resolve using title
                if not event_id:
                    title = params.get("title", "")
                    if not title:
                        state.response_message = (
                            "I couldn't identify which event to delete. "
                            "Please provide the event name."
                        )
                        return state

                    time_min, time_max = resolve_date_range(params.get("date_filter"))

                    matched = service.get_events({
                        "time_min": time_min,
                        "time_max": time_max,
                        "query": title,
                        "max_results": 10,
                    })

                    if not matched:
                        state.response_message = (
                            f"I couldn't find any event named \"{title}\" "
                            "in your calendar."
                        )
                        return state

                    # Multiple matches → ask user
                    if len(matched) > 1:
                        options = "\n".join(
                            [f"{i+1}. {e['title']} at {e['start']}" for i, e in enumerate(matched)]
                        )
                        state.response_message = (
                            f"I found multiple events named \"{title}\":\n{options}\n"
                            "Which one should I delete?"
                        )
                        return state

                    # Single match → extract event_id
                    event_id = matched[0]["event_id"]

                # Perform delete
                result = service.delete_event({
                    "event_id": event_id
                })
                print(result, "----delete")

            elif intent == "check_availability":
                result = service.check_availability({
                    "start": params.get("start", ""),
                    "end":   params.get("end", "")
                })
                print(result, "----check_availability")
                
            elif intent == "extract_mom":
                notes = params.get("meeting_notes", "")
                mom_service = MOMService()
                try:
                    mom_response = await mom_service.extract(notes)
                    state.mom_result = mom_response
                    
                    mom_text = f"### {mom_response.get('meeting_title', 'Minutes of Meeting')}\n\n"
                    mom_text += f"**Summary:**\n{mom_response.get('summary', '')}\n\n"
                    
                    decisions = mom_response.get('decisions', [])
                    if decisions:
                        mom_text += "**Decisions:**\n"
                        for d in decisions:
                            mom_text += f"- {d}\n"
                        mom_text += "\n"
                        
                    tasks = mom_response.get('tasks', [])
                    if tasks:
                        mom_text += "**Action Items:**\n"
                        for t in tasks:
                            mom_text += f"- {t.get('title', '')} (Owner: {t.get('owner', 'TBD')}, Due: {t.get('due_date', 'TBD')})\n"
                            
                    state.response_message = mom_text.strip()
                except Exception as e:
                    state.response_message = f"Failed to extract MOM: {str(e)}"
                print(state.mom_result, "----extract_mom")
                return state

            else:
                result = f"Unknown intent: {intent}"

            state.calendar_result = result

        except Exception as e:
            if "AUTH_REQUIRED" in str(e):
                auth_url = service.get_auth_url()

                state.calendar_result = None
                state.response_message = (
                    "Please authenticate your Google Calendar:\n"
                    f"{auth_url}"
                )
                return state
            state.calendar_result = f"Tool execution error: {str(e)}"

        return state
