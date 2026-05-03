import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import questionary
from questionary import Choice, Separator, Style, form

HOMESTACK_STYLE = Style(
    [
        ("qmark", "fg:#7c6af7 bold"),
        ("question", "fg:#e2e8f0 bold"),
        ("answer", "fg:#a3e635 bold"),
        ("pointer", "fg:#7c6af7 bold"),
        ("highlighted", "fg:#f0abfc bold"),
        ("selected", "fg:#a3e635"),
        ("separator", "fg:#475569 italic"),
        ("instruction", "fg:#64748b italic"),
        ("text", "fg:#cbd5e1"),
        ("disabled", "fg:#475569 italic"),
        ("search_success", "noinherit fg:#4ade80 bold"),
        ("search_none", "noinherit fg:#f87171 bold"),
        ("completion-menu.completion", "bg:#1e1b2e fg:#cbd5e1"),
        ("completion-menu.completion.current", "bg:#7c6af7 fg:#ffffff bold"),
        ("completion-menu.meta.completion", "bg:#1e1b2e fg:#475569"),
        ("completion-menu.meta.completion.current", "bg:#7c6af7 fg:#e2e8f0"),
    ]
)

S = HOMESTACK_STYLE

print()

answers = form(
    # ── select ────────────────────────────────────────────────────────────
    dns_resolver=questionary.select(
        "Choose a DNS resolver:",
        style=S,
        choices=[
            Choice("Pihole + Unbound  (recommended)", value="pihole-unbound"),
            Choice("Pihole only", value="pihole"),
            Choice("System default", value="system"),
        ],
    ),
    # ── select with separators + disabled ─────────────────────────────────
    gpu_profile=questionary.select(
        "Select GPU transcoding profile:",
        style=S,
        choices=[
            Separator("── Hardware ──"),
            Choice("NVIDIA NVENC", value="nvenc"),
            Choice("Intel QSV", value="qsv"),
            Choice("AMD AMF", value="amf"),
            Separator("── Software ──"),
            Choice("CPU (software)", value="cpu"),
            Choice("VirtualBox (not supported)", value="vbox", disabled="unsupported"),
        ],
    ),
    # ── checkbox ──────────────────────────────────────────────────────────
    features=questionary.checkbox(
        "Which optional features do you want to enable?",
        style=S,
        choices=[
            Choice("Traefik reverse proxy", value="traefik", checked=True),
            Choice("Watchtower auto-update", value="watchtower"),
            Choice("Dozzle log viewer", value="dozzle", checked=True),
            Choice("Uptime Kuma monitor", value="uptime"),
            Separator("── Storage ──"),
            Choice("Filebrowser", value="filebrowser"),
            Choice("Immich photo manager", value="immich"),
        ],
    ),
    # ── path ──────────────────────────────────────────────────────────────
    media_path=questionary.path(
        "Media library path:",
        default="/mnt/media",
        style=S,
    ),
    # ── autocomplete ──────────────────────────────────────────────────────
    project=questionary.autocomplete(
        "Search for a project to deploy:",
        style=S,
        choices=[
            "pihole-unbound",
            "traefik",
            "vaultwarden",
            "immich",
            "plex",
            "filebrowser",
            "linkwarden",
            "homepage",
            "karakeep",
            "dozzle",
            "beszel",
            "gatus",
        ],
    ),
    # ── rawselect ─────────────────────────────────────────────────────────
    target=questionary.rawselect(
        "Confirm deployment target:",
        style=S,
        choices=[
            Choice("Production", value="prod"),
            Choice("Staging", value="staging"),
            Choice("Local dev", value="local"),
        ],
    ),
).ask()

if answers is None:
    print("\nCancelled.")
else:
    print("\n── Collected answers ─────────────────────────")
    for key, value in answers.items():
        print(f"  {key}: {value}")
    print()
