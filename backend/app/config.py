import os

from dotenv import load_dotenv

load_dotenv()

class Settings:
    PROJECT_NAME = "BR1DG3 API"

    ALLOWED_ORIGINS = (
        "*",
    )

    LLM_API_KEY: str = os.getenv("LLM_API_KEY")
    LLM_MODEL: str = os.getenv("LLM_MODEL")

    REMOTE_DRIVER_URL = os.getenv("REMOTE_DRIVER_URL")
    
settings = Settings()