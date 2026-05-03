from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from docker.errors import NotFound
from utils import docker_runtime


class FakeImage:
    def __init__(self, image: str):
        self.tags = [image]


class FakeContainer:
    def __init__(self, image: str, name: str, labels: dict[str, str] | None = None):
        self.image = FakeImage(image)
        self.name = name
        self.labels = labels or {}
        self.status = "created"
        self.stop_calls = 0
        self.remove_calls = 0

    def start(self) -> None:
        self.status = "running"

    def reload(self) -> None:
        return None

    def stop(self, timeout: int = 10) -> None:
        self.stop_calls += 1
        self.status = "exited"

    def remove(self, v: bool = False, force: bool = False) -> None:
        self.remove_calls += 1


class FakeContainers:
    def __init__(self):
        self.by_name: dict[str, FakeContainer] = {}
        self.created: list[tuple[str, dict]] = []

    def get(self, name: str) -> FakeContainer:
        if name not in self.by_name:
            raise NotFound("missing")
        return self.by_name[name]

    def create(self, image: str, **kwargs):
        container = FakeContainer(
            image=image, name=kwargs["name"], labels=kwargs.get("labels")
        )
        self.by_name[container.name] = container
        self.created.append((image, kwargs))
        return container

    def list(self, all: bool = True, filters=None):
        labels = (filters or {}).get("label", [])
        managed = None
        project = None
        for label in labels:
            if label.startswith(f"{docker_runtime.HOMESTACK_MANAGED_LABEL}="):
                managed = label.split("=", 1)[1]
            if label.startswith(f"{docker_runtime.HOMESTACK_PROJECT_LABEL}="):
                project = label.split("=", 1)[1]

        result = []
        for container in self.by_name.values():
            if (
                managed
                and container.labels.get(docker_runtime.HOMESTACK_MANAGED_LABEL)
                != managed
            ):
                continue
            if (
                project
                and container.labels.get(docker_runtime.HOMESTACK_PROJECT_LABEL)
                != project
            ):
                continue
            result.append(container)
        return result


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_project_items() -> list[dict[str, Any]]:
    repo_root = _repo_root()
    projects_path = repo_root / "00.api" / "v1" / "projects.json"
    return json.loads(projects_path.read_text(encoding="utf-8"))


def _render_env_template(template_path: Path, destination: Path) -> None:
    lines: list[str] = []
    in_metadata = False
    for raw_line in template_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip("\n")
        stripped = line.strip()
        if stripped == "# METADATA --- START":
            in_metadata = True
            continue
        if stripped == "# METADATA --- END":
            in_metadata = False
            continue
        if in_metadata or not stripped or stripped.startswith("#"):
            continue
        value_part = line.split("#", 1)[0].rstrip()
        if "=" in value_part:
            lines.append(value_part)
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _resolve_required_env_files(project: dict[str, Any], temp_root: Path) -> list[Path]:
    required_env_files = project.get("required_env_files")
    assert required_env_files is not None, (
        f"Project {project['project_name']} must define required_env_files in projects.json"
    )
    resolved: list[Path] = []

    for env_entry in required_env_files:
        env_path = Path(env_entry)
        if not env_path.is_absolute():
            env_path = temp_root / "00.env" / env_path
        resolved.append(env_path.resolve())
    return resolved


@pytest.mark.parametrize("project_item", _load_project_items())
def test_project_compose_files_parse_with_docker_runtime(
    tmp_path: Path, project_item: dict[str, Any]
):
    repo_root = _repo_root()
    project_name = project_item["project_name"]
    project_dir = tmp_path / project_item["dir_name"]

    shutil.copytree(repo_root / project_item["dir_name"], project_dir)
    shutil.copytree(repo_root / "00.env", tmp_path / "00.env")

    compose_path = project_dir / project_item["compose"]
    assert compose_path.exists(), f"Compose file missing for project: {project_name}"

    generated_env_path = project_dir / ".env"
    if not generated_env_path.exists():
        template_path = project_dir / project_item["env"]
        if template_path.exists():
            _render_env_template(template_path, generated_env_path)
        else:
            generated_env_path.write_text("\n", encoding="utf-8")

    env_files = [
        generated_env_path.resolve(),
        *_resolve_required_env_files(project_item, tmp_path),
    ]
    spec = docker_runtime.load_project_spec(
        compose_path, env_files, project_item["dir_name"]
    )

    assert spec.services, f"No services parsed for project: {project_name}"
    assert all(service.image for service in spec.services.values())


class FakeNetwork:
    def __init__(self, name: str, attrs: dict | None = None):
        self.name = name
        self.attrs = attrs or {
            "Driver": "bridge",
            "IPAM": {
                "Config": [
                    {
                        "Subnet": docker_runtime.TRAEFIK_NETWORK_SUBNET,
                        "Gateway": docker_runtime.TRAEFIK_NETWORK_GATEWAY,
                    }
                ]
            },
        }
        self.connected: list[tuple[str, str | None]] = []

    def connect(
        self, container: FakeContainer, ipv4_address: str | None = None
    ) -> None:
        self.connected.append((container.name, ipv4_address))


class FakeNetworks:
    def __init__(self, existing: dict[str, FakeNetwork] | None = None):
        self.existing = existing or {}
        self.created: list[tuple[str, dict]] = []

    def get(self, name: str) -> FakeNetwork:
        if name not in self.existing:
            raise NotFound("missing")
        return self.existing[name]

    def create(self, name: str, **kwargs):
        self.created.append((name, kwargs))
        self.existing[name] = FakeNetwork(name)
        return self.existing[name]


class FakeImages:
    def __init__(self):
        self.removed: list[str] = []
        self.pulled: list[str] = []

    def pull(self, image: str) -> None:
        self.pulled.append(image)

    def remove(self, image: str, force: bool = False, noprune: bool = False) -> None:
        _ = force
        _ = noprune
        self.removed.append(image)


class FakeClient:
    def __init__(
        self,
        networks: FakeNetworks | None = None,
        containers: FakeContainers | None = None,
    ):
        self.networks = networks or FakeNetworks()
        self.containers = containers or FakeContainers()
        self.images = FakeImages()


def test_ensure_traefik_bridge_network_creates_when_missing():
    client = FakeClient()

    docker_runtime.ensure_traefik_bridge_network(client)

    assert client.networks.created
    created_name, kwargs = client.networks.created[0]
    assert created_name == docker_runtime.TRAEFIK_NETWORK_NAME
    assert kwargs["driver"] == "bridge"


def test_ensure_traefik_bridge_network_rejects_conflicting_network():
    conflicting = FakeNetwork(
        docker_runtime.TRAEFIK_NETWORK_NAME,
        attrs={
            "Driver": "overlay",
            "IPAM": {"Config": [{"Subnet": "10.0.0.0/24", "Gateway": "10.0.0.1"}]},
        },
    )
    client = FakeClient(
        networks=FakeNetworks({docker_runtime.TRAEFIK_NETWORK_NAME: conflicting})
    )

    with pytest.raises(docker_runtime.DockerNetworkConflictError):
        docker_runtime.ensure_traefik_bridge_network(client)


def test_load_project_spec_interpolates_env_and_dependencies(tmp_path: Path):
    compose_dir = tmp_path / "project"
    compose_dir.mkdir(parents=True, exist_ok=True)
    env_dir = tmp_path / "00.env"
    env_dir.mkdir(parents=True, exist_ok=True)

    compose_path = compose_dir / "docker-compose.yml"
    compose_path.write_text(
        """
name: demo
services:
  db:
    image: postgres:16
    container_name: db-service
    env_file:
      - .env
      - ../00.env/network.env
    environment:
      - POSTGRES_DB=${POSTGRES_DB:-demo}
    networks:
      traefiknet:
        ipv4_address: ${DB_IP:-172.16.0.20}
  app:
    image: app:latest
    container_name: app-service
    depends_on:
      - db
    network_mode: service:db
    environment:
      - APP_MODE=${APP_MODE:-prod}
networks:
  traefiknet:
    name: ${DOCKER_NETWORK:-traefiknet}
    external: true
""",
        encoding="utf-8",
    )
    (compose_dir / ".env").write_text(
        "POSTGRES_DB=customdb\nDOCKER_NETWORK=traefiknet\n", encoding="utf-8"
    )
    (env_dir / "network.env").write_text("DB_IP=172.16.0.44\n", encoding="utf-8")

    spec = docker_runtime.load_project_spec(
        compose_path,
        [(compose_dir / ".env").resolve(), (env_dir / "network.env").resolve()],
        "demo-project",
    )

    assert spec.networks["traefiknet"].name == "traefiknet"
    assert spec.services["db"].environment["POSTGRES_DB"] == "customdb"
    assert spec.services["db"].networks[0].ipv4_address == "172.16.0.44"
    assert "db" in spec.services["app"].depends_on


def test_load_project_spec_strips_inline_env_comments_from_values(tmp_path: Path):
    compose_dir = tmp_path / "project"
    compose_dir.mkdir(parents=True, exist_ok=True)
    env_dir = tmp_path / "00.env"
    env_dir.mkdir(parents=True, exist_ok=True)

    compose_path = compose_dir / "docker-compose.yml"
    compose_path.write_text(
        """
services:
  dozzle:
    image: amir20/dozzle:latest
    container_name: dozzle
    ports:
      - ${IP_TAILSCALE}:${PORT_DZ_DOZZLE_EXTERNAL}:${PORT_DZ_DOZZLE_INTERNAL}
networks:
  traefiknet:
    name: traefiknet
    external: true
""",
        encoding="utf-8",
    )

    (compose_dir / ".env").write_text(
        "PORT_DZ_DOZZLE_EXTERNAL=8080 # external port\n"
        "PORT_DZ_DOZZLE_INTERNAL=8080 # internal port\n",
        encoding="utf-8",
    )
    (env_dir / "network.env").write_text(
        "IP_TAILSCALE=100.87.58.28 # tailscale ip\n",
        encoding="utf-8",
    )

    spec = docker_runtime.load_project_spec(
        compose_path,
        [(compose_dir / ".env").resolve(), (env_dir / "network.env").resolve()],
        "dozzle",
    )

    assert spec.services["dozzle"].ports == {
        "8080/tcp": {"HostIp": "100.87.58.28", "HostPort": "8080"}
    }


def test_parse_ports_supports_host_ip_mapping() -> None:
    ports = docker_runtime._parse_ports(["100.87.58.28:8080:8080"])

    assert ports == {"8080/tcp": {"HostIp": "100.87.58.28", "HostPort": "8080"}}


def test_compose_base_command_uses_absolute_paths_and_ordered_env_files(tmp_path: Path):
    compose_dir = tmp_path / "project"
    compose_dir.mkdir(parents=True, exist_ok=True)
    compose_path = compose_dir / "docker-compose.yml"
    compose_path.write_text("services: {}\n", encoding="utf-8")
    env_path = compose_dir / ".env"
    host_env_path = tmp_path / "00.env" / "host.env"
    host_env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("EXAMPLE=1\n", encoding="utf-8")
    host_env_path.write_text("HOST_UID=1000\n", encoding="utf-8")

    command = docker_runtime._compose_base_command(
        compose_path,
        "demo-project",
        [env_path, host_env_path],
    )

    assert command == [
        "docker",
        "compose",
        "--env-file",
        str(env_path.resolve()),
        "--env-file",
        str(host_env_path.resolve()),
        "--file",
        str(compose_path.resolve()),
        "--project-name",
        "demo-project",
    ]


def test_validate_compose_config_runs_config_quiet(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    compose_dir = tmp_path / "project"
    compose_dir.mkdir(parents=True, exist_ok=True)
    compose_path = compose_dir / "docker-compose.yml"
    compose_path.write_text("services: {}\n", encoding="utf-8")
    env_path = compose_dir / ".env"
    env_path.write_text("EXAMPLE=1\n", encoding="utf-8")

    captured: dict[str, Any] = {}

    def fake_run_compose_command(
        compose_path_arg: Path,
        project_slug: str,
        env_files: list[Path],
        compose_args: list[str],
        *,
        error_context: str,
    ):
        captured["compose_path"] = compose_path_arg
        captured["project_slug"] = project_slug
        captured["env_files"] = env_files
        captured["compose_args"] = compose_args
        captured["error_context"] = error_context
        return None

    monkeypatch.setattr(
        docker_runtime, "_run_compose_command", fake_run_compose_command
    )

    docker_runtime.validate_compose_config(
        compose_path,
        "demo-project",
        [env_path.resolve()],
    )

    assert captured == {
        "compose_path": compose_path,
        "project_slug": "demo-project",
        "env_files": [env_path.resolve()],
        "compose_args": ["config", "--quiet"],
        "error_context": "validate compose config",
    }


def test_deploy_project_stack_runs_compose_up_and_collects_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    compose_dir = tmp_path / "project"
    compose_dir.mkdir(parents=True, exist_ok=True)
    compose_path = compose_dir / "docker-compose.yml"
    compose_path.write_text("services: {}\n", encoding="utf-8")
    env_path = compose_dir / ".env"
    env_path.write_text("EXAMPLE=1\n", encoding="utf-8")

    calls: list[dict[str, Any]] = []

    def fake_run_compose_command(
        compose_path_arg: Path,
        project_slug: str,
        env_files: list[Path],
        compose_args: list[str],
        *,
        error_context: str,
    ):
        calls.append(
            {
                "compose_path": compose_path_arg,
                "project_slug": project_slug,
                "env_files": env_files,
                "compose_args": compose_args,
                "error_context": error_context,
            }
        )
        if compose_args == ["ps", "--format", "json"]:
            return type(
                "Completed",
                (),
                {
                    "stdout": json.dumps(
                        [
                            {
                                "Service": "app",
                                "Name": "app-service",
                                "Status": "running",
                                "Image": "app:latest",
                            },
                            {
                                "Service": "db",
                                "Name": "db-service",
                                "Status": "running",
                                "Image": "postgres:16",
                            },
                        ]
                    )
                },
            )()
        return type("Completed", (), {"stdout": ""})()

    monkeypatch.setattr(
        docker_runtime, "_run_compose_command", fake_run_compose_command
    )

    result = docker_runtime.deploy_project_stack(
        compose_path,
        "demo-project",
        [env_path.resolve()],
    )

    assert [call["compose_args"] for call in calls] == [
        ["up", "-d"],
        ["ps", "--format", "json"],
    ]
    assert [container.container_name for container in result.containers] == [
        "app-service",
        "db-service",
    ]


def test_collect_project_status_supports_json_lines(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    compose_dir = tmp_path / "project"
    compose_dir.mkdir(parents=True, exist_ok=True)
    compose_path = compose_dir / "docker-compose.yml"
    compose_path.write_text("services: {}\n", encoding="utf-8")
    env_path = compose_dir / ".env"
    env_path.write_text("EXAMPLE=1\n", encoding="utf-8")

    def fake_run_compose_command(
        compose_path_arg: Path,
        project_slug: str,
        env_files: list[Path],
        compose_args: list[str],
        *,
        error_context: str,
    ):
        _ = compose_path_arg
        _ = project_slug
        _ = env_files
        _ = compose_args
        _ = error_context
        return type(
            "Completed",
            (),
            {
                "stdout": "\n".join(
                    [
                        json.dumps(
                            {
                                "Service": "app",
                                "Name": "app-service",
                                "State": "running",
                                "Image": "app:latest",
                            }
                        ),
                        json.dumps(
                            {
                                "Service": "db",
                                "Name": "db-service",
                                "State": "running",
                                "Image": "postgres:16",
                            }
                        ),
                    ]
                )
            },
        )()

    monkeypatch.setattr(
        docker_runtime, "_run_compose_command", fake_run_compose_command
    )

    statuses = docker_runtime._collect_project_status(
        compose_path,
        "demo-project",
        [env_path.resolve()],
    )

    assert [(status.service_name, status.container_name) for status in statuses] == [
        ("app", "app-service"),
        ("db", "db-service"),
    ]


@pytest.mark.parametrize(
    ("runtime_function", "expected_args"),
    [
        (docker_runtime.start_project_stack, ["up", "-d"]),
        (docker_runtime.stop_project_stack, ["down"]),
        (docker_runtime.remove_project_stack, ["down", "--rmi", "all"]),
    ],
)
def test_lifecycle_commands_use_expected_compose_subcommands(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    runtime_function,
    expected_args: list[str],
):
    compose_dir = tmp_path / "project"
    compose_dir.mkdir(parents=True, exist_ok=True)
    compose_path = compose_dir / "docker-compose.yml"
    compose_path.write_text("services: {}\n", encoding="utf-8")
    env_path = compose_dir / ".env"
    env_path.write_text("EXAMPLE=1\n", encoding="utf-8")

    calls: list[dict[str, Any]] = []

    def fake_run_compose_command(
        compose_path_arg: Path,
        project_slug: str,
        env_files: list[Path],
        compose_args: list[str],
        *,
        error_context: str,
    ):
        calls.append(
            {
                "compose_path": compose_path_arg,
                "project_slug": project_slug,
                "env_files": env_files,
                "compose_args": compose_args,
                "error_context": error_context,
            }
        )
        return type("Completed", (), {"stdout": ""})()

    monkeypatch.setattr(
        docker_runtime, "_run_compose_command", fake_run_compose_command
    )

    runtime_function(
        compose_path,
        "demo-project",
        [env_path.resolve()],
    )

    assert calls == [
        {
            "compose_path": compose_path,
            "project_slug": "demo-project",
            "env_files": [env_path.resolve()],
            "compose_args": expected_args,
            "error_context": (
                "start project 'demo-project'"
                if expected_args == ["up", "-d"]
                else (
                    "stop project 'demo-project'"
                    if expected_args == ["down"]
                    else "remove project 'demo-project'"
                )
            ),
        }
    ]
