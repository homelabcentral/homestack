---
author: Homelab Central
project_name: Hat.sh
project_description: Encrypt and Decrypt files securely in your browser. 
project_source: https://github.com/sh-dv/hat.sh
project_website: https://hat.sh
project_docs: https://github.com/sh-dv/hat.sh
project_status: Not Active
stable_images:
  - shdv/hat.sh
stable_versions:
  - latest
latest_images:
  - shdv/hat.sh
latest_versions:
  - latest
warning: Maintenance
date: 2026-04-30
last_updated: 2026-04-30
required_env_files:
  - host.env
  - network.env
config_files:
  - config_file:
      path: ports.yml
      immutable: true
supported_architecture:
  - x86_64
  - arm64
ready_to_deploy: true
---