from enum import Enum


class CompletionTier(str, Enum):
    """How complete a pipeline run is for a given episode."""
    FULL = "full"
    ENHANCED = "enhanced"
    BASIC = "basic"
    INCOMPLETE = "incomplete"


class TranscribeMode(str, Enum):
    """Transcription backend. Groq only — no offline mode."""
    GROQ = "groq"


class StageStatus(str, Enum):
    """Status of a single pipeline stage."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
