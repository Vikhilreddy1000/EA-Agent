# nodes/calendar_intent.py
import json
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
# from nemoguardrails import RailsConfig
# from nemoguardrails.integrations.langchain.runnable_rails import RunnableRails
from dotenv import load_dotenv
import os
from datetime import datetime
from agent.nodes.llm import build_llm


load_dotenv()

class CalendarIntentNode:
    """
    Parses raw user_message → detects intent + extracts structured parameters.
    Equivalent role to CodeAnalysisNode (reads input, produces structured analysis).
    """

    def __init__(self):
        load_dotenv()
        # model = os.getenv("MODEL", "gpt-4.1")
        # self.llm = ChatOpenAI(model=model, temperature=0, api_key=os.getenv("OPENAI_API_KEY"))
        self.llm = build_llm()

        self.system_prompt = """You are an intent parser for an executive assistant agent. 
Extract structured intent from the user message and return ONLY valid JSON.

INTENTS: create | get | update | delete | check_availability | extract_mom

Convert a natural-language date label (today / tomorrow / this week / next week)
into (start, end) ISO strings with IST offset.

OUTPUT FORMAT (strict JSON):
{
  "intent": "<one of the intents>",
  "params": {
    "title":       "<event title if mentioned>",
    "start":       "<YYYY-MM-DD HH:MM if mentioned>",
    "end":         "<YYYY-MM-DD HH:MM if mentioned>",
    "attendees":   "<comma-separated emails if mentioned>",
    "description": "<description if mentioned>",
    "event_id":    "",
    "date_filter": "<YYYY-MM-DD — see rules below>",
    "meeting_notes": "<the raw notes or transcript provided by the user for MOM extraction>"
  },
  "clarification_needed": "<question to ask user if critical info is missing, else null>"
}

Rules:
1. event_id: ALWAYS output empty string "". Never populate it. Never ask the user for it.The system resolves events automatically by title. This field is reserved for internal use only.
2. Never guess times — if not mentioned, leave as empty string ""
3. If intent is unclear, set intent to "get" and set clarification_needed
4. If start and end are present, DO NOT ask for date clarification Only ask if BOTH are missing.
5. clarification_needed: Set to null UNLESS the user's request is genuinely ambiguous 
   and cannot proceed at all. 
   NEVER ask for event_id. 
   NEVER ask for clarification if title + start + end are present for update.
   NEVER ask for clarification if title is present for delete.
   ONLY ask if intent itself is completely unclear.
6. Convert a natural-language date label (today / tomorrow / this week / next week) into start, end ISO strings with IST offset.
7. date_filter: Used to scope the calendar search window.
   - For "get" intent: set to the date the user mentions (e.g. "today" → today's date YYYY-MM-DD, "tomorrow" → tomorrow's date).
     If no date mentioned, set to today's date.
   - For "update" or "delete" intent: set date_filter to the DATE PART of the existing event's start time
8. For "extract_mom" intent: If the user asks to summarize meeting notes, extract minutes of meeting (MOM), action items, or decisions from provided text/notes, use this intent. Put ALL provided notes/text into the `meeting_notes` field.
"""

    async def __call__(self, state):
        
        today = datetime.now().strftime("%Y-%m-%d")

        messages = [
            SystemMessage(content=self.system_prompt + f"\nToday's date: {today}"),
            *state.messages[-10:],
            HumanMessage(content=state.user_message)
        ]

        response = await self.llm.ainvoke(messages)

        try:
            content = response.content.strip()

            if content.startswith("```"):
                content = content.replace("```json", "")
                content = content.replace("```", "")
                content = content.strip()
            parsed = json.loads(content)
            state.intent = parsed.get("intent", "")
            state.action_params = parsed.get("params", {})

            # Store clarification back into response_message if needed
            clarification = parsed.get("clarification_needed")
            if clarification:
                state.response_message = clarification

        except Exception as e:
            print(f"JSON parsing error: {e}")
            print(f"LLM response: {response.content}")
            state.response_message = "I didn’t understand that. Can you rephrase?"

        return state