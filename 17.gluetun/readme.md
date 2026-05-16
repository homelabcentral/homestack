---
author: Homelab Central
project_name: Arr stack with Gluetun VPN
project_description: A full arr stack - sonarr, radarr, readarr, lidarr, bazarr, prowlarr, requestrr, flaresolverr with downloader qbittorrent and deluge along with firefox, metube and speedtest.
project_source: Multiple Sources
project_website: Multiple Websites
project_docs: Multiple Docs
project_status: Active
stable_images:
  - qmcgaw/gluetun
  - lscr.io/linuxserver/qbittorrent:latest
  - lscr.io/linuxserver/firefox:latest
  - henrywhitaker3/speedtest-tracker
  - lscr.io/linuxserver/prowlarr:develop
  - lscr.io/linuxserver/bazarr:latest
  - lscr.io/linuxserver/readarr:develop
  - lscr.io/linuxserver/lidarr:latest
  - lscr.io/linuxserver/radarr:latest
  - lscr.io/linuxserver/sonarr:latest
  - lscr.io/linuxserver/overseerr:latest
  - alexta69/metube:latest
  - ghcr.io/flaresolverr/flaresolverr:latest
  - thomst08/requestrr
  - lscr.io/linuxserver/deluge:latest
  - ghcr.io/hollanbm/renamarr:latest
latest_images:
  - qmcgaw/gluetun
  - lscr.io/linuxserver/qbittorrent:latest
  - lscr.io/linuxserver/firefox:latest
  - henrywhitaker3/speedtest-tracker
  - lscr.io/linuxserver/prowlarr:develop
  - lscr.io/linuxserver/bazarr:latest
  - lscr.io/linuxserver/readarr:develop
  - lscr.io/linuxserver/lidarr:latest
  - lscr.io/linuxserver/radarr:latest
  - lscr.io/linuxserver/sonarr:latest
  - lscr.io/linuxserver/overseerr:latest
  - alexta69/metube:latest
  - ghcr.io/flaresolverr/flaresolverr:latest
  - thomst08/requestrr
  - lscr.io/linuxserver/deluge:latest
  - ghcr.io/hollanbm/renamarr:latest
warning: none
date: 2026-05-01
last_updated: 2026-05-01
required_env_files:
  - host.env
  - network.env
  - vpn.env
supported_architecture:
  - x86_64
  - arm64
ready_to_deploy: true
---