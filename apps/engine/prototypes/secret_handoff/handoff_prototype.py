#!/usr/bin/env python3
"""Host-side minimal prototype for one-time stdin secret handoff."""

from __future__ import annotations

import json
import re
import secrets
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

READY_PATTERN = re.compile(r"^READY\s+(?P<port>\d+)\s+(?P<nonce>[A-Za-z0-9._\-]+)$")


@dataclass
class HandoffResult:
    success: bool
    reason: str


def run_handoff(simulate_mismatch: bool = False) -> HandoffResult:
    expected_nonce = secrets.token_urlsafe(16)
    sidecar_path = Path(__file__).with_name("sidecar_mock.py")

    sidecar_cmd = [sys.executable, str(sidecar_path), "--expected-nonce", expected_nonce]
    if simulate_mismatch:
        sidecar_cmd.extend(["--ready-nonce", "mismatched_nonce"])

    proc = subprocess.Popen(
        sidecar_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        ready_line = proc.stdout.readline().strip()
        match = READY_PATTERN.match(ready_line)
        if not match:
            proc.kill()
            return HandoffResult(False, f"Malformed READY line: {ready_line!r}")

        ready_port = int(match.group("port"))
        ready_nonce = match.group("nonce")

        if ready_port < 1 or ready_port > 65535:
            proc.kill()
            return HandoffResult(False, f"Invalid sidecar port: {ready_port}")

        if ready_nonce != expected_nonce:
            proc.kill()
            proc.wait(timeout=1)
            return HandoffResult(False, "READY nonce mismatch detected before secret handoff")

        bootstrap_payload = {"nonce": expected_nonce, "secret": "kalshi_api_key_placeholder"}
        assert proc.stdin is not None
        proc.stdin.write(json.dumps(bootstrap_payload) + "\n")
        proc.stdin.flush()
        proc.stdin.close()

        outcome = proc.stdout.readline().strip()
        stderr = proc.stderr.read().strip()
        exit_code = proc.wait(timeout=5)

        if exit_code == 0 and outcome == "HANDOFF_OK":
            return HandoffResult(True, "Secret handoff succeeded through stdin one-time payload")

        detail = stderr or outcome or f"exit code {exit_code}"
        return HandoffResult(False, f"Secret handoff failed: {detail}")
    finally:
        if proc.stdin and not proc.stdin.closed:
            proc.stdin.close()
        if proc.stdout and not proc.stdout.closed:
            proc.stdout.close()
        if proc.stderr and not proc.stderr.closed:
            proc.stderr.close()


if __name__ == "__main__":
    mismatch = "--simulate-mismatch" in sys.argv
    result = run_handoff(simulate_mismatch=mismatch)
    print(result.reason)
    raise SystemExit(0 if result.success else 1)
