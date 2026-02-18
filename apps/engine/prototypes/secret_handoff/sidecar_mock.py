#!/usr/bin/env python3
"""Minimal sidecar mock used to validate one-time stdin secret handoff."""

from __future__ import annotations

import argparse
import json
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Secret handoff sidecar mock")
    parser.add_argument("--expected-nonce", required=True)
    parser.add_argument("--ready-port", type=int, default=43125)
    parser.add_argument(
        "--ready-nonce",
        help="Nonce emitted in the READY line. Defaults to --expected-nonce.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    ready_nonce = args.ready_nonce or args.expected_nonce

    print(f"READY {args.ready_port} {ready_nonce}", flush=True)

    bootstrap_line = sys.stdin.readline()
    if not bootstrap_line:
        print("ERROR bootstrap payload missing", file=sys.stderr, flush=True)
        return 1

    try:
        bootstrap = json.loads(bootstrap_line)
    except json.JSONDecodeError:
        print("ERROR bootstrap payload is not valid JSON", file=sys.stderr, flush=True)
        return 1

    if bootstrap.get("nonce") != args.expected_nonce:
        print("ERROR bootstrap nonce mismatch", file=sys.stderr, flush=True)
        return 1

    if "secret" not in bootstrap:
        print("ERROR bootstrap missing secret", file=sys.stderr, flush=True)
        return 1

    print("HANDOFF_OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
