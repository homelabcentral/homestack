"""
Rich formatting abstraction layer for beautiful, consistent console output.

Provides a global singleton `formatter` instance with 10 message types (info, error, warning,
debug, success, hint, step, command, result, title), each with contextual emoji, varied
formatting (bold, italic, underline), and distinct colors.

Usage:
    from utils.rich_formatter import formatter
    
    formatter.info("Starting deployment")
    formatter.success("Deployment complete")
    formatter.error("Connection failed", details="Check your network")
    formatter.warning("Using default config")
    formatter.step("Step 1: Validating configuration")
    formatter.hint("Run 'homestack help' for more info")
    formatter.command("Executing: docker-compose up -d")
    formatter.result("Services ready at http://localhost:3000")
    formatter.debug("Debug: variable x = 42")
    formatter.title("🎯 Deployment Summary")
    
    # Complex formatting
    formatter.panel("Setup Complete", "Your services are ready")
    formatter.table({"Host": "localhost", "Port": "3000"})
    formatter.code_block("docker ps -a", language="bash")
    formatter.list_items(["Item 1", "Item 2", "Item 3"])
    formatter.horizontal_rule()
"""

from typing import Any, Dict, List, Optional, Union

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text


class RichFormatter:
    """Abstraction layer for beautiful, context-aware console output using Rich."""

    # Message type configuration: emoji, color, and formatting styles
    _MESSAGE_CONFIG = {
        "info": {"emoji": "💡", "color": "cyan", "format": ["bold"]},
        "error": {"emoji": "✗", "color": "red", "format": ["bold"]},
        "warning": {"emoji": "⚠", "color": "yellow", "format": ["bold"]},
        "debug": {"emoji": "🐛", "color": "magenta", "format": ["dim"]},
        "success": {"emoji": "✓", "color": "green", "format": ["bold"]},
        "hint": {"emoji": "💬", "color": "blue", "format": ["italic"]},
        "step": {"emoji": "▶", "color": "white", "format": ["bold"]},
        "command": {"emoji": "⚙", "color": "bright_cyan", "format": ["bold"]},
        "result": {"emoji": "🎯", "color": "bright_green", "format": ["bold"]},
        "title": {"emoji": "★", "color": "bright_white", "format": ["bold", "underline"]},
    }

    def __init__(self) -> None:
        """Initialize the formatter with a Rich Console instance."""
        self._console = Console()

    def _render_message(
        self,
        message_type: str,
        text: str,
        details: Optional[str] = None,
        prefix: bool = True,
        title: Optional[str] = None,
    ) -> None:
        """
        Render a formatted message to console.

        Args:
            message_type: Type of message (info, error, warning, etc.)
            text: Main message text
            details: Optional supplementary details (shown in dim text)
            prefix: Whether to include emoji prefix
            title: Optional title for panel-wrapped messages
        """
        if message_type not in self._MESSAGE_CONFIG:
            raise ValueError(f"Unknown message type: {message_type}")

        config = self._MESSAGE_CONFIG[message_type]
        emoji = config["emoji"] if prefix else ""
        color = config["color"]
        formats = config["format"]

        # Build the main message text with emoji and formatting
        if emoji:
            message_text = Text(f"{emoji} {text}", style=f"{color} {' '.join(formats)}")
        else:
            message_text = Text(text, style=f"{color} {' '.join(formats)}")

        # If details provided, append as dim secondary text
        if details:
            message_text.append("\n")
            message_text.append(details, style="dim")

        # Render with or without panel
        if title:
            panel = Panel(message_text, title=title, expand=False, style=f"{color} dim")
            self._console.print(panel)
        elif details:
            # Use panel for messages with details (better visual hierarchy)
            panel = Panel(
                message_text,
                title=f"{emoji} {message_type.upper()}" if prefix else message_type.upper(),
                expand=False,
                style=f"{color} dim",
            )
            self._console.print(panel)
        else:
            # Simple line output for basic messages
            self._console.print(message_text)

    def info(
        self,
        text: str,
        details: Optional[str] = None,
        prefix: bool = True,
        title: Optional[str] = None,
    ) -> None:
        """Print an informational message."""
        self._render_message("info", text, details, prefix, title)

    def error(
        self,
        text: str,
        details: Optional[str] = None,
        prefix: bool = True,
        title: Optional[str] = None,
    ) -> None:
        """Print an error message."""
        self._render_message("error", text, details, prefix, title)

    def warning(
        self,
        text: str,
        details: Optional[str] = None,
        prefix: bool = True,
        title: Optional[str] = None,
    ) -> None:
        """Print a warning message."""
        self._render_message("warning", text, details, prefix, title)

    def debug(
        self,
        text: str,
        details: Optional[str] = None,
        prefix: bool = True,
        title: Optional[str] = None,
    ) -> None:
        """Print a debug message."""
        self._render_message("debug", text, details, prefix, title)

    def success(
        self,
        text: str,
        details: Optional[str] = None,
        prefix: bool = True,
        title: Optional[str] = None,
    ) -> None:
        """Print a success message."""
        self._render_message("success", text, details, prefix, title)

    def hint(
        self,
        text: str,
        details: Optional[str] = None,
        prefix: bool = True,
        title: Optional[str] = None,
    ) -> None:
        """Print a hint/suggestion message."""
        self._render_message("hint", text, details, prefix, title)

    def step(
        self,
        text: str,
        details: Optional[str] = None,
        prefix: bool = True,
        title: Optional[str] = None,
    ) -> None:
        """Print a step indicator for multi-step processes."""
        self._render_message("step", text, details, prefix, title)

    def command(
        self,
        text: str,
        details: Optional[str] = None,
        prefix: bool = True,
        title: Optional[str] = None,
    ) -> None:
        """Print a command/action being executed."""
        self._render_message("command", text, details, prefix, title)

    def result(
        self,
        text: str,
        details: Optional[str] = None,
        prefix: bool = True,
        title: Optional[str] = None,
    ) -> None:
        """Print a result/outcome message."""
        self._render_message("result", text, details, prefix, title)

    def title(
        self,
        text: str,
        details: Optional[str] = None,
        prefix: bool = True,
        title: Optional[str] = None,
    ) -> None:
        """Print a title/section header."""
        self._render_message("title", text, details, prefix, title)

    def panel(
        self,
        title: str,
        content: str,
        style: str = "blue dim",
        expand: bool = False,
    ) -> None:
        """
        Render content in a titled panel.

        Args:
            title: Panel title
            content: Panel content
            style: Rich style string for the panel
            expand: Whether to expand panel to full width
        """
        panel = Panel(content, title=title, style=style, expand=expand)
        self._console.print(panel)

    def table(
        self,
        data: Union[Dict[str, Any], List[Dict[str, Any]]],
        title: Optional[str] = None,
    ) -> None:
        """
        Render data as a formatted table.

        Args:
            data: Dictionary (single row) or list of dicts (multiple rows)
            title: Optional table title
        """
        if isinstance(data, dict):
            # Single row: render as key-value table
            table = Table(title=title, show_header=False, box=None, expand=False)
            table.add_column("Key", style="cyan bold")
            table.add_column("Value", style="green")
            for key, value in data.items():
                table.add_row(str(key), str(value))
        else:
            # Multiple rows: render as columnar table
            if not data:
                return
            table = Table(title=title, expand=False)
            first_row = data[0]
            for key in first_row.keys():
                table.add_column(key, style="cyan bold")
            for row in data:
                table.add_row(*[str(v) for v in row.values()])

        self._console.print(table)

    def code_block(
        self,
        code: str,
        language: str = "python",
        theme: str = "monokai",
        line_numbers: bool = False,
    ) -> None:
        """
        Render a syntax-highlighted code block.

        Args:
            code: Code content
            language: Programming language for syntax highlighting
            theme: Pygments theme (e.g., 'monokai', 'github-dark')
            line_numbers: Whether to show line numbers
        """
        syntax = Syntax(
            code,
            language,
            theme=theme,
            line_numbers=line_numbers,
            word_wrap=True,
            background_color="default",
        )
        self._console.print(syntax)

    def list_items(
        self,
        items: List[str],
        bullet: str = "•",
        color: str = "cyan",
    ) -> None:
        """
        Render a formatted bullet list.

        Args:
            items: List of items to display
            bullet: Bullet character
            color: Color for bullet points
        """
        for item in items:
            self._console.print(f"[{color}]{bullet}[/{color}] {item}")

    def horizontal_rule(
        self,
        char: str = "─",
        color: str = "dim white",
    ) -> None:
        """
        Render a horizontal separator line.

        Args:
            char: Character to use for the rule
            color: Color for the rule
        """
        self._console.rule(style=color)

    def status_line(
        self,
        status: str,
        info: str,
        status_color: str = "cyan",
        separator: str = "→",
    ) -> None:
        """
        Render a status line with info.

        Args:
            status: Status/state text
            info: Additional info text
            status_color: Color for status text
            separator: Separator between status and info
        """
        status_text = Text(status, style=f"{status_color} bold")
        status_text.append(f" {separator} ", style="dim")
        status_text.append(info, style="white")
        self._console.print(status_text)

    def key_value_pairs(
        self,
        data: Dict[str, Any],
        key_color: str = "cyan",
        value_color: str = "green",
    ) -> None:
        """
        Render key-value pairs in aligned format.

        Args:
            data: Dictionary of key-value pairs
            key_color: Color for keys
            value_color: Color for values
        """
        if not data:
            return
        max_key_len = max(len(str(k)) for k in data.keys())
        for key, value in data.items():
            key_text = str(key).ljust(max_key_len)
            self._console.print(
                f"[{key_color}]{key_text}[/{key_color}] : [{value_color}]{value}[/{value_color}]"
            )

    def success_summary(
        self,
        items: Union[Dict[str, str], List[str]],
        title: str = "✓ Summary",
    ) -> None:
        """
        Render a success summary with checkmarks.

        Args:
            items: Dictionary of label-value pairs or list of strings
            title: Summary title
        """
        self._console.print(f"[green bold]{title}[/green bold]")
        if isinstance(items, dict):
            for label, value in items.items():
                self._console.print(f"  [green]✓[/green] [white]{label}:[/white] {value}")
        else:
            for item in items:
                self._console.print(f"  [green]✓[/green] {item}")


# Global singleton instance
formatter = RichFormatter()
