from domain import Platform, PLATFORMS
from services.gemini import call_gemini


# ── Prompt builders ───────────────────────────────────────────────────────────

def build_prompt(transcript: str, platform: Platform, spotify_url: str | None = None) -> str:
    """Build a caption generation prompt for a given platform."""
    spotify_line = f"\nSpotify link: {spotify_url}" if spotify_url else ""
    return f"""\
You are a social media copywriter for a podcast.

Platform: {platform.name}
Canvas size: {platform.width}x{platform.height}px

Using the transcript below, write 5 engaging captions for {platform.name}.
Each caption should:
- Be punchy and attention-grabbing
- Match the tone of the episode
- Include relevant hashtags
- Be platform-appropriate in length

Transcript:
{transcript}
{spotify_line}

Return exactly 5 captions, numbered 1–5. No preamble or commentary.\
"""


def build_reference_prompt(transcript: str, references: list[str]) -> str:
    """Build a prompt to generate a reference list from a transcript."""
    ref_block = "\n".join(f"- {r}" for r in references) if references else "(none provided)"
    return f"""\
You are a research assistant for a podcast.

From the transcript below, identify and list all books, articles, people,
tools, studies, or resources mentioned. Format as a clean numbered list.

Previously noted references:
{ref_block}

Transcript:
{transcript}

Return only the numbered list. No preamble.\
"""


# ── Generation ────────────────────────────────────────────────────────────────

def generate_captions(transcript: str, platforms: list[Platform], spotify_url: str | None = None) -> dict[str, list[str]]:
    """
    Generate captions for each selected platform.
    Returns {platform_slug: [caption1, caption2, ...]}
    """
    results = {}
    for platform in platforms:
        prompt = build_prompt(transcript, platform, spotify_url)
        raw = call_gemini(prompt)
        results[platform.slug] = _parse_numbered_list(raw)
    return results


def regenerate_single_caption(
    transcript: str,
    platform: Platform,
    caption_index: int,
    feedback: str | None = None,
    spotify_url: str | None = None,
) -> str:
    """Regenerate one specific caption, optionally with feedback."""
    feedback_line = f"\nFeedback on previous attempt: {feedback}" if feedback else ""
    prompt = f"""\
{build_prompt(transcript, platform, spotify_url)}

Regenerate caption #{caption_index + 1} only.{feedback_line}

Return only the single caption text, no numbering.\
"""
    return call_gemini(prompt).strip()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_numbered_list(text: str) -> list[str]:
    """Extract items from a numbered list response."""
    lines = text.strip().splitlines()
    captions = []
    for line in lines:
        line = line.strip()
        if line and line[0].isdigit() and "." in line[:3]:
            captions.append(line.split(".", 1)[1].strip())
    return captions
