from pathlib import Path
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from groq import Groq, APIError, APIConnectionError, RateLimitError
from config import settings


_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=settings.GROQ_API_KEY)
    return _client


@retry(
    retry=retry_if_exception_type((APIConnectionError, RateLimitError)),
    stop=stop_after_attempt(settings.GROQ_MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=2, max=30),
)
def transcribe_groq(audio_path: Path, diarize: bool = False) -> dict:
    """
    Transcribe audio via Groq Whisper.
    Returns the full API response dict (segments, words, text).
    Retries on connection errors and rate limits — fails hard on all else.
    """
    client = _get_client()

    extra = {}
    if diarize:
        extra["diarization_enabled"] = True

    with open(audio_path, "rb") as f:
        response = client.audio.transcriptions.create(
            file=(audio_path.name, f),
            model=settings.GROQ_MODEL,
            response_format="verbose_json",
            timestamp_granularities=["segment", "word"],
            **extra,
        )

    return response.model_dump()
