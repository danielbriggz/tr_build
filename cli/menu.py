import typer
from rich.console import Console
from rich.text import Text
from rich.align import Align

from storage.db import init_db
from storage import episodes as ep_store
from storage.episodes import list_episodes, get_all_stage_results
from domain import Episode, PipelineConfig, PLATFORMS, StageStatus
from core.pipeline import (
    run_pipeline, rerun_stage, get_available_actions,
    stage_fetch, stage_transcribe, stage_captions,
)
from services.rss import load_feed, check_new_episodes, get_audio_url, get_cover_art_url
from services.audio import pick_file_dialog
from core.pipeline import stage_transcribe_pc
from config import settings
from slugify import slugify
import datetime

console = Console()

MAX_RETRIES  = 3
BLOCK_WIDTH  = 44          # width of the centred content block
STAGE_ORDER  = ["fetch", "transcribe", "captions"]
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


# ── Layout helpers ────────────────────────────────────────────────────────────

class _Block:
    """
    Accumulates lines of Rich markup, then prints them all as a single
    centred block — so every line shares the same left edge.
    """
    def __init__(self):
        self._lines: list[str] = []

    def add(self, markup: str = "") -> "_Block":
        self._lines.append(markup)
        return self

    def flush(self) -> None:
        if not self._lines:
            return
        combined = Text()
        for i, markup in enumerate(self._lines):
            combined.append_text(Text.from_markup(markup))
            if i < len(self._lines) - 1:
                combined.append("\n")
        console.print(Align.center(combined))
        self._lines.clear()


def _print_line(markup: str = "") -> None:
    """Print a single line centred by its own width (for short status messages)."""
    console.print(Align.center(Text.from_markup(markup)))


def _print_block(*lines: str) -> None:
    """
    Print multiple lines as a single centred block — all lines share
    the same left edge, left-aligned within the block.
    Pad every line to BLOCK_WIDTH so the block has a consistent width.
    """
    combined = Text()
    for i, markup in enumerate(lines):
        t = Text.from_markup(markup)
        # Pad plain-text length to BLOCK_WIDTH so all lines are the same width
        plain_len = len(t.plain)
        if plain_len < BLOCK_WIDTH:
            t.append(" " * (BLOCK_WIDTH - plain_len))
        combined.append_text(t)
        if i < len(lines) - 1:
            combined.append("\n")
    console.print(Align.center(combined))


def _print_divider() -> None:
    _print_line("[dim]" + "-" * BLOCK_WIDTH + "[/dim]")


def _blank() -> None:
    console.print()


def _stage_line(number: int, label: str, status: StageStatus | None) -> Text:
    """Render a stage row with colour-coded label."""
    if status == StageStatus.SUCCESS:
        colour = "green"
    elif status == StageStatus.FAILED:
        colour = "red"
    else:
        colour = "dark_orange"

    t = Text()
    t.append(f"{number}.  ", style="bold cyan")
    t.append(label, style=colour)
    return t


# ── Error formatting ──────────────────────────────────────────────────────────

def _friendly_error_message(error: Exception) -> str:
    from services.gemini import GeminiQuotaExceeded, GeminiUnavailable

    last_attempt = getattr(error, "last_attempt", None)
    if last_attempt is not None:
        try:
            underlying = last_attempt.exception()
        except Exception:
            underlying = None
        if underlying is not None:
            error = underlying

    if isinstance(error, (GeminiQuotaExceeded, GeminiUnavailable)):
        return str(error)

    return str(error) or error.__class__.__name__


# ── Entry point ───────────────────────────────────────────────────────────────

def run_menu() -> None:
    init_db()

    while True:
        _print_header()
        _print_block(
            "[bold cyan]1.[/bold cyan]  Podcast RSS feed",
            "[bold cyan]2.[/bold cyan]  Upload from PC  [dim](transcription only)[/dim]",
        )
        _print_divider()
        _print_block("[bold cyan]0.[/bold cyan]  Exit")
        _blank()

        choice = typer.prompt(
            typer.style("     Select source", fg=typer.colors.CYAN),
            default="0"
        )

        if choice == "0":
            _print_line("Goodbye!")
            raise typer.Exit()
        elif choice == "1":
            episode = _select_episode()
            if episode:
                _episode_loop(episode)
        elif choice == "2":
            _pc_upload_flow()
        else:
            _print_line("[yellow]Invalid choice.[/yellow]")


# ── Episode selection ─────────────────────────────────────────────────────────

def _select_episode() -> Episode | None:
    episodes = list_episodes()
    _print_header()

    if not episodes:
        _print_line("No episodes yet.")
        _blank()
        _print_block("[bold cyan]1.[/bold cyan]  Load a podcast feed")
        _print_divider()
        _print_block("[bold cyan]0.[/bold cyan]  Exit")
        _blank()
        choice = typer.prompt(
            typer.style("     Select", fg=typer.colors.CYAN), default="0"
        )
        if choice == "1":
            return _fetch_new_episode()
        return None

    _print_line(f"[bold]{len(episodes)} episode(s) in library[/bold]")
    _blank()
    episode_lines = []
    for i, ep in enumerate(episodes, 1):
        results     = get_all_stage_results(ep.id)
        stages_done = sum(
            1 for s in STAGE_ORDER
            if results.get(s) and results[s].status == StageStatus.SUCCESS
        )
        label = f"{ep.title[:36]}{'...' if len(ep.title) > 36 else ''}"
        bar   = f"{stages_done}/{len(STAGE_ORDER)}"
        episode_lines.append(f"[bold cyan]{i}.[/bold cyan]  {label}  [dim]({bar})[/dim]")
    _print_block(*episode_lines)
    _blank()
    _print_block("[bold cyan]N.[/bold cyan]  Load a new episode")
    _print_divider()
    _print_block("[bold cyan]0.[/bold cyan]  Back")
    _blank()

    choice = typer.prompt(
        typer.style("     Select episode", fg=typer.colors.CYAN), default="0"
    )

    if choice == "0":
        return None
    if choice.upper() == "N":
        return _fetch_new_episode()
    if choice.isdigit() and 1 <= int(choice) <= len(episodes):
        return episodes[int(choice) - 1]

    _print_line("[yellow]Invalid choice.[/yellow]")
    return _select_episode()


def _fetch_new_episode() -> Episode | None:
    _blank()
    feed_url = typer.prompt("     Paste RSS feed URL")
    _print_line("Fetching feed...")

    try:
        feed = load_feed(feed_url)
    except Exception as e:
        _print_line(f"[red]Could not load feed: {e}[/red]")
        return None

    new_entries = check_new_episodes(feed)
    if not new_entries:
        _print_line("[green]No new episodes found.[/green]")
        return None

    _blank()
    _print_line(f"[bold]{len(new_entries)} new episode(s)[/bold]")
    _blank()
    entry_lines = []
    for i, entry in enumerate(new_entries, 1):
        title = entry.get('title', 'Untitled')
        entry_lines.append(f"[bold cyan]{i}.[/bold cyan]  {title[:36]}{'...' if len(title) > 36 else ''}")
    _print_block(*entry_lines)
    _blank()
    _print_block("[bold cyan]0.[/bold cyan]  Cancel")
    _blank()
    choice = typer.prompt(
        typer.style("     Select episode", fg=typer.colors.CYAN), default="0"
    )

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
        _print_line("[red]No audio URL found for this episode.[/red]")
        return None

    ep_id = ep_store.insert_episode(ep)
    ep.id = ep_id
    _print_line(f"[green]Episode saved:[/green] {title[:30]}{'...' if len(title) > 30 else ''}")
    return ep


# ── Episode loop ──────────────────────────────────────────────────────────────

def _episode_loop(episode: Episode) -> None:
    while True:
        results   = get_all_stage_results(episode.id)
        is_fresh  = "fetch" not in results
        platforms = _get_or_prompt_platforms(episode, results)
        config    = PipelineConfig(
            episode_id=episode.id,
            selected_platforms=platforms,
        )

        _print_episode_menu(episode, results)

        if is_fresh:
            advanced = _auto_advance(episode, config, results)
            if advanced:
                continue

        _print_block(
            "[bold cyan]R.[/bold cyan]  Re-run a stage",
            "[bold cyan]H.[/bold cyan]  View stage history",
        )
        _print_divider()
        _print_block(
            "[bold cyan]B.[/bold cyan]  Back to episode list",
            "[bold cyan]0.[/bold cyan]  Exit",
        )
        _blank()

        choice = typer.prompt(
            typer.style("     Select", fg=typer.colors.CYAN), default="B"
        )

        if choice == "0":
            _print_line("Goodbye!")
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
            _print_line("[yellow]Invalid choice.[/yellow]")


def _auto_advance(episode: Episode, config: PipelineConfig, results: dict) -> bool:
    attempted = False
    for stage in STAGE_ORDER:
        existing = results.get(stage)
        if existing and existing.status == StageStatus.SUCCESS:
            continue
        attempted = True
        success   = _run_stage_with_retry(episode, config, stage)
        if not success:
            _print_line(f"[red]Auto-advance stopped — {stage} failed after {MAX_RETRIES} attempts.[/red]")
            return attempted
        results = get_all_stage_results(episode.id)
    return attempted


def _run_stage_with_retry(episode: Episode, config: PipelineConfig, stage: str) -> bool:
    runner = STAGE_RUNNERS[stage]
    for attempt in range(1, MAX_RETRIES + 1):
        _print_line(f"[bold]{stage.upper()}[/bold]  attempt {attempt}/{MAX_RETRIES}")
        try:
            result = runner(episode, config)
            if result.status == StageStatus.SUCCESS:
                _print_line(f"[green]{stage} complete.[/green]")
                return True
            raise RuntimeError(result.error or "Non-success status.")
        except Exception as e:
            _print_line(f"[red]{stage} failed:[/red] {_friendly_error_message(e)}")
            if attempt < MAX_RETRIES:
                retry = typer.confirm("     Retry?", default=True)
                if not retry:
                    return False
            else:
                _print_line(f"[red]Dropping back to menu after {MAX_RETRIES} failed attempts.[/red]")
    return False


# ── Re-run menu ───────────────────────────────────────────────────────────────

def _rerun_menu(episode: Episode, config: PipelineConfig) -> None:
    _blank()
    _print_line("[bold]Which stage would you like to re-run?[/bold]")
    _blank()
    _print_block(*[f"[bold cyan]{i}.[/bold cyan]  {STAGE_LABELS[s]}" for i, s in enumerate(STAGE_ORDER, 1)])
    _blank()
    _print_block("[bold cyan]0.[/bold cyan]  Cancel")
    _blank()

    choice = typer.prompt(
        typer.style("     Select", fg=typer.colors.CYAN), default="0"
    )
    if not choice.isdigit() or int(choice) == 0:
        return

    idx = int(choice) - 1
    if 0 <= idx < len(STAGE_ORDER):
        stage    = STAGE_ORDER[idx]
        existing = ep_store.get_latest_stage_result(episode.id, stage)
        if existing and existing.output_path:
            from storage.archives import archive_stage_output
            archive_stage_output(episode.id, stage, existing.output_path)
        _run_stage_with_retry(episode, config, stage)


# ── History menu ──────────────────────────────────────────────────────────────

def _history_menu(episode: Episode) -> None:
    _blank()
    _print_line("[bold]Which stage history would you like to view?[/bold]")
    _blank()
    _print_block(*[f"[bold cyan]{i}.[/bold cyan]  {STAGE_LABELS[s]}" for i, s in enumerate(STAGE_ORDER, 1)])
    _blank()
    _print_block("[bold cyan]0.[/bold cyan]  Cancel")
    _blank()

    choice = typer.prompt(
        typer.style("     Select", fg=typer.colors.CYAN), default="0"
    )
    if not choice.isdigit() or int(choice) == 0:
        return

    idx = int(choice) - 1
    if 0 <= idx < len(STAGE_ORDER):
        stage    = STAGE_ORDER[idx]
        from storage.archives import list_archive_versions
        versions = list_archive_versions(episode.id, stage)

        if not versions:
            _print_line(f"[yellow]No history for {stage}.[/yellow]")
            return

        _blank()
        _print_line(f"[bold]{stage} history[/bold]")
        _blank()
        for v in versions:
            _print_line(f"v{v.version}  {v.created_at}  {v.archived_path}")


# ── PC upload ─────────────────────────────────────────────────────────────────

def _pc_upload_flow() -> None:
    _print_line("Opening file picker...")
    try:
        audio_path = pick_file_dialog()
    except RuntimeError as e:
        _print_line(f"[red]{e}[/red]")
        return

    if not audio_path:
        _print_line("[yellow]No file selected.[/yellow]")
        return

    _print_line(f"Selected: {str(audio_path)[:36]}{'...' if len(str(audio_path)) > 36 else ''}")
    diarize = typer.confirm("     Enable speaker labelling (diarization)?", default=False)

    _print_line("[bold]Transcribing...[/bold]")
    try:
        paths = stage_transcribe_pc(audio_path, diarize=diarize)
        _print_line("[green]Done.[/green]")
        for label, path in paths.items():
            _print_line(f"{label}: {str(path)[:30]}...")
    except Exception as e:
        _print_line(f"[red]Transcription failed:[/red] {_friendly_error_message(e)}")

    _blank()
    typer.prompt("     Press Enter to return to menu", default="")


# ── Platform selection ────────────────────────────────────────────────────────

def _get_or_prompt_platforms(episode: Episode, results: dict) -> list:
    cap_result = results.get("captions")
    if cap_result and cap_result.metadata.get("platforms"):
        slugs = cap_result.metadata["platforms"]
        return [p for p in PLATFORMS.values() if p.slug in slugs]

    _blank()
    _print_line("[bold]Select platforms for caption generation[/bold]")
    _blank()
    platform_list = list(PLATFORMS.values())
    _print_block(*[f"[bold cyan]{i}.[/bold cyan]  {p.name}" for i, p in enumerate(platform_list, 1)])

    _blank()
    raw = typer.prompt("     Enter numbers separated by commas", default="1,2,3,4")
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
    _blank()
    _print_line("[bold]TRANSCRIRE[/bold]")
    _print_divider()
    _blank()


def _print_episode_menu(episode: Episode, results: dict) -> None:
    _print_header()
    short = episode.title[:46] + ("..." if len(episode.title) > 46 else "")
    _print_line(f"[bold]{short}[/bold]")
    _blank()

    for i, stage in enumerate(STAGE_ORDER, 1):
        r      = results.get(stage)
        status = r.status if r else None
        console.print(Align.center(_stage_line(i, STAGE_LABELS[stage], status)))

    _blank()
    _print_divider()
    _blank()