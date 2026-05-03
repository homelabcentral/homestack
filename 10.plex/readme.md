---
author: Homelab Central
project_name: Plex CPU
project_description: Plex Server With CPU Transcoding
project_source: https://github.com/linuxserver/docker-plex
project_website: https://github.com/linuxserver/docker-plex
project_docs: https://docs.linuxserver.io/images/docker-plex/#via-docker-compose
project_status: Active
stable_images:
  - lscr.io/linuxserver/plex:1.43.1
stable_versions:
  - 1.43.1
latest_images:
  - lscr.io/linuxserver/plex:latest
latest_versions:
  - latest
warning: none
date: 2026-04-30
last_updated: 2026-04-30
required_env_files:
  - host.env
  - network.env
post_setup_steps:
  - step:
      number: 1
      description: Update plex settings
      todo: After the container is up, go to settings -> network -> Custom server access URLs -> add "http://<ip_address>:32400,https://<ip_address>:32400" without quotes, where IP address is the ip address of the server hosting plex OR tailscale IP address.
      required: true
  - step:
      number: 2
      description: Update LAN networks IP addresses
      todo: Go to plex settings -> network -> LAN networks -> add your subnet -> eg. "192.168.0.1/24,10.0.0.1/24" etc. without quotes.
      required: true
supported_architecture:
  - amd64
  - x86
  - arm64
ready_to_deploy: true
---