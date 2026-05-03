---
author: Homelab Central
project_name: Beszel
project_description: Beszel Hub for monitoring systems and Docker workloads, with agents deployed separately per host.
project_source: https://github.com/henrygd/beszel
project_website: https://beszel.dev/
project_docs: https://beszel.dev/guide/getting-started
project_status: Active
stable_images:
  - henrygd/beszel:latest
stable_versions:
  - latest
latest_images:
  - henrygd/beszel:latest
latest_versions:
  - latest
warning: This stack deploys only Beszel Hub. Deploy Beszel Agent separately on each system you want to monitor.
date: 2026-05-02
last_updated: 2026-05-02
required_env_files:
  - host.env
  - network.env
post_install_steps:
  - step:
      number: 1
      description: Connect a monitored system
      todo: After Beszel Hub is running, open the Beszel UI, choose Add system, copy the token and public key, then deploy `homestack deploy beszel-agent` on the target host and provide those values during setup.
supported_architecture:
  - amd64
  - x86
  - arm64
ready_to_deploy: true
---

# Beszel

This project deploys the Beszel Hub service.

The hub stores monitoring data and exposes the web UI. Agents are not deployed in this compose file; use the separate Beszel Agent project for each monitored system.

The stack persists hub data and the Beszel socket under `${DIR_DATA}`, publishes the service via `${PORT_BZ_BESZEL_EXTERNAL:-3013}`, and includes Traefik labels for routed HTTPS access when Traefik is enabled.
