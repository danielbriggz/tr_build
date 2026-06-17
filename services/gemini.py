import re
from datetime import datetime, timedelta, timezone

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, RetryError
from google import genai
from google.genai import errors as genai_errors
from config import settings


_client: genai.Client | None = None

FORMAT_PROMPT = """\
Role:
You are a professional transcript formatter.

Task:
Reformat the raw podcast transcript into clean, readable paragraphs.

Instructions:
- Group related sentences and ideas together.
- Create a new paragraph whenever there is a shift in topic, argument, example, narrative beat, or speaker.
- If speaker labels exist, ensure each speaker begins on a new paragraph.
- Preserve the transcript exactly as written.
- Do not change, add, remove, autocorrect, punctuate, or reorder any words.
- Preserve filler words, stammers, repetitions, and transcription errors.
- Separate paragraphs using a single blank line only.

Output:
Return only the formatted transcript. No explanations, headers, notes, commentary, or code fences.\
"""


class GeminiQuotaExceeded(Exception):
    """Raised when Gemini's API quota is exhausted. Message includes recovery guidance."""
    pass


class GeminiUnavailable(Exception):
    """Raised when Gemini's servers are temporarily overloaded (503). Message includes guidance."""
    pass


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


def _is_daily_quota_error(error: genai_errors.ClientError) -> bool:
    """Detect the free-tier *daily* request quota (as opposed to a short per-minute limit)."""
    message = str(error)
    return "GenerateRequestsPerDayPerProjectPerModel" in message or "free_tier_requests" in message


def _extract_retry_delay_seconds(error: genai_errors.ClientError) -> int | None:
    """Pull the retryDelay (e.g. '6s') out of the error payload, if present."""
    match = re.search(r"'retryDelay':\s*'(\d+)s'", str(error))
    if match:
        return int(match.group(1))
    return None


def _next_pacific_midnight_utc() -> datetime:
    """
    Gemini's free-tier daily quota resets at midnight Pacific Time.
    Returns that reset moment as a UTC datetime (approximation — ignores DST edge cases).
    """
    now_utc = datetime.now(timezone.utc)
    pacific_offset = timedelta(hours=7)
    now_pacific = now_utc - pacific_offset
    next_midnight_pacific = (now_pacific + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return next_midnight_pacific + pacific_offset


def _friendly_quota_error(error: genai_errors.ClientError) -> GeminiQuotaExceeded:
    """Convert a raw Gemini 429 into a clear, actionable exception."""
    if _is_daily_quota_error(error):
        reset_at = _next_pacific_midnight_utc()
        local_str = reset_at.strftime("%Y-%m-%d %H:%M UTC")
        return GeminiQuotaExceeded(
            "Gemini's daily free-tier request limit has been reached.\n"
            f"This resets at approximately {local_str} (midnight Pacific Time).\n"
            "Options: wait for the reset, or add billing at https://aistudio.google.com "
            "to lift the daily cap."
        )

    delay = _extract_retry_delay_seconds(error)
    if delay is not None:
        return GeminiQuotaExceeded(
            f"Gemini is temporarily rate-limited. Try again in about {delay} seconds."
        )

    return GeminiQuotaExceeded(
        "Gemini's API quota appears to be exhausted. Please wait a few minutes and try again, "
        "or check your usage at https://aistudio.google.com."
    )


def _friendly_unavailable_error(error: genai_errors.ServerError) -> GeminiUnavailable:
    """Convert a raw Gemini 503 into a clear, actionable exception."""
    return GeminiUnavailable(
        "Gemini's servers are temporarily overloaded with requests.\n"
        "This is on Google's end, not yours — it usually clears up within a few minutes.\n"
        "Try again shortly; if it keeps happening, check https://aistudio.google.com for status."
    )


def _translate_error(error: Exception) -> Exception:
    """Map a raw Gemini exception to a friendly one, if a mapping exists."""
    if isinstance(error, genai_errors.ClientError) and ("RESOURCE_EXHAUSTED" in str(error) or "429" in str(error)):
        return _friendly_quota_error(error)
    if isinstance(error, genai_errors.ServerError) and ("UNAVAILABLE" in str(error) or "503" in str(error)):
        return _friendly_unavailable_error(error)
    return error


@retry(
    retry=retry_if_exception_type((genai_errors.ServerError,)),
    stop=stop_after_attempt(settings.GEMINI_MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=2, max=30),
)
def _call_gemini_raw(prompt: str) -> str:
    client = _get_client()
    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=prompt,
    )
    return response.text.strip()


def call_gemini(prompt: str) -> str:
    """
    Send a prompt to Gemini and return the text response.

    Retries on transient ServerError via tenacity. Once retries are exhausted
    (or on a non-retried ClientError like a 429), the underlying exception is
    unwrapped from tenacity's RetryError and translated into a friendly
    GeminiQuotaExceeded / GeminiUnavailable exception where recognized.
    """
    try:
        return _call_gemini_raw(prompt)
    except RetryError as e:
        underlying = e.last_attempt.exception()
        raise _translate_error(underlying) from underlying
    except (genai_errors.ClientError, genai_errors.ServerError) as e:
        raise _translate_error(e) from e


def format_transcript_paragraphs(raw_text: str) -> str:
    """
    Run the locked formatting prompt against a silence-segmented transcript.
    Returns the formatted transcript text.
    """
    prompt = f"{FORMAT_PROMPT}\n\n---\n\n{raw_text}"
    return call_gemini(prompt)