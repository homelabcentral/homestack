---
author: Homelab Central
project_name: Homepage
project_description: A highly customizable homepage (or startpage / application dashboard) with Docker and service API integrations. 
project_source: https://github.com/gethomepage/homepage
project_website: https://gethomepage.dev/
project_docs: https://gethomepage.dev/configs/
project_status: Active
stable_images:
  - ghcr.io/gethomepage/homepage:v1.12.3
  - gethomepage/homepage:v1.12.3
stable_versions:
  - v1.12.3
  - v1.12
latest_images:
  - ghcr.io/gethomepage/homepage:latest
  - gethomepage/homepage:latest
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
      description: Configure your dashboard
      todo: Read the docs website to see as to how to customize the homepage
supported_architecture:
  - amd64
  - x86
  - arm64
ready_to_deploy: true
---