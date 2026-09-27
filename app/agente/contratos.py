"""Metadados dos especialistas lógicos; valores financeiros ficam no estado existente."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


TextoNaoVazio = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Especialista = Literal[
    "contexto_relacionamento",
    "conta_liquidez",
    "compromissos_alternativas",
    "revisao_evidencias",
]


class EvidenciaExecucao(BaseModel):
    """Referência ao dado ou resultado que sustentou um passo da execução."""

    model_config = ConfigDict(extra="forbid", strict=True)

    origem: TextoNaoVazio
    status: Literal["ok", "erro"]
    referencia: TextoNaoVazio


class ResultadoEspecialista(BaseModel):
    """Envelope mínimo compartilhado pelos quatro especialistas do mesmo grafo."""

    model_config = ConfigDict(extra="forbid", strict=True)

    especialista: Especialista
    request_id: TextoNaoVazio
    versao_contexto_consumida: int = Field(ge=0)
    referencia_dados: TextoNaoVazio
    status: Literal["ok", "precisa_dados", "recalcular", "bloqueado", "erro"]
    evidencias: list[EvidenciaExecucao] = Field(default_factory=list)
    pendencias: list[TextoNaoVazio] = Field(default_factory=list)


def referencia_resultado(resultado: dict[str, Any]) -> str:
    """Identifica um resultado JSON sem copiar nem recalcular seus valores.

    O hash detecta alteração do conteúdo vinculado à evidência; não é uma
    assinatura criptográfica nem comprova a correção financeira do resultado.
    """
    conteudo = json.dumps(
        resultado, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    )
    return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()
