---
author: Homelab Central
project_name: StirlingPDF
project_description: No.1 PDF Application on GitHub that lets you edit PDFs on any device anywhere 
project_source: https://github.com/Stirling-Tools/Stirling-PDF
project_website: https://www.stirling.com/
project_docs: https://docs.stirlingpdf.com/
project_status: Active
stable_images:
  - stirlingtools/stirling-pdf:2.9.2-ultra-lite
  - stirlingtools/stirling-pdf:2.9.2-fat
  - stirlingtools/stirling-pdf:2.9.2
stable_versions:
  - 2.9.2
latest_images:
  - stirlingtools/stirling-pdf:latest-ultra-lite
  - stirlingtools/stirling-pdf:latest-fat
  - stirlingtools/stirling-pdf:latest
latest_versions:
  - latest
  - latest-fat
  - latest-ultra-lite
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
      description: Set username
      todo: Set your preferred username as `USERNAME_SP_STIRLINGPDF` in the .env
      required: false
    - step:
      number: 2
      description: Set password
      todo: Set your preferred password as `PASSWORD_SP_STIRLINGPDF` in the .env
      required: false
supported_architecture:
  - x86_64
  - arm64
ready_to_deploy: true
---