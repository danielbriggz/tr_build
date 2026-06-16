import typer
from rich.console import Console
from domain import PLATFORMS, PipelineConfig
from storage.db import init_db
from core.pipeline import run_pipeline, rerun_stage, get_available_actions

app = typer.Typer(help="Pipeline run commands.")
console = Console()


@app.command("start")
def cmd_run(
    episode_id: int = typer.Argument(..., help="Episode ID to process."),
    diarize: bool = typer.Option(False, "--diarize", help="Enable speaker diarization."),
) -> None:
    """Run the full pipeline for an episode."""
    init_db()
    ep = _get_episode_or_exit(episode_id)

    platforms = _prompt_platform_selection()
    if not platforms:
        console.print("[yellow]No platforms selected — exiting.[/yellow]")
        raise typer.Exit()

    config = PipelineConfig(
        episode_id=episode_id,
        diarize=diarize,
        selected_platforms=platforms,
    )

    console.print(f"\n[bold]Processing:[/bold] {ep.title}")
    results = run_pipeline(ep, config)

    console.print("\n[bold]Pipeline summary:[/bold]")
    for stage, result in results.items():
        icon = "✅" if result.status.value == "success" else "❌"
        console.print(f"  {icon} {stage}: {result.status.value}")


@app.command("rerun")
def cmd_rerun(
    episode_id: int = typer.Argument(..., help="Episode ID."),
    stage: str = typer.Argument(..., help="Stage to rerun: fetch | transcribe | captions"),
    diarize: bool = typer.Option(False, "--diarize", help="Enable diarization (transcribe stage only)."),
) -> None:
    """Rerun a single stage. Archives the previous output first."""
    init_db()
    ep = _get_episode_or_exit(episode_id)

    platforms = _prompt_platform_selection()
    config = PipelineConfig(
        episode_id=episode_id,
        diarize=diarize,
        selected_platforms=platforms,
        rerun_stage=stage,
    )

    console.print(f"\n[bold]Rerunning stage:[/bold] {stage} for '{ep.title}'")
    result = rerun_stage(ep, stage, config)
    icon = "✅" if result.status.value == "success" else "❌"
    console.print(f"{icon} {stage}: {result.status.value}")


@app.command("actions")
def cmd_actions(
    episode_id: int = typer.Argument(..., help="Episode ID."),
) -> None:
    """Show available next actions for an episode based on its current state."""
    init_db()
    _get_episode_or_exit(episode_id)
    actions = get_available_actions(episode_id)
    console.print(f"\n[bold]Available actions for episode {episode_id}:[/bold]")
    for action in actions:
        console.print(f"  → {action}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_episode_or_exit(episode_id: int):
    from storage.episodes import list_episodes
    eps = {e.id: e for e in list_episodes()}
    ep = eps.get(episode_id)
    if not ep:
        console.print(f"[red]No episode found with id={episode_id}[/red]")
        raise typer.Exit(1)
    return ep


def _prompt_platform_selection() -> list:
    console.print("\n[bold]Select platforms for caption generation:[/bold]")
    platform_list = list(PLATFORMS.values())
    for i, p in enumerate(platform_list):
        console.print(f"  [cyan]{i + 1}.[/cyan] {p.name}")

    raw = typer.prompt("Enter numbers separated by commas (e.g. 1,3)", default="1,2,3,4")
    selected = []
    for part in raw.split(","):
        try:
            idx = int(part.strip()) - 1
            if 0 <= idx < len(platform_list):
                selected.append(platform_list[idx])
        except ValueError:
            pass
    return selected