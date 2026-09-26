"""Tools da conversa. Cada uma embrulha um cálculo determinístico de app.calculos.

O cliente vem do contexto de execução (`ToolRuntime.context`), nunca de argumento: o modelo não
consegue consultar outro id por prompt injection. A fatura default é a do cálculo do turno, que já
considera o valor informado pelo cliente.
"""

from __future__ import annotations

from typing import Any

from langchain.tools import ToolRuntime, tool

from app import calculos
from app.agente.estado import Contexto


def _fatura_do_turno(runtime: ToolRuntime[Contexto]) -> float | None:
    comparacao = runtime.state.get("comparacao") or {}
    if "valor_fatura" in comparacao:
        return float(comparacao["valor_fatura"])
    prev = calculos.prever_fatura(runtime.context.carregar())
    return float(prev["valor_estimado"]) if prev["pronta"] else None


@tool
def obter_contexto_cliente(runtime: ToolRuntime[Contexto]) -> dict[str, Any]:
    """Persona, saldo atual, renda média, próximo vencimento, próxima renda, últimas faturas e decisões anteriores."""
    ctx = runtime.context.carregar()
    decisoes = runtime.store.search(("decisoes", ctx.id_usuario), limit=3) if runtime.store else []
    return {**ctx.resumo(), "decisoes_anteriores": [d.value for d in decisoes]}


@tool
def prever_fatura(runtime: ToolRuntime[Contexto]) -> dict[str, Any]:
    """Estima o valor da próxima fatura do cartão a partir do consumo do mês anterior."""
    return calculos.prever_fatura(runtime.context.carregar())


@tool
def projetar_saldo_ate_vencimento(runtime: ToolRuntime[Contexto]) -> dict[str, Any]:
    """Projeta o saldo em conta no dia do vencimento da fatura (sem o pagamento da fatura)."""
    return calculos.projetar_saldo_ate_vencimento(runtime.context.carregar())


@tool
def projetar_essenciais_ate_renda(runtime: ToolRuntime[Contexto]) -> dict[str, Any]:
    """Gastos essenciais esperados (casa, mercado, financiamentos...) entre o vencimento e a próxima renda."""
    return calculos.projetar_essenciais_ate_renda(runtime.context.carregar())


@tool
def simular_custo_rolagem(valor_pago: float, runtime: ToolRuntime[Contexto], valor_fatura: float | None = None) -> dict[str, Any]:
    """Custo de pagar só `valor_pago` e levar o resto no rotativo por 30 dias (juros + IOF).

    Se `valor_fatura` não vier, usa a fatura do cálculo atual.
    """
    fatura = valor_fatura if valor_fatura is not None else _fatura_do_turno(runtime)
    if fatura is None:
        return {"erro": "fatura_desconhecida", "acao": "pergunte o valor da fatura ao cliente"}
    return calculos.simular_custo_rolagem(fatura, valor_pago)


@tool
def simular_pagamento_com_negativo(runtime: ToolRuntime[Contexto], valor_fatura: float | None = None) -> dict[str, Any]:
    """Custo de pagar a fatura inteira mesmo que a conta fique no negativo até a próxima renda."""
    fatura = valor_fatura if valor_fatura is not None else _fatura_do_turno(runtime)
    if fatura is None:
        return {"erro": "fatura_desconhecida", "acao": "pergunte o valor da fatura ao cliente"}
    ctx = runtime.context.carregar()
    saldo = calculos.projetar_saldo_ate_vencimento(ctx)["saldo_projetado_no_vencimento"]
    return calculos.simular_pagamento_com_negativo(fatura, saldo, (ctx.proxima_renda - ctx.proximo_vencimento).days)


@tool
def comparar_opcoes(
    runtime: ToolRuntime[Contexto],
    valor_fatura: float | None = None,
    saldo_atual_informado: float | None = None,
    reserva_desejada: float = 0.0,
) -> dict[str, Any]:
    """Compara integral, parcial viável e mínimo com valores hipotéticos ("e se eu guardar 500?").

    Respeita essenciais + reserva até a próxima renda.
    """
    return calculos.comparar_opcoes(runtime.context.carregar(), valor_fatura, saldo_atual_informado, reserva_desejada)


FERRAMENTAS = [
    obter_contexto_cliente,
    prever_fatura,
    projetar_saldo_ate_vencimento,
    projetar_essenciais_ate_renda,
    simular_custo_rolagem,
    simular_pagamento_com_negativo,
    comparar_opcoes,
]
