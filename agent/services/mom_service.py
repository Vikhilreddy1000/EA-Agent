from agent.nodes.llm import build_llm
import json

class MOMService:

    def __init__(self):
        self.llm = build_llm()

    async def extract(self, transcript: str):

        prompt = f"""
You are an Executive Assistant.

Extract:

- Meeting Title
- Summary
- Decisions
- Action Items

Return ONLY JSON.

Schema:

{{
 "meeting_title":"",
 "summary":"",
 "decisions":[],
 "tasks":[
   {{
      "title":"",
      "owner":"",
      "due_date":"",
      "priority":""
   }}
 ]
}}

Transcript:

{transcript}

"""

        response = await self.llm.ainvoke(prompt)

        return json.loads(response.content)