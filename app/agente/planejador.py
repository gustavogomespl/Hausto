"""Planejador: subagente que monta o plano até a próxima renda.

O orquestrador (`conversa`) só enxerga a tool `montar_plano`. O planejador roda com prompt próprio,
histórico isolado (o pedido do orquestrador + a última fala do cliente) e limite de chamadas: simula com
`simular_plano`, propõe com `propor_plano` e devolve a proposta estruturada. Número no resumo dele que
não veio das tools é descartado, para não virar fonte da resposta ao cliente.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ModelRequest, dynamic_prompt
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain.tools import BaseTool, ToolRuntime, tool
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app import logs, plano
from app.agente.contexto_financeiro import comparar_contexto
from app.agente.estado import Contexto, EstadoConversa
from app.agente.ferramentas import FERRAMENTAS_PLANEJADOR
from app.agente.texto import brl
from app.guardrails import numeros_sem_fonte

log = logging.getLogger("agente")
PROMPT = (Path(__file__).parent / "prompt_planejador.md").read_text(encoding="utf-8")
LIMITE_CHAMADAS = 6  # simular, ajustar, propor e resumir cabem com folga; passou disso, é loop
FATOS = ("comparacao", "dados_confirmados", "despesas_confirmadas")


@dynamic_prompt
def instrucao_do_planejador(request: ModelRequest) -> str:
    ctx = request.runtime.context.carregar()
    return (PROMPT.replace("{data_ref}", ctx.data_ref.isoformat())
            .replace("{fatos}", json.dumps(request.state.get("comparacao"), ensure_ascii=False)))


def criar(modelo: Any, store: Any = None) -> Any:
    return create_agent(
        model=modelo,
        tools=FERRAMENTAS_PLANEJADOR,
        middleware=[instrucao_do_planejador, ModelCallLimitMiddleware(run_limit=LIMITE_CHAMADAS, exit_behavior="error")],
        state_schema=EstadoConversa,
        context_schema=Contexto,
        store=store,
        checkpointer=False,  # sem memória própria: cada pedido começa do zero
        name="planejador",
    )


def _saida(m: ToolMessage) -> dict[str, Any]:
    try:
        saida = json.loads(m.content) if isinstance(m.content, str) else m.content
    except (ValueError, TypeError):
        return {"erro": "saida_tool_invalida"}
    return saida if isinstance(saida, dict) else {"erro": "saida_tool_invalida"}


def _resumo_saida(s: dict[str, Any]) -> str:
    if "erro" in s:
        return "erro_tool"
    return ", ".join(f"{k}={s[k]}" for k in ("cabe", "limite_diario", "limite_maximo", "reserva") if k in s) or "ok"


def simulacoes_iniciais(contexto: Contexto, fatos: dict[str, Any]) -> list[dict[str, Any]]:
    """O ponto de partida de todo plano, pela regra: pagar a fatura inteira no limite máximo e, se sobrar,
    no gasto normal guardando a sobra; se a fatura inteira não couber, pagar o mínimo. Poupa ao planejador
    as chamadas que ele sempre faria primeiro."""
    ctx = contexto.carregar()
    c = comparar_contexto(ctx, fatos.get("dados_confirmados") or {}, fatos.get("despesas_confirmadas") or [])
    if c.get("erro"):
        return []
    maximo = plano.simular(ctx, c, c["valor_fatura"])
    if not maximo["cabe"]:
        return [maximo, plano.simular(ctx, c, c["opcoes"]["minimo"]["valor_pago"])]
    if maximo["normal_diario"] >= maximo["limite_maximo"]:
        return [maximo]
    return [maximo, plano.simular(ctx, c, c["valor_fatura"], limite_diario=maximo["normal_diario"])]


def executar(agente: Any, pedido: str, fala_do_cliente: str, fatos: dict[str, Any], contexto: Contexto) -> dict[str, Any]:
    """Roda o planejador e devolve {proposta, tentativas, resumo} para o orquestrador."""
    inicio = time.perf_counter()
    iniciais = [{"tool": "simular_plano", **s} for s in simulacoes_iniciais(contexto, fatos)]
    if iniciais and not any(s["cabe"] for s in iniciais):
        # Nem o mínimo fecha: não há plano a montar e o LLM não mudaria isso. Sem as simulações, o déficit
        # que o cliente vê continua sendo só o do cálculo do turno.
        logs.evento(log, "[AGENTE][PLANEJADOR] nem pagando o mínimo fecha; sem plano, sem LLM")
        return {"proposta": None, "tentativas": [], "resumo": None,
                "motivo": "Nem pagando o mínimo e sem gastos do dia a dia o caixa fecha até a renda."}
    entrada = (f"Pedido do assistente: {pedido}\nÚltima fala do cliente: {fala_do_cliente}\n"
               f"Simulações já feitas: {json.dumps(iniciais, ensure_ascii=False)}")
    try:
        saida = agente.invoke({"messages": [HumanMessage(entrada)], **fatos}, context=contexto)
    except ModelCallLimitExceededError:
        logs.evento(log, f"[AGENTE][PLANEJADOR] parou no limite de {LIMITE_CHAMADAS} chamadas", logging.WARNING,
                    ms=round((time.perf_counter() - inicio) * 1000))
        return {"proposta": None, "tentativas": iniciais, "resumo": None, "motivo": "O planejador não fechou um plano a tempo."}
    mensagens = saida["messages"]
    chamadas = {tc["id"]: tc["args"] for m in mensagens if isinstance(m, AIMessage) for tc in m.tool_calls}
    tools = [m for m in mensagens if isinstance(m, ToolMessage)]
    feitas = [{"tool": m.name, **_saida(m)} for m in tools]
    tentativas = [*iniciais, *feitas]
    for m, t in zip(tools, feitas, strict=True):
        args = ", ".join(f"{k}={v}" for k, v in chamadas.get(m.tool_call_id, {}).items())
        logs.evento(log, f"[AGENTE][PLANEJADOR] {m.name}({args}) → {_resumo_saida(t)}", tool=m.name)
    proposta = next((t for t in reversed(tentativas) if t["tool"] == "propor_plano" and t.get("proposto") and t.get("cabe")), None)
    resumo = next((m.text for m in reversed(mensagens) if isinstance(m, AIMessage) and m.text), "")
    if suspeitos := numeros_sem_fonte(resumo, [json.dumps(fatos.get("comparacao")), *tentativas]):
        logs.evento(log, f"[AGENTE][PLANEJADOR] resumo descartado: {len(suspeitos)} números sem fonte", logging.WARNING)
        resumo = ""
    ms = round((time.perf_counter() - inicio) * 1000)
    segundos = f"{ms / 1000:.1f} s".replace(".", ",")
    desfecho = f"plano proposto (até {brl(proposta['limite_diario'])} por dia)" if proposta else "sem plano que caiba"
    logs.evento(log, f"[AGENTE][PLANEJADOR] respondeu em {segundos} com {len(tools)} tools: {desfecho}",
                ms=ms, proposto=proposta is not None)
    return {"proposta": proposta, "tentativas": tentativas, "resumo": resumo or None}


def ferramenta(agente: Any) -> BaseTool:
    """`montar_plano` do orquestrador: delega ao planejador com o pedido e os fatos do turno."""

    @tool
    def montar_plano(pedido: str, runtime: ToolRuntime[Contexto]) -> dict[str, Any]:
        """Monta um plano até a próxima renda: quanto pagar da fatura, quanto guardar e um limite diário
        para o dia a dia. Em `pedido`, resuma o que o cliente quer (ex.: "guardar 300", "pagar só o mínimo",
        "gastar até 50 por dia"). Devolve `proposta` (ou None, com o motivo em `resumo`/`motivo`) e as
        simulações feitas em `tentativas`.
        """
        estado = runtime.state
        fala = next((m.text for m in reversed(estado.get("messages", [])) if isinstance(m, HumanMessage)), "")
        fatos = {k: estado[k] for k in FATOS if estado.get(k) is not None}
        return executar(agente, pedido, fala, fatos, runtime.context)

    return montar_plano
