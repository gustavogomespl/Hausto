"""Escolhe um cliente REAL da base (BigQuery ou mock) que se encaixa no perfil de um roteiro.

A escolha é determinística por roteiro (hash do id), para que duas execuções usem o mesmo cliente.
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any

from app import calculos
from app.dados import Repositorio, repositorio
from app.features import ContextoCliente, montar_contexto

LIMITE_CLIENTES = 200  # amostra da base avaliada para achar candidatos

_CACHE: dict[tuple[int, date | None], list[tuple[ContextoCliente, dict[str, Any]]]] = {}


def perfil_do(ctx: ContextoCliente) -> dict[str, Any]:
    c = calculos.comparar_opcoes(ctx)
    return {
        "persona": ctx.persona,
        "status": c.get("status", "fatura_desconhecida"),
        "fatura_pronta": calculos.prever_fatura(ctx)["pronta"],
        "gatilho": calculos.avaliar_gatilho(ctx)["dispara"],
    }


def _perfis(repo: Repositorio, data_ref: date | None) -> list[tuple[ContextoCliente, dict[str, Any]]]:
    chave = (id(repo), data_ref)
    if chave not in _CACHE:
        extratos = repo.transacoes_em_lote(repo.listar_clientes(LIMITE_CLIENTES))
        contextos = [montar_contexto(tx, data_ref) for tx in extratos.values() if tx]
        _CACHE[chave] = [(ctx, perfil_do(ctx)) for ctx in contextos]
    return _CACHE[chave]


def escolher_cliente(perfil: dict[str, Any], semente: str, repo: Repositorio | None = None) -> ContextoCliente:
    data_ref = date.fromisoformat(perfil["data_ref"]) if perfil.get("data_ref") else None
    criterios = {k: v for k, v in perfil.items() if k != "data_ref"}
    candidatos = [ctx for ctx, p in _perfis(repo or repositorio(), data_ref) if all(p.get(k) == v for k, v in criterios.items())]
    if not candidatos:
        raise LookupError(f"nenhum cliente da amostra tem o perfil {criterios} (data_ref={data_ref})")
    candidatos.sort(key=lambda c: c.id_usuario)
    return candidatos[int(hashlib.sha256(semente.encode()).hexdigest(), 16) % len(candidatos)]
