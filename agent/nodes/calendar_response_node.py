from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from dotenv import load_dotenv
import os
from agent.nodes.llm import build_llm


class CalendarResponseNode:
    """
    Converts raw calendar_result into a warm, conversational ARIA response.
    Equivalent role to TestExecutionNode (takes raw output → produces final report).
    """

    def __init__(self):
        load_dotenv()
        # model = os.getenv("MODEL", "gpt-4.1")
        # self.llm = ChatOpenAI(model=model, temperature=0, api_key=os.getenv("O
        # self.llm = build_llm()

#         self.system_prompt = """You are ARIA, a friendly and professional Executive Assistant.
# Convert the raw calendar tool output into a natural, warm conversational response.

# Rules:
# - Keep it concise (2-4 sentences max)
# - Preserve all event details (times, IDs, titles) exactly as given
# - If a conflict was detected, empathetically acknowledge and suggest a fix
# - If an action succeeded, confirm it enthusiastically
# - If data is missing, politely ask for it
# - Never fabricate event details
# """

    def _format_event(self, event):
        title = event.get("title") or "Untitled event"
        start = event.get("start") or "no start time"
        end = event.get("end") or "no end time"
        return f"{title} from {start} to {end}"

    def _format_response(self, state, raw_result):
        if isinstance(raw_result, str):
            return raw_result

        if isinstance(raw_result, list):
            if not raw_result:
                return "I couldn't find any matching events."

            lines = [f"{idx + 1}. {self._format_event(event)}" for idx, event in enumerate(raw_result)]
            return "Here are the events I found:\n" + "\n".join(lines)

        if not isinstance(raw_result, dict):
            return "Done."

        action = raw_result.get("action")
        title = raw_result.get("title") or "the event"
        start = raw_result.get("start")
        end = raw_result.get("end")
        meet_link = raw_result.get("meet_link")
        html_link = raw_result.get("html_link")

        if action == "created":
            message = f"Created '{title}'"
            if start and end:
                message += f" from {start} to {end}"
            if meet_link:
                message += f". Meet link: {meet_link}"
            elif html_link:
                message += f". Calendar link: {html_link}"
            return message + "."

        if action == "updated":
            message = f"Updated '{title}'"
            if start and end:
                message += f" from {start} to {end}"
            changes = raw_result.get("changes") or []
            if changes:
                message += f". Changed: {', '.join(changes)}"
            return message + "."

        if action == "deleted":
            return raw_result.get("message") or f"Cancelled '{title}' and notified attendees."

        if "has_conflicts" in raw_result:
            recommendation = raw_result.get("recommendation")
            if recommendation:
                return recommendation
            if raw_result.get("has_conflicts"):
                return f"That slot has {raw_result.get('conflict_count', 1)} conflict(s)."
            return "That slot is free."

        return str(raw_result)

    async def __call__(self, state):
        # If clarification was already set by intent/action node, skip LLM call
        if state.response_message and not state.calendar_result:
            return state

        raw_result = state.calendar_result or "No result available."

        state.response_message = self._format_response(state, raw_result)

        # Gemini response generation disabled for speed. Re-enable this block if
        # you want natural-language polishing instead of deterministic templates.
        # messages = [
        #     SystemMessage(content=self.system_prompt),
        #     HumanMessage(content=f"User said: {state.user_message}"),
        #     AIMessage(content=f"Tool returned: {raw_result}"),
        #     HumanMessage(content="Now respond naturally to the user.")
        # ]
        #
        # response = await self.llm.ainvoke(messages)
        # state.response_message = response.content
        # state.messages.append(AIMessage(content=response.content))
        return state
# content=response.content))
#         return state