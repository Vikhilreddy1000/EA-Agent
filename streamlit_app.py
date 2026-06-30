import os
import sys
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uuid
import requests
import streamlit as st


API_URL = os.getenv("EA_AGENT_API_URL", "http://localhost:8000/chat")


st.set_page_config(
    page_title="EA Agent POC",
    page_icon="EA",
    layout="centered",
)


def send_message(message: str, session_id: str) -> dict:
    response = requests.post(
        API_URL,
        json={"message": message, "session_id": session_id},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []


st.title("EA Agent")

with st.sidebar:
    st.subheader("Session")
    st.caption(st.session_state.session_id)

    api_url = st.text_input("API URL", value=API_URL)
    if api_url:
        API_URL = api_url

    if st.button("New session", use_container_width=True):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()
        
for item in st.session_state.messages:
    with st.chat_message(item["role"]):
        st.write(item["content"])

        payload = item.get("payload")
        if payload:
            with st.expander("Details"):
                st.json(payload)


user_input = st.chat_input("Ask me to schedule a meeting, or attach a meeting file...", accept_file=True, file_type=["mp4", "mp3", "wav", "txt", "pdf"])

prompt_text = ""
uploaded_file = None

if user_input:
    if hasattr(user_input, "text"):
        prompt_text = user_input.text
    elif isinstance(user_input, str):
        prompt_text = user_input

    if hasattr(user_input, "files") and user_input.files:
        uploaded_file = user_input.files[0]

    if uploaded_file is not None:
        with st.chat_message("assistant"):
            with st.spinner("Transcribing attached file (this may take a minute)..."):
                try:
                    transcribe_url = API_URL.replace("/chat", "/transcribe")
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                    resp = requests.post(transcribe_url, files=files, timeout=None)
                    resp.raise_for_status()
                    data = resp.json()
                    if "transcript" in data:
                        transcript = data["transcript"]
                        if prompt_text:
                            prompt_text = f"{prompt_text}\n\n[Attached File Transcript]:\n{transcript}"
                        else:
                            prompt_text = f"Extract MOM from these notes:\n\n{transcript}"
                    else:
                        st.error(data.get("error", "Unknown error during transcription"))
                        prompt_text = None
                except Exception as e:
                    st.error(f"Failed to transcribe: {e}")
                    prompt_text = None

    if prompt_text:
        st.session_state.messages.append({"role": "user", "content": prompt_text})

        with st.chat_message("user"):
            st.write(prompt_text)

        with st.chat_message("assistant"):
            with st.spinner("Working on your request..."):
                try:
                    result = send_message(prompt_text, st.session_state.session_id)
                    answer = result.get("response_message") or "Done."
                    st.write(answer)

                    with st.expander("Details"):
                        st.json(result)

                    st.session_state.messages.append(
                        {
                            "role": "assistant",
                            "content": answer,
                            "payload": result,
                        }
                    )
                except requests.exceptions.RequestException as exc:
                    error = (
                        "I couldn't reach the EA Agent API. Make sure FastAPI is "
                        f"running and the API URL is correct.\n\n{exc}"
                    )
                    st.error(error)
                    st.session_state.messages.append(
                        {"role": "assistant", "content": error}
                    )
