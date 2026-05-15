---
author: Homelab Central
project_name: Karakeep
project_description: A self-hostable bookmark-everything app (links, notes and images) with AI-based automatic tagging and full text search.
project_source: https://github.com/karakeep-app/karakeep
project_website: https://karakeep.app/
project_docs: https://docs.karakeep.app/
project_status: Active
stable_images:
  - ghcr.io/karakeep-app/karakeep:release
stable_versions:
  - 0.30.1
latest_images:
  - ghcr.io/karakeep-app/karakeep:latest
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
      description: Add NEXTAUTH_SECRET in .env
      todo: Add a random string for `NEXTAUTH_SECRET` in .env file. Use `openssl rand -base64 36` command in a different terminal to generate this string. You do not need to save this elsewhere.
      required: true
  - step:
      number: 2
      description: Add MEILI_MASTER_KEY in .env
      todo: Add a random string for `MEILI_MASTER_KEY` in .env file. Use `openssl rand -base64 36` command in a different terminal to generate this string. You do not need to save this elsewhere.
      required: true
  - step:
      number: 3
      description: Add NEXTAUTH_URL in .env
      todo: Add external URL for `NEXTAUTH_URL` in .env file. This has to be the external URL if you have one or internal if you don't.
      required: true
  - step:
      number: 4
      description: Add OPENAI_API_KEY key
      todo: Add the API key for OPENAI as `OPENAI_API_KEY` in .env file. Or if you are using Ollama or other providers use 
      required: false
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
  - x86_64
  - arm64
ready_to_deploy: true
---