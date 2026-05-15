#!/usr/bin/env python3
"""
Compact demo script for user-facing rich formatter lifecycle messages.

Run from 00.homestack:
    python scripts/demo_user_messages_compact.py
"""

from utils.rich_formatter import formatter


def main() -> None:
    formatter.title("HomeStack Lifecycle Demo")
    formatter.step("Init")
    formatter.info("Collecting host preferences")
    formatter.success("Preferences saved")

    formatter.step("Pull")
    formatter.command("Fetching compose, env, and readme files")
    formatter.success("Project artifacts pulled")

    formatter.step("Deploy")
    formatter.command("Running docker compose up -d")
    formatter.warning("Container restart policy is set to unless-stopped")
    formatter.hint("Run homestack status to verify service health")

    formatter.result("Lifecycle finished")
    formatter.success_summary(
        {
            "List": "homestack list",
            "Status": "homestack status",
            "Logs": "docker compose logs -f",
        },
        title="Useful Follow-ups",
    )


if __name__ == "__main__":
    main()
