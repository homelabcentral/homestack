---
author: Homelab Central
project_name: Uptime Kuma
project_description: A fancy self-hosted monitoring tool 
project_source: https://github.com/louislam/uptime-kuma
project_website: https://uptime.kuma.pet/
project_docs: https://github.com/louislam/uptime-kuma/wiki
project_status: Active
stable_images:
  - ghcr.io/louislam/uptime-kuma:2.2.1-rootless
  - ghcr.io/louislam/uptime-kuma:2-rootless
stable_versions:
  - 2.2.1
latest_images:
  - ghcr.io/louislam/uptime-kuma:2-rootless
  - ghcr.io/louislam/uptime-kuma:2.2.1-rootless
latest_versions:
  - 2.2.1
warning: none
date: 2026-04-30
last_updated: 2026-04-30
required_env_files:
  - host.env
  - network.env
config_files:
  - config_file:
      path: ports.yml
      immutable: true
supported_architecture:
  - x86_64
  - arm64
ready_to_deploy: true
---