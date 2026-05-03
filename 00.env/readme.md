---
---

# 00.env

## Purpose

This directory contains various .env files that have several .env variables that are more or less constant for all docker containers and don't change very often. Rather than having to pass the same variables across different containers, having them in one place is convenient.

For any variables that are `constant=true`, they are universal and can not be changed, such as HTTP_PORT=80, HTTPS_PORT=443.

### local.env

This file contains variables related to the computer it is being run on and the variables that are not required by any containers. This is mostly to store user preferences.

### host.env

This file containers variables related to the machine it is being run/hosted on. It contains variables such as username, uid, gid, docker gid, host name, timezone etc.

### network.env

This file contains basically every reusable variables related to networking for both host and docker. The name of the docker network does not matter. Most of the networking is already being handled by this repo and various docker containers. This is done so that you can deploy any container at any time without having to deal with communications between containers, overlaping ip etc.

### email.env

This file contains SMTP settings for the email and if you want to send notifications from any app. Since not all containers have support to send outgoing emails, including this file is optional.

### vpn.env

This file contains VPN related settings for any wireguard or other containers. Since not all containers have support for VPN, including this file is optional.