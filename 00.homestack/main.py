"""Local development launcher.

Delegates to the homestack Typer application so the CLI can be invoked
via `python main.py` in addition to the installed `homestack` command.
"""

from cli.cli import app

if __name__ == "__main__":
    app()
