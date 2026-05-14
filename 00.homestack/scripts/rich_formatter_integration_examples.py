"""
Integration examples showing how to use rich_formatter in your CLI commands.

This file demonstrates the recommended patterns for replacing typer.echo() calls
with the rich_formatter module throughout the codebase.
"""

# ============================================================================
# BEFORE: Using typer.echo() (current pattern in cli.py)
# ============================================================================

def example_before_init_command():
    """Example: old pattern using typer.echo()."""
    import typer
    
    # Current pattern: simple string concatenation with emoji
    typer.echo("✓ Environment initialized successfully")
    
    # With variables: requires f-string
    project_name = "my-service"
    typer.echo(f"✓ Created project: {project_name}")
    
    # Error case: using err=True parameter
    typer.echo("Error: Invalid configuration", err=True)
    
    # Warning case: emoji prefix
    typer.echo("⚠ Using default configuration")


# ============================================================================
# AFTER: Using rich_formatter (recommended pattern)
# ============================================================================

def example_after_init_command():
    """Example: new pattern using rich_formatter."""
    from utils.rich_formatter import formatter
    
    # Simple success message
    formatter.success("Environment initialized successfully")
    
    # With variables: cleaner, no f-string needed
    project_name = "my-service"
    formatter.success(f"Created project: {project_name}")
    
    # Error case: dedicated error method
    formatter.error("Invalid configuration")
    
    # Warning case: dedicated warning method
    formatter.warning("Using default configuration")


# ============================================================================
# INTEGRATION PATTERNS
# ============================================================================

def pattern_success_with_details():
    """Display success with supplementary information."""
    from utils.rich_formatter import formatter
    
    formatter.success(
        "Deployment completed successfully",
        details="All services are running and health checks passed.",
    )


def pattern_multi_step_process():
    """Display a multi-step process with progress indicators."""
    from utils.rich_formatter import formatter
    
    formatter.title("🚀 Initializing HomeStack")
    formatter.horizontal_rule()
    
    formatter.step("Step 1: Validating environment")
    formatter.info("Checking Docker installation...")
    formatter.success("Docker is installed")
    
    formatter.horizontal_rule()
    
    formatter.step("Step 2: Loading configuration")
    formatter.command("Reading configuration from 00.env/")
    formatter.success("Configuration loaded")
    
    formatter.horizontal_rule()
    
    formatter.step("Step 3: Initializing project")
    formatter.command("Creating project directories")
    formatter.success("Project initialized successfully")
    
    formatter.horizontal_rule()
    formatter.result("All steps completed successfully!")


def pattern_error_with_hints():
    """Display errors with helpful hints."""
    from utils.rich_formatter import formatter
    
    formatter.error("Connection to database failed")
    formatter.hint("Ensure the database container is running: docker-compose up -d postgres")
    formatter.hint("Check connectivity: docker-compose logs postgres")


def pattern_table_display():
    """Display tabular data (services, status, etc.)."""
    from utils.rich_formatter import formatter
    
    formatter.title("Service Status")
    formatter.table(
        [
            {"Service": "web-app", "Status": "✓ Running", "Port": "8000"},
            {"Service": "database", "Status": "✓ Running", "Port": "5432"},
            {"Service": "redis", "Status": "✓ Running", "Port": "6379"},
            {"Service": "backup", "Status": "⏸ Stopped", "Port": "—"},
        ],
        title="Services",
    )


def pattern_summary_after_deploy():
    """Display a summary after deployment completion."""
    from utils.rich_formatter import formatter
    
    formatter.title("✓ Deployment Complete")
    formatter.success_summary(
        {
            "Dashboard": "http://localhost:8080",
            "API": "http://localhost:8000",
            "Admin Panel": "http://localhost:9000",
            "Metrics": "http://localhost:9090",
        },
        title="🎯 Services Available At",
    )
    formatter.hint("Run 'homestack list' to see all services")


def pattern_code_example():
    """Display code examples or commands."""
    from utils.rich_formatter import formatter
    
    formatter.step("Next Steps")
    formatter.hint("Deploy services with:")
    formatter.code_block(
        """
homestack deploy web-app
homestack deploy database
homestack status
""".strip(),
        language="bash",
    )


def pattern_progress_feedback():
    """Provide feedback during long-running operations."""
    import time

    from utils.rich_formatter import formatter
    
    steps = [
        ("Validating configuration", 0.5),
        ("Building Docker images", 1.0),
        ("Creating containers", 0.7),
        ("Starting services", 0.8),
        ("Running health checks", 0.5),
    ]
    
    formatter.title("🚀 Deployment in Progress")
    
    for step_name, duration in steps:
        formatter.status_line("In Progress", step_name, status_color="cyan")
        time.sleep(duration)  # Simulate work
        formatter.success(f"✓ {step_name}")
    
    formatter.horizontal_rule()
    formatter.success("Deployment completed successfully!")


def pattern_configuration_display():
    """Display configuration settings."""
    from utils.rich_formatter import formatter
    
    formatter.title("🔧 Configuration")
    formatter.key_value_pairs(
        {
            "Environment": "production",
            "Region": "us-east-1",
            "Database": "postgresql",
            "Cache": "redis",
            "Log Level": "info",
            "Max Workers": "4",
        }
    )


# ============================================================================
# MIGRATION PATH: Replace in cli.py
# ============================================================================

# Example locations in cli.py that should be updated:
#
# Line 345:  typer.echo(f"✓ {msg}")
#   → formatter.success(msg)
#
# Line 400:  typer.echo(f"✓ {msg}")
#   → formatter.success(msg)
#
# Line 156-195: _friendly_api_error_message() function
#   → formatter.error(title, details=error_details)
#
# Line 732, 786, 799: typer.echo(f"⚠ {message}")
#   → formatter.warning(message)
#
# Line 1231: console.print(ProjectTableBuilder.build(...))
#   → Can still use this, or switch to formatter.table()
#
# Line 1331, 1571: Panel-based output
#   → Can migrate to formatter.panel() for consistency

print(__doc__)
print("\n✓ Integration examples are ready to use!")
print("See pattern functions above for recommended usage in cli.py")
