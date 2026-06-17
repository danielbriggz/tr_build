import json
import socket
from pathlib import Path
from slugify import slugify

from config import settings
from domain import Episode, StageResult, StageStatus, PipelineConfig
from services.audio import check_ffmpeg, compress_for_groq
from services.groq import transcribe_groq
from services.gemini import format_transcript_paragraphs
from services.rss import download_file
from core.transcript import segment_by_silence, write_transcript_files
from core.captions import generate_captions
from storage import episodes as ep_store
from storage.archives import archive_stage_output


# ── Preflight ─────────────────────────────────────────────────────────────────

def check_internet() -> None:
    try:
        socket.setdefaulttimeout(5)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
    except OSError:
        raise ConnectionError("No internet connection detected.")


def preflight_validation() -> None:
    check_internet()
    check_ffmpeg()
    _validate_api_key_format(settings.GROQ_API_KEY, "GROQ_API_KEY")
    _validate_api_key_format(settings.GEMINI_API_KEY, "GEMINI_API_KEY")


def _validate_api_key_format(key: str, name: str) -> None:
    if not key or len(key.strip()) < 20:
        raise ValueError(f"{name} looks invalid — check your .env file.")


# ── Stage: fetch ──────────────────────────────────────────────────────────────

def stage_fetch(episode: Episode, config: PipelineConfig) -> StageResult:
    folder = Path(episode.folder_path)
    folder.mkdir(parents=True, exist_ok=True)

    audio_dest = folder / "audio" / "original.mp3"
    cover_dest = folder / "cover.jpg"

    download_file(episode.audio_url, audio_dest, label="audio")
    download_file(episode.cover_art_url, cover_dest, label="cover art")

    result = StageResult(
        id=None, episode_id=episode.id, stage="fetch",
        status=StageStatus.SUCCESS, output_path=str(audio_dest),
        metadata={"cover_art_path": str(cover_dest)},
    )
    ep_store.upsert_stage_result(result)
    return result


# ── Stage: transcribe ─────────────────────────────────────────────────────────

def stage_transcribe(episode: Episode, config: PipelineConfig) -> StageResult:
    fetch_result = ep_store.get_latest_stage_result(episode.id, "fetch")
    if not fetch_result:
        raise RuntimeError("Fetch stage must complete before transcription.")

    audio_path = Path(fetch_result.output_path)
    folder = Path(episode.folder_path)
    compressed = folder / "audio" / "compressed.mp3"

    compress_for_groq(audio_path, compressed)

    response = transcribe_groq(compressed, diarize=config.diarize)
    segments = response.get("segments", [])
    words    = response.get("words", [])

    raw_plain       = segment_by_silence(segments, threshold=settings.SILENCE_THRESHOLD)
    formatted_plain = format_transcript_paragraphs(raw_plain)

    slug    = slugify(episode.title)
    out_dir = folder / "transcripts"
    paths   = write_transcript_files(segments, words, formatted_plain, out_dir, slug)

    result = StageResult(
        id=None, episode_id=episode.id, stage="transcribe",
        status=StageStatus.SUCCESS, output_path=str(paths["plain"]),
        metadata={k: str(v) for k, v in paths.items()},
    )
    ep_store.upsert_stage_result(result)
    return result


# ── Stage: captions ───────────────────────────────────────────────────────────

def stage_captions(episode: Episode, config: PipelineConfig) -> StageResult:
    tx_result = ep_store.get_latest_stage_result(episode.id, "transcribe")
    if not tx_result:
        raise RuntimeError("Transcription must complete before caption generation.")

    transcript_text = Path(tx_result.output_path).read_text(encoding="utf-8")
    captions = generate_captions(transcript_text, config.selected_platforms, episode.spotify_url)

    folder   = Path(episode.folder_path)
    out_path = folder / "captions" / "captions.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(captions, indent=2, ensure_ascii=False), encoding="utf-8")

    result = StageResult(
        id=None, episode_id=episode.id, stage="captions",
        status=StageStatus.SUCCESS, output_path=str(out_path),
        metadata={"platforms": [p.slug for p in config.selected_platforms]},
    )
    ep_store.upsert_stage_result(result)
    return result




# ── Pipeline orchestrator ─────────────────────────────────────────────────────

STAGE_RUNNERS = {
    "fetch":      stage_fetch,
    "transcribe": stage_transcribe,
    "captions":   stage_captions,
}


def run_pipeline(episode: Episode, config: PipelineConfig) -> dict[str, StageResult]:
    preflight_validation()
    results = {}

    for stage_name in config.stages:
        runner = STAGE_RUNNERS[stage_name]
        print(f"\n[{stage_name}] Starting...")
        try:
            result = runner(episode, config)
            results[stage_name] = result
            print(f"[{stage_name}] Done.")
        except Exception as e:
            failed = StageResult(
                id=None, episode_id=episode.id, stage=stage_name,
                status=StageStatus.FAILED, output_path=None, error=str(e),
            )
            ep_store.upsert_stage_result(failed)
            results[stage_name] = failed
            print(f"[{stage_name}] Failed: {e}")
            break

    return results


def rerun_stage(episode: Episode, stage: str, config: PipelineConfig) -> StageResult:
    """Archive the previous stage output and rerun just that stage."""
    existing = ep_store.get_latest_stage_result(episode.id, stage)
    if existing and existing.output_path:
        archive_stage_output(episode.id, stage, existing.output_path)

    config.rerun_stage = stage
    return STAGE_RUNNERS[stage](episode, config)


# ── Available actions ─────────────────────────────────────────────────────────

def get_available_actions(episode_id: int) -> list[str]:
    """Derive valid next steps from DB state — drives the CLI menu."""
    results = ep_store.get_all_stage_results(episode_id)
    actions = []

    fetch = results.get("fetch")
    tx    = results.get("transcribe")
    caps  = results.get("captions")

    actions.append("view-history")
    return actions


# ── Stage: transcribe (PC upload) ─────────────────────────────────────────────

def stage_transcribe_pc(audio_path: str, diarize: bool = False) -> str:
    """
    Transcribe a local audio file directly — no episode in DB required.
    Compresses, transcribes, formats, and saves to pc_transcripts/.
    Returns the path to the saved transcript.
    """
    from pathlib import Path
    from slugify import slugify
    from services.audio import compress_for_groq
    from services.groq import transcribe_groq
    from services.gemini import format_transcript_paragraphs
    from core.transcript import segment_by_silence, write_transcript_files
    from config import settings

    src = Path(audio_path)
    if not src.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    out_dir = settings.BASE_OUTPUT_DIR / "pc_transcripts"
    out_dir.mkdir(parents=True, exist_ok=True)

    compressed = out_dir / "_compressed.mp3"
    compress_for_groq(src, compressed)

    response  = transcribe_groq(compressed, diarize=diarize)
    segments  = response.get("segments", [])

    raw_plain       = segment_by_silence(segments, threshold=settings.SILENCE_THRESHOLD)
    formatted_plain = format_transcript_paragraphs(raw_plain)

    slug  = slugify(src.stem)
    paths = write_transcript_files(segments, formatted_plain, out_dir, slug)

    compressed.unlink(missing_ok=True)

    return str(paths["plain"])


# ── Stage: transcribe (PC upload) ─────────────────────────────────────────────

def stage_transcribe_pc(audio_path: str, diarize: bool = False) -> dict:
    """
    Transcribe a local audio file directly — no episode DB entry needed.
    Saves output to pc_transcripts/ and returns paths dict.
    """
    from pathlib import Path
    from services.audio import compress_for_groq
    from services.groq import transcribe_groq
    from services.gemini import format_transcript_paragraphs
    from core.transcript import segment_by_silence, write_transcript_files
    from config import settings
    from slugify import slugify

    src       = Path(audio_path)
    slug      = slugify(src.stem)
    out_dir   = settings.BASE_OUTPUT_DIR / "pc_transcripts" / slug
    compressed = out_dir / "compressed.mp3"

    out_dir.mkdir(parents=True, exist_ok=True)
    compress_for_groq(src, compressed)

    response  = transcribe_groq(compressed, diarize=diarize)
    segments  = response.get("segments", [])

    raw_plain       = segment_by_silence(segments, threshold=settings.SILENCE_THRESHOLD)
    formatted_plain = format_transcript_paragraphs(raw_plain)

    paths = write_transcript_files(segments, formatted_plain, out_dir, slug)

    # Clean up compressed file
    compressed.unlink(missing_ok=True)

    return {k: str(v) for k, v in paths.items()}