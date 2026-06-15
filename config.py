from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API keys
    GROQ_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    # Paths
    BASE_OUTPUT_DIR: Path = Path("output")
    FONTS_DIR: Path = Path("assets/fonts")

    # Transcription
    SILENCE_THRESHOLD: float = 2.0
    GROQ_MODEL: str = "whisper-large-v3"
    GROQ_MAX_RETRIES: int = 3

    # Gemini
    GEMINI_MODEL: str = "gemini-3.5-flash"
    GEMINI_MAX_RETRIES: int = 3


settings = Settings()
