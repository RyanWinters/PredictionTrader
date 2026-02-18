# Secret Handoff Path Prototype

This prototype defines and verifies the Milestone-1 secret handoff path from desktop host (Tauri-equivalent) to sidecar engine.

## Defined handoff path

1. Host generates a cryptographically strong one-time nonce.
2. Host spawns sidecar with the expected nonce.
3. Sidecar prints a startup line: `READY <port> <nonce>`.
4. Host validates line format, port bounds, and nonce equality.
5. Host sends a single bootstrap JSON payload over **stdin** with:
   - `nonce`
   - `secret`
6. Sidecar validates payload nonce before accepting secret material.
7. Sidecar confirms with `HANDOFF_OK` and exits.

The nonce-mismatch case is validated to ensure the host kills the sidecar before any secret transfer.

## Prototype files

- `apps/engine/prototypes/secret_handoff/handoff_prototype.py`
- `apps/engine/prototypes/secret_handoff/sidecar_mock.py`
- `apps/engine/prototypes/secret_handoff/test_handoff_prototype.py`

## Validation commands

Run from repository root:

```bash
python -m unittest apps.engine.prototypes.secret_handoff.test_handoff_prototype
```

Optional manual runs:

```bash
python apps/engine/prototypes/secret_handoff/handoff_prototype.py
python apps/engine/prototypes/secret_handoff/handoff_prototype.py --simulate-mismatch
```
