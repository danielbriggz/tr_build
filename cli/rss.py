import typer
from rich.console import Console
from rich.table import Table
from storage.db import init_db
from services import rss as rss_service
from storage import episodes as ep_store
from domain import Episode
from config import settings
from pathlib import Path
from slugify import slugify
import datetime

app = typer.Typer(help="RSS feed commands.")
console = Console()


@app.command("fetch")
def cmd_fetch(
    feed_url: str = typer.Argument(..., help="RSS feed URL to fetch episodes from.")
) -> None:
    """Fetch new episodes from a podcast RSS feed."""
    init_db()
    console.print(f"[cyan]Fetching feed:[/cyan] {feed_url}")

    feed = rss_service.load_feed(feed_url)
    new_entries = rss_service.check_new_episodes(feed)

    if not new_entries:
        console.print("[green]No new episodes found.[/green]")
        raise typer.Exit()

    console.print(f"\n[bold]{len(new_entries)} new episode(s):[/bold]\n")
    for i, entry in enumerate(new_entries):
        console.print(f"  [cyan]{i + 1}.[/cyan] {entry.get('title', 'Untitled')}")

    choice = typer.prompt("\nEnter episode number to process (or 0 to exit)", type=int)
    if choice == 0 or choice > len(new_entries):
        raise typer.Exit()

    entry = new_entries[choice - 1]
    guid  = entry.get("id") or entry.get("link")
    title = entry.get("title", "Untitled")
    slug  = slugify(title)
    folder = settings.BASE_OUTPUT_DIR / slug

    cover_art_url = rss_service.get_cover_art_url(feed) or ""
    audio_url     = rss_service.get_audio_url(entry) or ""

    if not audio_url:
        console.print("[red]No audio URL found for this episode.[/red]")
        raise typer.Exit(1)

    ep = Episode(
        id=None,
        guid=guid,
        title=title,
        published=entry.get("published", str(datetime.date.today())),
        audio_url=audio_url,
        cover_art_url=cover_art_url,
        spotify_url=None,
        folder_path=str(folder),
    )

    ep_id = ep_store.insert_episode(ep)
    console.print(f"\n[green]Episode saved:[/green] {title} (id={ep_id})")
    console.print(f"Run [cyan]transcrire run start {ep_id}[/cyan] to begin processing.")
