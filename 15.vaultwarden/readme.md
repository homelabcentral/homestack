---
author: Homelab Central
project_name: Vaultwarden
project_description: Unofficial Bitwarden compatible server written in Rust, formerly known as bitwarden_rs 
project_source: https://github.com/dani-garcia/vaultwarden
project_website: https://github.com/dani-garcia/vaultwarden
project_docs: https://github.com/dani-garcia/vaultwarden/wiki
project_status: Active
stable_images:
  - vaultwarden/server:1.35.8
  - ghcr.io/dani-garcia/vaultwarden:1.35.8
stable_versions:
  - 1.35.8
latest_images:
  - ghcr.io/dani-garcia/vaultwarden:latest
  - vaultwarden/server:latest
latest_versions:
  - latest
warning: none
date: 2026-04-30
last_updated: 2026-04-30
required_env_files:
  - host.env
  - network.env
  - email.env
config_files:
  - config_file:
      path: ports.yml
      immutable: true
supported_architecture:
  - x86_64
  - arm64
ready_to_deploy: true
---