#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPENAPI_FILE="$ROOT_DIR/openapi/local-fastapi.openapi.yaml"
TS_OUTPUT="$ROOT_DIR/generated/typescript/local-fastapi.ts"
PY_OUTPUT="$ROOT_DIR/generated/python/local_fastapi_models.py"

mkdir -p "$(dirname "$TS_OUTPUT")" "$(dirname "$PY_OUTPUT")"

if ! command -v npx >/dev/null 2>&1; then
  echo "error: npx is required to generate TypeScript models" >&2
  exit 1
fi

if ! command -v datamodel-codegen >/dev/null 2>&1; then
  echo "error: datamodel-codegen is required to generate Python models" >&2
  echo "hint: pip install -r $ROOT_DIR/requirements-contracts.txt" >&2
  exit 1
fi

echo "Generating TypeScript models from $OPENAPI_FILE"
npx --yes openapi-typescript "$OPENAPI_FILE" --output "$TS_OUTPUT"

echo "Generating Python models from $OPENAPI_FILE"
datamodel-codegen \
  --input "$OPENAPI_FILE" \
  --input-file-type openapi \
  --output "$PY_OUTPUT" \
  --output-model-type pydantic_v2.BaseModel

echo "Contract generation complete"
