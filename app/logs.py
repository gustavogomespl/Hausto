"""Logs estruturados para acompanhar um turno passo a passo.

- LOG_FORMATO=json (padrão no container): uma linha JSON por evento, no formato do Cloud Logging.
  Com o cabeçalho X-Cloud-Trace-Context do Cloud Run, todas as linhas de uma request ficam
  agrupadas no Logs Explorer.
- LOG_FORMATO=texto (padrão local): `hora NÍVEL logger mensagem campo=valor ...`.

Campos vão em `extra={"campos": {...}}` (ou pela função `evento`); `contexto` guarda os campos
da request (trace, sessão, usuário) e é somado a toda linha emitida durante ela.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any

contexto: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar("log_contexto", default={})


def evento(logger: logging.Logger, mensagem: str, /, nivel: int = logging.INFO, **campos: Any) -> None:
    logger.log(nivel, mensagem, extra={"campos": campos})


def adicionar(**campos: Any) -> None:
    """Soma campos ao contexto da request atual (ex.: sessão e usuário depois de ler o corpo)."""
    contexto.set({**contexto.get(), **campos})


def _campos(record: logging.LogRecord) -> dict[str, Any]:
    return {**contexto.get(), **getattr(record, "campos", {})}


class FormatoJson(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        linha = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "logger": record.name,
            **_campos(record),
        }
        projeto = os.getenv("GOOGLE_CLOUD_PROJECT")
        if linha.get("trace") and projeto:
            linha["logging.googleapis.com/trace"] = f"projects/{projeto}/traces/{linha['trace']}"
        if record.exc_info:
            linha["stack_trace"] = self.formatException(record.exc_info)
        return json.dumps(linha, ensure_ascii=False, default=str)


class FormatoTexto(logging.Formatter):
    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)s %(name)s %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        campos = " ".join(f"{k}={v}" for k, v in _campos(record).items())
        return f"{super().format(record)} {campos}".rstrip()


def configurar() -> None:
    formato = FormatoJson() if os.getenv("LOG_FORMATO", "texto") == "json" else FormatoTexto()
    saida = logging.StreamHandler(sys.stdout)
    saida.setFormatter(formato)
    raiz = logging.getLogger()
    raiz.handlers[:] = [saida]
    raiz.setLevel(os.getenv("LOG_NIVEL", "INFO"))
    # O SDK do Gemini repete um aviso sobre function calling a cada chamada; os erros reais sobem como exceção.
    logging.getLogger("google_genai").setLevel(logging.ERROR)
