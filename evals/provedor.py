"""Provider Python do promptfoo: roda um roteiro inteiro (multiturno) no alvo configurado.

A saída é a transcrição que o juiz LLM lê; a execução completa vai em `metadata` para as checagens.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # o promptfoo carrega este arquivo solto

from app.dados import repositorio  # noqa: E402
from app.features import montar_contexto  # noqa: E402
from evals.alvo import ALVOS  # noqa: E402


def call_api(prompt: str, options: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    v = context["vars"]
    roteiro = json.loads(v["roteiro"])
    nome_alvo = (options.get("config") or {}).get("alvo", "grafo")
    try:
        ctx = montar_contexto(repositorio().transacoes(v["id_usuario"]), date.fromisoformat(v["data_ref"]))
        ex = ALVOS[nome_alvo]().rodar(ctx, [t["mensagem"] for t in roteiro["turnos"]])
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    return {
        "output": ex.transcricao(),
        "metadata": {"execucao": ex.para_dict(), "alvo": nome_alvo},
        "latencyMs": sum(t.latencia_ms for t in ex.turnos),
    }
