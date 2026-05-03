---
author: Homelab Central
project_name: Pihole with Unbound
project_description: A network wide ad blocker with unbound DNS resolver.
project_source: https://github.com/mpgirro/docker-pihole-unbound
project_website: https://github.com/mpgirro/docker-pihole-unbound
project_docs: https://github.com/mpgirro/docker-pihole-unbound
project_status: Active
stable_images:
    - mpgirro/pihole-unbound:2026.04.0
    - ghcr.io/mpgirro/docker-pihole-unbound:2026.04.0
stable_versions:
    - 2026.04.0
latest_images:
    - mpgirro/pihole-unbound:latest
    - ghcr.io/mpgirro/docker-pihole-unbound:latest
latest_versions:
    - 2026.04.0
warning: none
date: 2026-04-22
last_updated: 2026-04-22
required_env_files:
    - host.env
    - network.env
supported_architecture:
    - amd64
    - x86
    - arm64
ready_to_deploy: true
---