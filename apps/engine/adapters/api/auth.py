"""Tauri-local trust model auth + nonce guard."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .errors import ApiError


@dataclass
class AuthNonceGuard:
    expected_token: str
    last_nonce_by_token: dict[str, int] = field(default_factory=dict)

    def validate(self, headers: Mapping[str, str]) -> None:
        token = headers.get("x-pt-auth-token", "")
        if token != self.expected_token:
            raise ApiError("auth", details={"reason": "invalid_token"})

        raw_nonce = headers.get("x-pt-nonce", "")
        if not raw_nonce:
            raise ApiError("auth", details={"reason": "missing_nonce"})

        try:
            nonce = int(raw_nonce)
        except ValueError as exc:
            raise ApiError("auth", details={"reason": "invalid_nonce"}) from exc

        previous = self.last_nonce_by_token.get(token)
        if previous is not None and nonce <= previous:
            raise ApiError("auth", details={"reason": "replayed_nonce"})
        self.last_nonce_by_token[token] = nonce
