---
author: Homelab Central
project_name: Immich
project_description: High performance self-hosted photo and video management solution.
project_source: https://github.com/immich-app/immich
project_website: https://immich.app/
project_docs: https://docs.immich.app
project_status: Active
stable_images:
  - ghcr.io/immich-app/immich-server:release
  - ghcr.io/immich-app/immich-machine-learning:release
  - docker.io/valkey/valkey:9@sha256:3b55fbaa0cd93cf0d9d961f405e4dfcc70efe325e2d84da207a0a8e6d8fde4f9
  - ghcr.io/immich-app/postgres:14-vectorchord0.4.3-pgvectors0.2.0@sha256:bcf63357191b76a916ae5eb93464d65c07511da41e3bf7a8416db519b40b1c23
stable_versions:
  - v2
latest_images:
  - ghcr.io/immich-app/immich-server:release
  - ghcr.io/immich-app/immich-machine-learning:release
  - docker.io/valkey/valkey:9@sha256:3b55fbaa0cd93cf0d9d961f405e4dfcc70efe325e2d84da207a0a8e6d8fde4f9
  - ghcr.io/immich-app/postgres:14-vectorchord0.4.3-pgvectors0.2.0@sha256:bcf63357191b76a916ae5eb93464d65c07511da41e3bf7a8416db519b40b1c23
latest_versions:
  - release
warning: none
date: 2026-05-02
last_updated: 2026-05-02
required_env_files:
  - host.env
  - network.env
supported_architecture:
  - amd64
  - x86
  - arm64
ready_to_deploy: true
---