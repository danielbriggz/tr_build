import json
from pathlib import Path
from datetime import datetime
from domain import Episode, StageResult, StageStatus
from storage.db import get_conn


# ── Episode CRUD ──────────────────────────────────────────────────────────────

def insert_episode(ep: Episode) -> int:
    """Insert a new episode. Returns the new row id."""
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO episodes
                (guid, title, published, audio_url, cover_art_url, spotify_url, folder_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (ep.guid, ep.title, ep.published, ep.audio_url,
             ep.cover_art_url, ep.spotify_url, ep.folder_path),
        )
        return cur.lastrowid


def get_episode_by_guid(guid: str) -> Episode | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM episodes WHERE guid = ?", (guid,)
        ).fetchone()
    return _row_to_episode(row) if row else None


def get_episode_by_id(episode_id: int) -> Episode | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM episodes WHERE id = ?", (episode_id,)
        ).fetchone()
    return _row_to_episode(row) if row else None


def list_episodes(limit: int = 50) -> list[Episode]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM episodes ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_episode(r) for r in rows]


def episode_exists(guid: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM episodes WHERE guid = ?", (guid,)
        ).fetchone()
    return row is not None


def create_episode_folder(base_output_dir: Path, slug: str) -> Path:
    """Create and return the output folder for an episode."""
    folder = base_output_dir / slug
    folder.mkdir(parents=True, exist_ok=True)
    return folder


# ── StageResult CRUD ──────────────────────────────────────────────────────────

def insert_stage_result(result: StageResult) -> int:
    """Insert a new stage result. Returns the new row id."""
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO stage_results
                (episode_id, stage, status, output_path, metadata, error, version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.episode_id,
                result.stage,
                result.status.value,
                result.output_path,
                json.dumps(result.metadata),
                result.error,
                result.version,
            ),
        )
        return cur.lastrowid


def update_stage_result(result_id: int, status: StageStatus,
                         output_path: str | None = None,
                         metadata: dict | None = None,
                         error: str | None = None) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE stage_results
            SET status = ?, output_path = ?, metadata = ?, error = ?
            WHERE id = ?
            """,
            (
                status.value,
                output_path,
                json.dumps(metadata or {}),
                error,
                result_id,
            ),
        )


def get_latest_stage_result(episode_id: int, stage: str) -> StageResult | None:
    """Get the most recent version of a stage result for an episode."""
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT * FROM stage_results
            WHERE episode_id = ? AND stage = ?
            ORDER BY version DESC LIMIT 1
            """,
            (episode_id, stage),
        ).fetchone()
    return _row_to_stage_result(row) if row else None


def get_all_stage_results(episode_id: int) -> dict[str, StageResult]:
    """Return the latest result for every stage of an episode."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM stage_results
            WHERE episode_id = ?
            ORDER BY stage, version DESC
            """,
            (episode_id,),
        ).fetchall()

    seen: dict[str, StageResult] = {}
    for row in rows:
        r = _row_to_stage_result(row)
        if r.stage not in seen:
            seen[r.stage] = r
    return seen


def get_next_version(episode_id: int, stage: str) -> int:
    """Return the next version number for a stage rerun."""
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT MAX(version) as max_v FROM stage_results
            WHERE episode_id = ? AND stage = ?
            """,
            (episode_id, stage),
        ).fetchone()
    return (row["max_v"] or 0) + 1


def mark_reviewed(result_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE stage_results SET reviewed = 1 WHERE id = ?", (result_id,)
        )


def list_unreviewed(stage: str) -> list[StageResult]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM stage_results
            WHERE stage = ? AND reviewed = 0 AND status = 'success'
            ORDER BY created_at ASC
            """,
            (stage,),
        ).fetchall()
    return [_row_to_stage_result(r) for r in rows]


# ── Private helpers ───────────────────────────────────────────────────────────

def _row_to_episode(row) -> Episode:
    return Episode(
        id=row["id"],
        guid=row["guid"],
        title=row["title"],
        published=row["published"],
        audio_url=row["audio_url"],
        cover_art_url=row["cover_art_url"],
        spotify_url=row["spotify_url"],
        folder_path=row["folder_path"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _row_to_stage_result(row) -> StageResult:
    return StageResult(
        id=row["id"],
        episode_id=row["episode_id"],
        stage=row["stage"],
        status=StageStatus(row["status"]),
        output_path=row["output_path"],
        metadata=json.loads(row["metadata"]),
        error=row["error"],
        version=row["version"],
        reviewed=bool(row["reviewed"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def upsert_stage_result(result: StageResult) -> int:
    """
    Insert a stage result, or update it if one already exists for
    this episode/stage/version combo. Returns the row id.
    """
    existing = get_latest_stage_result(result.episode_id, result.stage)
    if existing and existing.version == result.version:
        update_stage_result(
            existing.id,
            status=result.status,
            output_path=result.output_path,
            metadata=result.metadata,
            error=result.error,
        )
        return existing.id
    return insert_stage_result(result)
