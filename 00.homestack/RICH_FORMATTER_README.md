# Rich Formatter Module

A beautiful, consistent abstraction layer for printing visually rich messages to the console using the [Rich](https://github.com/Textualize/rich) library.

## Features

✨ **10 Message Types** with contextual emoji, colors, and formatting:
- 💡 **info** — cyan, bold
- ✗ **error** — red, bold
- ⚠ **warning** — yellow, bold
- 🐛 **debug** — magenta, dim
- ✓ **success** — green, bold
- 💬 **hint** — blue, italic
- ▶ **step** — white, bold
- ⚙ **command** — bright cyan, bold
- 🎯 **result** — bright green, bold
- ★ **title** — bright white, bold, underline

🎨 **Helper Methods** for complex formatting:
- `panel()` — titled panels with custom styling
- `table()` — render dictionaries or lists as formatted tables
- `code_block()` — syntax-highlighted code with line numbers
- `list_items()` — formatted bullet lists with custom colors
- `horizontal_rule()` — visual separator lines

🔧 **Specialized Formatters** for common CLI patterns:
- `status_line()` — horizontal status → info format
- `key_value_pairs()` — aligned key-value display
- `success_summary()` — summary lists with green checkmarks

## Installation & Usage

The module provides a global singleton instance for zero-import friction:

```python
from utils.rich_formatter import formatter

# 10 message types (all with optional details, prefix, title parameters)
formatter.info("Starting deployment")
formatter.success("Deployment complete")
formatter.error("Connection failed", details="Check your network")
formatter.warning("Using default configuration")
formatter.step("Step 1: Validating configuration")
formatter.hint("Run 'homestack help' for more info")
formatter.command("Executing: docker-compose up -d")
formatter.result("Services ready at http://localhost:3000")
formatter.debug("Debug: variable x = 42")
formatter.title("🎯 Deployment Summary")

# Helper methods
formatter.panel("Setup Complete", "Your services are ready")
formatter.table({"Host": "localhost", "Port": "3000"})
formatter.code_block("docker ps -a", language="bash")
formatter.list_items(["Item 1", "Item 2", "Item 3"])
formatter.horizontal_rule()

# Specialized formatters
formatter.status_line("Deploying", "services/web-app")
formatter.key_value_pairs({"Environment": "production", "Region": "us-east-1"})
formatter.success_summary({"Dashboard": "http://localhost:8080", "API": "http://localhost:8000"})
```

## Message Type Details

### Basic Message Type Methods

Each message type accepts the same parameters:

```python
def message_type(
    text: str,
    details: Optional[str] = None,  # Shown in dim text within a panel
    prefix: bool = True,             # Include emoji prefix
    title: Optional[str] = None,     # Use panel with custom title
) -> None
```

### Examples

**Simple message:**
```python
formatter.info("Loading configuration")
# Output: 💡 Loading configuration
```

**With details (renders in panel):**
```python
formatter.error("Connection failed", details="Timeout after 30 seconds")
# Output:
# ╭────────────── ✗ ERROR ──────────────╮
# │ ✗ Connection failed               │
# │ Timeout after 30 seconds          │
# ╰───────────────────────────────────╯
```

**Without emoji prefix:**
```python
formatter.warning("Configuration incomplete", prefix=False)
# Output: Configuration incomplete
```

**With custom title (renders in panel):**
```python
formatter.info("Database migrated", title="🔧 Maintenance")
# Output:
# ╭──────── 🔧 Maintenance ────────╮
# │ 💡 Database migrated           │
# ╰────────────────────────────────╯
```

## Helper Methods

### panel(title, content, style="blue dim", expand=False)

Render content in a titled panel:

```python
formatter.panel(
    "🎯 Deployment Complete",
    """Services available at:
  • Dashboard: http://localhost:8080
  • API: http://localhost:8000"""
)
```

### table(data, title=None)

Render tables from dictionaries or lists:

```python
# Single row (dict → key-value table)
formatter.table({"Host": "localhost", "Port": "3000", "Status": "Running"})

# Multiple rows (list of dicts → columnar table)
formatter.table([
    {"Name": "service1", "Status": "✓ Running"},
    {"Name": "service2", "Status": "✓ Running"},
])
```

### code_block(code, language="python", theme="monokai", line_numbers=False)

Display syntax-highlighted code:

```python
formatter.code_block(
    "docker-compose up -d && docker-compose logs -f",
    language="bash",
    line_numbers=True
)
```

### list_items(items, bullet="•", color="cyan")

Render formatted bullet lists:

```python
formatter.list_items(
    ["Install Docker", "Clone repository", "Run setup"],
    bullet="✓",
    color="green"
)
```

### horizontal_rule(char="─", color="dim white")

Display a visual separator:

```python
formatter.horizontal_rule()
formatter.horizontal_rule(char="=", color="cyan")
```

## Specialized Formatters

### status_line(status, info, status_color="cyan", separator="→")

Display status with associated information:

```python
formatter.status_line("Deploying", "services/web-app")
formatter.status_line("Complete", "all services running", separator="✓", status_color="green")
```

### key_value_pairs(data, key_color="cyan", value_color="green")

Display aligned key-value pairs:

```python
formatter.key_value_pairs({
    "Environment": "production",
    "Region": "us-east-1",
    "Uptime": "45 days"
})
```

### success_summary(items, title="✓ Summary")

Display a summary with green checkmarks:

```python
# With dict
formatter.success_summary({
    "Database": "✓ Connected",
    "Cache": "✓ Ready",
    "Queue": "✓ Running"
})

# With list
formatter.success_summary([
    "Configuration validated",
    "Dependencies installed",
    "Health checks passed"
])
```

## Real-World Example: Multi-Step Deployment

```python
from utils.rich_formatter import formatter

formatter.title("🚀 Starting Deployment")
formatter.horizontal_rule()

formatter.step("Step 1: Validate Configuration")
formatter.info("Loading environment variables...")
formatter.success("Configuration valid")

formatter.horizontal_rule()

formatter.step("Step 2: Build Services")
formatter.command("docker-compose build")
formatter.success("All services built")

formatter.horizontal_rule()

formatter.step("Step 3: Deploy")
formatter.command("docker-compose up -d")
formatter.success("Services deployed successfully")

formatter.horizontal_rule()

formatter.title("✓ Deployment Complete")
formatter.success_summary({
    "Dashboard": "http://localhost:8080",
    "API": "http://localhost:8000",
    "Metrics": "http://localhost:9090"
})

formatter.hint("Run 'homestack status' to monitor services")
```

## Integration with CLI

To integrate with existing `cli.py` commands, replace `typer.echo()` calls:

**Before:**
```python
typer.echo(f"✓ {msg}")
typer.echo("⚠ Using default config")
typer.echo(f"Error: {error_msg}", err=True)
```

**After:**
```python
from utils.rich_formatter import formatter

formatter.success(msg)
formatter.warning("Using default config")
formatter.error(error_msg)
```

See `scripts/rich_formatter_integration_examples.py` for detailed migration patterns.

## Demo

Run the demo scripts to see message types, formatting options, and practical
user-facing message flows:

```bash
python scripts/demo_rich_formatter.py
python scripts/demo_user_messages.py
python scripts/demo_user_messages_compact.py
```

## Testing

Comprehensive test suite with 113 test cases:

```bash
pytest tests/test_rich_formatter.py -v
```

**Test Coverage:**
- All 10 message types with basic usage
- Message types with details, custom prefixes, custom titles
- Configuration validation (emoji, color, formatting)
- Helper methods: panel, table, code_block, list_items, horizontal_rule
- Specialized formatters: status_line, key_value_pairs, success_summary
- Singleton behavior (same instance across imports)
- Error handling (invalid message types, special characters, multiline text)
- Console integration (mock verification of print calls, panel rendering)

## Architecture

```
RichFormatter (class)
├── _MESSAGE_CONFIG: dict with emoji/color/format per type
├── 10 message type methods (info, error, warning, etc.)
├── _render_message(): internal method for message rendering
├── Helper methods (panel, table, code_block, list_items, horizontal_rule)
└── Specialized formatters (status_line, key_value_pairs, success_summary)

formatter: global singleton instance
```

## Design Decisions

- **Global Singleton**: Simplifies API and reduces import clutter; aligns with existing `console` pattern in cli.py and questionary.py
- **Pure Output Abstraction**: No exit code handling; CLI commands retain responsibility via `typer.Exit()`
- **Separate from Logging**: rich_formatter handles user-facing console output; app_logger.py handles file-based logging
- **Rich Panel for Details**: Messages with details render in panels for better visual hierarchy
- **Thread-Safe**: Module-level singleton creation is safe in CPython due to GIL + import locks

## Future Considerations

1. **Color Scheme Customization**: Add support for `--no-color` flag respecting `NO_COLOR` environment variable
2. **Emoji Fallback**: For environments without emoji support, provide ASCII alternatives (e.g., `[!]` for `✗`)
3. **Internationalization**: Support for translated message types or customizable emoji/formatting
4. **Async Support**: If async output becomes needed, consider explicit lock around console.print()

## References

- [Rich Library Documentation](https://rich.readthedocs.io/)
- [Rich Style Reference](https://rich.readthedocs.io/en/latest/style.html)
- See `scripts/rich_formatter_integration_examples.py` for integration patterns
