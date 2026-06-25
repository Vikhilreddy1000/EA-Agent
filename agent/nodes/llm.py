import os

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI


def build_llm():
    load_dotenv()
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    return ChatGoogleGenerativeAI(
        model=model,
        temperature=0,
        google_api_key=os.getenv("GOOGLE_API_KEY"),
    )
