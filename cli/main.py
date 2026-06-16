import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="transcrire",
    help="Podcast content pipeline — transcription, and captions",
    no_args_is_help=True,
)
console = Console()

from cli.rss import app as rss_app
from cli.run import app as run_app
from cli.review import app as review_app

app.add_typer(rss_app, name="feed")
app.add_typer(run_app, name="run")
app.add_typer(review_app, name="review")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        console.print("[bold]Transcrire[/bold] — use [cyan]transcrire --help[/cyan] to see available commands.")


if __name__ == "__main__":
    app()
