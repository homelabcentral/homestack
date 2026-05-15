---
author: Homelab Central
project_name: Omni Tools
project_description: Self-hosted collection of powerful web-based tools for everyday tasks. No ads, no tracking, just fast, accessible utilities right from your browser! 
project_source: https://github.com/iib0011/omni-tools
project_website: https://omnitools.app/
project_docs: https://github.com/iib0011/omni-tools
project_status: Active
stable_images:
  - iib0011/omni-tools:latest
stable_versions:
  - latest
latest_images:
  - iib0011/omni-tools:latest
latest_versions:
  - latest
warning: none
date: 2026-05-01
last_updated: 2026-05-01
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