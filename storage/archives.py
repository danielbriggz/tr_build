import shutil
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
from storage.episodes import get_next_version
from storage.db import get_conn


@dataclass
class ArchiveEntry:
    stage: str
    version: int
    archived_path: Path
    original_path: str | None
    created_at: str


# ── Archive ───────────────────────────────────────────────────────────────────

def archive_stage_output(episode_id: int, stage: str, current_output_path: str) -> Path | None:
    """
    Move the current stage output into _archive/v{n}/ before a rerun.
    Returns the archive path, or None if there was nothing to archive.
    """
    current = Path(current_output_path)
    if not current.exists():
        return None

    version = get_next_version(episode_id, stage) - 1  # version of the run being archived
    archive_dir = current.parent / "_archive" / f"v{version}"
    archive_dir.mkdir(parents=True, exist_ok=True)

    dest = archive_dir / current.name
    shutil.move(str(current), dest)

    _record_archive(episode_id, stage, version, str(dest), current_output_path)
    return dest


def list_archive_versions(episode_id: int, stage: str) -> list[ArchiveEntry]:
    """Return all archived versions of a stage for an episode, newest first."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM stage_archives
            WHERE episode_id = ? AND stage = ?
            ORDER BY version DESC
            """,
            (episode_id, stage),
        ).fetchall()
    return [
        ArchiveEntry(
            stage=r["stage"],
            version=r["version"],
            archived_path=Path(r["archived_path"]),
            original_path=r["original_path"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


# ── Private ───────────────────────────────────────────────────────────────────

def _record_archive(episode_id: int, stage: str, version: int,
                    archived_path: str, original_path: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO stage_archives
                (episode_id, stage, version, archived_path, original_path)
            VALUES (?, ?, ?, ?, ?)
            """,
            (episode_id, stage, version, archived_path, original_path),
        )
