"""Error normalization for Kalshi integrations."""

from __future__ import annotations

from enum import Enum
from typing import Any


class ConnectorErrorCode(str, Enum):
    AUTHENTICATION_FAILED = "authentication_failed"
    AUTHORIZATION_FAILED = "authorization_failed"
    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    BAD_REQUEST = "bad_request"
    SCHEMA_VALIDATION = "schema_validation"
    REMOTE_ERROR = "remote_error"
    UNKNOWN = "unknown"


class ConnectorError(Exception):
    """Engine-level normalized connector error."""

    def __init__(self, code: ConnectorErrorCode, message: str, *, cause: Exception | None = None):
        super().__init__(message)
        self.code = code
        self.cause = cause


def map_kalshi_error(error: Exception | Any) -> ConnectorError:
    """Map Kalshi or transport errors to internal connector errors.

    Supports both structured HTTP errors and generic exceptions.
    """

    status_code = getattr(error, "status_code", None)
    message = str(error)

    if status_code == 400:
        return ConnectorError(ConnectorErrorCode.BAD_REQUEST, message, cause=error)
    if status_code == 401:
        return ConnectorError(ConnectorErrorCode.AUTHENTICATION_FAILED, message, cause=error)
    if status_code == 403:
        return ConnectorError(ConnectorErrorCode.AUTHORIZATION_FAILED, message, cause=error)
    if status_code == 404:
        return ConnectorError(ConnectorErrorCode.NOT_FOUND, message, cause=error)
    if status_code == 429:
        return ConnectorError(ConnectorErrorCode.RATE_LIMITED, message, cause=error)
    if isinstance(error, TimeoutError):
        return ConnectorError(ConnectorErrorCode.TIMEOUT, message, cause=error)
    if isinstance(error, OSError):
        return ConnectorError(ConnectorErrorCode.NETWORK_ERROR, message, cause=error)

    lowered = message.lower()
    if "timeout" in lowered:
        return ConnectorError(ConnectorErrorCode.TIMEOUT, message, cause=error)
    if "connection" in lowered or "network" in lowered:
        return ConnectorError(ConnectorErrorCode.NETWORK_ERROR, message, cause=error)
    if status_code and int(status_code) >= 500:
        return ConnectorError(ConnectorErrorCode.REMOTE_ERROR, message, cause=error)

    if isinstance(error, ValueError):
        return ConnectorError(ConnectorErrorCode.SCHEMA_VALIDATION, message, cause=error)

    return ConnectorError(ConnectorErrorCode.UNKNOWN, message, cause=error)
