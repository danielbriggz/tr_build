import typer
from rich.console import Console
from rich.table import Table
from storage import episodes as ep_store
from storage.archives import list_archive_versions
from storage.db import init_db

app = typer.Typer(help="Review and history commands.")
console = Console()


@app.command("captions")
def cmd_review_captions(
    episode_id: int = typer.Argument(..., help="Episode ID to review captions for.")
) -> None:
    """Review generated captions for an episode and mark as approved."""
    init_db()
    result = ep_store.get_latest_stage_result(episode_id, "captions")
    if not result:
        console.print("[red]No captions found for this episode.[/red]")
        raise typer.Exit(1)

    import json
    from pathlib import Path
    captions = json.loads(Path(result.output_path).read_text(encoding="utf-8"))

    for platform, caps in captions.items():
        console.print(f"\n[bold]{platform.upper()}[/bold]")
        for i, caption in enumerate(caps, 1):
            console.print(f"  [cyan]{i}.[/cyan] {caption}")

    approve = typer.confirm("\nMark captions as reviewed?", default=True)
    if approve:
        ep_store.mark_reviewed(result.id)
        console.print("[green]Captions marked as reviewed.[/green]")


@app.command("images")
def cmd_review_images(
    episode_id: int = typer.Argument(..., help="Episode ID to review images for.")
) -> None:
    """List generated image paths for an episode and mark as approved."""
    init_db()
    result = ep_store.get_latest_stage_result(episode_id, "images")
    if not result:
        console.print("[red]No images found for this episode.[/red]")
        raise typer.Exit(1)

    import json
    meta = result.metadata.get("platforms", {})
    for platform, paths in meta.items():
        console.print(f"\n[bold]{platform.upper()}[/bold]")
        for path in paths:
            console.print(f"  {path}")

    approve = typer.confirm("\nMark images as reviewed?", default=True)
    if approve:
        ep_store.mark_reviewed(result.id)
        console.print("[green]Images marked as reviewed.[/green]")


@app.command("history")
def cmd_history(
    episode_id: int = typer.Argument(..., help="Episode ID."),
    stage: str = typer.Argument(..., help="Stage name: fetch | transcribe | captions | images"),
) -> None:
    """Show all historical versions of a stage for an episode."""
    init_db()
    versions = list_archive_versions(episode_id, stage)

    if not versions:
        console.print(f"[yellow]No history found for stage '{stage}' on episode {episode_id}.[/yellow]")
        raise typer.Exit()

    table = Table(title=f"History — {stage} — episode {episode_id}")
    table.add_column("Version", style="cyan")
    table.add_column("Status")
    table.add_column("Reviewed")
    table.add_column("Created at")
    table.add_column("Output path")

    for v in versions:
        table.add_row(
            str(v.version),
            "archived",
            "—",
            v.created_at,
            str(v.archived_path),
        )

    console.print(table)
