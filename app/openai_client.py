from openai import OpenAI

from app.config import get_settings


settings = get_settings()

client = OpenAI(api_key=settings.openai_api_key)
