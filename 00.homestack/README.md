# homestack

Deploy self-hosted Docker Compose stacks with ease — works similarly to Homebrew but for containers.

`homestack` is a CLI tool that manages the full lifecycle of self-hosted services: browse a curated catalogue of projects, pull their compose files, fill in environment configuration interactively (or with recommended defaults), and start, restart, stop, or remove stacks — all from a single command.

---

## ⚠️ Warnings

### Development Stage

> [!IMPORTANT]
> This project is **in active development**. Features and APIs may change without warning. Use at your own risk.

### Security Notice

> [!WARNING]
> **Do not use this project to deploy applications that are exposed to the public internet** unless you understand the security implications. Even with firewall rules in place, Docker can bypass firewall restrictions by exposing ports directly.
>
> **Recommended approach:** Use this with a VPN solution such as **WireGuard**, **Twingate**, or **Tailscale** to ensure secure access and protect your services from unauthorized access.

---

## Table of Contents

- [homestack](#homestack)
  - [⚠️ Warnings](#️-warnings)
    - [Development Stage](#development-stage)
    - [Security Notice](#security-notice)
  - [Table of Contents](#table-of-contents)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Getting Started](#getting-started)
    - [1. Initialise homestack](#1-initialise-homestack)
    - [2. Fill in shared environment files](#2-fill-in-shared-environment-files)
    - [3. Deploy a project](#3-deploy-a-project)
  - [Production Setup (Pi-hole + Traefik)](#production-setup-pi-hole--traefik)
    - [Requirements](#requirements)
    - [Step-by-step setup](#step-by-step-setup)
    - [Post-deploy validation checklist](#post-deploy-validation-checklist)
  - [Required Environment Files](#required-environment-files)
  - [Directory Layout](#directory-layout)
  - [Commands](#commands)
    - [`init`](#init)
    - [`update`](#update)
    - [`list`](#list)
    - [`search`](#search)
    - [`info`](#info)
    - [`show-secrets`](#show-secrets)
    - [`pull`](#pull)
    - [`deploy`](#deploy)
    - [`start`](#start)
    - [`restart`](#restart)
    - [`recreate`](#recreate)
    - [`stop`](#stop)
    - [`remove`](#remove)
    - [`upgrade`](#upgrade)
  - [Typical Workflow](#typical-workflow)
  - [How It Works](#how-it-works)
    - [High-level Architecture](#high-level-architecture)
    - [Lifecycle Runtime Semantics](#lifecycle-runtime-semantics)
    - [Remote Static API](#remote-static-api)
    - [Preferences Store](#preferences-store)
    - [File Downloader](#file-downloader)
    - [`.env.template` Format and Parser](#envtemplate-format-and-parser)
      - [Inline key=value fields](#inline-keyvalue-fields)
      - [`compute=` safety model](#compute-safety-model)
      - [`derive=` value interpolation](#derive-value-interpolation)
    - [Text Interpolation \& Variable Resolution](#text-interpolation--variable-resolution)
    - [User-Facing Console Output (Rich Formatter)](#user-facing-console-output-rich-formatter)
    - [Questionary Form Builder](#questionary-form-builder)
    - [Deploy Flow (Step by Step)](#deploy-flow-step-by-step)
    - [Path Derivation](#path-derivation)
    - [Platform Directories](#platform-directories)

---

## Prerequisites

- **Python 3.10+**
- **Docker Engine** running and accessible to your user account
- Linux or macOS (Windows is not officially supported)

---

## Installation

Download the latest `.whl` file from the [GitHub Releases page](<GITHUB_RELEASES_URL_PLACEHOLDER>) and install it with `pip`:

```bash
pip install homestack-<VERSION>-py3-none-any.whl
```

After installation the `homestack` command is available on your `PATH`:

```bash
homestack --help
```

> **Tip:** Install inside a virtual environment to keep your system Python clean:
>
> ```bash
> python3 -m venv ~/.venv/homestack
> source ~/.venv/homestack/bin/activate
> pip install homestack-<VERSION>-py3-none-any.whl
> ```

---

## Getting Started

### 1. Initialise homestack

```bash
homestack init
```

You will be prompted to choose an install directory (default: `~/homestack`). homestack will:

- Collect host metadata (username, UID/GID, CPU, RAM, architecture).
- Create `<install_dir>/compose/` and `<install_dir>/data/`.
- Download shared environment template files to `<install_dir>/compose/00.env/`.

### 2. Fill in shared environment files

After `init`, navigate to your install directory and fill in the env files in `compose/00.env/` that your selected projects declare in `required_env_files`. Many projects use `host.env` and `network.env`, but the exact list is project-specific. See [Required Environment Files](#required-environment-files) for details.

### 3. Deploy a project

```bash
homestack deploy karakeep
```

If local project files are missing, homestack pulls them, walks you through configuration interactively, writes a `.env` file, and starts the containers.

If local `docker-compose.yml` and `.env` already exist, `deploy` behaves like `start`: it validates required env files and starts existing or missing containers without regenerating `.env`.

> **Tip:** If deployment or startup appears slow and you want to see live `docker compose` progress/output, run lifecycle commands with `--verbose` (or `-v`).

---

## Production Setup (Pi-hole + Traefik)

Use this flow to prepare a stable DNS + reverse-proxy foundation before deploying additional services.

### Requirements

- Docker installed and working (`docker info` should succeed)
- Python 3.10 or newer
- A domain name you control (for example `example.com`)
- A free Cloudflare account (DNS + ACME DNS challenge)
- A free Tailscale account (recommended for secure remote admin access)

### Step-by-step setup

<!-- markdownlint-disable MD029 -->

1. Install homestack and verify it works:

```bash
homestack --help
```

2. Initialize homestack:

```bash
homestack init
```

3. Move to shared environment templates:

```bash
cd <path_to_your_homestack>/compose/00.env
```

4. Create required shared env files from templates:

```bash
cp host.env.template host.env
cp network.env.template network.env
```

5. Edit and complete host settings:

```bash
nano host.env
```

6. Edit and complete network settings:

```bash
nano network.env
```

7. Optional: deploy Pi-hole if you do not already run a DNS server:

```bash
homestack deploy pihole
```

8. Prepare Traefik project files:

```bash
homestack pull traefik
mkdir -p <path_to_your_homestack>/compose/traefik/data
cd <path_to_your_homestack>/compose/traefik/data
```

9. Create and secure ACME storage (required by Traefik):

```bash
touch acme.json
chmod 600 acme.json
```

10. Download Traefik static and dynamic configuration files:

```bash
curl -fsSL "https://raw.githubusercontent.com/homelabcentral/homestack/refs/heads/main/02.traefik/data/traefik.yml" -o traefik.yml
curl -fsSL "https://raw.githubusercontent.com/homelabcentral/homestack/refs/heads/main/02.traefik/data/config.yml" -o config.yml
```

11. Update the ACME contact email in `traefik.yml` to the email used for your Cloudflare account.

12. Install `htpasswd` (Debian/Ubuntu example):

```bash
sudo apt update && sudo apt install -y apache2-utils
```

13. Generate a bcrypt hash for Traefik dashboard basic auth (replace `admin` with your preferred username):

```bash
echo "$(htpasswd -nB admin)" | sed -e 's/\$/\$\$/g'
```

> **Important:** Treat the generated bcrypt hash as a credential. Store it securely, do not commit it to git, and then place it in your Traefik auth configuration.

14. Deploy Traefik:

```bash
homestack deploy traefik
```

These steps establish a production-style baseline: optional local DNS (Pi-hole) and a reverse proxy (Traefik) that can front your remaining homestack services.

<!-- markdownlint-enable MD029 -->

### Post-deploy validation checklist

Run these checks after `homestack deploy traefik` to confirm your foundation is healthy.

<!-- markdownlint-disable MD029 -->

1. Confirm containers are running:

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

2. Confirm your domain resolves to the expected public IP:

```bash
dig +short your_domain.com
```

3. Confirm DNS records are proxied/configured correctly in Cloudflare:

- `A`/`AAAA` records point to your server public IP (or upstream endpoint).
- If you rely on DNS-01 ACME challenges, ensure the API token has DNS edit permission for the target zone.

4. Confirm ACME certificate issuance succeeded:

```bash
docker logs traefik --tail 200 | grep -Ei 'acme|certificate|error'
```

Expected result: no repeated ACME failures and at least one successful certificate acquisition/renewal event.

5. Confirm Traefik dashboard authentication works:

- Open your Traefik dashboard URL.
- Verify your configured username and password authenticate successfully.
- If auth fails, regenerate the bcrypt hash and update the auth value in your Traefik configuration.

6. Confirm routing for one service behind Traefik:

```bash
curl -I https://your_service.your_domain.com
```

Expected result: a valid HTTP response (for example `200`, `301`, or `302`) and a trusted TLS certificate.

7. Optional hardening checks:

- Close unused inbound ports at your firewall/router.
- Ensure only required ports (typically `80` and `443`) are exposed publicly.
- Store Cloudflare API credentials and generated secrets outside shell history and screenshots.

<!-- markdownlint-enable MD029 -->

---

## Required Environment Files

Shared environment files live in `<install_dir>/compose/00.env/`. They are referenced by every project and **must be filled in before running `deploy`**.

| File          | Purpose                                                                                                                                                           |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `host.env`    | Host-level variables: `USER_NAME`, `UID`, `GID`, `GID_DOCKER`, `HOST_NAME`, `DOMAIN`, `TZ`, `LOCALTIME`, `DOCKER_SOCKET`, `DIR_DOCKER`, `DIR_COMPOSE`, `DIR_DATA` |
| `network.env` | Networking variables shared across stacks (e.g. VLAN IDs, subnet ranges, reverse-proxy settings)                                                                  |
| `email.env`   | Email / SMTP credentials used by services that send notifications                                                                                                 |
| `vpn.env`     | VPN-related variables (e.g. WireGuard keys, peer configuration)                                                                                                   |

Template files (`.env.template`) are downloaded automatically during `init`. Copy the relevant template, strip the `.template` suffix, and fill in your values:

```bash
cd <install_dir>/compose/00.env
cp host.env.template host.env
nano host.env   # fill in your values

cd <install_dir>/compose/00.env
cp network.env.template network.env
nano network.env
```

Each project's readme front-matter declares which of these files it actually requires. homestack checks that all required files exist before attempting a deploy.

---

## Directory Layout

```bash
<install_dir>/
├── compose/
│   ├── 00.env/               # shared environment files
│   │   ├── host.env.template
│   │   ├── host.env          # (you create this from the template)
│   │   ├── network.env
│   │   └── ...
│   ├── karakeep/             # one directory per deployed project
│   │   ├── docker-compose.yml
│   │   ├── .env.template
│   │   ├── .env              # generated by homestack deploy
│   │   └── readme.md
│   └── ...
└── data/                     # reserved for container data volumes (future use)
```

---

## Commands

### `init`

```bash
homestack init [--force]
```

Initialises homestack on this machine. Collects host system information, prompts for an install directory, creates the directory layout, and downloads shared environment templates.

| Option    | Description                                                                                                            |
| --------- | ---------------------------------------------------------------------------------------------------------------------- |
| `--force` | Re-run initialisation even if already initialised (preserves the existing install directory as the suggested default). |

---

### `update`

```bash
homestack update
```

Fetches the remote metadata index and refreshes the local project cache. Run this to pick up newly added projects or updated compose files.

---

### `list`

```bash
homestack list
```

Displays all projects available in the catalogue as a formatted table. Triggers a background cache refresh before rendering.

---

### `search`

```bash
homestack search <query>
```

Case-insensitive substring search across project names, descriptions, website URLs, and architecture tags.

```bash
homestack search bookmark
homestack search arm64
```

---

### `info`

```bash
homestack info <project>
```

Displays detailed metadata for a single project: description, supported architectures, source repository, website, and any post-deploy instructions.

```bash
homestack info karakeep
```

---

### `show-secrets`

```bash
homestack show-secrets <project> [--all] [--keys-only]
```

Displays secret values currently stored in the local `<project>/.env` file.

- By default, only secret variables with `remember=true` in the project's `.env.template` are shown.
- With `--all`, secrets marked `remember=false` are included as well.
- With `--keys-only`, only matching secret variable names are printed (no plaintext values).

```bash
# show only remember=true secrets
homestack show-secrets karakeep

# show all template-defined secret values
homestack show-secrets karakeep --all

# show secret variable names only
homestack show-secrets karakeep --keys-only
```

> [!WARNING]
> This command prints plaintext values from your local `.env` file to the terminal.

---

### `pull`

```bash
homestack pull <project>
```

Downloads the project's `docker-compose.yml`, `.env.template`, and `readme.md` into `<install_dir>/compose/<project>/`. Does **not** start containers.

Use this when you want to inspect or manually edit files before deploying.

```bash
homestack pull traefik
```

If the query matches multiple projects you are presented with an interactive selection list.

---

### `deploy`

```bash
homestack deploy <project> [--use-recommends] [--force] [--verbose]
```

Deploy has two runtime paths:

1. Start-equivalent path (default when local files already exist):
   1. Requires local `<project_dir>/docker-compose.yml` and `<project_dir>/.env`.
   2. Verifies all required shared env files exist.
   3. Starts the stack using the same lifecycle runtime as `start`.
   4. Does not rewrite `.env`.
2. Full generation path (when local files are missing, or with `--force`):
   1. Pulls project files if needed.
   2. Parses `.env.template` and prompts for values (or uses recommended values).
   3. Writes `.env`.
   4. Verifies required shared env files.
   5. Deploys containers.

|Option|Description|
|---|---|
|`--use-recommends` / `--use-recommended`|Skip interactive prompts and apply recommended/default values for all variables. Useful for scripted or automated deployments.|
|`--force`|Refresh local project files and regenerate `.env` before deploying, even if local files already exist.|
|`--verbose` / `-v`|Stream docker compose output in the console while the spinner is shown.|

```bash
# interactive
homestack deploy karakeep

# non-interactive with recommended defaults
homestack deploy karakeep --use-recommends

# show docker compose output while deploying
homestack deploy pihole --verbose
```

> **Note:** Deploy fails with a clear error if any required env file (for example `host.env`) is missing from `compose/00.env/`.

---

### `start`

```bash
homestack start <project> [--verbose]
```

Starts a locally installed project using the existing local files (`docker-compose.yml` and `.env`) plus required shared env files.

This command:

1. Resolves the project from local installed candidates.
2. Verifies `docker-compose.yml`, `.env`, and required shared env files exist.
3. Starts existing stopped containers.
4. Creates missing containers for services that are not present.

```bash
homestack start karakeep

# shorthand for verbose output
homestack start pihole -v
```

---

### `restart`

```bash
homestack restart <project> [--verbose]
```

Performs a full stop/start cycle for a locally installed project using the existing local files (`docker-compose.yml` and `.env`) plus required shared env files.

This command:

1. Resolves the project from local installed candidates.
2. Verifies `docker-compose.yml`, `.env`, and required shared env files exist.
3. Validates the compose config with the full env-file set.
4. Runs docker compose with `down`, then `up -d`.

```bash
homestack restart karakeep

# shorthand for verbose output
homestack restart pihole -v
```

---

### `recreate`

```bash
homestack recreate <project> [--verbose]
```

Recreates a locally installed project using the existing local files (`docker-compose.yml` and `.env`) plus required shared env files.

This command:

1. Resolves the project from local installed candidates.
2. Verifies `docker-compose.yml`, `.env`, and required shared env files exist.
3. Validates the compose config with the full env-file set.
4. Runs docker compose with `up -d --force-recreate` so containers are rebuilt from the current configuration.

```bash
homestack recreate karakeep
```

---

### `stop`

```bash
homestack stop <project> [--verbose]
```

Stops a running project by stopping and removing homestack-managed containers for that project. Only locally installed projects are shown as candidates.

```bash
homestack stop karakeep
```

---

### `remove`

```bash
homestack remove <project> [--verbose]
```

Fully removes a locally installed project:

1. Stops and removes project containers (same lifecycle teardown semantics as `stop`).
2. Removes service images referenced by that project's compose spec.
3. Deletes the local project directory from `<install_dir>/compose/<project-slug>/`.

Shared env files under `compose/00.env/` are not removed.

```bash
homestack remove karakeep
```

---

### `upgrade`

```bash
homestack upgrade <project>
```

Displays the current project metadata and image information in preparation for upgrading. Full automated image pull and restart logic is planned for a future release.

---

## Typical Workflow

```bash
# First-time setup
homestack init
# Edit ~/homestack/compose/00.env/host.env with your values

# Browse available projects
homestack list
homestack search pdf

# Deploy a project
homestack deploy stirlingpdf

# Deploy without prompts (use recommended or generated values)
homestack deploy stirlingpdf --use-recommends

# Regenerate .env and re-run prompts even if .env already exists
homestack deploy stirlingpdf --force

# Later: stop it
homestack stop stirlingpdf

# Start it again
homestack start stirlingpdf

# Restart it (full stop then start)
homestack restart stirlingpdf

# Force-recreate containers with current compose/env values
homestack recreate stirlingpdf

# Remove it entirely
homestack remove stirlingpdf

# Keep the catalogue up to date
homestack update
```

## How It Works

This section describes the internal architecture of homestack for contributors and advanced users.

### High-level Architecture

```bash
homestack (cli/cli.py — orchestrator)
├── api/client.py          Async HTTP client — fetches JSON from the static remote API
├── client/downloader.py   Async file downloader — pulls compose/env/readme files
├── parsers/               .env.template and readme front-matter parsers
├── models/                Pydantic + dataclass models for all data shapes
├── utils/
│   ├── shared_pref.py     SQLite-backed preferences store (sqlitedict)
│   ├── secure_values.py   Cryptographic value generators (passwords, passphrases, keys)
│   ├── project_table.py   Rich table builder for CLI catalogue output
│   ├── app_logger.py      Structured per-command logging setup
│   └── utils.py           Shared filesystem helpers
├── server/                Static API artifact generator (maintenance tooling, not user-facing)
│   ├── main.py            Orchestrates generation of env.json, projects.json, meta.json
│   ├── projects.py        Walks numbered project directories → projects.json
│   ├── env.py             Reads 00.env templates → env.json
│   ├── meta.py            Computes SHA hashes of generated files → meta.json
│   ├── readme.py          Parses readme front-matter for project metadata
│   └── generate_env_template.py  Creates .env.template files from source YAML
└── settings/settings.py   Pydantic-settings config, platformdirs paths, base URL
```

> **`server/` is maintenance tooling**, not part of the end-user runtime. It is used by the repository maintainer to regenerate the static JSON files that are pushed to the `gostatic` branch and served as the remote API. End users never invoke it directly.

The CLI layer (`cli.py`) is intentionally thin. It orchestrates calls to the modules above, handles errors, formats Rich output, and maps results to `typer.Exit` codes. Business logic lives in the dedicated modules.

### Lifecycle Runtime Semantics

All lifecycle commands (`start`, `restart`, `recreate`, `stop`, `remove`) resolve absolute paths for both compose and env files, then execute docker compose with the same base shape:

```bash
docker compose \
   --env-file <project/.env absolute path> \
   --env-file <required shared env absolute paths...> \
   --file <compose absolute path> \
   --project-name <project-slug> \
   <subcommand args>
```

The subcommand arguments differ by command:

| Command | Compose args |
| --- | --- |
| `start` | `up -d` |
| `restart` | `down` then `up -d` |
| `recreate` | `up -d --force-recreate` |
| `stop` | `down` |
| `remove` | `down --rmi all` |

---

### Remote Static API

homestack reads its project catalogue from a **static file API** hosted on a GitHub branch (`gostatic`). There is no backend server — everything is raw JSON files served directly from GitHub's CDN.

Base URL (configurable via `HOMESTACK_BASE_URL`):

```bash
https://raw.githubusercontent.com/homelabcentral/homestack/refs/heads/main
```

Three JSON endpoints are consumed:

| Endpoint                  | Purpose                                                                   |
| ------------------------- | ------------------------------------------------------------------------- |
| `00.api/v1/meta.json`     | Index of tracked files with SHA hashes — used to detect stale local cache |
| `00.api/v1/projects.json` | Full catalogue of deployable projects                                     |
| `00.api/v1/env.json`      | List of shared env template files available for download                  |

The `APIClient` class (`api/client.py`) wraps `httpx.AsyncClient` with automatic retry (exponential backoff), timeout handling, and typed exceptions (`APIHTTPError`, `APINetworkError`, `APITimeoutError`, `APIParseError`). All async calls are bridged to the sync CLI via `asyncio.run()`.

**Cache invalidation** (`homestack update`): fetches `meta.json`, diffs the `sha` field of each entry against the locally cached version, and re-downloads only stale files. The local cache lives in the XDG cache directory (`~/.cache/homestack/api/v1/` on Linux).

---

### Preferences Store

Host preferences are persisted in a SQLite database (`~/.config/homelabcentral/homestack/prefs.db`) via [sqlitedict](https://github.com/RaRe-Technologies/sqlitedict). The `SharedPreferences` class is always used as a context manager to guarantee commits and proper connection teardown.

The `HostPreferences` dataclass holds:

```python
username, uid, gid, docker_gid   # user identity
architecture, cpu_count, ram_mb  # hardware
install_dir, install_dir_total_gb # install location
```

These values are collected once during `init` and re-read by every subsequent command via `_require_init_or_exit()`, which exits with code 1 and a helpful message if the store has not been initialised.

---

### File Downloader

`client/downloader.py` provides an async `Downloader` class built on `httpx.AsyncClient`. Key properties:

- **Atomic writes** — files are written to a temporary path first, then renamed, so a partial download never leaves a corrupt file at the destination.
- **Batch downloads** — `download_many(jobs, strict=True)` runs all `DownloadJob` tasks concurrently with `asyncio.gather`. In strict mode, a `BatchDownloadError` is raised if any individual job fails.
- **Typed errors** — `DownloadHTTPError`, `DownloadNetworkError`, `DownloadTimeoutError`, `DownloadIOError` give callers precise failure information.

---

### `.env.template` Format and Parser

Each project ships a `.env.template` file. It is a plain `.env`-style file extended with two kinds of structured annotations:

**1. File-level metadata block** (at the top of the file):

```ini
# METADATA --- START
# DO NOT CHANGE THE BELOW
Description=Human-readable description of this env file
Required=true
# METADATA --- END
```

**2. Per-variable inline annotations** (as a comment suffix after `KEY=`):

```ini
POSTGRES_PASSWORD= # type=password | prompt=Enter the database password | description=Used by the app container
TZ=                # type=string   | prompt=Enter your timezone         | immutable=true
PORT=8080          # type=port     | prompt=Enter the listening port    | recommended=8080
```

The `EnvTemplateParser` (`parsers/env_template_parser.py`) reads these annotations and produces a `ParsedEnvTemplate` containing:

- `metadata` — `EnvTemplateMetadata` (description, required flag)
- `variables` — list of `EnvTemplateVariable`, each with key, default value, type metadata, prompt text, instruction, choices, recommended value, immutable flag, remember flag, and description
- `warnings` — non-fatal parse issues (unknown type, malformed annotations, etc.)

**Supported `type=` values:**

| Type                       | Behaviour                                            |
| -------------------------- | ---------------------------------------------------- |
| `string`                   | Free-text input                                      |
| `path`                     | Path input via Questionary path prompt               |
| `boolean`                  | `true`/`false` input with validation                 |
| `int` / `float`            | Numeric input with validation                        |
| `password`                 | Auto-generates a secure random password              |
| `passphrase`               | Auto-generates an XKCD-style passphrase              |
| `base64` / `base64urlsafe` | Auto-generates random bytes encoded as Base64        |
| `bcrypthash`               | Auto-generates a bcrypt hash of a generated password |
| `memory`                   | Docker memory string (e.g. `512M`, `2G`)             |
| `ip`                       | IPv4/IPv6 address with validation                    |
| `port`                     | Integer in range 1–65535                             |

Bounds are supported for `string`, `int`, `float`, `password`, `passphrase`, `base64`, and `base64urlsafe` using `type=kind(min,max)` syntax (for example `type=string(3,16)`).

Variables marked `immutable=true` are pre-filled and not shown as interactive prompts (for example `DOCKER_SOCKET=/var/run/docker.sock`).

#### Inline key=value fields

All per-variable inline metadata keys are optional.

| Key | Default | Required | Description | Example |
| --- | --- | --- | --- | --- |
| `recommended` | `None` | No | Suggested value used by `--use-recommends` or as the default prompt value when appropriate. For `type=boolean`, values are normalized to `true`/`false`. | `recommended=8080` |
| `type` | `None` | No | Value kind and optional bounds used for validation, prompt behavior, and secure generation. | `type=password(12,64)` |
| `prompt` | `None` | No | Prompt text shown to the user in interactive mode. | `prompt=Enter service port` |
| `instruction` | `None` | No | Helper text shown below the prompt. | `instruction=Use a value between 1024 and 65535` |
| `choices` | `None` (or `[]` if explicitly set) | No | Allowed choices for select-style input. Supports per-choice `description` and `default=true`. | `choices=[80 (description=HTTP, default=true), 443 (description=HTTPS)]` |
| `immutable` | `false` | No | Skip prompting for this variable and keep the resolved value as-is. | `immutable=true` |
| `remember` | `false` | No | For generated secrets, include plaintext in the end-of-run summary so the user can save it. | `remember=true` |
| `description` | `None` | No | Human-readable variable description used in docs and summaries. | `description=Public web port` |
| `compute` | `None` | No | Compute default value from a safe built-in resolver. Allowed resolvers: `username`, `uid`, `gid`, `docker_gid`, `private_ip`, `public_ip`, `tailscale_ip`. | `compute=uid` |
| `derive` | `None` | No | Derive value from other variables in shared env files or current .env file using `${VAR}` syntax. Follows precedence: 00.env < current .env < in-session answers. For mutable variables, shows derived value as recommended default. | `derive=${SOURCE_HOST}-${SOURCE_PORT}` |

Composite example:

```ini
FEATURE_ENABLED= # recommended=true | type=boolean | prompt=Enable feature? | instruction=true or false | choices=[true (description=Enabled, default=true), false (description=Disabled)] | immutable=false | remember=false | description=Feature flag
```

Per-field mini examples:

```ini
APP_NAME= # type=string(3,16)
SERVICE_PORT= # recommended=8080 | type=port
TZ= # prompt=Enter your timezone | instruction=Example: Europe/Berlin
TLS_MODE= # choices=[off, strict (description=TLS required, default=true)]
UID= # type=int | compute=uid
IP_PRIVATE= # type=ip | compute=private_ip
IP_PUBLIC= # type=ip | compute=public_ip
IP_TAILSCALE= # type=ip | compute=tailscale_ip
DOCKER_SOCKET=/var/run/docker.sock # immutable=true
JWT_SECRET= # type=password(32,64) | remember=true
DB_HOST= # derive=${DATABASE_HOST}
DB_PORT= # derive=${DATABASE_PORT:-5432}
SERVICE_URL= # derive=http://${HOSTNAME}-${SERVICE_NAME}:${SERVICE_PORT}
```

#### `compute=` safety model

`compute=` is intentionally strict and fail-closed:

- Only exact resolver names are accepted: `username`, `uid`, `gid`, `docker_gid`, `private_ip`, `public_ip`, `tailscale_ip`.
- `public_ip` uses a small allow-list of trusted HTTPS endpoints from Python code; it does not shell out.
- Shell commands and function expressions are rejected (for example `compute=id -u` or `compute=uid()`).
- The CLI never uses `subprocess`, `os.system`, `eval`, `exec`, or dynamic imports for `compute`.
- Invalid or unsupported `compute` values stop generation with an explicit error.

#### `derive=` value interpolation

`derive=` allows variables to reference values from other variables using `${VAR}` and `${VAR:-default}` syntax. This enables building composite values from shared configuration, shared env files, and previously-collected template answers.

**Derivation context and precedence:**

Values are resolved in precedence order:
1. **Shared env files** (`00.env/*.env`) — baseline values shared across all projects
2. **Current project `.env` file** — project-specific overrides (if already exists)
3. **In-session answers** — values collected from the current template generation run (highest precedence)

**How derive interacts with immutable and mutable variables:**

- **Immutable variables** (`immutable=true`): The derived value is auto-applied without prompting. Example:
  ```ini
  SHARED_HOSTNAME=localhost # computed or provided in host.env
  ADMIN_URL=http://${SHARED_HOSTNAME}:9000 # immutable=true | derive=...
  ```
  If `SHARED_HOSTNAME` is found, `ADMIN_URL` is automatically set to `http://localhost:9000` without asking.

- **Mutable variables** (`immutable=false` or not set): The derived value is shown as the recommended default in an interactive prompt, allowing the user to override it:
  ```ini
  DB_HOST=postgres.example.com # in host.env
  DB_CONNECTION= # mutable | derive=postgresql://user:pass@${DB_HOST}:5432/app
  ```
  During deployment, the user is prompted: "Enter database connection" with a recommended default of `postgresql://user:pass@postgres.example.com:5432/app`. They can accept it or type a different value.

**Examples:**

```ini
# Simple variable reference
SOURCE_HOST=192.168.1.10 # from shared host.env
BACKUP_HOST= # derive=${SOURCE_HOST}

# With default fallback (if variable is missing, use the default)
REPLICA_PORT= # derive=${BACKUP_PORT:-5432}

# Composite URLs
DOMAIN=example.com # from network.env
SERVICE_NAME=app
SERVICE_PORT=8080
PUBLIC_URL= # derive=https://${SERVICE_NAME}.${DOMAIN}:${SERVICE_PORT}

# Multi-variable derivation with defaults
MAIL_SERVER=smtp.internal # from email.env or 00.env/email.env.template
MAIL_PORT=587 # default
MAIL_FROM_URL= # derive=smtp://${MAIL_SERVER}:${MAIL_PORT:-587}
```

**Validation on derived values:**

Derived values are validated the same way as typed input:
- If the variable has `type=int`, the derived value must be parseable as an integer.
- If the variable has `choices=`, the derived value must be one of the allowed choices.
- If the variable is marked `type=secret` or similar secret type, derivation is rejected (secrets must be generated fresh or provided interactively).

**Safety notes:**

- Only `${VAR}` and `${VAR:-default}` syntax is supported. Expressions like `${VAR?error}` or `${VAR##pattern}` are not evaluated (shell expansions are not supported).
- Derive expressions do not execute shell commands, Python code, or external processes.
- Circular or multi-step derives (e.g., A depends on B, B depends on C) are detected and fail with a clear error.

---

### Text Interpolation & Variable Resolution

The `utils/text_interpolation.py` module handles variable interpolation across `.env.template` parsing, form generation, and deployment workflows.

**Interpolation syntax:**

- `${VAR}` — requires `VAR` to exist; fails if missing (in strict mode)
- `${VAR:-default}` — uses `default` if `VAR` is missing or empty
- `${VAR?error message}` — requires `VAR`; shows custom error message if missing

**Context layers:**

`load_interpolation_context()` builds a three-layer resolution context:
1. Load all files from `00.env/*.env` (shared baseline)
2. Load the target project's `.env` file (if it already exists)
3. Merge with in-session answers (e.g., values collected during template prompting)

Each layer overrides the previous one, allowing late-stage customization.

**Usage in derive and compute:**

Both `derive=` and template variable resolution use the same interpolation engine:
- During template generation, the context includes shared env + current .env + in-session answers
- During deployment, the full resolved context is available for variable substitution

Example flow:
```
00.env/host.env:        HOSTNAME=myhost
00.env/network.env:     VLAN_ID=10
current .env:           HOSTNAME=custom-host    (overrides 00.env/host.env)
in-session answers:     VLAN_ID=20              (overrides 00.env/network.env)

Interpolation context:
  HOSTNAME=custom-host  (from current .env)
  VLAN_ID=20            (from in-session)
  
Variable resolution:
  derive=${HOSTNAME}-${VLAN_ID}  →  custom-host-20
```

---

### User-Facing Console Output (Rich Formatter)

The `utils/rich_formatter.py` module provides beautifully formatted console messages via a global `formatter` singleton. This ensures consistent, visually rich output across all CLI commands.

**10 Message Types:**

- 💡 **info** — informational messages (cyan, bold)
- ✗ **error** — error messages (red, bold)
- ⚠ **warning** — warnings (yellow, bold)
- 🐛 **debug** — debug output (magenta, dim)
- ✓ **success** — success confirmations (green, bold)
- 💬 **hint** — user hints and suggestions (blue, italic)
- ▶ **step** — multi-step process indicators (white, bold)
- ⚙ **command** — commands being executed (bright cyan, bold)
- 🎯 **result** — result/outcome messages (bright green, bold)
- ★ **title** — section headers (bright white, bold, underline)

**Usage in CLI:**

```python
from utils.rich_formatter import formatter

# Simple messages
formatter.success("Deployment completed")
formatter.error("Connection timeout", details="Retry in 5 seconds")
formatter.step("Step 1: Validating configuration")

# Structured output
formatter.table([
    {"Service": "web-app", "Status": "Running"},
    {"Service": "database", "Status": "Running"},
])

formatter.success_summary({
    "Dashboard": "http://localhost:8080",
    "API": "http://localhost:8000",
})
```

All rich formatter output respects terminal capabilities and gracefully degrades on non-TTY outputs.

---



### Questionary Form Builder

`cli/questionary.py` translates a `ParsedEnvTemplate` into an interactive terminal form using the [questionary](https://github.com/tmbo/questionary) library.

- Each `EnvTemplateVariable` becomes a prompt (text, password, select, etc.) based on its `type`.
- When `--use-recommends` is passed, variables with `recommended` values are auto-filled (secure kinds still generate fresh values). Variables without `recommended` values remain interactive unless `immutable=true`, in which case the template value is used.
- The result is a `GeneratedEnv` model that serialises to a standard `.env` file string (`KEY=value\n` per line).
- Secret values (passwords, passphrases, keys) are displayed in a masked summary panel after generation so you can record them.

---

### Deploy Flow (Step by Step)

```bash
homestack deploy <project>
         │
         ▼
1. Load projects.json from local cache
   └─ _load_cached_projects()
         │
         ▼
2. Resolve project by name (fuzzy search → interactive select if ambiguous)
   └─ _select_project_from_query()
         │
         ▼
3. Resolve local files and choose path
   └─ If docker-compose.yml + .env exist and --force is not set:
      start-equivalent path
      (skip template parsing and .env regeneration)
   └─ Else:
      full generation path (pull, parse template, generate .env)
         │
         ▼
4. Preflight: verify all required env files exist
   └─ _resolve_project_required_env_files()
      checks <compose_dir>/00.env/<file> for each entry in ProjectItem.required_env_files
         │
         ▼
5. Start/deploy containers via Docker SDK runtime
   └─ start_project_stack() for start-equivalent path
   └─ deploy_project_stack() for full generation path
```

---

### Path Derivation

All runtime paths are derived from a single persisted value: `install_dir`.

| Path              | Derived as                                  |
| ----------------- | ------------------------------------------- |
| `compose_dir`     | `install_dir / "compose"`                   |
| `data_dir`        | `install_dir / "data"`                      |
| Shared env files  | `compose_dir / "00.env" / <filename>`       |
| Project directory | `compose_dir / slug(project_name)`          |
| Generated `.env`  | `compose_dir / slug(project_name) / ".env"` |

The slug is produced by lowercasing the project name and collapsing non-alphanumeric characters to hyphens (e.g. `Pihole-Unbound` → `pihole-unbound`).

---

### Platform Directories

homestack uses [platformdirs](https://github.com/platformdirs/platformdirs) to resolve OS-appropriate config and cache locations:

|Purpose|Default path (Linux)|
|---|---|
|Preferences DB|`~/.config/homelabcentral/homestack/prefs.db`|
|API cache|`~/.cache/homelabcentral/homestack/api/v1/`|
|Log file|`~/.cache/homelabcentral/homestack/logs/homestack.log`|

The log level defaults to `WARNING`. Set `HOMESTACK_LOG_LEVEL=DEBUG` in your environment for verbose output.

---
