"""Tests for markdown printer utility."""

from pathlib import Path

from rich.console import Console
from utils.markdown_printer import MarkdownPrinter


def test_print_markdown_text_renders_non_empty_content() -> None:
    console = Console(record=True)

    rendered = MarkdownPrinter.print_markdown_text(
        console,
        "# Heading\n\nBody",
        title="README: Test",
    )

    assert rendered is True
    exported = console.export_text()
    assert "Heading" in exported
    assert "Body" in exported


def test_print_markdown_text_returns_false_for_empty_content() -> None:
    console = Console(record=True)

    rendered = MarkdownPrinter.print_markdown_text(console, "   \n\n", title="README")

    assert rendered is False


def test_print_markdown_file_reads_and_renders(tmp_path: Path) -> None:
    console = Console(record=True)
    readme = tmp_path / "readme.md"
    readme.write_text("# Local README\n\nFrom file", encoding="utf-8")

    rendered = MarkdownPrinter.print_markdown_file(console, readme, title="README")

    assert rendered is True
    exported = console.export_text()
    assert "Local README" in exported
    assert "From file" in exported


def test_print_markdown_file_returns_false_when_missing(tmp_path: Path) -> None:
    console = Console(record=True)

    rendered = MarkdownPrinter.print_markdown_file(
        console,
        tmp_path / "missing.md",
        title="README",
    )

    assert rendered is False


def test_print_markdown_text_strips_front_matter() -> None:
    console = Console(record=True)

    rendered = MarkdownPrinter.print_markdown_text(
        console,
        """---
project_name: Demo
description: Example front matter
---

# Title

Visible body
""",
        title="README: Test",
    )

    assert rendered is True
    exported = console.export_text()
    assert "Title" in exported
    assert "Visible body" in exported
    assert "project_name: Demo" not in exported


def test_print_markdown_file_strips_front_matter(tmp_path: Path) -> None:
    console = Console(record=True)
    readme = tmp_path / "readme.md"
    readme.write_text(
        """---
project_name: Demo
category: Utility
---

# Local README

From file
""",
        encoding="utf-8",
    )

    rendered = MarkdownPrinter.print_markdown_file(console, readme, title="README")

    assert rendered is True
    exported = console.export_text()
    assert "Local README" in exported
    assert "From file" in exported
    assert "project_name: Demo" not in exported
