---
author: Homelab Central
project_name: Filebrowser
project_description: Web File Browser 
project_source: https://github.com/filebrowser/filebrowser
project_website: https://filebrowser.org/installation.html
project_docs: https://filebrowser.org/installation.html
project_status: Maintainance
stable_images:
  - filebrowser/filebrowser:s6
  - filebrowser/filebrowser
stable_versions:
  - s6
warning: none
date: 2026-04-30
last_updated: 2026-04-30
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
      description: Notedown password
      todo: Please note down the password, it won't be displayed again. If you forget or lose the password, you need to manually delete the database and start filebrowser again.
supported_architecture:
  - x86_64
  - arm64
ready_to_deploy: true
---