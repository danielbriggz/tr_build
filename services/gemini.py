from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
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


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


@retry(
    retry=retry_if_exception_type((genai_errors.ServerError,)),
    stop=stop_after_attempt(settings.GEMINI_MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=2, max=30),
)
def call_gemini(prompt: str) -> str:
    """Send a prompt to Gemini and return the text response."""
    client = _get_client()
    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=prompt,
    )
    return response.text.strip()


def format_transcript_paragraphs(raw_text: str) -> str:
    """
    Run the locked formatting prompt against a silence-segmented transcript.
    Returns the formatted transcript text.
    """
    prompt = f"{FORMAT_PROMPT}\n\n---\n\n{raw_text}"
    return call_gemini(prompt)
