# Contracts package

This package defines source-of-truth contracts for PredictionTrader and generates language-specific models from those contracts.

## Source contracts

- `schemas/canonical-events.schema.json`: canonical event schemas:
  - `orderbook_delta`
  - `trade`
  - `order_state`
  - `position_state`
  - `risk_alert`
- `openapi/local-fastapi.openapi.yaml`: local FastAPI endpoint contract, including request/response models.

Both contract files include versioning metadata:

- contract-level schema version
- compatibility notes for 1.x evolution
- per-schema `x-schema-version` and `x-compatibility-notes`

## Generation flow

The OpenAPI contract is used as the single source for generated local API models:

- TypeScript: `generated/typescript/local-fastapi.ts` via `openapi-typescript`
- Python (Pydantic v2): `generated/python/local_fastapi_models.py` via `datamodel-code-generator`

Run generation:

```bash
cd packages/contracts
./scripts/generate-models.sh
```

Or via npm script:

```bash
npm run generate:contracts
```

## Tooling dependencies

- Node tooling in `package.json`
- Python tooling in `requirements-contracts.txt`
