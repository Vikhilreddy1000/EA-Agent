import uvicorn
from fastapi import FastAPI, Request, UploadFile, File
import os
import shutil
from google import genai
from dotenv import load_dotenv
from agent.nodes.graph import workflow
from agent.nodes.calendar_tools import GoogleCalendarService
import uuid
from agent import models
from agent.db import engine, Base
from pydantic import BaseModel, Field
from typing import Optional, Union

calendar_service = GoogleCalendarService()

# 🔥 Request schema
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    session_id: str
    intent: Optional[str] = None
    action_params: Optional[dict] = None
    calendar_result: Optional[Union[dict, str]] = None
    mom_result: Optional[str] = None
    response_message: str


app = FastAPI(title="EA Agent")

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.get("/")
async def root():
    return {"message": "Calendar AI Agent is running"}


@app.get("/auth/callback")
async def auth_callback(request: Request):
    return await calendar_service.handle_oauth_callback(request)

@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest):
    user_message = body.message
    session_id = body.session_id or str(uuid.uuid4())

    if not user_message:
        return {"error": "message is required"}

    state = {
        "user_id": session_id,
        "user_message": user_message
    }

    result = await workflow.ainvoke(state)

    return ChatResponse(
        session_id=session_id,
        intent=result.get("intent"),
        action_params=result.get("action_params"),
        calendar_result=result.get("calendar_result"),
        mom_result=result.get("mom_result"),
        response_message=result.get("response_message")
    )

@app.post("/transcribe")
async def transcribe_file(file: UploadFile = File(...)):
    load_dotenv()
    temp_dir = "temp_uploads"
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, file.filename)
    
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        client = genai.Client()
        uploaded_file = client.files.upload(file=temp_path)
        
        import time
        state_str = getattr(uploaded_file.state, "name", str(uploaded_file.state))
        while state_str == "PROCESSING":
            time.sleep(5)
            uploaded_file = client.files.get(name=uploaded_file.name)
            state_str = getattr(uploaded_file.state, "name", str(uploaded_file.state))
            
        if state_str == "FAILED":
            return {"error": "File processing failed on Google servers."}
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[uploaded_file, "Please provide a highly accurate, full transcript of this meeting file."]
        )
        
        return {"transcript": response.text}
    except Exception as e:
        return {"error": str(e)}
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

def start():
    uvicorn.run("agent.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    start()
