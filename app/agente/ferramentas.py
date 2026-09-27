"""Tools da conversa. Cada uma embrulha um cálculo determinístico de app.calculos.

O cliente vem do contexto de execução (`ToolRuntime.context`), nunca de argumento: o modelo não
consegue consultar outro id por prompt injection. A fatura default é a do cálculo do turno, que já
considera o valor informado pelo cliente.
"""

from __future__ import annotations

from typing import Any, Literal

from langchain.tools import ToolRuntime, tool

from app import calculos, plano, visuais
from app.agente.contexto_financeiro import comparar_contexto
from app.agente.estado import Contexto


def _comparacao_atual(runtime: ToolRuntime[Contexto]) -> dict[str, Any]:
    return comparar_contexto(runtime.context.carregar(), runtime.state.get("dados_confirmados") or {}, runtime.state.get("despesas_confirmadas") or [])


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
    return {**ctx.resumo(), "dados_confirmados": runtime.state.get("dados_confirmados") or {},
            "despesas_confirmadas": runtime.state.get("despesas_confirmadas") or [],
            "decisoes_anteriores": [d.value for d in decisoes]}


@tool
def prever_fatura(runtime: ToolRuntime[Contexto]) -> dict[str, Any]:
    """Estima o valor da próxima fatura do cartão a partir do consumo do mês anterior."""
    return calculos.prever_fatura(runtime.context.carregar())


@tool
def projetar_saldo_ate_vencimento(runtime: ToolRuntime[Contexto]) -> dict[str, Any]:
    """Projeta o saldo em conta no dia do vencimento da fatura (sem o pagamento da fatura)."""
    c = _comparacao_atual(runtime)
    return c if c.get("erro") else {"saldo_projetado_no_vencimento": c["saldo_projetado_no_vencimento"], "origem": "contexto_confirmado_e_projecao"}


@tool
def projetar_essenciais_ate_renda(runtime: ToolRuntime[Contexto]) -> dict[str, Any]:
    """Gastos essenciais esperados (casa, mercado, financiamentos...) entre o vencimento e a próxima renda."""
    c = _comparacao_atual(runtime)
    return c if c.get("erro") else {"essenciais_ate_renda": c["essenciais_ate_renda"], "proxima_renda": c["proxima_renda"], "origem": "contexto_confirmado_e_projecao"}


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
    c = _comparacao_atual(runtime)
    if c.get("erro"):
        return c
    from datetime import date
    return calculos.simular_pagamento_com_negativo(fatura, c["saldo_projetado_no_vencimento"], (date.fromisoformat(c["proxima_renda"]) - ctx.proximo_vencimento).days)


@tool
def comparar_opcoes(
    runtime: ToolRuntime[Contexto],
    valor_fatura: float | None = None,
    saldo_atual_informado: float | None = None,
    reserva_desejada: float | None = None,
) -> dict[str, Any]:
    """Compara integral, parcial viável e mínimo com valores hipotéticos ("e se eu guardar 500?").

    Respeita essenciais + reserva até a próxima renda.
    """
    dados = dict(runtime.state.get("dados_confirmados") or {})
    for campo, valor in (("valor_fatura", valor_fatura), ("saldo_atual", saldo_atual_informado), ("reserva_desejada", reserva_desejada)):
        if valor is not None:
            dados[campo] = valor
    # Uma hipótese usa uma cópia: a chamada da ferramenta não altera fatos da sessão.
    return comparar_contexto(runtime.context.carregar(), dados, runtime.state.get("despesas_confirmadas") or [])


@tool
def mostrar_visual(
    tipo: Literal["comparar_opcoes", "caixa_ate_renda", "linha_do_tempo", "progresso_plano"],
    runtime: ToolRuntime[Contexto],
    pagamento: Literal["integral", "parcial_viavel", "minimo"] | None = None,
    valor_pago: float | None = None,
) -> dict[str, Any]:
    """Mostra um gráfico no chat, montado com os números do cálculo atual (você não escreve os números dele).

    - comparar_opcoes: custo de pagar tudo, parte ou o mínimo, lado a lado.
    - caixa_ate_renda: quanto sobra ou falta até a próxima renda com um pagamento (`pagamento` ou `valor_pago`).
    - linha_do_tempo: hoje, despesas informadas, vencimento e próxima renda.
    - progresso_plano: como o cliente está no plano aceito (gasto real x combinado).
    Use no máximo um por resposta, quando ajudar o cliente a enxergar a decisão.
    """
    ctx = runtime.context.carregar()
    if tipo == "progresso_plano":
        salvo = runtime.store.get(("planos", ctx.id_usuario), "ativo") if runtime.store else None
        if salvo is None:  # não é erro de tool: o modelo só precisa saber que não há plano
            return {"sem_plano": True, "mensagem": "O cliente não tem plano ativo."}
        return plano.visual(salvo.value, plano.progresso(salvo.value, ctx))
    c = _comparacao_atual(runtime)
    if c.get("erro"):
        return c
    return visuais.montar(tipo, runtime.context.carregar(), c, valor_pago if valor_pago is not None else pagamento)


@tool
def simular_plano(pagamento_fatura: float, runtime: ToolRuntime[Contexto], reserva: float | None = None,
                  limite_diario: float | None = None) -> dict[str, Any]:
    """Confere um plano até a próxima renda: pagar `pagamento_fatura`, guardar `reserva` e gastar até
    `limite_diario` por dia no dia a dia (lazer, delivery, lojas...; essenciais já estão contados).

    Sem `limite_diario`, devolve o limite máximo que o caixa aguenta. Use para testar variações antes de propor.
    """
    c = _comparacao_atual(runtime)
    if c.get("erro"):
        return c
    return plano.simular(runtime.context.carregar(), c, pagamento_fatura, reserva, limite_diario)


@tool
def propor_plano(pagamento_fatura: float, limite_diario: float, runtime: ToolRuntime[Contexto],
                 reserva: float | None = None) -> dict[str, Any]:
    """Propõe ao cliente um plano que `simular_plano` mostrou que cabe. O sistema pede o aceite dele
    e só então liga os avisos; não diga que o plano já está ativo.
    """
    c = _comparacao_atual(runtime)
    if c.get("erro"):
        return c
    return {**plano.simular(runtime.context.carregar(), c, pagamento_fatura, reserva, limite_diario), "proposto": True}


FERRAMENTAS = [
    obter_contexto_cliente,
    prever_fatura,
    projetar_saldo_ate_vencimento,
    projetar_essenciais_ate_renda,
    simular_custo_rolagem,
    simular_pagamento_com_negativo,
    comparar_opcoes,
    mostrar_visual,
    simular_plano,
    propor_plano,
]
