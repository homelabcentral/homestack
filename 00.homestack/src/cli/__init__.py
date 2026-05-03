"""CLI package for homestack.

Exports the root Typer application so it can be referenced from
pyproject.toml's [project.scripts] entry point and from main.py.
"""

from cli.cli import app

__all__ = ["app"]
