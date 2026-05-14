---
author: Homelab Central
project_name: Gatus
project_description: Automated developer-oriented status page with alerting and incident support.
project_source: https://github.com/TwiN/gatus
project_website: https://gatus.io/
project_docs: https://github.com/TwiN/gatus#configuration
project_status: Active
stable_images:
  - ghcr.io/twin/gatus:stable
  - twinproduction/gatus:stable
stable_versions:
  - v5.35.0
latest_images:
  - ghcr.io/twin/gatus:latest
  - twinproduction/gatus:latest
latest_versions:
  - latest
warning: none
date: 2026-04-23
last_updated: 2026-04-23
required_env_files:
  - host.env
  - network.env
config_files:
  - config_file:
      path: config/config.yml
      constant: true
pre_install_steps:
  - step:
      number: 1
      description: Configure config.yml
      todo: Configure config.yml according to your needs as to what you want to monitor. Docs are here - https://github.com/TwiN/gatus#configuration
supported_architecture:
  - x86_64
  - arm64
ready_to_deploy: true
---