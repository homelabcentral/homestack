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
config_files:
  - config_file:
      path: ports.yml
      immutable: true
  - config_file:
      path: dashboard.yml
      immutable: true
supported_architecture:
    - x86_64
    - arm64
ready_to_deploy: true
---

# Pihole With Unbound

Pihole is a network wide ad blocker and unbound is a DNS resolver. This container helps with resolving DNS records in your homelab at the same time blocking ads.

## How To Deploy

Deploy this project easily with a single command `homestack deploy pihole`. Follow the instructions properly to set it up correctly. If you want to make changes, you can edit the `docker-compose.yml` and `.env` files in `<path-to-your-homestack-directory/compose/pihole-with-unbound>` directory.

## Post-Install

After you have installed this project. You can go add block lists from [firebog](https://firebog.net/).
