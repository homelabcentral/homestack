"""Tests for async downloader client."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from src.client.downloader import (
    BatchDownloadError,
    Downloader,
    DownloadFileExistsError,
    DownloadHTTPError,
    DownloadIOError,
    DownloadJob,
    DownloadNetworkError,
    DownloadResult,
    DownloadTimeoutError,
    DownloadValidationError,
)
from src.settings.settings import settings

api_url = settings.api_url


def run(coro):
    """Execute async test helper."""
    return asyncio.run(coro)


def test_download_file_success(tmp_path: Path):
    """Downloader saves remote content to disk and returns metadata."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"hello world")

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    async def scenario() -> DownloadResult:
        downloader = Downloader(client=client)
        return await downloader.download_file(
            "https://example.com/file.txt",
            tmp_path / "file.txt",
        )

    result = run(scenario())

    assert result.success is True
    assert result.status_code == 200
    assert result.bytes_written == 11
    assert (tmp_path / "file.txt").read_bytes() == b"hello world"

    run(client.aclose())


def test_download_file_fails_when_destination_exists(tmp_path: Path):
    """Existing destination should fail based on policy."""

    existing_file = tmp_path / "already.txt"
    existing_file.write_text("existing")

    downloader = Downloader(
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200))
        )
    )

    with pytest.raises(DownloadFileExistsError):
        run(downloader.download_file("https://example.com/file.txt", existing_file))

    run(downloader._client.aclose())


def test_download_file_invalid_url(tmp_path: Path):
    """Invalid URL should fail before network request."""

    downloader = Downloader(
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200))
        )
    )

    with pytest.raises(DownloadValidationError):
        run(downloader.download_file("not-a-url", tmp_path / "file.txt"))

    run(downloader._client.aclose())


def test_download_file_404_not_retried(tmp_path: Path):
    """404 should fail fast as non-retryable."""

    calls = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    downloader = Downloader(client=client, max_retries=3)

    with pytest.raises(DownloadHTTPError):
        run(
            downloader.download_file(
                "https://example.com/missing.txt", tmp_path / "missing.txt"
            )
        )

    assert calls["count"] == 1
    run(client.aclose())


def test_download_file_retries_on_503_then_succeeds(tmp_path: Path):
    """Retryable server errors should be retried with backoff."""

    calls = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, content=b"ok")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    downloader = Downloader(client=client, max_retries=3, backoff_factor=0)

    result = run(
        downloader.download_file(
            "https://example.com/retry.txt",
            tmp_path / "retry.txt",
        )
    )

    assert result.success is True
    assert result.retries_used == 2
    assert calls["count"] == 3
    assert (tmp_path / "retry.txt").read_bytes() == b"ok"
    run(client.aclose())


def test_download_file_timeout_raises_timeout_error(tmp_path: Path):
    """Timeout errors should map to DownloadTimeoutError."""

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    downloader = Downloader(client=client, max_retries=0)

    with pytest.raises(DownloadTimeoutError):
        run(
            downloader.download_file(
                "https://example.com/slow.txt", tmp_path / "slow.txt"
            )
        )

    run(client.aclose())


def test_download_file_network_error(tmp_path: Path):
    """Connectivity errors should map to DownloadNetworkError."""

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    downloader = Downloader(client=client, max_retries=0)

    with pytest.raises(DownloadNetworkError):
        run(
            downloader.download_file(
                "https://example.com/down.txt", tmp_path / "down.txt"
            )
        )

    run(client.aclose())


def test_download_many_collects_failures_without_strict(tmp_path: Path):
    """Non-strict batch should return mixed success/failure results."""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("missing.txt"):
            return httpx.Response(404)
        return httpx.Response(200, content=b"payload")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    downloader = Downloader(client=client)

    jobs = [
        DownloadJob("https://example.com/ok.txt", tmp_path / "ok.txt"),
        DownloadJob("https://example.com/missing.txt", tmp_path / "missing.txt"),
    ]

    results = run(downloader.download_many(jobs, strict=False))

    assert len(results) == 2
    assert results[0].success is True
    assert results[1].success is False
    assert "404" in (results[1].error or "")
    run(client.aclose())


def test_download_many_strict_raises_batch_error(tmp_path: Path):
    """Strict batch mode should raise aggregate exception."""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("missing.txt"):
            return httpx.Response(404)
        return httpx.Response(200, content=b"payload")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    downloader = Downloader(client=client)

    jobs = [
        DownloadJob("https://example.com/ok.txt", tmp_path / "ok.txt"),
        DownloadJob("https://example.com/missing.txt", tmp_path / "missing.txt"),
    ]

    with pytest.raises(BatchDownloadError):
        run(downloader.download_many(jobs, strict=True))

    run(client.aclose())


def test_download_io_error_on_file_as_directory(tmp_path: Path):
    """Filesystem errors should map to DownloadIOError."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"payload")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    downloader = Downloader(client=client)

    blocker = tmp_path / "blocker"
    blocker.write_text("not a dir")

    with pytest.raises(DownloadIOError):
        run(
            downloader.download_file(
                "https://example.com/file.txt", blocker / "file.txt"
            )
        )

    run(client.aclose())


# ---------------------------------------------------------------------------
# Dev API endpoint tests (api_url = http://api:8043/00.api/v1)
# All tests use MockTransport so they run offline without the real server.
# ---------------------------------------------------------------------------

_API_FILES = ("env.json", "meta.json", "projects.json")

# Expected list lengths for each file (matches the real API payload shapes).
_API_FILE_LENGTHS = {
    "env.json": 5,
    "meta.json": 2,
    "projects.json": 7,
}


def _dev_api_transport() -> httpx.MockTransport:
    """Return a MockTransport that serves all active dev API JSON files."""

    async def handler(request: httpx.Request) -> httpx.Response:
        filename = request.url.path.rsplit("/", 1)[-1]
        payloads: dict[str, bytes] = {
            "env.json": b'[{"file_name":"email.env","description":"Email env vars","required":false}]',
            "meta.json": b'[{"file_name":"env.json","sha":"abc123","last_modified":"2026-04-23T08:16:40"}]',
            "projects.json": b'[{"slug":"pihole-unbound","name":"Pi-hole + Unbound","ready_to_deploy":true}]',
        }
        body = payloads.get(filename)
        if body is None:
            return httpx.Response(404)
        return httpx.Response(
            200, content=body, headers={"content-type": "application/json"}
        )

    return httpx.MockTransport(handler)


@pytest.mark.parametrize("filename", _API_FILES)
def test_dev_api_download_each_json_file(tmp_path: Path, filename: str):
    """Each JSON file can be downloaded from the dev API base URL."""

    client = httpx.AsyncClient(transport=_dev_api_transport())
    downloader = Downloader(client=client)

    url = f"{api_url}/{filename}"
    dest = tmp_path / filename

    result = run(downloader.download_file(url, dest))

    assert result.success is True
    assert result.status_code == 200
    assert result.bytes_written > 0
    assert dest.exists()
    parsed = json.loads(dest.read_bytes())
    assert isinstance(parsed, list)

    run(client.aclose())


def test_dev_api_download_all_files_batch(tmp_path: Path):
    """All active dev API JSON files can be downloaded in a single batch."""

    client = httpx.AsyncClient(transport=_dev_api_transport())
    downloader = Downloader(client=client)

    jobs = [
        DownloadJob(url=f"{api_url}/{name}", destination=tmp_path / name)
        for name in _API_FILES
    ]

    results = run(downloader.download_many(jobs, strict=True))

    assert len(results) == 3
    assert all(r.success for r in results)
    for name in _API_FILES:
        dest = tmp_path / name
        assert dest.exists(), f"{name} was not written to disk"
        parsed = json.loads(dest.read_bytes())
        assert isinstance(parsed, list)

    run(client.aclose())


def test_dev_api_unknown_file_returns_404(tmp_path: Path):
    """Requesting a file not served by the dev API raises DownloadHTTPError with 404."""

    client = httpx.AsyncClient(transport=_dev_api_transport())
    downloader = Downloader(client=client, max_retries=0)

    with pytest.raises(DownloadHTTPError) as exc_info:
        run(
            downloader.download_file(
                f"{api_url}/unknown.json", tmp_path / "unknown.json"
            )
        )

    assert exc_info.value.status_code == 404
    run(client.aclose())


def test_dev_api_server_unavailable_raises_http_error(tmp_path: Path):
    """A 503 from the dev API server raises DownloadHTTPError after retries are exhausted."""

    async def unavailable_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = httpx.AsyncClient(transport=httpx.MockTransport(unavailable_handler))
    downloader = Downloader(client=client, max_retries=1, backoff_factor=0)

    with pytest.raises(DownloadHTTPError) as exc_info:
        run(downloader.download_file(f"{api_url}/env.json", tmp_path / "env.json"))

    assert exc_info.value.status_code == 503
    run(client.aclose())


def test_dev_api_connection_refused_raises_network_error(tmp_path: Path):
    """A connection-refused error to the dev API host raises DownloadNetworkError."""

    async def refused_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(refused_handler))
    downloader = Downloader(client=client, max_retries=0)

    with pytest.raises(DownloadNetworkError):
        run(downloader.download_file(f"{api_url}/env.json", tmp_path / "env.json"))

    run(client.aclose())


def test_dev_api_batch_partial_failure_reported(tmp_path: Path):
    """Batch download from dev API surfaces per-item failure without raising."""

    async def partial_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("projects.json"):
            return httpx.Response(503)
        return httpx.Response(200, content=b'[{"ok":true}]')

    client = httpx.AsyncClient(transport=httpx.MockTransport(partial_handler))
    downloader = Downloader(client=client, max_retries=0)

    jobs = [
        DownloadJob(url=f"{api_url}/{name}", destination=tmp_path / name)
        for name in _API_FILES
    ]

    results = run(downloader.download_many(jobs, strict=False))

    assert len(results) == 3
    successes = [r for r in results if r.success]
    failures = [r for r in results if not r.success]
    assert len(successes) == 2
    assert len(failures) == 1
    assert failures[0].url.endswith("projects.json")

    run(client.aclose())


# ---------------------------------------------------------------------------
# Live integration tests — skipped unless the real dev API is reachable.
# Run with:  pytest -m integration
# ---------------------------------------------------------------------------

pytestmark_integration = pytest.mark.integration


def _dev_api_reachable() -> bool:
    """Return True if api_url returns HTTP 200 within 2 seconds."""
    try:
        response = httpx.get(f"{api_url}/env.json", timeout=2)
        return response.status_code == 200
    except httpx.TransportError:
        return False


_skip_if_no_dev_api = pytest.mark.skipif(
    not _dev_api_reachable(),
    reason=f"Dev API not reachable at {api_url}",
)


@_skip_if_no_dev_api
@pytest.mark.integration
@pytest.mark.parametrize("filename", _API_FILES)
def test_dev_api_live_download_each_file(tmp_path: Path, filename: str):
    """[LIVE] Download each JSON file from the real dev API and verify it is valid JSON."""

    async def scenario() -> DownloadResult:
        async with Downloader(timeout_seconds=10) as downloader:
            return await downloader.download_file(
                f"{api_url}/{filename}",
                tmp_path / filename,
            )

    result = run(scenario())

    assert result.success is True
    assert result.status_code == 200
    assert (tmp_path / filename).exists()
    parsed = json.loads((tmp_path / filename).read_bytes())
    assert isinstance(parsed, list)
    assert len(parsed) > 0


@_skip_if_no_dev_api
@pytest.mark.integration
def test_dev_api_live_batch_download_all(tmp_path: Path):
    """[LIVE] Download all active files from the real dev API in one batch."""

    async def scenario() -> list[DownloadResult]:
        jobs = [
            DownloadJob(url=f"{api_url}/{name}", destination=tmp_path / name)
            for name in _API_FILES
        ]
        async with Downloader(timeout_seconds=10) as downloader:
            return await downloader.download_many(jobs, strict=True)

    results = run(scenario())

    assert len(results) == 3
    assert all(r.success for r in results)
