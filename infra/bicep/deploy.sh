#!/usr/bin/env bash
# Deploy AI Compliance NLWeb — `azure` runtime profile (ADR 0001). RG-scoped.
# Pairs with the `local` Docker stack in infra/compose/ — same app, two runtimes.
set -euo pipefail

RG="${RG:-compliance-rg}"
LOCATION="${LOCATION:-eastus2}"          # needs gpt-4.1 + text-embedding-3-small capacity
PARAM="${PARAM:-$(dirname "$0")/env/dev.bicepparam}"
MAIN="$(dirname "$0")/main.bicep"

echo "==> Resource group $RG ($LOCATION)"
az group create -n "$RG" -l "$LOCATION" -o none

echo "==> Deploying main.bicep (Azure OpenAI + AI Search + Container App + SWA + RBAC)"
az deployment group create -g "$RG" --name nlweb -f "$MAIN" -p "$PARAM" -o table

echo "==> Outputs"
az deployment group show -g "$RG" -n nlweb --query properties.outputs -o json

cat <<'NOTE'

Next: create the two AI Search indexes from the committed schemas
(scripts/aisearch/compliance-docs-index.json + compliance-chunks-index.json),
then ingest with RUNTIME_PROFILE=azure NLWEB_BACKEND=real:

  # create indexes (REST API; SEARCH_ENDPOINT + an admin key or AAD token)
  for f in scripts/aisearch/*-index.json; do
    curl -s -X PUT "$SEARCH_ENDPOINT/indexes/$(jq -r .name "$f")?api-version=2024-07-01" \
      -H "Content-Type: application/json" -H "api-key: $SEARCH_ADMIN_KEY" -d @"$f"
  done

  RUNTIME_PROFILE=azure NLWEB_BACKEND=real PYTHONPATH=src python scripts/ingest.py
NOTE
