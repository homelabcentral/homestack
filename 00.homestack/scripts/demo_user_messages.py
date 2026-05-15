#!/usr/bin/env python3
"""
Demo script showing practical user-facing message flows with rich_formatter.

Run from 00.homestack:
    python scripts/demo_user_messages.py
"""

from utils.rich_formatter import formatter


def _section(name: str) -> None:
    print("\n" + "=" * 72)
    print(name)
    print("=" * 72)


def main() -> None:
    _section("WELCOME")
    formatter.title("HomeStack User Message Demo")
    formatter.info("This script demonstrates common user communication patterns")

    _section("STARTUP CHECKS")
    formatter.step("Step 1: Validate local environment")
    formatter.command("Checking Docker daemon")
    formatter.success("Docker is available")

    formatter.step("Step 2: Read configuration")
    formatter.command("Loading environment from 00.env/")
    formatter.info(
        "Loaded environment values",
        details="Using host.env, local.env, and network.env",
    )

    _section("ACTIONABLE WARNING")
    formatter.warning(
        "Optional value missing: VPN_COUNTRY",
        details="Continuing with default region for VPN-enabled services.",
    )
    formatter.hint("Set VPN_COUNTRY in 00.env/vpn.env if you need a specific region")

    _section("ERROR WITH RECOVERY")
    formatter.error(
        "Could not reach image registry",
        details="Network timeout while fetching image metadata.",
    )
    formatter.hint("Check internet connectivity and retry with: make pull")
    formatter.hint("If the issue persists, inspect logs with: docker compose logs")

    _section("SERVICE STATUS")
    formatter.table(
        [
            {"Service": "traefik", "Status": "Running", "Port": "80/443"},
            {"Service": "gatus", "Status": "Running", "Port": "8080"},
            {"Service": "linkwarden", "Status": "Starting", "Port": "3000"},
            {"Service": "immich", "Status": "Stopped", "Port": "2283"},
        ],
        title="Current Service Snapshot",
    )

    _section("SUCCESS SUMMARY")
    formatter.result("Deployment checks completed")
    formatter.success_summary(
        {
            "Dashboard": "http://localhost:8080",
            "Service List": "homestack list",
            "Deploy Command": "make deploy",
        },
        title="Next Actions",
    )
    formatter.horizontal_rule()
    formatter.hint("Run homestack ready-to-deploy to see recommended services")


if __name__ == "__main__":
    main()
