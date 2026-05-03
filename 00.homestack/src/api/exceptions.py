"""Exception types for static API client operations."""

from __future__ import annotations


class APIClientError(Exception):
    """Base exception for all API client failures."""


class APIValidationError(APIClientError):
    """Raised when client configuration or endpoint inputs are invalid."""


class APITimeoutError(APIClientError):
    """Raised when a request times out."""


class APINetworkError(APIClientError):
    """Raised for network-related request failures."""


class APIHTTPError(APIClientError):
    """Raised when the remote endpoint returns an HTTP error status."""

    def __init__(self, url: str, status_code: int, message: str) -> None:
        super().__init__(message)
        self.url = url
        self.status_code = status_code


class APIParseError(APIClientError):
    """Raised when response payload cannot be decoded or mapped."""


class APIBatchError(APIClientError):
    """Raised when strict aggregate fetch fails for one or more endpoints."""

    def __init__(self, failures: list[tuple[str, APIClientError]]) -> None:
        endpoint_names = ", ".join(endpoint for endpoint, _ in failures)
        super().__init__(f"Failed to fetch one or more endpoints: {endpoint_names}")
        self.failures = failures
