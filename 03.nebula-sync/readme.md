---
author: Homelab Central
project_name: Nebula Sync
project_description: Synchronize Pi-hole v6.x configuration to replicas.
project_source: https://github.com/lovelaze/nebula-sync
project_website: https://github.com/lovelaze/nebula-sync
project_docs: https://github.com/lovelaze/nebula-sync
project_status: Active
stable_images:
  - ghcr.io/lovelaze/nebula-sync:v0.11.1
  - lovelaze/nebula-sync:v0.11.1
stable_versions:
  - v0.11.1
latest_images:
  - ghcr.io/lovelaze/nebula-sync:latest
  - lovelaze/nebula-sync:latest
latest_versions:
  - v0.11.1
warning: This project is not a part of the official Pi-hole project, but uses the api provided by Pi-hole instances to perform the synchronization actions.
date: 2026-04-23
last_updated: 2026-04-23
required_env_files:
  - host.env
  - network.env
pre_install_steps:
  - step:
      number: 1
      description: Update Cron Job
      todo: Update the environment variable `CRON` in `docker-compose.yml` to run sync however frequently you want. Use https://crontab.guru/ if you need help to set this.
post_install_steps:
  - step:
      number: 1
      description: Check Docker Logs
      todo: Check docker logs for this container using `docker logs nebula-sync`
post_setup_steps:
  - step:
      number: 1
      description: Delete this step
      todo: Delete this step
supported_architecture:
  - x86_64
  - arm64
ready_to_deploy: true
---