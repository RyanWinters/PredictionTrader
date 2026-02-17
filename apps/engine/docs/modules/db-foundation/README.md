# DB Foundation Artifacts

This module contains the initial SQLite foundation for engine ingestion.

## Included artifacts
- `0001_initial_event_ledger.sql`
  - enables WAL mode and baseline safety pragmas,
  - creates `event_ledger` with source IDs and ingest timestamps,
  - defines unique constraints and indexes for idempotent upsert behavior.

## Canonical idempotent write
Use `INSERT ... ON CONFLICT(source_system, source_event_id) DO UPDATE` to:
- coalesce duplicates from reconnect/replay,
- increment attempt counters,
- keep first-seen/last-seen ingest visibility,
- avoid reviving rows already quarantined as `dead_letter`.
