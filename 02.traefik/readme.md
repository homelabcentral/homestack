---
author: Homelab Central
project_name: Traefik
project_description: The Cloud Native Application Proxy
project_source: https://github.com/traefik/traefik
project_website: https://traefik.io/
project_docs: https://doc.traefik.io/traefik/
project_status: Active
stable_images:
  - traefik:v3.6.14
  - traefik:v3.6
stable_versions:
  - v3.6.14
latest_images:
  - traefik:latest
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
      path: data/acme.json
      constant: true
      uid: UID
      gid: GID
      permissions: 600
  - config_file:
      path: data/traefik.yml
      constant: false
      uid: UID
      gid: GID
      permissions: 644
  - config_file:
      path: data/config.yml
      constant: false
      permissions: 644
      keys:
        key1: value1
        key2: value2
pre_install_steps:
  - step:
      number: 1
      description: Description of step 1
      todo: Todo for step 1
post_install_steps:
  - step:
      description: Description of post-install step 1
      todo: Todo for post-install step 1
post_setup_steps:
  - step:
      number: 1
      description: Description for post setup
      todo: Todo for post setup steps
supported_architecture:
  - amd64
  - x86
  - arm64
ready_to_deploy: true
---