import os
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
        
    st.divider()
    st.subheader("Upload Meeting File")
    uploaded_file = st.file_uploader("Upload video/audio/text for MOM", type=["mp4", "mp3", "wav", "txt", "pdf"])
    if uploaded_file is not None:
        if st.button("Transcribe & Extract MOM", use_container_width=True):
            with st.spinner("Transcribing file (this may take a minute)..."):
                try:
                    transcribe_url = API_URL.replace("/chat", "/transcribe")
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                    resp = requests.post(transcribe_url, files=files, timeout=None)
                    resp.raise_for_status()
                    data = resp.json()
                    if "transcript" in data:
                        transcript = data["transcript"]
                        st.session_state.mom_prompt = f"Extract MOM from these notes:\n\n{transcript}"
                        st.rerun()
                    else:
                        st.error(data.get("error", "Unknown error during transcription"))
                except Exception as e:
                    st.error(f"Failed to transcribe: {e}")


for item in st.session_state.messages:
    with st.chat_message(item["role"]):
        st.write(item["content"])

        payload = item.get("payload")
        if payload:
            with st.expander("Details"):
                st.json(payload)


prompt = st.chat_input("Ask me to schedule, update, cancel a meeting, or extract MOM from notes")

if "mom_prompt" in st.session_state:
    prompt = st.session_state.mom_prompt
    del st.session_state.mom_prompt

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Working on your calendar..."):
            try:
                result = send_message(prompt, st.session_state.session_id)
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
