import os
from pathlib import Path

from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)
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