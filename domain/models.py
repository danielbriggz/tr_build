from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from .enums import StageStatus, CompletionTier, TranscribeMode
from .platforms import Platform


@dataclass
class Episode:
    """A single podcast episode tracked in the DB."""
    id: int | None
    guid: str                   # unique RSS GUID — DB UNIQUE constraint
    title: str
    published: str              # ISO date string from RSS
    audio_url: str
    cover_art_url: str
    spotify_url: str | None
    folder_path: str            # absolute path to episode output folder
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class StageResult:
    """Output of a single pipeline stage for one episode."""
    id: int | None
    episode_id: int
    stage: str                  # "fetch" | "transcribe" | "captions"
    status: StageStatus
    output_path: str | None     # path to primary output file
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    version: int = 1            # increments on rerun; old output archived
    created_at: datetime = field(default_factory=datetime.utcnow)
    reviewed: bool = False


@dataclass
class PipelineConfig:
    """Runtime config for a single pipeline run."""
    episode_id: int
    mode: TranscribeMode = TranscribeMode.GROQ
    diarize: bool = False
    selected_platforms: list[Platform] = field(default_factory=list)
    stages: list[str] = field(default_factory=lambda: [
        "fetch", "transcribe", "captions"
    ])
    rerun_stage: str | None = None  # if set, only this stage reruns
