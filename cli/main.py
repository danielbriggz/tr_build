import typer
from rich.console import Console

app = typer.Typer(
    name="transcrire",
    help="Podcast content pipeline — transcription and captions.",
    no_args_is_help=False,
)
console = Console()

from cli.rss    import app as rss_app
from cli.run    import app as run_app
from cli.review import app as review_app

app.add_typer(rss_app,    name="feed")
app.add_typer(run_app,    name="run")
app.add_typer(review_app, name="review")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Launch the interactive menu (default behaviour)."""
    if ctx.invoked_subcommand is None:
        from cli.menu import run_menu
        run_menu()


if __name__ == "__main__":
    app()