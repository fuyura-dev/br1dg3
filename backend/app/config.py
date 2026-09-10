import os

from dotenv import load_dotenv

load_dotenv()

class Settings:
    PROJECT_NAME = "BR1DG3 API"

    ALLOWED_ORIGINS = [
        "*",
    ]

    LLM_API_KEY = os.getenv("LLM_API_KEY")
    LLM_MODEL = os.getenv("LLM_MODEL")

settings = Settings()