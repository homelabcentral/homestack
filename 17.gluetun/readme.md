---
author: Homelab Central
project_name: Gluetun VPN
project_description: VPN client in a thin Docker container for multiple VPN providers, written in Go, and using OpenVPN or Wireguard, DNS over TLS, with a few proxy servers built-in.
project_source: https://github.com/qdm12/gluetun
project_website: https://github.com/qdm12/gluetun
project_docs: https://github.com/qdm12/gluetun-wiki
project_status: Active
stable_images:
  - qmcgaw/gluetun:latest
latest_images:
  - qmcgaw/gluetun:latest
warning: none
date: 2026-05-01
last_updated: 2026-05-01
required_env_files:
  - host.env
  - network.env
  - vpn.env
config_files:
  - config_file:
      path: ports.yml
      immutable: true
supported_architecture:
  - x86_64
  - arm64
ready_to_deploy: true
---