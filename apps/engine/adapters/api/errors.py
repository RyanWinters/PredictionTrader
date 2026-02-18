"""Structured API errors aligned to the project error catalog."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ErrorCatalogEntry:
    code: str
    user_message: str


ERROR_CATALOG: dict[str, ErrorCatalogEntry] = {
    "validation": ErrorCatalogEntry("PT-INT-001", "Unexpected internal error occurred."),
    "auth": ErrorCatalogEntry("PT-AUTH-001", "API credentials are missing or invalid."),
    "rate_limit": ErrorCatalogEntry("PT-HTTP-429", "Too many requests sent. Retrying automatically."),
    "network": ErrorCatalogEntry("PT-NET-001", "Cannot reach exchange services right now."),
    "internal": ErrorCatalogEntry("PT-INT-001", "Unexpected internal error occurred."),
}


@dataclass(frozen=True)
class ErrorPayload:
    code: str
    message: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class ApiError(Exception):
    def __init__(self, kind: str, *, details: dict[str, Any] | None = None):
        self.kind = kind
        self.details = details or {}
        super().__init__(kind)

    @property
    def payload(self) -> ErrorPayload:
        entry = ERROR_CATALOG.get(self.kind, ERROR_CATALOG["internal"])
        return ErrorPayload(code=entry.code, message=entry.user_message, details=self.details)
