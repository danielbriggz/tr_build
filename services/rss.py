import feedparser
import httpx
from pathlib import Path
from domain import Episode
from storage.episodes import get_episode_by_guid


def load_feed(url: str) -> feedparser.FeedParserDict:
    """Fetch and parse an RSS feed from a URL."""
    feed = feedparser.parse(url)
    if feed.bozo and not feed.entries:
        raise ValueError(f"Failed to parse feed: {url}")
    return feed


def check_new_episodes(feed: feedparser.FeedParserDict) -> list[dict]:
    """
    Return feed entries not already in the DB.
    Comparison is done by GUID — no history.json needed.
    """
    new = []
    for entry in feed.entries:
        guid = entry.get("id") or entry.get("link")
        if not get_episode_by_guid(guid):
            new.append(entry)
    return new


def download_file(url: str, dest: Path, label: str = "file") -> Path:
    """Stream-download a file from url to dest. Returns dest path."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", url, follow_redirects=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = int(downloaded / total * 100)
                    print(f"\r  Downloading {label}... {pct}%", end="", flush=True)
    print()
    return dest


def get_audio_url(entry: dict) -> str | None:
    """Extract the audio enclosure URL from a feed entry."""
    for link in entry.get("enclosures", []):
        if "audio" in link.get("type", ""):
            return link["href"]
    return None


def get_cover_art_url(feed: feedparser.FeedParserDict) -> str | None:
    """Extract feed-level cover art URL."""
    return feed.feed.get("image", {}).get("href")
