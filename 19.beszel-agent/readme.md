---
author: Homelab Central
project_name: Beszel Agent
project_description: Beszel Agent for collecting host and Docker metrics and forwarding them to Beszel Hub.
project_source: https://github.com/henrygd/beszel
project_website: https://beszel.dev/
project_docs: https://beszel.dev/guide/getting-started
project_status: Active
stable_images:
  - henrygd/beszel-agent:latest
stable_versions:
  - latest
latest_images:
  - henrygd/beszel-agent:latest
latest_versions:
  - latest
warning: none
date: 2026-05-02
last_updated: 2026-05-02
required_env_files:
  - host.env
  - network.env
pre_install_steps:
  - step:
      number: 1
      description: Get token and public key from Beszel Hub
      todo: In Beszel Hub, choose Add system, copy the token and public key, then run `homestack deploy beszel-agent` on the host to monitor and enter those values when prompted.
supported_architecture:
  - x86_64
  - arm64
ready_to_deploy: true
---

# Beszel Agent

This project deploys a Beszel Agent container in host network mode and connects it to a Beszel Hub instance.

It mounts `/var/run/docker.sock` read-only and stores agent state under `${DIR_DATA}`. Configure `HUB_URL_BA_BESZEL_AGENT`, `BESZEL_AGENT_TOKEN`, and `BESZEL_AGENT_KEY` in the generated `.env` file to complete registration.
