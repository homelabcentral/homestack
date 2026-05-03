"""Async file downloader with robust error handling.

This module provides a focused Downloader class responsible for
retrieving remote files and storing them on disk atomically.
"""

from __future__ import annotations

import asyncio
import errno
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from urllib.parse import urlparse
from uuid import uuid4

import httpx


class DownloaderError(Exception):
    """Base exception for all downloader failures."""


class DownloadValidationError(DownloaderError):
    """Raised when downloader input is invalid."""


class DownloadFileExistsError(DownloaderError):
    """Raised when destination path already exists."""


class DownloadTimeoutError(DownloaderError):
    """Raised when request times out."""


class DownloadNetworkError(DownloaderError):
    """Raised for network-related failures."""


class DownloadHTTPError(DownloaderError):
    """Raised when remote server returns an error status."""

    def __init__(self, url: str, status_code: int, message: str) -> None:
        super().__init__(message)
        self.url = url
        self.status_code = status_code


class DownloadIOError(DownloaderError):
    """Raised when local file operations fail."""


class BatchDownloadError(DownloaderError):
    """Raised when strict batch download mode encounters failures."""

    def __init__(self, failures: list[tuple[DownloadJob, DownloaderError]]) -> None:
        urls = ", ".join(job.url for job, _ in failures)
        super().__init__(f"Batch download failed for {len(failures)} item(s): {urls}")
        self.failures = failures


@dataclass(frozen=True)
class DownloadJob:
    """Represents one URL -> destination download request."""

    url: str
    destination: Path


@dataclass(frozen=True)
class DownloadResult:
    """Represents the outcome of one download operation."""

    url: str
    destination: Path
    success: bool
    status_code: int | None = None
    bytes_written: int = 0
    error: str | None = None
    retries_used: int = 0


class Downloader:
    """Asynchronous file downloader using httpx."""

    def __init__(
        self,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        max_concurrency: int = 5,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise DownloadValidationError("timeout_seconds must be greater than 0")
        if max_retries < 0:
            raise DownloadValidationError("max_retries cannot be negative")
        if backoff_factor < 0:
            raise DownloadValidationError("backoff_factor cannot be negative")
        if max_concurrency <= 0:
            raise DownloadValidationError("max_concurrency must be greater than 0")

        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._backoff_factor = backoff_factor
        self._max_concurrency = max_concurrency
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> Downloader:
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    async def download_file(self, url: str, destination: Path) -> DownloadResult:
        """Download a single remote file and persist it on disk.

        Raises a DownloaderError subclass on failure.
        """

        normalized_destination = Path(destination)
        self._validate_job(DownloadJob(url=url, destination=normalized_destination))

        response, retries_used = await self._fetch_with_retries(url)
        bytes_written = await self._write_response_to_disk(
            response, normalized_destination
        )

        return DownloadResult(
            url=url,
            destination=normalized_destination,
            success=True,
            status_code=response.status_code,
            bytes_written=bytes_written,
            retries_used=retries_used,
        )

    async def download_many(
        self,
        jobs: Sequence[DownloadJob],
        strict: bool = False,
    ) -> list[DownloadResult]:
        """Download many files concurrently.

        When strict=True, raises BatchDownloadError if any download fails.
        """

        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def _run_job(job: DownloadJob) -> DownloadResult:
            async with semaphore:
                return await self.download_file(job.url, job.destination)

        tasks = [_run_job(job) for job in jobs]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        failures: list[tuple[DownloadJob, DownloaderError]] = []
        results: list[DownloadResult] = []

        for index, item in enumerate(raw_results):
            job = jobs[index]
            if isinstance(item, DownloaderError):
                if strict:
                    failures.append((job, item))
                    continue
                results.append(
                    DownloadResult(
                        url=job.url,
                        destination=job.destination,
                        success=False,
                        error=str(item),
                    )
                )
                continue

            if isinstance(item, Exception):
                unexpected_error = DownloadNetworkError(
                    f"Unexpected error while downloading {job.url}: {item}"
                )
                if strict:
                    failures.append((job, unexpected_error))
                    continue
                results.append(
                    DownloadResult(
                        url=job.url,
                        destination=job.destination,
                        success=False,
                        error=str(unexpected_error),
                    )
                )
                continue

            results.append(item)

        if strict and failures:
            raise BatchDownloadError(failures)

        return results

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            timeout = httpx.Timeout(self._timeout_seconds)
            self._client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)
            self._owns_client = True
        return self._client

    def _validate_job(self, job: DownloadJob) -> None:
        if not job.url or not job.url.strip():
            raise DownloadValidationError("url cannot be empty")

        parsed = urlparse(job.url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise DownloadValidationError(
                f"url must be absolute and use http or https: {job.url}"
            )

        if job.destination.exists():
            raise DownloadFileExistsError(
                f"destination already exists: {job.destination}"
            )

    async def _fetch_with_retries(self, url: str) -> tuple[httpx.Response, int]:
        client = await self._ensure_client()
        last_error: DownloaderError | None = None

        for attempt in range(self._max_retries + 1):
            try:
                response = await client.get(url)
                if response.status_code >= 400:
                    error = self._map_http_status_error(url, response)
                    if (
                        self._is_retryable_status(response.status_code)
                        and attempt < self._max_retries
                    ):
                        await self._sleep_before_retry(attempt)
                        continue
                    raise error

                return response, attempt
            except httpx.TimeoutException as exc:
                last_error = DownloadTimeoutError(f"Request timed out for {url}: {exc}")
            except httpx.ConnectError as exc:
                last_error = DownloadNetworkError(
                    f"Could not connect to remote host for {url}: {exc}"
                )
            except httpx.NetworkError as exc:
                last_error = DownloadNetworkError(
                    f"Network error while downloading {url}: {exc}"
                )
            except httpx.RequestError as exc:
                last_error = DownloadNetworkError(
                    f"Request failed for {url}. Check internet connectivity: {exc}"
                )
            except DownloadHTTPError as exc:
                last_error = exc

            if last_error is None:
                continue

            if attempt >= self._max_retries or not self._is_retryable_error(last_error):
                raise last_error

            await self._sleep_before_retry(attempt)

        if last_error is not None:
            raise last_error

        raise DownloadNetworkError(f"Download failed unexpectedly for {url}")

    async def _sleep_before_retry(self, attempt: int) -> None:
        delay = self._backoff_factor * (2**attempt)
        await asyncio.sleep(delay)

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        return status_code == 429 or 500 <= status_code <= 599

    @staticmethod
    def _is_retryable_error(error: DownloaderError) -> bool:
        if isinstance(error, DownloadHTTPError):
            return Downloader._is_retryable_status(error.status_code)
        return isinstance(error, (DownloadTimeoutError, DownloadNetworkError))

    @staticmethod
    def _map_http_status_error(url: str, response: httpx.Response) -> DownloadHTTPError:
        status_code = response.status_code
        reason = response.reason_phrase or "Unknown error"
        message = f"HTTP {status_code} while downloading {url}: {reason}"

        if status_code == 404:
            message = f"Remote file not found (404): {url}"
        elif status_code in {502, 503, 504}:
            message = f"Server not available (HTTP {status_code}) for {url}"

        return DownloadHTTPError(url=url, status_code=status_code, message=message)

    async def _write_response_to_disk(
        self, response: httpx.Response, destination: Path
    ) -> int:
        content = await response.aread()
        return await self._write_bytes_atomically(destination, content)

    async def _write_bytes_atomically(self, destination: Path, content: bytes) -> int:
        temp_path = destination.with_name(f".{destination.name}.part-{uuid4().hex}")

        def _write() -> int:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with temp_path.open("xb") as tmp_file:
                tmp_file.write(content)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            os.replace(temp_path, destination)
            return len(content)

        try:
            return await asyncio.to_thread(_write)
        except PermissionError as exc:
            raise DownloadIOError(
                f"Permission denied while writing to {destination}: {exc}"
            ) from exc
        except OSError as exc:
            if exc.errno == errno.ENOSPC:
                raise DownloadIOError(
                    f"No space left on device for {destination}"
                ) from exc
            raise DownloadIOError(
                f"Filesystem error while writing {destination}: {exc}"
            ) from exc
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
