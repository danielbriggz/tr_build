import logging
from dataclasses import dataclass, field
from typing import Optional

from domain import Platform
from services.gemini import call_gemini


# ── Logger ────────────────────────────────────────────────────────────────────

def _get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    return logger

logger = _get_logger(__name__)


# ── Platform rules ────────────────────────────────────────────────────────────

PLATFORM_RULES: dict[str, str] = {
    "ig_story": """\
Write 5 captions for an Instagram Story slide.
- Each caption is a single punchy sentence or question (max 12 words)
- Conversational and bold — written like you are talking directly to someone
- No hashtags
- No emoji""",

    "ig_portrait": """\
Write 5 captions for an Instagram feed post.
- Each caption is 2-4 sentences long
- Hook the reader in the first sentence
- Conversational tone — warm, direct, relatable
- End each caption with 3-5 relevant hashtags on a new line
- No emoji""",

    "twitter": """\
Write 5 tweets.
- Each tweet is a single punchy statement or question
- Hard limit: 240 characters per tweet (strictly enforced)
- No hashtags — Twitter reach does not depend on them
- No emoji
- Opinions, provocations, and hot takes work well here""",

    "linkedin": """\
Write 5 LinkedIn posts.
- Each post is 80-120 words
- Start with a strong hook line, then develop the idea in short paragraphs
- Professional but human tone — not corporate speak
- End with a reflective question to drive comments
- Max 2 relevant hashtags at the very end
- No emoji""",
}

DEFAULT_RULES = """\
Write 5 captions for a social media post.
- Each caption is 2-4 sentences
- Punchy, direct, and engaging
- No emoji"""


# ── Prompt builders ───────────────────────────────────────────────────────────

def build_prompt(transcript: str, platform: Platform, spotify_url: str | None = None) -> str:
    """Build a platform-specific caption generation prompt."""
    rules = PLATFORM_RULES.get(platform.slug, DEFAULT_RULES)
    spotify_line = f"\nSpotify link to include as CTA where appropriate: {spotify_url}" if spotify_url else ""

    return f"""\
You are a social media copywriter for a podcast called "Volatile Times with Daniel" — \
a Nigerian podcast about relationships, identity, masculinity, mental health, and culture.

Platform: {platform.name}

{rules}

Use plain text only — no markdown, no asterisks, no special characters.
Each caption must feel distinct — vary the angle, hook, and framing across the 5.
Draw directly from the ideas, arguments, and quotes in the transcript below.
{spotify_line}

Transcript:
{transcript[:4000]}

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


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class CaptionResult:
    platform: str
    captions: list[str]
    with_spotify: Optional[list[str]] = None


@dataclass
class CaptionBundle:
    """All platform captions for one episode, plus error tracking."""
    results: dict[str, CaptionResult] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    def all_generated(self) -> bool:
        return len(self.errors) == 0

    def to_dict(self) -> dict[str, list[str]]:
        return {slug: r.captions for slug, r in self.results.items()}


# ── Generation ────────────────────────────────────────────────────────────────

def generate_captions(
    transcript: str,
    platforms: list[Platform],
    spotify_url: str | None = None,
) -> dict[str, list[str]]:
    """
    Generate captions for each selected platform.
    Failures on individual platforms are caught and logged — one platform
    failing does not block the others.
    Returns {platform_slug: [caption1, caption2, ...]}
    """
    bundle = CaptionBundle()

    for platform in platforms:
        try:
            logger.info("Generating captions for platform: %s", platform.slug)
            prompt = build_prompt(transcript, platform, spotify_url)
            raw = call_gemini(prompt)
            captions = _parse_numbered_list(raw)

            if not captions:
                raise ValueError("Gemini returned an empty or unparseable caption list.")

            result = CaptionResult(platform=platform.slug, captions=captions)
            if spotify_url:
                result.with_spotify = [f"{c}\n\nListen: {spotify_url}" for c in captions]

            bundle.results[platform.slug] = result
            logger.info("Captions generated for %s: %d items", platform.slug, len(captions))

        except Exception as e:
            bundle.errors[platform.slug] = str(e)
            logger.error("Caption generation failed for %s: %s", platform.slug, e)

    if bundle.errors:
        logger.warning("Caption generation completed with errors: %s", list(bundle.errors.keys()))

    return bundle.to_dict()


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
    logger.info("Regenerating caption #%d for %s", caption_index + 1, platform.slug)
    result = call_gemini(prompt).strip()
    logger.info("Caption regenerated for %s", platform.slug)
    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_numbered_list(text: str) -> list[str]:
    """
    Extract captions from a numbered list response.
    Handles the standard Gemini format: '1. Caption text on same line'
    including multi-line captions where continuation lines follow.
    """
    import re
    items = re.split(r'\n\s*\d+\.\s+', '\n' + text.strip())
    return [item.strip() for item in items if item.strip()]