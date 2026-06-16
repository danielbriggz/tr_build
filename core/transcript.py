from pathlib import Path


# ── Formatting helpers (kept from old codebase) ──────────────────────────────

def format_timestamp(seconds: float) -> str:
    """Convert float seconds to HH:MM:SS.mmm string."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def format_segments(segments: list[dict]) -> str:
    """
    Build a timestamped transcript string from Groq segment dicts.
    Format: [HH:MM:SS.mmm] text
    """
    lines = []
    for seg in segments:
        ts = format_timestamp(seg["start"])
        lines.append(f"[{ts}] {seg['text'].strip()}")
    return "\n".join(lines)


# ── Paragraph segmentation ───────────────────────────────────────────────────

def segment_by_silence(segments: list[dict], threshold: float = 2.0) -> str:
    """
    Join segment text into a plain transcript, inserting a blank line
    (paragraph break) wherever the gap between segments is >= threshold seconds.

    This is step 1 of 2 — the Gemini formatting pass cleans it up after.
    """
    if not segments:
        return ""

    paragraphs = []
    current: list[str] = []

    for i, seg in enumerate(segments):
        text = seg["text"].strip()
        if not text:
            continue

        if i > 0:
            gap = seg["start"] - segments[i - 1]["end"]
            if gap >= threshold:
                if current:
                    paragraphs.append(" ".join(current))
                    current = []

        current.append(text)

    if current:
        paragraphs.append(" ".join(current))

    return "\n\n".join(paragraphs)


# ── Output writers ────────────────────────────────────────────────────────────

def write_transcript_files(
    segments: list[dict],
    plain_text: str,
    output_dir: Path,
    episode_slug: str,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "timestamped": output_dir / f"{episode_slug}_timestamped.txt",
        "plain": output_dir / f"{episode_slug}_plain.txt",
    }

    paths["timestamped"].write_text(format_segments(segments), encoding="utf-8")
    paths["plain"].write_text(plain_text, encoding="utf-8")

    return paths
