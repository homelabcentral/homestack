#!/usr/bin/env python3
"""
Demo script showcasing the rich_formatter module with all message types and features.

Run this to see the beautiful formatted output:
    cd 00.homestack
    python scripts/demo_rich_formatter.py
"""

from utils.rich_formatter import formatter

# ============================================================================
# Basic Message Types (10 types with emoji and colors)
# ============================================================================
print("\n" + "=" * 70)
print("BASIC MESSAGE TYPES (10 types with emoji and formatting)")
print("=" * 70)

formatter.info("This is an informational message (cyan, bold)")
formatter.error("This is an error message (red, bold)")
formatter.warning("This is a warning message (yellow, bold)")
formatter.debug("This is a debug message (magenta, dim)")
formatter.success("This is a success message (green, bold)")
formatter.hint("This is a hint message (blue, italic)")
formatter.step("This is a step indicator (white, bold)")
formatter.command("This is a command being executed (bright cyan, bold)")
formatter.result("This is a result message (bright green, bold)")
formatter.title("This is a title/header (bright white, bold, underline)")

# ============================================================================
# Messages with Details (panels with visual hierarchy)
# ============================================================================
print("\n" + "=" * 70)
print("MESSAGES WITH DETAILS (shown in panels)")
print("=" * 70)

formatter.info(
    "Starting deployment",
    details="Validating configuration files and dependencies...",
)

formatter.error(
    "Connection timeout occurred",
    details="Failed to connect to database after 30 seconds. Check network connectivity.",
)

formatter.success(
    "Deployment completed successfully",
    details="All services are running and health checks passed.",
)

# ============================================================================
# Messages with Custom Options (prefix, title)
# ============================================================================
print("\n" + "=" * 70)
print("MESSAGES WITH OPTIONS (prefix=False, custom titles)")
print("=" * 70)

formatter.info("Message without emoji prefix", prefix=False)

formatter.warning(
    "Configuration loaded from defaults",
    title="⚙ Configuration Notice",
)

# ============================================================================
# Helper Methods: Panel
# ============================================================================
print("\n" + "=" * 70)
print("HELPER METHOD: panel()")
print("=" * 70)

formatter.panel(
    "🎯 Setup Complete",
    """Your homestack is ready to deploy!

Services are available at:
  • Web UI: http://localhost:8080
  • API: http://localhost:8000
  • Admin Panel: http://localhost:9000

Run 'homestack list' to see all available services.""",
)

# ============================================================================
# Helper Methods: Table
# ============================================================================
print("\n" + "=" * 70)
print("HELPER METHOD: table()")
print("=" * 70)

print("\nSingle-row table (dict):")
formatter.table(
    {
        "Host": "homelab.local",
        "Port": "8080",
        "Status": "Running",
        "Uptime": "45 days",
    },
    title="System Status",
)

print("\nMulti-row table (list of dicts):")
formatter.table(
    [
        {"Service": "Nginx", "Status": "✓ Running", "Memory": "64 MB"},
        {"Service": "PostgreSQL", "Status": "✓ Running", "Memory": "256 MB"},
        {"Service": "Redis", "Status": "✓ Running", "Memory": "128 MB"},
        {"Service": "Backup", "Status": "⏸ Paused", "Memory": "0 MB"},
    ],
    title="Service Status",
)

# ============================================================================
# Helper Methods: Code Block
# ============================================================================
print("\n" + "=" * 70)
print("HELPER METHOD: code_block()")
print("=" * 70)

formatter.code_block(
    """docker-compose up -d
docker-compose ps
docker-compose logs -f web-app""",
    language="bash",
    line_numbers=True,
)

# ============================================================================
# Helper Methods: List Items
# ============================================================================
print("\n" + "=" * 70)
print("HELPER METHOD: list_items()")
print("=" * 70)

formatter.list_items(
    [
        "Install Docker and Docker Compose",
        "Clone the homestack repository",
        "Configure environment variables",
        "Run 'make deploy' to start services",
        "Access dashboard at http://localhost:8080",
    ],
    bullet="✓",
    color="green",
)

# ============================================================================
# Helper Methods: Horizontal Rule
# ============================================================================
print("\n" + "=" * 70)
print("HELPER METHOD: horizontal_rule()")
print("=" * 70)

formatter.horizontal_rule()

# ============================================================================
# Specialized Formatters: Status Line
# ============================================================================
print("\n" + "=" * 70)
print("SPECIALIZED FORMATTER: status_line()")
print("=" * 70)

formatter.status_line("Deploying", "services/web-app")
formatter.status_line("Completed", "all 5 services are running", separator="✓")
formatter.status_line("Failed", "connection to redis", separator="✗", status_color="red")

# ============================================================================
# Specialized Formatters: Key-Value Pairs
# ============================================================================
print("\n" + "=" * 70)
print("SPECIALIZED FORMATTER: key_value_pairs()")
print("=" * 70)

formatter.key_value_pairs(
    {
        "Environment": "production",
        "Region": "us-east-1",
        "Version": "1.2.3",
        "License": "MIT",
    }
)

# ============================================================================
# Specialized Formatters: Success Summary
# ============================================================================
print("\n" + "=" * 70)
print("SPECIALIZED FORMATTER: success_summary()")
print("=" * 70)

print("\nWith dict:")
formatter.success_summary(
    {
        "Web Server": "http://localhost:8080",
        "API Endpoint": "http://localhost:8000/api",
        "Admin Panel": "http://localhost:9000",
        "Metrics": "http://localhost:9090",
    },
    title="🚀 Deployment Successful",
)

print("\nWith list:")
formatter.success_summary(
    [
        "Configuration validated",
        "Dependencies installed",
        "Database migrations completed",
        "Health checks passed",
        "Services are ready",
    ],
    title="✓ Ready to Deploy",
)

# ============================================================================
# All Combined: A Realistic Deployment Scenario
# ============================================================================
print("\n" + "=" * 70)
print("REALISTIC SCENARIO: Multi-step deployment flow")
print("=" * 70)

formatter.title("🚀 HomeStack Deployment")
formatter.step("Step 1: Validating configuration")
formatter.info("Loading environment variables from 00.env/")
formatter.success("Configuration validated successfully")

formatter.horizontal_rule(char="·")

formatter.step("Step 2: Building services")
formatter.command("Executing: docker-compose build")
formatter.debug("Building service: web-app (progress: 75%)")
formatter.success("All services built successfully")

formatter.horizontal_rule(char="·")

formatter.step("Step 3: Starting services")
formatter.command("Executing: docker-compose up -d")
formatter.info("Services starting...", details="This may take 30-60 seconds")
formatter.success("All services started successfully")

formatter.horizontal_rule(char="·")

formatter.title("✓ Deployment Complete")
formatter.success_summary(
    {
        "Dashboard": "http://localhost:8080",
        "API": "http://localhost:8000",
        "Admin": "http://localhost:9000",
    }
)

formatter.hint("Run 'homestack status' to monitor your services")

print("\n" + "=" * 70)
print("Demo completed! Explore the rich_formatter in your CLI application.")
print("=" * 70 + "\n")
