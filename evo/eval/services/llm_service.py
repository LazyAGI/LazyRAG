from zipfile import stringEndArchive
from lazyllm import OnlineChatModule, JsonFormatter
from config import LLM_BASE_URL, LLM_MODEL, LLM_API_KEY
import requests

chat = OnlineChatModule(
    source="openai",
    base_url=LLM_BASE_URL,
    model=LLM_MODEL,
    api_key=LLM_API_KEY,
).formatter(JsonFormatter())

# chat = OnlineChatModule().formatter(JsonFormatter())

