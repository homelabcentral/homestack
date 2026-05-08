from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import docker
import yaml
from docker.errors import APIError, DockerException, NotFound
from docker.types import IPAMConfig, IPAMPool

HOMESTACK_MANAGED_LABEL = "homestack.managed"
HOMESTACK_PROJECT_LABEL = "homestack.project"
HOMESTACK_SERVICE_LABEL = "homestack.service"

TRAEFIK_NETWORK_NAME = "traefiknet"
TRAEFIK_NETWORK_SUBNET = "172.16.0.0/16"
TRAEFIK_NETWORK_GATEWAY = "172.16.0.1"

_INTERPOLATION_PATTERN = re.compile(r"\$\{([^}:]+)(?::-([^}]*))?\}")


class DockerRuntimeError(RuntimeError):
    """Raised when Docker compose operations fail."""


class DockerNetworkConflictError(DockerRuntimeError):
    """Raised when the required shared network exists with incompatible settings."""


@dataclass(slots=True)
class NetworkSpec:
    alias: str
    name: str
    external: bool


@dataclass(slots=True)
class ServiceNetworkAttachment:
    name: str
    ipv4_address: str | None = None


@dataclass(slots=True)
class ServiceSpec:
    name: str
    image: str
    container_name: str
    hostname: str | None = None
    command: str | list[str] | None = None
    restart: str | None = None
    environment: dict[str, str] = field(default_factory=dict)
    volumes: dict[str, dict[str, str]] = field(default_factory=dict)
    ports: dict[str, Any] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    network_mode: str | None = None
    depends_on: list[str] = field(default_factory=list)
    networks: list[ServiceNetworkAttachment] = field(default_factory=list)
    nano_cpus: int | None = None
    mem_limit: str | None = None
    mem_reservation: str | None = None


@dataclass(slots=True)
class ProjectSpec:
    name: str
    services: dict[str, ServiceSpec]
    networks: dict[str, NetworkSpec]


@dataclass(slots=True)
class ContainerStatus:
    service_name: str
    container_name: str
    status: str
    image: str


@dataclass(slots=True)
class DeploymentResult:
    containers: list[ContainerStatus]


def validate_compose_config(
    compose_path: Path,
    project_slug: str,
    env_files: list[Path],
    *,
    show_output: bool = False,
) -> None:
    _run_compose_command(
        compose_path,
        project_slug,
        env_files,
        ["config", "--quiet"],
        error_context="validate compose config",
        show_output=show_output,
    )


def _compose_base_command(
    compose_path: Path,
    project_slug: str,
    env_files: list[Path],
) -> list[str]:
    resolved_compose_path = compose_path.resolve()
    resolved_env_files = [env_file.resolve() for env_file in env_files]

    command = ["docker", "compose"]
    for env_file in resolved_env_files:
        command.extend(["--env-file", str(env_file)])
    command.extend(
        [
            "--file",
            str(resolved_compose_path),
            "--project-name",
            project_slug,
        ]
    )
    return command


def _run_compose_command(
    compose_path: Path,
    project_slug: str,
    env_files: list[Path],
    compose_args: list[str],
    *,
    error_context: str,
    show_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    command = [
        *_compose_base_command(compose_path, project_slug, env_files),
        *compose_args,
    ]

    try:
        if show_output:
            completed = subprocess.run(
                command,
                cwd=compose_path.resolve().parent,
                check=False,
            )
        else:
            completed = subprocess.run(
                command,
                cwd=compose_path.resolve().parent,
                capture_output=True,
                text=True,
                check=False,
            )
    except FileNotFoundError as exc:
        raise DockerRuntimeError(
            "Failed to run docker compose: 'docker' executable was not found on PATH."
        ) from exc
    except OSError as exc:
        raise DockerRuntimeError(f"Failed to run docker compose: {exc}") from exc

    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        details = stderr or stdout or "docker compose returned a non-zero exit code."
        raise DockerRuntimeError(f"Failed to {error_context}: {details}")

    return completed


def _collect_project_status(
    compose_path: Path,
    project_slug: str,
    env_files: list[Path],
) -> list[ContainerStatus]:
    completed = _run_compose_command(
        compose_path,
        project_slug,
        env_files,
        ["ps", "--format", "json"],
        error_context=f"collect container status for project '{project_slug}'",
    )

    output = completed.stdout.strip()
    if not output:
        return []

    try:
        payload = json.loads(output)
        if isinstance(payload, dict):
            rows = [payload]
        elif isinstance(payload, list):
            rows = payload
        else:
            raise TypeError("unexpected compose ps payload")
    except (json.JSONDecodeError, TypeError):
        rows = []
        for line in output.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise DockerRuntimeError(
                    f"Failed to parse docker compose status output for project '{project_slug}': {exc}"
                ) from exc
            if not isinstance(parsed, dict):
                raise DockerRuntimeError(
                    f"Failed to parse docker compose status output for project '{project_slug}': expected JSON objects."
                )
            rows.append(parsed)

    statuses = [
        ContainerStatus(
            service_name=str(
                row.get("Service")
                or row.get("service")
                or row.get("Name")
                or row.get("name")
                or "unknown"
            ),
            container_name=str(
                row.get("Name")
                or row.get("name")
                or row.get("Service")
                or row.get("service")
                or "unknown"
            ),
            status=str(
                row.get("Status")
                or row.get("status")
                or row.get("State")
                or row.get("state")
                or "unknown"
            ),
            image=str(row.get("Image") or row.get("image") or "unknown"),
        )
        for row in rows
        if isinstance(row, dict)
    ]
    return sorted(statuses, key=lambda item: item.service_name)


def ensure_traefik_bridge_network(client=None) -> None:
    docker_client = client or docker.from_env()

    try:
        network = docker_client.networks.get(TRAEFIK_NETWORK_NAME)
    except NotFound:
        ipam_config = IPAMConfig(
            pool_configs=[
                IPAMPool(subnet=TRAEFIK_NETWORK_SUBNET, gateway=TRAEFIK_NETWORK_GATEWAY)
            ]
        )
        try:
            docker_client.networks.create(
                TRAEFIK_NETWORK_NAME,
                driver="bridge",
                ipam=ipam_config,
            )
            return
        except (APIError, DockerException) as exc:
            raise DockerRuntimeError(
                f"Failed to create Docker network '{TRAEFIK_NETWORK_NAME}': {exc}"
            ) from exc
    except (APIError, DockerException) as exc:
        raise DockerRuntimeError(
            f"Failed to inspect Docker network '{TRAEFIK_NETWORK_NAME}': {exc}"
        ) from exc

    attrs = getattr(network, "attrs", {}) or {}
    driver = attrs.get("Driver")
    ipam_configs = attrs.get("IPAM", {}).get("Config", [])
    matching_ipam = any(
        config.get("Subnet") == TRAEFIK_NETWORK_SUBNET
        and config.get("Gateway") == TRAEFIK_NETWORK_GATEWAY
        for config in ipam_configs
    )
    if driver != "bridge" or not matching_ipam:
        raise DockerNetworkConflictError(
            f"Docker network '{TRAEFIK_NETWORK_NAME}' already exists but is not a "
            f"bridge network with subnet {TRAEFIK_NETWORK_SUBNET} and gateway "
            f"{TRAEFIK_NETWORK_GATEWAY}."
        )


def deploy_project_stack(
    compose_path: Path,
    project_slug: str,
    env_files: list[Path],
    *,
    client=None,
    show_output: bool = False,
) -> DeploymentResult:
    _ = client
    _run_compose_command(
        compose_path,
        project_slug,
        env_files,
        ["up", "-d"],
        error_context=f"deploy project '{project_slug}'",
        show_output=show_output,
    )

    return DeploymentResult(
        containers=_collect_project_status(compose_path, project_slug, env_files)
    )


def stop_project_stack(
    compose_path: Path,
    project_slug: str,
    env_files: list[Path],
    *,
    client=None,
    show_output: bool = False,
) -> None:
    _ = client
    _run_compose_command(
        compose_path,
        project_slug,
        env_files,
        ["down"],
        error_context=f"stop project '{project_slug}'",
        show_output=show_output,
    )


def start_project_stack(
    compose_path: Path,
    project_slug: str,
    env_files: list[Path],
    *,
    client=None,
    show_output: bool = False,
) -> None:
    _ = client
    _run_compose_command(
        compose_path,
        project_slug,
        env_files,
        ["up", "-d"],
        error_context=f"start project '{project_slug}'",
        show_output=show_output,
    )


def restart_project_stack(
    compose_path: Path,
    project_slug: str,
    env_files: list[Path],
    *,
    client=None,
    show_output: bool = False,
) -> None:
    _ = client
    _run_compose_command(
        compose_path,
        project_slug,
        env_files,
        ["down"],
        error_context=f"stop project '{project_slug}'",
        show_output=show_output,
    )
    _run_compose_command(
        compose_path,
        project_slug,
        env_files,
        ["up", "-d"],
        error_context=f"start project '{project_slug}'",
        show_output=show_output,
    )


def recreate_project_stack(
    compose_path: Path,
    project_slug: str,
    env_files: list[Path],
    *,
    client=None,
    show_output: bool = False,
) -> None:
    _ = client
    _run_compose_command(
        compose_path,
        project_slug,
        env_files,
        ["up", "-d", "--force-recreate"],
        error_context=f"recreate project '{project_slug}'",
        show_output=show_output,
    )


def remove_project_stack(
    compose_path: Path,
    project_slug: str,
    env_files: list[Path],
    *,
    client=None,
    show_output: bool = False,
) -> None:
    _ = client
    _run_compose_command(
        compose_path,
        project_slug,
        env_files,
        ["down", "--rmi", "all"],
        error_context=f"remove project '{project_slug}'",
        show_output=show_output,
    )


def _pull_project_images(docker_client, spec: ProjectSpec) -> None:
    image_names = sorted({service.image for service in spec.services.values()})
    for image_name in image_names:
        try:
            docker_client.images.pull(image_name)
        except (APIError, DockerException) as exc:
            raise DockerRuntimeError(
                f"Failed to pull image '{image_name}': {exc}"
            ) from exc


def load_project_spec(
    compose_path: Path,
    env_files: list[Path],
    project_slug: str,
) -> ProjectSpec:
    interpolation_env = _merge_env_files(env_files)
    interpolation_scope = {**os.environ, **interpolation_env}
    payload = _load_compose_payload(
        compose_path=compose_path,
        env_files=env_files,
        project_slug=project_slug,
        interpolation_scope=interpolation_scope,
    )

    if not isinstance(payload, dict) or not isinstance(payload.get("services"), dict):
        raise DockerRuntimeError("Compose file must define a 'services' mapping.")

    networks = _parse_networks(payload.get("networks") or {})
    services = {
        service_name: _parse_service(
            service_name=service_name,
            service_payload=service_payload,
            compose_dir=compose_path.parent,
            project_slug=project_slug,
            network_specs=networks,
            interpolation_scope=interpolation_scope,
        )
        for service_name, service_payload in payload["services"].items()
    }

    return ProjectSpec(
        name=str(payload.get("name") or project_slug),
        services=services,
        networks=networks,
    )


def _load_compose_payload(
    compose_path: Path,
    env_files: list[Path],
    project_slug: str,
    interpolation_scope: dict[str, str],
) -> dict[str, Any]:
    # Prefer Docker Compose rendered output so features like `extends` are resolved.
    compose_config_args = ["config", "--no-normalize"]
    try:
        completed = _run_compose_command(
            compose_path,
            project_slug,
            env_files,
            compose_config_args,
            error_context=f"resolve compose config for project '{project_slug}'",
        )
    except DockerRuntimeError as exc:
        message = str(exc)
        if "unknown flag: --no-normalize" in message:
            completed = _run_compose_command(
                compose_path,
                project_slug,
                env_files,
                ["config"],
                error_context=f"resolve compose config for project '{project_slug}'",
            )
        elif "'docker' executable was not found on PATH" in message:
            # Fallback for test/dev environments without Docker installed.
            compose_text = compose_path.read_text(encoding="utf-8")
            interpolated_text = _interpolate_string(compose_text, interpolation_scope)
            payload = yaml.safe_load(interpolated_text) or {}
            if not isinstance(payload, dict):
                raise DockerRuntimeError("Compose file must deserialize to a mapping.")
            return payload
        else:
            raise

    output = completed.stdout.strip()
    if not output:
        raise DockerRuntimeError(
            f"Failed to resolve compose config for project '{project_slug}': empty output."
        )

    payload = yaml.safe_load(output) or {}
    if not isinstance(payload, dict):
        raise DockerRuntimeError(
            f"Failed to resolve compose config for project '{project_slug}': expected a mapping output."
        )
    return payload


def _parse_networks(raw_networks: dict[str, Any]) -> dict[str, NetworkSpec]:
    networks: dict[str, NetworkSpec] = {}
    for alias, raw in raw_networks.items():
        raw = raw or {}
        if not isinstance(raw, dict):
            raise DockerRuntimeError(f"Unsupported network definition for '{alias}'.")

        external = raw.get("external", False)
        if isinstance(external, dict):
            external = external.get("external", False)
        networks[alias] = NetworkSpec(
            alias=alias,
            name=str(raw.get("name") or alias),
            external=bool(external),
        )
    return networks


def _parse_service(
    service_name: str,
    service_payload: dict[str, Any],
    compose_dir: Path,
    project_slug: str,
    network_specs: dict[str, NetworkSpec],
    interpolation_scope: dict[str, str],
) -> ServiceSpec:
    unsupported_keys = {"build", "profiles", "configs", "secrets"}
    present_unsupported = sorted(
        key for key in unsupported_keys if key in service_payload
    )
    if present_unsupported:
        joined = ", ".join(present_unsupported)
        raise DockerRuntimeError(
            f"Service '{service_name}' uses unsupported compose features: {joined}."
        )

    image = service_payload.get("image")
    if not image:
        raise DockerRuntimeError(f"Service '{service_name}' is missing an image.")

    environment = _build_service_environment(
        service_payload=service_payload,
        compose_dir=compose_dir,
        interpolation_scope=interpolation_scope,
    )

    depends_on = _parse_depends_on(service_payload.get("depends_on"))
    network_mode = service_payload.get("network_mode")
    if isinstance(network_mode, str) and network_mode.startswith("service:"):
        depends_on.append(network_mode.split(":", 1)[1])

    return ServiceSpec(
        name=service_name,
        image=str(image),
        container_name=str(
            service_payload.get("container_name") or f"{project_slug}-{service_name}"
        ),
        hostname=service_payload.get("hostname"),
        command=service_payload.get("command"),
        restart=service_payload.get("restart"),
        environment=environment,
        volumes=_parse_volumes(service_payload.get("volumes") or [], compose_dir),
        ports=_parse_ports(service_payload.get("ports") or []),
        labels=_parse_labels(service_payload.get("labels") or []),
        network_mode=network_mode,
        depends_on=list(dict.fromkeys(depends_on)),
        networks=_parse_service_networks(
            service_payload.get("networks") or {}, network_specs
        ),
        nano_cpus=_parse_nano_cpus(service_payload),
        mem_limit=_parse_memory_limit(service_payload, limit_type="limits"),
        mem_reservation=_parse_memory_limit(service_payload, limit_type="reservations"),
    )


def _build_service_environment(
    service_payload: dict[str, Any],
    compose_dir: Path,
    interpolation_scope: dict[str, str],
) -> dict[str, str]:
    merged: dict[str, str] = {}
    for env_path in _resolve_service_env_files(
        service_payload.get("env_file") or [], compose_dir
    ):
        merged.update(_read_env_file(env_path))

    raw_environment = service_payload.get("environment") or {}
    if isinstance(raw_environment, dict):
        for key, value in raw_environment.items():
            if value is None:
                merged[str(key)] = interpolation_scope.get(str(key), "")
            else:
                merged[str(key)] = str(value)
    elif isinstance(raw_environment, list):
        for entry in raw_environment:
            key, value = _split_key_value(str(entry))
            if value is None:
                merged[key] = interpolation_scope.get(key, "")
            else:
                merged[key] = value
    else:
        raise DockerRuntimeError("Unsupported environment section in compose service.")

    return merged


def _resolve_service_env_files(raw_env_files: Any, compose_dir: Path) -> list[Path]:
    if isinstance(raw_env_files, str):
        raw_env_files = [raw_env_files]

    resolved: list[Path] = []
    for raw in raw_env_files:
        env_path = Path(str(raw))
        if not env_path.is_absolute():
            env_path = (compose_dir / env_path).resolve()
        resolved.append(env_path)
    return resolved


def _parse_depends_on(raw_depends_on: Any) -> list[str]:
    if isinstance(raw_depends_on, list):
        return [str(entry) for entry in raw_depends_on]
    if isinstance(raw_depends_on, dict):
        return [str(entry) for entry in raw_depends_on.keys()]
    return []


def _parse_service_networks(
    raw_networks: Any,
    network_specs: dict[str, NetworkSpec],
) -> list[ServiceNetworkAttachment]:
    attachments: list[ServiceNetworkAttachment] = []

    if isinstance(raw_networks, list):
        for alias in raw_networks:
            spec = network_specs.get(str(alias))
            if spec is None:
                raise DockerRuntimeError(
                    f"Service references unknown network '{alias}'."
                )
            attachments.append(ServiceNetworkAttachment(name=spec.name))
        return attachments

    if isinstance(raw_networks, dict):
        for alias, raw in raw_networks.items():
            spec = network_specs.get(str(alias))
            if spec is None:
                raise DockerRuntimeError(
                    f"Service references unknown network '{alias}'."
                )
            raw = raw or {}
            if not isinstance(raw, dict):
                raise DockerRuntimeError(
                    f"Unsupported network attachment for service network '{alias}'."
                )
            attachments.append(
                ServiceNetworkAttachment(
                    name=spec.name,
                    ipv4_address=raw.get("ipv4_address"),
                )
            )
        return attachments

    raise DockerRuntimeError("Unsupported service network configuration.")


def _parse_volumes(
    raw_volumes: list[Any], compose_dir: Path
) -> dict[str, dict[str, str]]:
    volumes: dict[str, dict[str, str]] = {}
    for raw_volume in raw_volumes:
        source: str | None
        target: str
        mode: str
        if isinstance(raw_volume, str):
            parts = raw_volume.split(":")
            if len(parts) == 1:
                source, target, mode = None, parts[0], "rw"
            elif len(parts) == 2:
                source, target = parts
                mode = "rw"
            else:
                source, target = parts[0], parts[1]
                mode = parts[2]
        elif isinstance(raw_volume, dict):
            source = raw_volume.get("source") or raw_volume.get("src")
            raw_target = raw_volume.get("target") or raw_volume.get("dst")
            if raw_target in {None, ""}:
                raise DockerRuntimeError("Volume mapping must define a target path.")
            target = str(raw_target)
            mode = "ro" if raw_volume.get("read_only") else "rw"
        else:
            raise DockerRuntimeError(
                "Unsupported volume format; expected string or mapping."
            )

        if source is None:
            continue
        source_path = source
        if _looks_like_filesystem_path(source):
            source_path = (
                str((compose_dir / Path(source)).resolve())
                if not Path(source).is_absolute()
                else source
            )

        volumes[source_path] = {"bind": target, "mode": mode}
    return volumes


def _parse_ports(raw_ports: list[Any]) -> dict[str, Any]:
    ports: dict[str, Any] = {}
    for raw_port in raw_ports:
        if isinstance(raw_port, str):
            protocol = "tcp"
            port_value = raw_port
            if "/" in port_value:
                port_value, protocol = port_value.rsplit("/", 1)

            parts = port_value.split(":")
            if len(parts) == 1:
                container_port = parts[0]
                binding: Any = None
            elif len(parts) == 2:
                host_port, container_port = parts
                binding = int(host_port)
            elif len(parts) == 3:
                host_ip, host_port, container_port = parts
                # Use explicit keys to avoid tuple-order ambiguity in Docker SDK conversions.
                binding = {"HostIp": host_ip, "HostPort": str(int(host_port))}
            else:
                raise DockerRuntimeError(f"Unsupported port mapping '{raw_port}'.")
            ports[f"{container_port}/{protocol}"] = binding
            continue

        if isinstance(raw_port, dict):
            container_port = raw_port.get("target")
            if container_port in {None, ""}:
                raise DockerRuntimeError(
                    "Port mapping must define a container target port."
                )

            protocol = str(raw_port.get("protocol") or "tcp")
            host_port = raw_port.get("published")
            host_ip = raw_port.get("host_ip")

            if host_port in {None, ""}:
                binding = None
            elif host_ip not in {None, ""}:
                binding = {"HostIp": str(host_ip), "HostPort": str(int(host_port))}
            else:
                binding = int(host_port)

            ports[f"{container_port}/{protocol}"] = binding
            continue

        raise DockerRuntimeError("Unsupported port format; expected string or mapping.")
    return ports


def _parse_labels(raw_labels: Any) -> dict[str, str]:
    labels: dict[str, str] = {}
    if isinstance(raw_labels, dict):
        return {str(key): str(value) for key, value in raw_labels.items()}

    if isinstance(raw_labels, list):
        for entry in raw_labels:
            key, value = _split_key_value(str(entry))
            labels[key] = value or ""
        return labels

    raise DockerRuntimeError("Unsupported labels configuration.")


def _parse_nano_cpus(service_payload: dict[str, Any]) -> int | None:
    raw_cpus = (
        service_payload.get("deploy", {})
        .get("resources", {})
        .get("limits", {})
        .get("cpus")
    )
    if raw_cpus in {None, ""}:
        return None
    return int(float(raw_cpus) * 1_000_000_000)


def _parse_memory_limit(
    service_payload: dict[str, Any], *, limit_type: str
) -> str | None:
    raw_memory = (
        service_payload.get("deploy", {})
        .get("resources", {})
        .get(limit_type, {})
        .get("memory")
    )
    return None if raw_memory in {None, ""} else str(raw_memory)


def _merge_env_files(env_files: list[Path]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for env_file in env_files:
        merged.update(_read_env_file(env_file))
    return merged


def _read_env_file(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        raise DockerRuntimeError(f"Required env file not found: {env_path}")

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, value = _split_key_value(stripped)
        values[key] = value or ""
    return values


def _split_key_value(value: str) -> tuple[str, str | None]:
    if "=" not in value:
        return value.strip(), None
    key, raw = value.split("=", 1)

    parsed_value = raw.strip()
    if parsed_value and not parsed_value.startswith(("'", '"')):
        # Templates in this repo append metadata as inline comments after values.
        # Preserve hashes inside tokens (for example, passwords) by only trimming
        # comments that are preceded by whitespace.
        inline_comment_index = parsed_value.find(" #")
        if inline_comment_index != -1:
            parsed_value = parsed_value[:inline_comment_index].rstrip()

    return key.strip(), parsed_value


def _interpolate_string(value: str, env: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        variable, default = match.groups()
        return env.get(variable, default or "")

    return _INTERPOLATION_PATTERN.sub(replace, value)


def _ensure_runtime_networks(docker_client, spec: ProjectSpec) -> None:
    for network in spec.networks.values():
        if not network.external:
            raise DockerRuntimeError(
                f"Network '{network.alias}' must be declared as external for Docker SDK deployments."
            )
        try:
            docker_client.networks.get(network.name)
        except NotFound as exc:
            raise DockerRuntimeError(
                f"Required Docker network '{network.name}' was not found. Run 'homestack init' first."
            ) from exc
        except (APIError, DockerException) as exc:
            raise DockerRuntimeError(
                f"Failed to inspect Docker network '{network.name}': {exc}"
            ) from exc


def _get_existing_container(docker_client, container_name: str):
    try:
        return docker_client.containers.get(container_name)
    except NotFound:
        return None
    except (APIError, DockerException) as exc:
        raise DockerRuntimeError(
            f"Failed to inspect container '{container_name}': {exc}"
        ) from exc


def _remove_existing_managed_container(container, project_slug: str) -> None:
    labels = getattr(container, "labels", {}) or {}
    if (
        labels.get(HOMESTACK_MANAGED_LABEL) != "true"
        or labels.get(HOMESTACK_PROJECT_LABEL) != project_slug
    ):
        raise DockerRuntimeError(
            f"Container '{container.name}' already exists and is not managed by homestack."
        )

    try:
        container.stop(timeout=10)
    except NotFound:
        return
    except (APIError, DockerException) as exc:
        raise DockerRuntimeError(
            f"Failed to stop existing container '{container.name}': {exc}"
        ) from exc

    try:
        container.remove(v=False, force=True)
    except NotFound:
        return
    except (APIError, DockerException) as exc:
        raise DockerRuntimeError(
            f"Failed to remove existing container '{container.name}': {exc}"
        ) from exc


def _create_service_container(
    *,
    docker_client,
    compose_path: Path,
    project_slug: str,
    service: ServiceSpec,
    created_containers: dict[str, Any],
):
    labels = {
        **service.labels,
        HOMESTACK_MANAGED_LABEL: "true",
        HOMESTACK_PROJECT_LABEL: project_slug,
        HOMESTACK_SERVICE_LABEL: service.name,
    }

    create_kwargs: dict[str, Any] = {
        "detach": True,
        "name": service.container_name,
        "hostname": service.hostname,
        "command": service.command,
        "environment": service.environment,
        "volumes": service.volumes or None,
        "ports": service.ports or None,
        "labels": labels,
        "restart_policy": {"Name": service.restart} if service.restart else None,
        "mem_limit": service.mem_limit,
        "mem_reservation": service.mem_reservation,
        "nano_cpus": service.nano_cpus,
    }

    if service.network_mode:
        create_kwargs["network_mode"] = _resolve_network_mode(
            service.network_mode, created_containers
        )
    elif service.networks:
        create_kwargs["network_disabled"] = True

    sanitized_kwargs = {
        key: value for key, value in create_kwargs.items() if value is not None
    }

    def _create_start_and_connect():
        container = docker_client.containers.create(service.image, **sanitized_kwargs)
        if service.networks and not service.network_mode:
            for attachment in service.networks:
                network = docker_client.networks.get(attachment.name)
                network.connect(container, ipv4_address=attachment.ipv4_address)
        container.start()
        container.reload()
        return container

    try:
        return _create_start_and_connect()
    except APIError as exc:
        if not _is_missing_image_error(exc):
            raise DockerRuntimeError(
                f"Failed to deploy service '{service.name}' from {compose_path.name}: {exc}"
            ) from exc

        try:
            docker_client.images.pull(service.image)
        except (APIError, DockerException) as pull_exc:
            raise DockerRuntimeError(
                f"Failed to pull image '{service.image}' for service '{service.name}': {pull_exc}"
            ) from pull_exc

        try:
            return _create_start_and_connect()
        except (APIError, DockerException) as retry_exc:
            raise DockerRuntimeError(
                f"Failed to deploy service '{service.name}' from {compose_path.name}: {retry_exc}"
            ) from retry_exc
    except DockerException as exc:
        raise DockerRuntimeError(
            f"Failed to deploy service '{service.name}' from {compose_path.name}: {exc}"
        ) from exc


def _is_missing_image_error(error: APIError) -> bool:
    explanation = str(getattr(error, "explanation", "") or "").lower()
    message = str(error).lower()
    return "no such image" in explanation or "no such image" in message


def _resolve_network_mode(network_mode: str, created_containers: dict[str, Any]) -> str:
    if not network_mode.startswith("service:"):
        return network_mode

    target_service = network_mode.split(":", 1)[1]
    target_container = created_containers.get(target_service)
    if target_container is None:
        raise DockerRuntimeError(
            f"Service network_mode depends on unknown or unordered service '{target_service}'."
        )
    return f"container:{target_container.name}"


def _container_image_name(container) -> str:
    image = getattr(container, "image", None)
    tags = getattr(image, "tags", None) or []
    return tags[0] if tags else getattr(image, "short_id", "unknown")


def _topological_service_order(services: dict[str, ServiceSpec]) -> list[ServiceSpec]:
    ordered: list[ServiceSpec] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(service_name: str) -> None:
        if service_name in visited:
            return
        if service_name in visiting:
            raise DockerRuntimeError(
                f"Circular service dependency detected at '{service_name}'."
            )
        if service_name not in services:
            raise DockerRuntimeError(
                f"Service dependency '{service_name}' was not found."
            )

        visiting.add(service_name)
        service = services[service_name]
        for dependency in service.depends_on:
            visit(dependency)
        visiting.remove(service_name)
        visited.add(service_name)
        ordered.append(service)

    for service_name in services:
        visit(service_name)

    return ordered


def _looks_like_filesystem_path(source: str) -> bool:
    return source.startswith(("/", "./", "../", "~")) or "/" in source
