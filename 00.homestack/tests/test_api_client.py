"""Tests for static API client."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from api.client import APIClient
from api.exceptions import (
    APIBatchError,
    APIHTTPError,
    APINetworkError,
    APIParseError,
    APITimeoutError,
    APIValidationError,
)
from models.env import EnvItem
from models.meta import MetaItem
from models.projects import ProjectItem
from settings.settings import settings

TEST_BASE_URL = settings.api_url


def run(coro):
    return asyncio.run(coro)


def test_init_defaults_to_prod_url():
    client = APIClient()
    assert "00.api/v1" in client._base_url


def test_init_invalid_environment_raises():
    with pytest.raises(APIValidationError, match="environment"):
        APIClient(environment="stage")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"timeout_seconds": 0},
        {"max_retries": -1},
        {"backoff_factor": -1},
        {"base_url": ""},
        {"base_url": "not-a-url"},
    ],
)
def test_init_invalid_config_raises(kwargs):
    with pytest.raises(APIValidationError):
        APIClient(**kwargs)


def test_fetch_json_empty_path_raises_validation_error():
    client = APIClient(base_url=TEST_BASE_URL)
    with pytest.raises(APIValidationError, match="endpoint_path"):
        run(client.fetch_json(""))


def test_fetch_json_absolute_path_rejected():
    client = APIClient(base_url=TEST_BASE_URL)
    with pytest.raises(APIValidationError, match="relative"):
        run(client.fetch_json(f"{TEST_BASE_URL}/env.json"))


def test_fetch_text_relative_path_returns_text():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("readme.md")
        return httpx.Response(200, text="# Project\n\nReadme content")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api = APIClient(base_url=TEST_BASE_URL, client=client)

    result = run(api.fetch_text("01.pihole-unbound/readme.md"))

    assert result == "# Project\n\nReadme content"
    run(client.aclose())


def test_fetch_bytes_absolute_url_returns_bytes():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://example.test/docker-compose.yml"
        return httpx.Response(200, content=b"services:\n  app:\n    image: nginx")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api = APIClient(base_url=TEST_BASE_URL, client=client)

    result = run(api.fetch_bytes("https://example.test/docker-compose.yml"))

    assert result == b"services:\n  app:\n    image: nginx"
    run(client.aclose())


def test_fetch_text_empty_value_raises_validation_error():
    client = APIClient(base_url=TEST_BASE_URL)
    with pytest.raises(APIValidationError, match="url_or_path"):
        run(client.fetch_text(""))


def test_fetch_bytes_invalid_absolute_url_raises_validation_error():
    client = APIClient(base_url=TEST_BASE_URL)
    with pytest.raises(APIValidationError, match="http or https"):
        run(client.fetch_bytes("ftp://example.test/file.txt"))


def test_fetch_text_sync_returns_text():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="version: '3.9'")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api = APIClient(base_url=TEST_BASE_URL, client=client)

    result = api.fetch_text_sync("docker-compose.yml")

    assert result == "version: '3.9'"
    run(client.aclose())


def test_fetch_bytes_404_raises_http_error_not_retried():
    calls = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api = APIClient(base_url=TEST_BASE_URL, max_retries=3, client=client)

    with pytest.raises(APIHTTPError) as exc:
        run(api.fetch_bytes("readme.md"))

    assert exc.value.status_code == 404
    assert calls["count"] == 1
    run(client.aclose())


def test_sequential_sync_calls_recreate_owned_client_safely(monkeypatch):
    calls = {"meta": 0, "readmes": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("meta.json"):
            calls["meta"] += 1
            return httpx.Response(
                200,
                json=[
                    {
                        "file_name": "env.json",
                        "last_modified": "2026-04-25T00:00:00Z",
                        "sha": "abc",
                        "md5": "def",
                    }
                ],
            )
        if path.endswith("readmes.json"):
            calls["readmes"] += 1
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    class _PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("api.client.httpx.AsyncClient", _PatchedAsyncClient)

    api = APIClient(base_url=TEST_BASE_URL)

    meta = api.fetch_meta_sync()
    readmes = api.fetch_json_sync("readmes.json")

    assert len(meta) == 1
    assert readmes == []
    assert calls["meta"] == 1
    assert calls["readmes"] == 1
    assert api._client is None


def test_fetch_env_success_returns_env_items():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "file_name": "host.env.template",
                    "description": "Host vars",
                    "required": True,
                }
            ],
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api = APIClient(base_url=TEST_BASE_URL, client=client)

    result = run(api.fetch_env())

    assert result == [
        EnvItem(file_name="host.env.template", description="Host vars", required=True)
    ]
    run(client.aclose())


def test_fetch_meta_success_returns_meta_items():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "file_name": "env.json",
                    "last_modified": "2026-04-25T00:00:00Z",
                    "sha": "abc",
                    "md5": "def",
                }
            ],
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api = APIClient(base_url=TEST_BASE_URL, client=client)

    result = run(api.fetch_meta())

    assert result == [
        MetaItem(
            file_name="env.json",
            last_modified="2026-04-25T00:00:00Z",
            sha="abc",
            md5="def",
        )
    ]
    run(client.aclose())


def test_fetch_projects_success_returns_project_items():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "project_index": 1,
                    "project_name": "Pi-hole",
                    "dir_name": "01.pihole-unbound",
                    "compose": "docker-compose.yml",
                    "env": ".env.template",
                    "readme": "readme.md",
                }
            ],
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api = APIClient(base_url=TEST_BASE_URL, client=client)

    result = run(api.fetch_projects())

    assert result == [
        ProjectItem(
            project_index=1,
            project_name="Pi-hole",
            dir_name="01.pihole-unbound",
            compose="docker-compose.yml",
            env=".env.template",
            readme="readme.md",
        )
    ]
    run(client.aclose())


def test_fetch_projects_wrong_root_shape_raises_parse_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"project_name": "Pi-hole"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api = APIClient(base_url=TEST_BASE_URL, client=client)

    with pytest.raises(APIParseError, match="top-level JSON array"):
        run(api.fetch_projects())

    run(client.aclose())


def test_fetch_projects_row_not_object_raises_parse_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["bad-row"])

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api = APIClient(base_url=TEST_BASE_URL, client=client)

    with pytest.raises(APIParseError, match="index 0"):
        run(api.fetch_projects())

    run(client.aclose())


def test_fetch_projects_invalid_row_schema_raises_parse_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"project_name": "Pi-hole"}])

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api = APIClient(base_url=TEST_BASE_URL, client=client)

    with pytest.raises(APIParseError, match="Invalid item"):
        run(api.fetch_projects())

    run(client.aclose())


def test_fetch_projects_404_raises_http_error_not_retried():
    calls = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api = APIClient(base_url=TEST_BASE_URL, max_retries=3, client=client)

    with pytest.raises(APIHTTPError) as exc:
        run(api.fetch_projects())

    assert exc.value.status_code == 404
    assert calls["count"] == 1
    run(client.aclose())


def test_refresh_projects_cache_sync_downloads_and_writes_cache(tmp_path: Path):
    payload = [
        {
            "project_index": 1,
            "project_name": "Pi-hole",
            "dir_name": "01.pihole-unbound",
            "compose": "docker-compose.yml",
            "env": ".env.template",
            "readme": "readme.md",
        }
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("projects.json")
        return httpx.Response(
            200,
            json=payload,
            headers={"Last-Modified": "Sun, 26 Apr 2026 10:00:00 GMT"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api = APIClient(base_url=TEST_BASE_URL, client=client)

    result = api.refresh_projects_cache_sync(tmp_path, silent=False)

    assert result == "downloaded"
    projects_path = tmp_path / "projects.json"
    validators_path = tmp_path / "projects.cache.json"
    assert projects_path.exists()
    assert validators_path.exists()
    assert json.loads(projects_path.read_text(encoding="utf-8")) == payload
    validators = json.loads(validators_path.read_text(encoding="utf-8"))
    assert validators["last_modified"] == "Sun, 26 Apr 2026 10:00:00 GMT"
    run(client.aclose())


def test_refresh_projects_cache_sync_returns_not_modified_on_304(tmp_path: Path):
    payload = [
        {
            "project_index": 1,
            "project_name": "Pi-hole",
            "dir_name": "01.pihole-unbound",
            "compose": "docker-compose.yml",
            "env": ".env.template",
            "readme": "readme.md",
        }
    ]

    projects_path = tmp_path / "projects.json"
    projects_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (tmp_path / "projects.cache.json").write_text(
        json.dumps({"last_modified": "Sun, 26 Apr 2026 10:00:00 GMT"}, indent=2) + "\n",
        encoding="utf-8",
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        assert (
            request.headers.get("If-Modified-Since") == "Sun, 26 Apr 2026 10:00:00 GMT"
        )
        return httpx.Response(304)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api = APIClient(base_url=TEST_BASE_URL, client=client)

    result = api.refresh_projects_cache_sync(tmp_path, silent=False)

    assert result == "not_modified"
    assert json.loads(projects_path.read_text(encoding="utf-8")) == payload
    run(client.aclose())


def test_refresh_projects_cache_sync_falls_back_silently_on_network_error(
    tmp_path: Path,
):
    payload = [
        {
            "project_index": 1,
            "project_name": "Local Only",
            "dir_name": "01.local-only",
            "compose": "docker-compose.yml",
            "env": ".env.template",
            "readme": "readme.md",
        }
    ]
    projects_path = tmp_path / "projects.json"
    projects_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api = APIClient(base_url=TEST_BASE_URL, client=client, max_retries=0)

    result = api.refresh_projects_cache_sync(tmp_path, silent=True)

    assert result == "error"
    assert json.loads(projects_path.read_text(encoding="utf-8")) == payload
    run(client.aclose())


def test_fetch_projects_retries_on_503_then_succeeds():
    calls = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 3:
            return httpx.Response(503)
        return httpx.Response(
            200,
            json=[
                {
                    "project_index": 1,
                    "project_name": "Pi-hole",
                    "dir_name": "01.pihole-unbound",
                    "compose": "docker-compose.yml",
                    "env": ".env.template",
                    "readme": "readme.md",
                }
            ],
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api = APIClient(
        base_url=TEST_BASE_URL, max_retries=3, backoff_factor=0, client=client
    )

    result = run(api.fetch_projects())

    assert calls["count"] == 3
    assert len(result) == 1
    assert result[0].project_name == "Pi-hole"
    run(client.aclose())


def test_fetch_projects_timeout_raises_api_timeout_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api = APIClient(base_url=TEST_BASE_URL, max_retries=0, client=client)

    with pytest.raises(APITimeoutError):
        run(api.fetch_projects())

    run(client.aclose())


def test_fetch_projects_network_raises_api_network_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api = APIClient(base_url=TEST_BASE_URL, max_retries=0, client=client)

    with pytest.raises(APINetworkError):
        run(api.fetch_projects())

    run(client.aclose())


def test_fetch_json_404_raises_http_error_not_retried():
    calls = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api = APIClient(base_url=TEST_BASE_URL, max_retries=3, client=client)

    with pytest.raises(APIHTTPError) as exc:
        run(api.fetch_json("env.json"))

    assert exc.value.status_code == 404
    assert calls["count"] == 1
    run(client.aclose())


def test_fetch_json_retries_on_503_then_succeeds():
    calls = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json=[{"ok": True}])

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api = APIClient(
        base_url=TEST_BASE_URL, max_retries=3, backoff_factor=0, client=client
    )

    result = run(api.fetch_json("env.json"))

    assert result == [{"ok": True}]
    assert calls["count"] == 3
    run(client.aclose())


def test_fetch_json_timeout_raises_api_timeout_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api = APIClient(base_url=TEST_BASE_URL, max_retries=0, client=client)

    with pytest.raises(APITimeoutError):
        run(api.fetch_json("env.json"))

    run(client.aclose())


def test_fetch_json_network_raises_api_network_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api = APIClient(base_url=TEST_BASE_URL, max_retries=0, client=client)

    with pytest.raises(APINetworkError):
        run(api.fetch_json("env.json"))

    run(client.aclose())


def test_fetch_json_malformed_json_raises_parse_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"{not-json")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api = APIClient(base_url=TEST_BASE_URL, client=client)

    with pytest.raises(APIParseError, match="Malformed JSON"):
        run(api.fetch_json("env.json"))

    run(client.aclose())


def test_fetch_env_wrong_root_shape_raises_parse_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"file_name": "host.env.template"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api = APIClient(base_url=TEST_BASE_URL, client=client)

    with pytest.raises(APIParseError, match="top-level JSON array"):
        run(api.fetch_env())

    run(client.aclose())


def test_fetch_env_row_not_object_raises_parse_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["bad-row"])

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api = APIClient(base_url=TEST_BASE_URL, client=client)

    with pytest.raises(APIParseError, match="index 0"):
        run(api.fetch_env())

    run(client.aclose())


def test_fetch_env_invalid_row_schema_raises_parse_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"file_name": "host.env.template"}])

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api = APIClient(base_url=TEST_BASE_URL, client=client)

    with pytest.raises(APIParseError, match="Invalid item"):
        run(api.fetch_env())

    run(client.aclose())


def test_fetch_all_success_returns_typed_aggregate():
    async def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("env.json"):
            return httpx.Response(
                200,
                json=[
                    {
                        "file_name": "host.env.template",
                        "description": "Host",
                        "required": True,
                    }
                ],
            )
        if path.endswith("meta.json"):
            return httpx.Response(
                200,
                json=[
                    {
                        "file_name": "env.json",
                        "last_modified": "2026-04-25T00:00:00Z",
                        "sha": "abc",
                        "md5": "def",
                    }
                ],
            )
        return httpx.Response(
            200,
            json=[
                {
                    "project_index": 1,
                    "project_name": "Pi-hole",
                    "dir_name": "01.pihole-unbound",
                    "compose": "docker-compose.yml",
                    "env": ".env.template",
                    "readme": "readme.md",
                }
            ],
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api = APIClient(base_url=TEST_BASE_URL, client=client)

    result = run(api.fetch_all())

    assert len(result.env) == 1
    assert len(result.meta) == 1
    assert len(result.projects) == 1
    assert isinstance(result.env[0], EnvItem)
    assert isinstance(result.meta[0], MetaItem)
    assert isinstance(result.projects[0], ProjectItem)
    run(client.aclose())


def test_fetch_all_strict_failure_raises_batch_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("meta.json"):
            return httpx.Response(500)
        if request.url.path.endswith("env.json"):
            return httpx.Response(
                200,
                json=[
                    {
                        "file_name": "host.env.template",
                        "description": "Host",
                        "required": True,
                    }
                ],
            )
        return httpx.Response(
            200,
            json=[
                {
                    "project_index": 1,
                    "project_name": "Pi-hole",
                    "dir_name": "01.pihole-unbound",
                    "compose": "docker-compose.yml",
                    "env": ".env.template",
                    "readme": "readme.md",
                }
            ],
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api = APIClient(base_url=TEST_BASE_URL, max_retries=0, client=client)

    with pytest.raises(APIBatchError) as exc:
        run(api.fetch_all())

    assert any(endpoint == "meta.json" for endpoint, _ in exc.value.failures)
    run(client.aclose())


def test_sync_wrapper_fetch_env():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "file_name": "host.env.template",
                    "description": "Host vars",
                    "required": True,
                }
            ],
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api = APIClient(base_url=TEST_BASE_URL, client=client)

    result = api.fetch_env_sync()
    assert result[0].file_name == "host.env.template"

    run(client.aclose())
