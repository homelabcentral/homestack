"""Helpers for rendering markdown content in the CLI via Rich."""

from __future__ import annotations

import re
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel


class MarkdownPrinter:
    """Render markdown file or text content using Rich widgets."""

    _FRONT_MATTER_PATTERN = re.compile(
        r"\A\ufeff?---\s*\r?\n.*?\r?\n---\s*(?:\r?\n|\Z)",
        flags=re.DOTALL,
    )

    @classmethod
    def _strip_yaml_front_matter(cls, markdown_text: str) -> str:
        """Strip leading YAML front matter when present.

        Only strips a front matter block at the start of the file delimited by
        `---` lines. Non-front-matter content is returned unchanged.
        """
        return cls._FRONT_MATTER_PATTERN.sub("", markdown_text, count=1)

    @classmethod
    def print_markdown_text(
        cls, console: Console, markdown_text: str, *, title: str = "README"
    ) -> bool:
        """Render markdown text inside a titled panel.

        Returns False when content is empty/whitespace only.
        """
        content = cls._strip_yaml_front_matter(markdown_text).strip()
        if not content:
            return False

        console.print(Panel(Markdown(content), title=title))
        return True

    @classmethod
    def print_markdown_file(
        cls, console: Console, markdown_path: Path, *, title: str = "README"
    ) -> bool:
        """Render a markdown file from disk.

        Returns False when file cannot be read or has empty content.
        """
        try:
            content = markdown_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            console.print(f"[red]Markdown file not found:[/red] {markdown_path}")
            return False
        except UnicodeDecodeError:
            console.print(
                f"[red]Unable to decode markdown file as UTF-8:[/red] {markdown_path}"
            )
            return False
        except OSError as exc:
            console.print(
                f"[red]Unable to read markdown file:[/red] {markdown_path} ({exc})"
            )
            return False

        return cls.print_markdown_text(console, content, title=title)
