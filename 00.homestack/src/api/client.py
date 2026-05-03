"""Async-first static API client for env.json, meta.json, and projects.json."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from models.env import EnvItem
from models.meta import MetaItem
from models.projects import ProjectItem
from settings.settings import settings

from .exceptions import (
    APIBatchError,
    APIClientError,
    APIHTTPError,
    APINetworkError,
    APIParseError,
    APITimeoutError,
    APIValidationError,
)

Environment = Literal["dev", "prod"]
ProjectsCacheRefreshStatus = Literal["downloaded", "not_modified", "error"]


@dataclass(frozen=True)
class StaticAPIData:
    """Aggregate result containing all typed static API payloads."""

    env: list[EnvItem]
    meta: list[MetaItem]
    projects: list[ProjectItem]


class APIClient:
    """Robust async client for static API JSON endpoints."""

    def __init__(
        self,
        *,
        environment: Environment = "prod",
        base_url: str | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if environment not in {"dev", "prod"}:
            raise APIValidationError("environment must be 'dev' or 'prod'")
        if timeout_seconds <= 0:
            raise APIValidationError("timeout_seconds must be greater than 0")
        if max_retries < 0:
            raise APIValidationError("max_retries cannot be negative")
        if backoff_factor < 0:
            raise APIValidationError("backoff_factor cannot be negative")

        if base_url is None:
            resolved_base_url = settings.api_url
        else:
            resolved_base_url = base_url
        self._validate_base_url(resolved_base_url)

        self._base_url = resolved_base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._backoff_factor = backoff_factor
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> APIClient:
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    async def fetch_json(self, endpoint_path: str) -> Any:
        """Fetch and decode JSON from one endpoint path."""
        url = self._build_url(endpoint_path)
        response = await self._fetch_with_retries(url)

        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise APIParseError(f"Malformed JSON from {url}: {exc}") from exc
        except ValueError as exc:
            raise APIParseError(f"Invalid JSON payload from {url}: {exc}") from exc

    async def fetch_text(self, url_or_path: str) -> str:
        """Fetch a raw text file from either a relative path or absolute URL."""
        url = self._resolve_url(url_or_path)
        response = await self._fetch_with_retries(url)
        return response.text

    async def fetch_bytes(self, url_or_path: str) -> bytes:
        """Fetch a raw file as bytes from either a relative path or absolute URL."""
        url = self._resolve_url(url_or_path)
        response = await self._fetch_with_retries(url)
        return await response.aread()

    async def fetch_env(self) -> list[EnvItem]:
        payload = await self.fetch_json("env.json")
        return self._map_items(payload, EnvItem, "env.json")

    async def fetch_meta(self) -> list[MetaItem]:
        payload = await self.fetch_json("meta.json")
        return self._map_items(payload, MetaItem, "meta.json")

    async def fetch_projects(self) -> list[ProjectItem]:
        payload = await self.fetch_json("projects.json")
        return self._map_items(payload, ProjectItem, "projects.json")

    async def fetch_all(self) -> StaticAPIData:
        """Fetch all three static endpoint payloads.

        Strict mode by design: any failure raises APIBatchError.
        """
        failures: list[tuple[str, APIClientError]] = []

        async def _capture(endpoint_name: str, coro: Any) -> Any:
            try:
                return await coro
            except APIClientError as exc:
                failures.append((endpoint_name, exc))
                return None

        env_items = await _capture("env.json", self.fetch_env())
        meta_items = await _capture("meta.json", self.fetch_meta())
        project_items = await _capture("projects.json", self.fetch_projects())

        if failures:
            raise APIBatchError(failures)

        return StaticAPIData(env=env_items, meta=meta_items, projects=project_items)

    async def _run_sync_call(self, coroutine: Any) -> Any:
        """Run one async client call and clean up owned clients for sync wrappers.

        Sync methods use asyncio.run(), which creates/closes event loops per call.
        If this instance created its own AsyncClient, we must close and reset it
        after each sync invocation so subsequent sync calls do not reuse a client
        bound to a closed event loop.
        """
        try:
            return await coroutine
        finally:
            if self._client is not None and self._owns_client:
                await self._client.aclose()
                self._client = None

    def fetch_json_sync(self, endpoint_path: str) -> Any:
        return asyncio.run(self._run_sync_call(self.fetch_json(endpoint_path)))

    def fetch_env_sync(self) -> list[EnvItem]:
        return asyncio.run(self._run_sync_call(self.fetch_env()))

    def fetch_meta_sync(self) -> list[MetaItem]:
        return asyncio.run(self._run_sync_call(self.fetch_meta()))

    def fetch_projects_sync(self) -> list[ProjectItem]:
        return asyncio.run(self._run_sync_call(self.fetch_projects()))

    def refresh_projects_cache_sync(
        self,
        cache_dir: Path,
        *,
        silent: bool = True,
    ) -> ProjectsCacheRefreshStatus:
        return asyncio.run(
            self._run_sync_call(self.refresh_projects_cache(cache_dir, silent=silent))
        )

    def fetch_all_sync(self) -> StaticAPIData:
        return asyncio.run(self._run_sync_call(self.fetch_all()))

    def fetch_text_sync(self, url_or_path: str) -> str:
        return asyncio.run(self._run_sync_call(self.fetch_text(url_or_path)))

    def fetch_bytes_sync(self, url_or_path: str) -> bytes:
        return asyncio.run(self._run_sync_call(self.fetch_bytes(url_or_path)))

    async def refresh_projects_cache(
        self,
        cache_dir: Path,
        *,
        silent: bool = True,
    ) -> ProjectsCacheRefreshStatus:
        """Conditionally refresh local projects.json using HTTP cache validators.

        Returns:
            - "downloaded": remote projects.json was fetched and written locally.
            - "not_modified": remote returned HTTP 304 and local cache remains valid.
            - "error": remote check/fetch failed and caller should use local cache.
        """
        projects_path = cache_dir / "projects.json"
        validators = self._load_projects_cache_validators(cache_dir)

        headers: dict[str, str] = {}
        if projects_path.exists():
            etag = validators.get("etag")
            last_modified = validators.get("last_modified")
            if isinstance(etag, str) and etag:
                headers["If-None-Match"] = etag
            if isinstance(last_modified, str) and last_modified:
                headers["If-Modified-Since"] = last_modified

        url = self._build_url("projects.json")

        try:
            response = await self._fetch_with_retries(url, headers=headers or None)

            if response.status_code == 304:
                return "not_modified"

            payload = response.json()
            self._map_items(payload, ProjectItem, "projects.json")

            cache_dir.mkdir(parents=True, exist_ok=True)
            projects_path.write_text(
                json.dumps(payload, indent=2) + "\n",
                encoding="utf-8",
            )
            self._write_projects_cache_validators(cache_dir, response)
            return "downloaded"
        except (APIClientError, APIParseError, ValueError, TypeError):
            if silent:
                return "error"
            raise

    @staticmethod
    def _projects_cache_validators_path(cache_dir: Path) -> Path:
        return cache_dir / "projects.cache.json"

    @classmethod
    def _load_projects_cache_validators(cls, cache_dir: Path) -> dict[str, str]:
        path = cls._projects_cache_validators_path(cache_dir)
        if not path.exists():
            return {}

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

        if not isinstance(payload, dict):
            return {}

        validators: dict[str, str] = {}
        etag = payload.get("etag")
        last_modified = payload.get("last_modified")
        if isinstance(etag, str) and etag:
            validators["etag"] = etag
        if isinstance(last_modified, str) and last_modified:
            validators["last_modified"] = last_modified
        return validators

    @classmethod
    def _write_projects_cache_validators(
        cls, cache_dir: Path, response: httpx.Response
    ) -> None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        payload: dict[str, str] = {}
        etag = response.headers.get("ETag")
        last_modified = response.headers.get("Last-Modified")
        if etag:
            payload["etag"] = etag
        if last_modified:
            payload["last_modified"] = last_modified

        path = cls._projects_cache_validators_path(cache_dir)
        path.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            timeout = httpx.Timeout(self._timeout_seconds)
            self._client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)
            self._owns_client = True
        return self._client

    @staticmethod
    def _validate_base_url(base_url: str) -> None:
        if not base_url or not base_url.strip():
            raise APIValidationError("base_url cannot be empty")
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise APIValidationError(
                f"base_url must be absolute and use http or https: {base_url}"
            )

    def _build_url(self, endpoint_path: str) -> str:
        path = endpoint_path.strip()
        if not path:
            raise APIValidationError("endpoint_path cannot be empty")
        if "://" in path:
            raise APIValidationError("endpoint_path must be relative, not absolute URL")
        return f"{self._base_url}/{path.lstrip('/')}"

    def _resolve_url(self, url_or_path: str) -> str:
        raw_value = url_or_path.strip()
        if not raw_value:
            raise APIValidationError("url_or_path cannot be empty")

        parsed = urlparse(raw_value)
        if parsed.scheme:
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise APIValidationError(
                    f"absolute URL must use http or https: {url_or_path}"
                )
            return raw_value

        return self._build_url(raw_value)

    async def _fetch_with_retries(
        self, url: str, headers: dict[str, str] | None = None
    ) -> httpx.Response:
        client = await self._ensure_client()
        last_error: APIClientError | None = None

        for attempt in range(self._max_retries + 1):
            try:
                response = await client.get(url, headers=headers)
                if response.status_code >= 400:
                    error = self._map_http_status_error(url, response)
                    if (
                        self._is_retryable_status(response.status_code)
                        and attempt < self._max_retries
                    ):
                        await self._sleep_before_retry(attempt)
                        continue
                    raise error

                return response
            except httpx.TimeoutException as exc:
                last_error = APITimeoutError(f"Request timed out for {url}: {exc}")
            except httpx.ConnectError as exc:
                last_error = APINetworkError(
                    f"Could not connect to remote host for {url}: {exc}"
                )
            except httpx.NetworkError as exc:
                last_error = APINetworkError(
                    f"Network error while requesting {url}: {exc}"
                )
            except httpx.RequestError as exc:
                last_error = APINetworkError(
                    f"Request failed for {url}. Check internet connectivity: {exc}"
                )
            except APIHTTPError as exc:
                last_error = exc

            if last_error is None:
                continue

            if attempt >= self._max_retries or not self._is_retryable_error(last_error):
                raise last_error

            await self._sleep_before_retry(attempt)

        if last_error is not None:
            raise last_error

        raise APINetworkError(f"Request failed unexpectedly for {url}")

    async def _sleep_before_retry(self, attempt: int) -> None:
        delay = self._backoff_factor * (2**attempt)
        await asyncio.sleep(delay)

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        return status_code == 429 or 500 <= status_code <= 599

    @staticmethod
    def _is_retryable_error(error: APIClientError) -> bool:
        if isinstance(error, APIHTTPError):
            return APIClient._is_retryable_status(error.status_code)
        return isinstance(error, (APITimeoutError, APINetworkError))

    @staticmethod
    def _map_http_status_error(url: str, response: httpx.Response) -> APIHTTPError:
        status_code = response.status_code
        reason = response.reason_phrase or "Unknown error"
        message = f"HTTP {status_code} while requesting {url}: {reason}"

        if status_code == 404:
            message = f"Remote file not found (404): {url}"
        elif status_code in {502, 503, 504}:
            message = f"Server not available (HTTP {status_code}) for {url}"

        return APIHTTPError(url=url, status_code=status_code, message=message)

    @staticmethod
    def _map_items(payload: Any, model: type, endpoint_name: str) -> list[Any]:
        if not isinstance(payload, list):
            raise APIParseError(
                f"Expected top-level JSON array from {endpoint_name}, got {type(payload).__name__}"
            )

        items: list[Any] = []
        for idx, row in enumerate(payload):
            if not isinstance(row, dict):
                raise APIParseError(
                    f"Expected object at index {idx} in {endpoint_name}, got {type(row).__name__}"
                )
            try:
                items.append(model(**row))
            except TypeError as exc:
                raise APIParseError(
                    f"Invalid item at index {idx} in {endpoint_name}: {exc}"
                ) from exc
        return items
