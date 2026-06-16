import typer
from rich.console import Console
from rich.table import Table

from storage.db import init_db
from storage import episodes as ep_store
from storage.episodes import list_episodes, get_all_stage_results
from domain import Episode, PipelineConfig, PLATFORMS, StageStatus
from core.pipeline import (
    run_pipeline, rerun_stage, get_available_actions,
    stage_fetch, stage_transcribe, stage_captions,
)
from services.rss import load_feed, check_new_episodes, get_audio_url, get_cover_art_url
from config import settings
from slugify import slugify
import datetime

console = Console()

MAX_RETRIES = 3

STAGE_ORDER = ["fetch", "transcribe", "captions"]

STAGE_LABELS = {
    "fetch":      "Fetch audio + cover art",
    "transcribe": "Transcribe",
    "captions":   "Generate captions",
}

STAGE_RUNNERS = {
    "fetch":      stage_fetch,
    "transcribe": stage_transcribe,
    "captions":   stage_captions,
}


# ── Entry point ───────────────────────────────────────────────────────────────

def run_menu() -> None:
    init_db()

    while True:
        episode = _select_episode()
        if episode is None:
            console.print("\nGoodbye! 👋")
            raise typer.Exit()

        _episode_loop(episode)


# ── Episode selection ─────────────────────────────────────────────────────────

def _select_episode() -> Episode | None:
    episodes = list_episodes()

    _print_header()

    if not episodes:
        console.print("  No episodes yet.\n")
        console.print("  [cyan]1.[/cyan]  Load a podcast feed")
        console.print("  [cyan]0.[/cyan]  Exit\n")
        choice = typer.prompt("Select", default="0")
        if choice == "1":
            return _fetch_new_episode()
        return None

    console.print(f"  [bold]{len(episodes)} episode(s) in library:[/bold]\n")
    for i, ep in enumerate(episodes, 1):
        results  = get_all_stage_results(ep.id)
        stages_done = sum(
            1 for s in STAGE_ORDER
            if results.get(s) and results[s].status == StageStatus.SUCCESS
        )
        bar = f"{stages_done}/{len(STAGE_ORDER)} stages"
        console.print(f"  [cyan]{i}.[/cyan]  {ep.title[:50]}  [dim]({bar})[/dim]")

    console.print(f"\n  [cyan]N.[/cyan]  Load a new episode")
    console.print(f"  [cyan]0.[/cyan]  Exit\n")

    choice = typer.prompt("Select episode", default="0")

    if choice == "0":
        return None
    if choice.upper() == "N":
        return _fetch_new_episode()
    if choice.isdigit() and 1 <= int(choice) <= len(episodes):
        return episodes[int(choice) - 1]

    console.print("[yellow]Invalid choice.[/yellow]")
    return _select_episode()


def _fetch_new_episode() -> Episode | None:
    feed_url = typer.prompt("\n  Paste RSS feed URL")
    console.print("\n  Fetching feed...")

    try:
        feed = load_feed(feed_url)
    except Exception as e:
        console.print(f"  [red]Could not load feed: {e}[/red]")
        return None

    new_entries = check_new_episodes(feed)
    if not new_entries:
        console.print("  [green]No new episodes found.[/green]")
        return None

    console.print(f"\n  [bold]{len(new_entries)} new episode(s):[/bold]\n")
    for i, entry in enumerate(new_entries, 1):
        console.print(f"  [cyan]{i}.[/cyan]  {entry.get('title', 'Untitled')}")

    console.print("  [cyan]0.[/cyan]  Cancel\n")
    choice = typer.prompt("  Select episode", default="0")

    if not choice.isdigit() or int(choice) == 0 or int(choice) > len(new_entries):
        return None

    entry = new_entries[int(choice) - 1]
    title = entry.get("title", "Untitled")
    guid  = entry.get("id") or entry.get("link")
    slug  = slugify(title)

    ep = Episode(
        id=None,
        guid=guid,
        title=title,
        published=entry.get("published", str(datetime.date.today())),
        audio_url=get_audio_url(entry) or "",
        cover_art_url=get_cover_art_url(entry, feed) or "",
        spotify_url=entry.get("link"),
        folder_path=str(settings.BASE_OUTPUT_DIR / slug),
    )

    if not ep.audio_url:
        console.print("  [red]No audio URL found for this episode.[/red]")
        return None

    ep_id = ep_store.insert_episode(ep)
    ep.id = ep_id
    console.print(f"\n  [green]Episode saved:[/green] {title}")
    return ep


# ── Episode loop ──────────────────────────────────────────────────────────────

def _episode_loop(episode: Episode) -> None:
    while True:
        results  = get_all_stage_results(episode.id)
        is_fresh = "fetch" not in results

        platforms = _get_or_prompt_platforms(episode, results)

        config = PipelineConfig(
            episode_id=episode.id,
            selected_platforms=platforms,
        )

        _print_episode_menu(episode, results)

        if is_fresh:
            # Auto-advance through all incomplete stages
            advanced = _auto_advance(episode, config, results)
            if not advanced:
                # All stages done or failed — fall through to manual menu
                pass
            else:
                continue

        # Manual mode — prompt user
        console.print("\n  [cyan]R.[/cyan]  Re-run a stage")
        console.print("  [cyan]H.[/cyan]  View stage history")
        console.print("  [cyan]B.[/cyan]  Back to episode list")
        console.print("  [cyan]0.[/cyan]  Exit\n")

        choice = typer.prompt("Select", default="B")

        if choice == "0":
            console.print("\nGoodbye! 👋")
            raise typer.Exit()
        elif choice.upper() == "B":
            return
        elif choice.upper() == "R":
            _rerun_menu(episode, config)
        elif choice.upper() == "H":
            _history_menu(episode)
        elif choice.isdigit() and choice in ["1", "2", "3"]:
            stage = STAGE_ORDER[int(choice) - 1]
            _run_stage_with_retry(episode, config, stage)
        else:
            console.print("[yellow]Invalid choice.[/yellow]")


def _auto_advance(episode: Episode, config: PipelineConfig, results: dict) -> bool:
    """Run all pending stages in sequence. Returns True if any stage was attempted."""
    attempted = False

    for stage in STAGE_ORDER:
        existing = results.get(stage)
        if existing and existing.status == StageStatus.SUCCESS:
            continue  # already done

        attempted = True
        success = _run_stage_with_retry(episode, config, stage)

        if not success:
            console.print(f"\n  [red]Stopping auto-advance — {stage} failed after {MAX_RETRIES} attempts.[/red]")
            return attempted

        # Refresh results after each stage
        results = get_all_stage_results(episode.id)

    return attempted


def _run_stage_with_retry(episode: Episode, config: PipelineConfig, stage: str) -> bool:
    """Run a stage with up to MAX_RETRIES attempts. Returns True on success."""
    runner = STAGE_RUNNERS[stage]

    for attempt in range(1, MAX_RETRIES + 1):
        console.print(f"\n  [bold][{stage}][/bold] Starting... (attempt {attempt}/{MAX_RETRIES})")
        try:
            result = runner(episode, config)
            if result.status == StageStatus.SUCCESS:
                console.print(f"  [green]✅ {stage} complete.[/green]")
                return True
            else:
                raise RuntimeError(result.error or "Stage returned non-success status.")
        except Exception as e:
            console.print(f"  [red]❌ {stage} failed: {e}[/red]")
            if attempt < MAX_RETRIES:
                retry = typer.confirm(f"  Retry {stage}?", default=True)
                if not retry:
                    return False
            else:
                console.print(f"  [red]Dropping back to menu after {MAX_RETRIES} failed attempts.[/red]")

    return False


# ── Re-run menu ───────────────────────────────────────────────────────────────

def _rerun_menu(episode: Episode, config: PipelineConfig) -> None:
    console.print("\n  [bold]Which stage would you like to re-run?[/bold]\n")
    for i, stage in enumerate(STAGE_ORDER, 1):
        console.print(f"  [cyan]{i}.[/cyan]  {STAGE_LABELS[stage]}")
    console.print("  [cyan]0.[/cyan]  Cancel\n")

    choice = typer.prompt("Select", default="0")
    if not choice.isdigit() or int(choice) == 0:
        return

    idx = int(choice) - 1
    if 0 <= idx < len(STAGE_ORDER):
        stage = STAGE_ORDER[idx]
        console.print(f"\n  Archiving previous {stage} output...")
        existing = ep_store.get_latest_stage_result(episode.id, stage)
        if existing and existing.output_path:
            from storage.archives import archive_stage_output
            archive_stage_output(episode.id, stage, existing.output_path)
        _run_stage_with_retry(episode, config, stage)


# ── History menu ──────────────────────────────────────────────────────────────

def _history_menu(episode: Episode) -> None:
    console.print("\n  [bold]Which stage history would you like to view?[/bold]\n")
    for i, stage in enumerate(STAGE_ORDER, 1):
        console.print(f"  [cyan]{i}.[/cyan]  {STAGE_LABELS[stage]}")
    console.print("  [cyan]0.[/cyan]  Cancel\n")

    choice = typer.prompt("Select", default="0")
    if not choice.isdigit() or int(choice) == 0:
        return

    idx = int(choice) - 1
    if 0 <= idx < len(STAGE_ORDER):
        stage = STAGE_ORDER[idx]
        from storage.archives import list_archive_versions
        versions = list_archive_versions(episode.id, stage)

        if not versions:
            console.print(f"  [yellow]No history for {stage}.[/yellow]")
            return

        table = Table(title=f"{stage} history")
        table.add_column("Version", style="cyan")
        table.add_column("Archived at")
        table.add_column("Path")
        for v in versions:
            table.add_row(str(v.version), v.created_at, str(v.archived_path))
        console.print(table)


# ── Platform selection ────────────────────────────────────────────────────────

def _get_or_prompt_platforms(episode: Episode, results: dict) -> list:
    cap_result = results.get("captions")
    if cap_result and cap_result.metadata.get("platforms"):
        slugs = cap_result.metadata["platforms"]
        return [p for p in PLATFORMS.values() if p.slug in slugs]

    console.print("\n  [bold]Select platforms for caption generation:[/bold]\n")
    platform_list = list(PLATFORMS.values())
    for i, p in enumerate(platform_list, 1):
        console.print(f"  [cyan]{i}.[/cyan]  {p.name}")

    raw = typer.prompt("\n  Enter numbers separated by commas", default="1,2,3,4")
    selected = []
    for part in raw.split(","):
        try:
            idx = int(part.strip()) - 1
            if 0 <= idx < len(platform_list):
                selected.append(platform_list[idx])
        except ValueError:
            pass
    return selected or list(PLATFORMS.values())


# ── Display ───────────────────────────────────────────────────────────────────

def _print_header() -> None:
    console.print("\n" + "=" * 44)
    console.print("           🎙️   TRANSCRIRE")
    console.print("=" * 44 + "\n")


def _print_episode_menu(episode: Episode, results: dict) -> None:
    _print_header()
    short_title = episode.title[:46] + ("..." if len(episode.title) > 46 else "")
    console.print(f"  [bold]{short_title}[/bold]\n")

    for i, stage in enumerate(STAGE_ORDER, 1):
        r = results.get(stage)
        if r and r.status == StageStatus.SUCCESS:
            icon = "[green]✅[/green]"
        elif r and r.status == StageStatus.FAILED:
            icon = "[red]❌[/red]"
        else:
            icon = "⬜"
        console.print(f"  [cyan]{i}.[/cyan]  {icon}  {STAGE_LABELS[stage]}")

    console.print("\n" + "=" * 44)