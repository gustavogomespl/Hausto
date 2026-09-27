#!/usr/bin/env bash
# Roda as 30 evals no promptfoo. Argumentos extras vão direto para o `promptfoo eval`.
#   evals/rodar.sh                          Vertex + BigQuery (precisa do gcloud auth application-default login)
#   EVALS_JUIZ=0 MODO_LLM=simulado FONTE_DADOS=mock evals/rodar.sh   só checagens, sem custo
#   evals/rodar.sh --filter-pattern "d0"    só os roteiros de dado novo
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync --group evals --quiet
export PROMPTFOO_PYTHON="$PWD/.venv/bin/python"
export GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-batalha-time-11-5pyw}"
export GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION:-global}"
export MODO_LLM="${MODO_LLM:-vertex}"
export FONTE_DADOS="${FONTE_DADOS:-bigquery}"
export BQ_TABELA="${BQ_TABELA:-batalha-time-11-5pyw.hackathon_dados.extrato_sintetico}"
exec npx -y promptfoo@0.123.1 eval -c evals/promptfooconfig.yaml --no-cache "$@"
