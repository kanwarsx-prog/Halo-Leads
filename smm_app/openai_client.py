from openai import OpenAI
from smm_app.config import get_settings

settings = get_settings()

client = OpenAI(api_key=settings.openai_api_key)
