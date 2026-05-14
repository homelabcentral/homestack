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
      permissions: 600
  - config_file:
      path: data/traefik.yml
      constant: false
      permissions: 644
  - config_file:
      path: data/config.yml
      constant: false
      permissions: 644
pre_install_steps:
  - step:
      number: 1
      description: Create `acme.json` and set permissions
      todo: Create a file called `acme.json` in directory `${DIR_HOMESTACK}/compose/${DIR_TR_TRAEFIK}/data` if it does not exist already and then change the permissions use these commands `cd ${DIR_HOMESTACK}/compose/${DIR_TR_TRAEFIK}/data && touch acme.json && chmod 600 acme.json`
      required: true
  - step:
      number: 2
      description: Change email in `treafik.yml`
      todo: "Change this email `email: youremail@email.com` to your email that you used for cloudflare account in `${DIR_HOMESTACK}/compose/${DIR_TR_TRAEFIK}/data/traefik.yml`"
      required: true
  - step:
      number: 3
      description: Configure `config.yml` if you require
      todo: If you have any other services that are not run in a docker container then edit the `${DIR_HOMESTACK}/compose/${DIR_TR_TRAEFIK}/data/config.yml`
      required: false
post_install_steps:
  - step:
      number: 1
      description: Check if it works
      todo: Do a `docker logs traefik` command in your console to see if treafik is working. If you don't see anything, that is a good sign. That means it is working. If there are any warnings or errors then you might need to resolve those
      required: true
  - step:
      number: 2
      description: Add DNS entry for traefik
      todo: Add DNS entry for `${APP_NAME_TR_TRAEFIK}.${SUB_DOMAIN}.${DOMAIN}` and your IP address (tailscale or private ip) in your pihole or any other DNS server that you are running
      required: true
post_setup_steps:
  - step:
      number: 1
      description: Go to the website
      todo: Go to `https://${APP_NAME_TR_TRAEFIK}.${SUB_DOMAIN}.${DOMAIN}` to open up the traefik dashboard
supported_architecture:
  - x86_64
  - arm64
ready_to_deploy: true
---

# Traefik

Traefik is a cloud native reserse proxy that is selfhostable.

## Pre-Install

Before you deploy the app using `homestack deploy traefik` there are some files that you need to have ready.
Follow the instruction below.

## Post-Install

After deploying each application using `homestack deploy` or any other way if you choose. Please add the DNS record in pihole or whatever DNS resolver that you use, otherwise even if the reserve proxy is setup the correct way, you won't be able to get to it.
