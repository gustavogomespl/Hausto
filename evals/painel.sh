#!/usr/bin/env bash
# Abre o painel local do promptfoo com todas as execuções (http://localhost:15500).
set -euo pipefail
exec npx -y promptfoo@0.123.1 view --port "${PORTA:-15500}" "$@"
