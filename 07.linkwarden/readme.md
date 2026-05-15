---
author: Homelab Central
project_name: Linkwarden
project_description: Self-hosted collaborative bookmark manager to collect, read, annotate, and fully preserve what matters, all in one place. 
project_source: https://github.com/linkwarden/linkwarden
project_website: https://linkwarden.app/
project_docs: https://docs.linkwarden.app/
project_status: Active
stable_images:
  - ghcr.io/linkwarden/linkwarden:v2.14.1
stable_versions:
  - v2.14.1
latest_images:
  - ghcr.io/linkwarden/linkwarden:latest
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
      path: ports.yml
      immutable: true
pre_install_steps:
  - step:
      number: 1
      description: Change some .env variables
      todo: Change `NEXTAUTH_URL` to the external URL of the app, if you don't have one then internal URL is fine. Change `NEXTAUTH_SECRET` and `MEILI_MASTER_KEY` using `openssl rand -base64 32` to do this.
supported_architecture:
  - x86_64
  - arm64
ready_to_deploy: true
---