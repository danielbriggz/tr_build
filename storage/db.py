import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "transcrire.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS episodes (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                guid          TEXT NOT NULL UNIQUE,
                title         TEXT NOT NULL,
                published     TEXT NOT NULL,
                audio_url     TEXT NOT NULL,
                cover_art_url TEXT NOT NULL,
                spotify_url   TEXT,
                folder_path   TEXT NOT NULL,
                created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            );

            CREATE TABLE IF NOT EXISTS stage_results (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id  INTEGER NOT NULL REFERENCES episodes(id),
                stage       TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'pending',
                output_path TEXT,
                metadata    TEXT NOT NULL DEFAULT '{}',
                error       TEXT,
                version     INTEGER NOT NULL DEFAULT 1,
                reviewed    INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            );

            CREATE TABLE IF NOT EXISTS setup (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS stage_archives (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id    INTEGER NOT NULL REFERENCES episodes(id),
                stage         TEXT NOT NULL,
                version       INTEGER NOT NULL,
                archived_path TEXT NOT NULL,
                original_path TEXT,
                created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            );

            CREATE INDEX IF NOT EXISTS idx_stage_results_episode
                ON stage_results(episode_id, stage, version);

            CREATE INDEX IF NOT EXISTS idx_stage_archives_episode
                ON stage_archives(episode_id, stage);
        """)
