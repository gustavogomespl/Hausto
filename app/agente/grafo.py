"""O fluxo do diagrama Hausto como StateGraph.

guardrail -> atualizar_estado -> dados suficientes? -(não)-> perguntar_cliente
                                                   -(sim)-> calcular_opcoes -> escolheu? -(sim)-> pedir_confirmacao -> registrar_decisao
                                                                                         -(não)-> conversa -> validar_numeros -(número sem fonte)-> conversa

Só `atualizar_estado` (extração) e `conversa` (create_agent + tools) usam LLM; o resto é regra.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest, dynamic_prompt
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt

from app import calculos
from app.agente import texto
from app.agente.estado import Contexto, Estado, EstadoConversa
from app.agente.extracao import Extrator, confirmou, extrair_por_regras
from app.agente.ferramentas import FERRAMENTAS
from app.features import ContextoCliente
from app.guardrails import RESPOSTA_INJECAO, numeros_sem_fonte, parece_injecao

log = logging.getLogger("agente")

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")
MAX_REESCRITAS = 1  # depois disso, a resposta segura (só números das tools) substitui a do modelo

ETAPAS = {
    "explicar_opcoes": "explique as opções viáveis (custo, caixa e dívida restante) e diga qual é a mais barata que cabe.",
    "informar_deficit": "nenhuma opção cabe no caixa sem apertar os essenciais: mostre o déficit e os próximos passos, sem culpa.",
}


@dynamic_prompt
def instrucao_do_turno(request: ModelRequest) -> str:
    ctx = request.runtime.context.carregar()
    estado = request.state
    correcao = estado.get("correcao")
    return (
        PROMPT.replace("{data_ref}", ctx.data_ref.isoformat())
        .replace("{persona}", f"{ctx.persona} ({ctx.persona_descricao})")
        .replace("{etapa}", ETAPAS.get(estado.get("etapa", ""), "responda à dúvida do cliente."))
        .replace("{mudou}", "O cliente trouxe dado novo: a recomendação anterior não vale mais.\n" if estado.get("dados_mudaram") else "")
        .replace("{fatos}", json.dumps(estado.get("comparacao"), ensure_ascii=False))
        .replace("{correcao}", f"\nCORREÇÃO: {correcao}" if correcao else "")
    )


def _texto_do_cliente(estado: Estado) -> str:
    return next(m.text for m in reversed(estado["messages"]) if isinstance(m, HumanMessage))


def construir_grafo(modelo: Any = None, extrator: Extrator = extrair_por_regras, checkpointer: Any = None, store: Any = None):
    """`modelo=None` é o modo simulado: a conversa usa o texto fixo com os números das tools."""
    agente = (
        create_agent(
            model=modelo,
            tools=FERRAMENTAS,
            middleware=[instrucao_do_turno],
            state_schema=EstadoConversa,
            context_schema=Contexto,
            name="conversa",
        )
        if modelo is not None
        else None
    )

    # ---- nós

    def guardrail(estado: Estado) -> dict[str, Any]:
        turno = {"dados_mudaram": False, "rascunho": "", "correcao": None, "fontes": [], "tools": [], "reescritas": 0, "numeros_sem_fonte": []}
        if parece_injecao(_texto_do_cliente(estado)):
            return {**turno, "etapa": "bloqueado", "messages": [AIMessage(RESPOSTA_INJECAO)]}
        return {**turno, "etapa": "entrada"}

    def atualizar_estado(estado: Estado) -> dict[str, Any]:
        e = extrator(_texto_do_cliente(estado))
        antes = estado.get("dados") or {}
        novos = {k: v for k in ("valor_fatura", "saldo_atual", "reserva_desejada") if (v := getattr(e, k)) is not None}
        escolha = {"opcao": e.opcao_escolhida, "valor": e.valor_escolhido} if e.opcao_escolhida else None
        return {
            "dados": {**antes, **novos},
            "dados_mudaram": any(antes.get(k) != v for k, v in novos.items()),
            "escolha": escolha,
        }

    def perguntar_cliente(estado: Estado, runtime: Runtime[Contexto]) -> dict[str, Any]:
        return {"etapa": "perguntar_cliente", "messages": [AIMessage(texto.pergunta_sem_fatura(runtime.context.carregar()))]}

    def calcular_opcoes(estado: Estado, runtime: Runtime[Contexto]) -> dict[str, Any]:
        d = estado["dados"]
        c = calculos.comparar_opcoes(runtime.context.carregar(), d.get("valor_fatura"), d.get("saldo_atual"), d.get("reserva_desejada", 0.0))
        return {"comparacao": c, "etapa": "explicar_opcoes" if c["status"] == "ok" else "informar_deficit"}

    def conversa(estado: Estado, runtime: Runtime[Contexto]) -> dict[str, Any]:
        ctx = runtime.context.carregar()
        if agente is None:
            return {"rascunho": texto.resposta_padrao(ctx, estado["comparacao"], estado["dados_mudaram"])}
        historico = list(estado["messages"])  # só falas: tool calls ficam dentro do subgrafo
        try:
            saida = agente.invoke(
                {
                    "messages": historico,
                    "comparacao": estado["comparacao"],
                    "etapa": estado["etapa"],
                    "dados_mudaram": estado["dados_mudaram"],
                    "correcao": estado.get("correcao"),
                },
                context=runtime.context,
            )
        except Exception:  # LLM fora do ar (503, cota, timeout): o cliente recebe os mesmos números em texto fixo
            log.exception("conversa_llm_falhou usuario=%s", ctx.id_usuario)
            return {"rascunho": texto.resposta_padrao(ctx, estado["comparacao"], estado["dados_mudaram"]), "correcao": None}
        novas = saida["messages"][len(historico):]
        tools = [m for m in novas if isinstance(m, ToolMessage)]
        final = next((m.text for m in reversed(novas) if isinstance(m, AIMessage) and m.text), "")
        return {
            "rascunho": final,
            "fontes": estado["fontes"] + [str(m.content) for m in tools],
            "tools": estado["tools"] + [m.name for m in tools],
            "correcao": None,
        }

    def validar_numeros(estado: Estado, runtime: Runtime[Contexto]) -> dict[str, Any]:
        ctx = runtime.context.carregar()
        fontes = [json.dumps(estado["comparacao"]), json.dumps(ctx.resumo()), json.dumps(estado["dados"]), *estado["fontes"]]
        suspeitos = numeros_sem_fonte(estado["rascunho"], fontes)
        if not suspeitos:
            return {"messages": [AIMessage(estado["rascunho"])], "numeros_sem_fonte": []}
        reescritas = estado["reescritas"] + 1
        log.warning("numeros_sem_fonte usuario=%s tentativa=%d %s", ctx.id_usuario, reescritas, suspeitos)
        if reescritas <= MAX_REESCRITAS:
            correcao = f"Sua última resposta usou números que não vieram de nenhuma tool: {', '.join(suspeitos)}. Reescreva usando só os números do cálculo e das tools."
            return {"reescritas": reescritas, "correcao": correcao}
        segura = texto.resposta_padrao(ctx, estado["comparacao"], estado["dados_mudaram"])
        return {"reescritas": reescritas, "messages": [AIMessage(segura)], "numeros_sem_fonte": []}

    def pedir_confirmacao(estado: Estado) -> dict[str, Any]:
        c, e = estado["comparacao"], estado["escolha"]
        if e["opcao"] == "parcial":
            valor = e["valor"] or c["opcoes"]["parcial_viavel"]["valor_pago"]
            sim = calculos.simular_custo_rolagem(c["valor_fatura"], valor)
            custo, atende = sim["custo_total"], c["disponivel_para_fatura"] >= valor
        else:
            op = c["opcoes"][e["opcao"]]
            valor = c["valor_fatura"] if e["opcao"] == "integral" else op["valor_pago"]
            custo, atende = op["custo_total"], op["atende_restricoes"]
        escolha = {**e, "valor": valor, "custo_total": custo, "atende_restricoes": atende}
        return {"escolha": escolha, "etapa": "confirmar_decisao", "messages": [AIMessage(texto.pergunta_confirmacao(escolha))]}

    def registrar_decisao(estado: Estado, runtime: Runtime[Contexto]) -> dict[str, Any]:
        e = estado["escolha"]
        resposta = interrupt({"opcao": e["opcao"], "valor": e["valor"], "pergunta": estado["messages"][-1].text})
        if not confirmou(resposta):
            return {"escolha": None, "etapa": "decisao_cancelada", "messages": [HumanMessage(resposta), AIMessage(texto.DECISAO_CANCELADA)]}
        ctx = runtime.context.carregar()
        registro = {
            **e,
            "quando": datetime.now(UTC).isoformat(timespec="seconds"),
            "vencimento": ctx.proximo_vencimento.isoformat(),
        }
        if runtime.store is not None:
            runtime.store.put(("decisoes", ctx.id_usuario), uuid.uuid4().hex, registro)
        return {"escolha": None, "etapa": "decisao_registrada", "messages": [HumanMessage(resposta), AIMessage(texto.decisao_registrada(e))]}

    # ---- arestas (os losangos do diagrama)

    def bloqueado(estado: Estado) -> str:
        return END if estado["etapa"] == "bloqueado" else "atualizar_estado"

    def dados_suficientes(estado: Estado, runtime: Runtime[Contexto]) -> str:
        pronta = "valor_fatura" in estado["dados"] or calculos.prever_fatura(runtime.context.carregar())["pronta"]
        return "calcular_opcoes" if pronta else "perguntar_cliente"

    def escolheu(estado: Estado) -> str:
        return "pedir_confirmacao" if estado.get("escolha") else "conversa"

    def numeros_ok(estado: Estado) -> str:
        return "conversa" if estado.get("correcao") else END

    g = StateGraph(Estado, context_schema=Contexto)
    for no in (guardrail, atualizar_estado, perguntar_cliente, calcular_opcoes, conversa, validar_numeros, pedir_confirmacao, registrar_decisao):
        g.add_node(no.__name__, no)
    g.add_edge(START, "guardrail")
    g.add_conditional_edges("guardrail", bloqueado, ["atualizar_estado", END])
    g.add_conditional_edges("atualizar_estado", dados_suficientes, ["calcular_opcoes", "perguntar_cliente"])
    g.add_edge("perguntar_cliente", END)
    g.add_conditional_edges("calcular_opcoes", escolheu, ["pedir_confirmacao", "conversa"])
    g.add_edge("conversa", "validar_numeros")
    g.add_conditional_edges("validar_numeros", numeros_ok, ["conversa", END])
    g.add_edge("pedir_confirmacao", "registrar_decisao")
    g.add_edge("registrar_decisao", END)
    return g.compile(checkpointer=checkpointer, store=store, name="agente_fatura")


# ------------------------------------------------------------------ um turno de conversa


@dataclass
class Turno:
    resposta: str
    etapa: str
    pendente_confirmacao: dict[str, Any] | None
    tools: list[str]
    numeros_sem_fonte: list[str]
    reescritas: int
    dados_mudaram: bool


def conversar(grafo: Any, ctx: ContextoCliente, sessao: str, mensagem: str) -> Turno:
    """Roda um turno. Se o grafo está parado pedindo confirmação, a mensagem retoma o interrupt."""
    config = {"configurable": {"thread_id": f"{ctx.id_usuario}:{sessao}"}}
    contexto = Contexto(id_usuario=ctx.id_usuario, data_ref=ctx.data_ref, cliente=ctx)
    pendente = grafo.get_state(config).interrupts
    entrada = Command(resume=mensagem) if pendente else {"messages": [HumanMessage(mensagem)]}
    estado = grafo.invoke(entrada, config, context=contexto)
    interrupcoes = estado.get("__interrupt__") or []
    pedido = interrupcoes[0].value if interrupcoes else None
    resposta = pedido["pergunta"] if pedido else next(m.text for m in reversed(estado["messages"]) if isinstance(m, AIMessage))
    return Turno(
        resposta=resposta,
        etapa=estado.get("etapa", ""),
        pendente_confirmacao=pedido,
        tools=estado.get("tools", []),
        numeros_sem_fonte=estado.get("numeros_sem_fonte", []),
        reescritas=estado.get("reescritas", 0),
        dados_mudaram=estado.get("dados_mudaram", False),
    )
