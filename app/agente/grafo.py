"""O fluxo do diagrama Hausto como StateGraph.

guardrail -> atualizar_estado -> esclarecer ou calcular_opcoes -> revisar_calculo
Revisão aprovada -> conversa/validar_numeros ou pedir_confirmacao/registrar_decisao.
Uma ressalva na confirmação volta à entrada e invalida a proposta pendente.

Só `atualizar_estado` (extração) e `conversa` (create_agent + tools) usam LLM; o resto é regra.
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest, dynamic_prompt
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.errors import GraphInterrupt
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt
from pydantic import ValidationError

from app import calculos, logs
from app.agente import aberturas, texto
from app.agente.contexto import atualizar_fatos, despesas_confirmadas, referencia
from app.agente.contexto_financeiro import comparar_contexto
from app.agente.estado import Contexto, Estado, EstadoConversa
from app.agente.extracao import Extracao, Extrator, confirmou, extrair_por_regras, negou
from app.agente.ferramentas import FERRAMENTAS
from app.agente.revisao import revisar_comparacao
from app.features import ContextoCliente
from app.guardrails import RESPOSTA_INJECAO, numeros_sem_fonte, parece_injecao

log = logging.getLogger("agente")

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")
MAX_REESCRITAS = 1  # depois disso, a resposta segura (só números das tools) substitui a do modelo

ETAPAS = {
    "explicar_opcoes": "explique a simulação, distinguindo capacidade de caixa e comparação com taxas ilustrativas. Não apresente isso como recomendação contratual.",
    "informar_deficit": "nenhuma opção cabe no caixa sem apertar os essenciais. Responda primeiro à pergunta do cliente, "
                        "sem culpa e em até 3 linhas. Nunca diga que sobra dinheiro, que uma opção cabe ou que ele deve pagar algo; "
                        "o sistema acrescenta a frase com o valor que falta.",
}


def _evento(estado: Estado, no: str, status: str, **detalhes: Any) -> list[dict[str, Any]]:
    evento = {"turno_id": estado.get("turno_id"), "no": no, "status": status,
              "versao_contexto": estado.get("versao_contexto", 0),
              "quando": datetime.now(UTC).isoformat(timespec="milliseconds"), **detalhes}
    logs.evento(log, "evento_hausto", logging.DEBUG, **evento)
    return [*estado.get("eventos", []), evento]


def _ms(inicio: float) -> int:
    return round((time.perf_counter() - inicio) * 1000)


def _seg(ms: int) -> str:
    return f"{ms / 1000:.1f} s".replace(".", ",")


def _resumo_calculo(s: dict[str, Any]) -> str:
    c = s.get("comparacao")
    if not c:
        return f"sem cálculo ({s.get('erro_calculo') or s.get('etapa')})"
    return f"fatura {texto.brl(c['valor_fatura'])} · disponível {texto.brl(c['disponivel_para_fatura'])} · status {c['status']}"


# Uma frase por passo do agente, no estilo "[AGENTE][PASSO] o que aconteceu" (campos vão no JSON).
PASSOS: dict[str, tuple[str, Any]] = {
    "guardrail": ("GUARDRAIL", lambda s: "injeção bloqueada" if s.get("etapa") == "bloqueado" else "mensagem liberada"),
    "atualizar_estado": ("CONTEXTO", lambda s: f"versão {s.get('versao_contexto')}, {'mudou' if s.get('dados_mudaram') else 'sem mudança'}"
                         + (f", {len(s['pendencias'])} pendência(s)" if s.get("pendencias") else "")),
    "perguntar_cliente": ("PERGUNTA", lambda s: "pede ao cliente o que falta"),
    "calcular_opcoes": ("CALCULO", _resumo_calculo),
    "revisar_calculo": ("REVISAO", lambda s: (s.get("revisao") or {}).get("status", "sem revisão").replace("_", " ")),
    "responder_origem": ("ABERTURA", lambda s: f"primeira mensagem pronta, {len(s.get('sugestoes') or [])} sugestões"),
    "conversa": ("CONVERSA", lambda s: f"rascunho pronto ({s.get('modo_resposta', '')})"),
    "validar_numeros": ("VALIDACAO", lambda s: "resposta segura no lugar" if s.get("modo_resposta") == "fallback_validacao"
                        else "reescrita pedida" if s.get("correcao") else "números conferidos"),
    "pedir_confirmacao": ("CONFIRMACAO", lambda s: f"pede confirmação: {s['escolha']['opcao']} de {texto.brl(s['escolha']['valor'])}"
                          if s.get("escolha") else "escolha não atende às restrições"),
    "registrar_decisao": ("DECISAO", lambda s: {"decisao_registrada": "intenção registrada, nada foi pago",
                                               "decisao_cancelada": "cancelada pelo cliente"}.get(s.get("etapa"), "ressalva: volta para a entrada")),
}


def _com_log(no: Any) -> Any:
    """Uma frase por nó executado, com nome, etapa e tempo nos campos: o passo a passo do turno."""
    rotulo, resumo = PASSOS[no.__name__]

    @functools.wraps(no)
    def rodar(*args: Any, **kwargs: Any) -> Any:
        inicio = time.perf_counter()
        try:
            saida = no(*args, **kwargs)
        except GraphInterrupt:
            logs.evento(log, f"[AGENTE][{rotulo}] aguardando sim/não do cliente", no=no.__name__, ms=_ms(inicio))
            raise
        except Exception:
            logs.evento(log, f"[AGENTE][{rotulo}] falhou", logging.ERROR, no=no.__name__, ms=_ms(inicio))
            raise
        mudancas = (saida.update if isinstance(saida, Command) else saida) or {}
        logs.evento(log, f"[AGENTE][{rotulo}] {resumo({**args[0], **mudancas})}", no=no.__name__,
                    etapa=mudancas.get("etapa", ""), ms=_ms(inicio))
        return saida

    return rodar


def _resumo_saida(conteudo: Any) -> str:
    """Até 4 campos numéricos da saída da tool (ou o erro), para caber numa linha."""
    try:
        dados = json.loads(conteudo) if isinstance(conteudo, str) else conteudo
    except ValueError:
        return str(conteudo)[:120]
    if not isinstance(dados, dict):
        return str(dados)[:120]
    if "erro" in dados:
        return f"erro={dados['erro']}"
    return ", ".join(f"{k}={v}" for k, v in dados.items() if isinstance(v, int | float) and not isinstance(v, bool))[:200] or "ok"


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


def _com_pendencias(resposta: str, estado: Estado) -> str:
    """O cálculo seguiu sem o que está pendente: o cliente precisa saber o que ficou de fora."""
    pendencias = estado.get("pendencias") or []
    return f"{resposta}\nPonto em aberto, fora deste cálculo: {pendencias[0]}" if pendencias else resposta


# No ramo de insuficiência, o texto do modelo não pode tratar o déficit como sobra ou recomendação.
_FALA_EM_SOBRA = re.compile(r"\bsobra(m|ndo|r)?\b|\bpague\b|\bpode pagar\b|recomend|tranquil|(?<!não )\bcabe(m)?\b", re.IGNORECASE)


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
            store=store,
            name="conversa",
        )
        if modelo is not None
        else None
    )

    def _trouxe_fato(mensagem: str) -> bool:
        """Uma negativa com dado novo ("não, minha reserva é 200") volta à entrada em vez de cancelar."""
        try:
            return bool(extrator(mensagem).model_dump(exclude_defaults=True))
        except (ValueError, TypeError):
            return True

    # ---- nós

    def guardrail(estado: Estado) -> dict[str, Any]:
        turno = {"dados_mudaram": False, "rascunho": "", "correcao": None, "fontes": [], "tools": [], "reescritas": 0, "numeros_sem_fonte": [],
                 "turno_id": uuid.uuid4().hex, "eventos": [], "revisao": {}, "erro_calculo": None, "modo_resposta": "deterministico",
                 "sugestoes": [], "ancora": None}
        turno["eventos"] = _evento({**estado, **turno}, "guardrail", "concluido")
        if parece_injecao(_texto_do_cliente(estado)):
            return {**turno, "eventos": _evento({**estado, **turno, "eventos": []}, "guardrail", "bloqueado"), "etapa": "bloqueado", "messages": [AIMessage(RESPOSTA_INJECAO)]}
        return {**turno, "etapa": "entrada"}

    def atualizar_estado(estado: Estado, runtime: Runtime[Contexto]) -> dict[str, Any]:
        mensagem = _texto_do_cliente(estado)
        # Resposta curta à pergunta sobre um gasto sem repetir o substantivo.
        if estado.get("campo_pergunta_aberta") == "despesas" and mensagem.lstrip().lower().startswith("r$"):
            mensagem = "Despesa de " + mensagem
        # Resposta ao pedido de imprevisto ("dentista R$ 150 no dia ..."): sem o substantivo, não vira despesa.
        # Vale só logo depois da abertura, e nunca para intenção de pagamento ("quero pagar R$ 200").
        elif (estado.get("campo_da_abertura") == "despesas" and re.search(r"\d", mensagem)
              and not re.search(r"despesa|gasto|compromisso|pag|fatura|m[ií]nimo", mensagem, re.IGNORECASE)):
            mensagem = "Despesa de " + mensagem
        # Resposta curta ("é R$ 900") à pergunta sobre o valor da fatura.
        elif estado.get("campo_pergunta_aberta") == "valor_fatura" and re.search(r"\d", mensagem) and "fatura" not in mensagem.lower():
            mensagem = "Valor da fatura: " + mensagem
        try:
            # Aberto por aviso ou valor ✦, a fala é o texto do botão: não há fato para extrair (nem LLM a esperar).
            inicio = time.perf_counter()
            e = Extracao() if estado.get("origem") else extrator(mensagem)
            campos = sorted(e.model_dump(exclude_defaults=True))
            logs.evento(log, f"[AGENTE][EXTRACAO] {', '.join(campos) if campos else 'nada novo na mensagem'} ({_seg(_ms(inicio))})",
                        campos=campos, ms=_ms(inicio))
        except ValidationError as erro:
            campo = str(erro.errors()[0]["loc"][0])
            e = Extracao(esclarecimento="Não consegui interpretar esse valor ou data. Pode informar novamente com o nome do campo?", campo_esclarecimento=campo if campo in {"valor_fatura", "saldo_atual", "reserva_desejada", "essenciais_informados", "proxima_renda", "despesas"} else None)
        except (ValueError, TypeError):
            e = Extracao(esclarecimento="Não consegui interpretar esse valor ou data. Pode informar novamente?")
        incompletas = [d for d in estado.get("despesas", []) if d.get("adicional") is not False and not d.get("data")]
        if len(incompletas) == 1 and e.data_despesa_pendente and not e.despesas and e.campo_esclarecimento == "despesas":
            e = e.model_copy(update={"esclarecimento": None, "campo_esclarecimento": None})
        atualizacao = {**atualizar_fatos(estado, e, runtime.context.carregar()), "campo_da_abertura": None}
        atualizacao["eventos"] = _evento({**estado, **atualizacao}, "contexto", "atualizado" if atualizacao["dados_mudaram"] else "mantido")
        return atualizacao

    def perguntar_cliente(estado: Estado, runtime: Runtime[Contexto]) -> dict[str, Any]:
        pendencias = estado.get("pendencias") or []
        pergunta = pendencias[0] if pendencias else texto.pergunta_sem_fatura(runtime.context.carregar())
        # Sem pendência, a pergunta é o valor da fatura: a próxima resposta curta preenche esse campo.
        aberta = {} if pendencias else {"pergunta_aberta": pergunta, "campo_pergunta_aberta": "valor_fatura"}
        return {**aberta, "etapa": "perguntar_cliente", "escolha": None, "comparacao": None,
                "revisao": {"status": "precisa_esclarecer", "motivos": estado.get("pendencias", [])},
                "eventos": _evento(estado, "contexto", "aguardando_informacao"), "messages": [AIMessage(pergunta)]}

    def calcular_opcoes(estado: Estado, runtime: Runtime[Contexto]) -> dict[str, Any]:
        try:
            c = comparar_contexto(runtime.context.carregar(), estado["dados"], despesas_confirmadas(estado))
        except Exception:
            log.exception("[AGENTE][CALCULO] falhou", extra={"campos": {"turno_id": estado["turno_id"]}})
            c = {"erro": "ferramenta_indisponivel"}
        c["versao_contexto"] = estado["versao_contexto"]
        if c.get("erro"):
            esclarecimento = c["erro"] in {"contexto_invalido", "contexto_nao_suportado", "fatura_desconhecida"}
            mensagem = c.get("motivo", "Precisamos confirmar os dados antes de continuar.") if esclarecimento else "Não consegui concluir o cálculo agora. A orientação anterior não deve ser usada. Tente novamente em instantes."
            return {"comparacao": None, "escolha": None, "erro_calculo": c["erro"],
                    "etapa": "perguntar_cliente" if esclarecimento else "falha_calculo",
                    "revisao": {"status": "precisa_esclarecer" if esclarecimento else "erro_tecnico", "motivos": [c["erro"]]},
                    "eventos": _evento(estado, "comparar_contexto", "informacao_insuficiente" if esclarecimento else "erro"),
                    "messages": [AIMessage(mensagem)]}
        return {"comparacao": c, "etapa": "explicar_opcoes" if c["status"] == "ok" else "informar_deficit",
                "eventos": _evento(estado, "comparar_contexto", "concluido")}

    def responder_origem(estado: Estado, runtime: Runtime[Contexto]) -> dict[str, Any]:
        origem = estado["origem"]
        abertura = aberturas.abrir(origem, runtime.context.carregar(), estado.get("comparacao"))
        return {"messages": [AIMessage(abertura["resposta"])], "sugestoes": abertura["sugestoes"], "ancora": abertura["ancora"],
                "campo_da_abertura": abertura.get("campo_da_abertura"), "origem": None,
                "etapa": estado["etapa"] if aberturas.precisa_calculo(origem) else "abertura",
                "eventos": _evento(estado, "abertura", "concluido", origem=origem)}

    def revisar_calculo(estado: Estado) -> dict[str, Any]:
        if estado.get("erro_calculo"):
            return {}
        revisao = revisar_comparacao(estado.get("comparacao"), estado["versao_contexto"])
        saida = {"revisao": revisao, "eventos": _evento(estado, "revisao", revisao["status"])}
        if revisao["status"] != "pode_apresentar":
            saida.update(escolha=None, etapa="falha_revisao", messages=[AIMessage("Os resultados precisam ser recalculados antes de comparar ou registrar uma escolha.")])
        return saida

    def conversa(estado: Estado, runtime: Runtime[Contexto]) -> dict[str, Any]:
        ctx = runtime.context.carregar()
        if agente is None:
            return {"rascunho": texto.resposta_padrao(ctx, estado["comparacao"], estado["dados_mudaram"]), "modo_resposta": "simulado"}
        historico = list(estado["messages"])  # só falas: tool calls ficam dentro do subgrafo
        inicio = time.perf_counter()
        try:
            saida = agente.invoke(
                {
                    "messages": historico,
                    "comparacao": estado["comparacao"],
                    "etapa": estado["etapa"],
                    "dados_mudaram": estado["dados_mudaram"],
                    "correcao": estado.get("correcao"),
                    "dados_confirmados": estado["dados"],
                    "despesas_confirmadas": despesas_confirmadas(estado),
                },
                context=runtime.context,
            )
        except Exception:  # LLM fora do ar (503, cota, timeout): o cliente recebe os mesmos números em texto fixo
            log.exception("[AGENTE][GEMINI] falhou; usando a resposta fixa", extra={"campos": {"etapa": estado["etapa"], "ms": _ms(inicio)}})
            return {"rascunho": texto.resposta_padrao(ctx, estado["comparacao"], estado["dados_mudaram"]), "correcao": None,
                    "modo_resposta": "fallback", "eventos": _evento(estado, "conversa", "falha_llm")}
        novas = saida["messages"][len(historico):]
        tools = [m for m in novas if isinstance(m, ToolMessage)]
        final = next((m.text for m in reversed(novas) if isinstance(m, AIMessage) and m.text), "")
        chamadas = {tc["id"]: tc for m in novas if isinstance(m, AIMessage) for tc in m.tool_calls}
        for m in tools:
            tc = chamadas.get(m.tool_call_id, {"name": m.name, "args": {}})
            args = ", ".join(f"{k}={v}" for k, v in tc["args"].items())
            logs.evento(log, f"[AGENTE][TOOL] {tc['name']}({args}) → {_resumo_saida(m.content)}", tool=tc["name"], args=tc["args"])
        logs.evento(log, f"[AGENTE][GEMINI] respondeu em {_seg(_ms(inicio))} com {len(tools)} tool{'s' if len(tools) != 1 else ''}"
                    + (" (reescrita)" if estado.get("correcao") else ""), etapa=estado["etapa"], ms=_ms(inicio))
        c = estado["comparacao"]
        if c["status"] == "insuficiente":
            # O modelo responde à pergunta; o valor que falta vem sempre da regra.
            if _FALA_EM_SOBRA.search(final):
                return {"rascunho": texto.resposta_padrao(ctx, c, estado["dados_mudaram"]), "correcao": None,
                        "modo_resposta": "deterministico_insuficiencia", "eventos": _evento(estado, "conversa", "texto_descartado")}
            deficit = texto.linha_deficit(c)
            final = final if f"faltam {texto.brl(c['deficit_para_o_minimo'])}" in final else f"{final}\n{deficit}"
        return {
            "rascunho": final,
            "fontes": estado["fontes"] + [str(m.content) for m in tools],
            "tools": estado["tools"] + [m.name for m in tools],
            "correcao": None,
            "modo_resposta": "llm",
            "eventos": _evento(estado, "conversa", "concluido", ferramentas=[m.name for m in tools]),
        }

    def validar_numeros(estado: Estado, runtime: Runtime[Contexto]) -> dict[str, Any]:
        ctx = runtime.context.carregar()
        fontes = [json.dumps(estado["comparacao"]), json.dumps(ctx.resumo()), json.dumps(estado["dados"]), *estado["fontes"]]
        suspeitos = numeros_sem_fonte(estado["rascunho"], fontes)
        if not suspeitos:
            return {"messages": [AIMessage(_com_pendencias(estado["rascunho"], estado))], "numeros_sem_fonte": [],
                    "eventos": _evento(estado, "revisao_texto", "concluido")}
        reescritas = estado["reescritas"] + 1
        logs.evento(log, f"[AGENTE][VALIDACAO] números sem fonte: {', '.join(suspeitos)} (tentativa {reescritas})", logging.WARNING,
                    tentativa=reescritas, suspeitos=suspeitos)
        if reescritas <= MAX_REESCRITAS:
            correcao = f"Sua última resposta usou números que não vieram de nenhuma tool: {', '.join(suspeitos)}. Reescreva usando só os números do cálculo e das tools."
            return {"reescritas": reescritas, "correcao": correcao}
        segura = texto.resposta_padrao(ctx, estado["comparacao"], estado["dados_mudaram"])
        return {"reescritas": reescritas, "messages": [AIMessage(_com_pendencias(segura, estado))], "numeros_sem_fonte": [],
                "modo_resposta": "fallback_validacao", "eventos": _evento(estado, "revisao_texto", "texto_substituido")}

    def pedir_confirmacao(estado: Estado) -> dict[str, Any]:
        c, e = estado["comparacao"], estado["escolha"]
        if e["opcao"] == "parcial":
            valor = e["valor"] if e["valor"] is not None else c["opcoes"]["parcial_viavel"]["valor_pago"]
            sim = calculos.simular_custo_rolagem(c["valor_fatura"], valor)
            custo, atende = sim["custo_total"], c["opcoes"]["minimo"]["valor_pago"] <= valor <= min(c["disponivel_para_fatura"], c["valor_fatura"])
        else:
            op = c["opcoes"][e["opcao"]]
            valor = c["valor_fatura"] if e["opcao"] == "integral" else op["valor_pago"]
            custo, atende = op["custo_total"], op["atende_restricoes"]
        if not atende:
            return {"escolha": None, "etapa": "escolha_incompativel", "revisao": {"status": "precisa_esclarecer", "motivos": ["escolha_viola_restricoes"]},
                    "messages": [AIMessage(texto.escolha_incompativel(e["opcao"], valor, c))],
                    "eventos": _evento(estado, "revisao_escolha", "restricao_nao_atendida")}
        escolha = {**e, "valor": valor, "custo_total": custo, "atende_restricoes": atende,
                   "versao_contexto": estado["versao_contexto"], "id_proposta": uuid.uuid4().hex}
        return {"escolha": escolha, "etapa": "confirmar_decisao", "messages": [AIMessage(texto.pergunta_confirmacao(escolha))],
                "eventos": _evento(estado, "revisao_escolha", "aguardando_confirmacao")}

    def registrar_decisao(estado: Estado, runtime: Runtime[Contexto]) -> Command:
        e = estado["escolha"]
        resposta = interrupt({"opcao": e["opcao"], "valor": e["valor"], "pergunta": estado["messages"][-1].text,
                              "versao_contexto": e["versao_contexto"], "id_proposta": e["id_proposta"]})
        if not isinstance(resposta, str):
            resposta = "Não consegui confirmar a resposta."
        novo_turno = {"turno_id": uuid.uuid4().hex, "eventos": [], "tools": [], "dados_mudaram": False, "modo_resposta": "deterministico"}
        estado_evento = {**estado, **novo_turno}
        ctx = runtime.context.carregar()
        valida = (e["versao_contexto"] == estado["versao_contexto"] and estado["referencia_dados"] == referencia(ctx)
                  and revisar_comparacao(estado.get("comparacao"), estado["versao_contexto"])["status"] == "pode_apresentar")
        if not confirmou(resposta) or not valida:
            if negou(resposta) and not _trouxe_fato(resposta):
                return Command(goto=END, update={**novo_turno, "escolha": None, "etapa": "decisao_cancelada", "messages": [HumanMessage(resposta), AIMessage(texto.DECISAO_CANCELADA)],
                                                "eventos": _evento(estado_evento, "confirmacao", "cancelada")})
            # Reentrar pela entrada normal permite extrair uma ressalva/nova despesa.
            # A proposta pendente é descartada, inclusive quando o texto começa com 'sim'.
            return Command(goto="guardrail", update={"escolha": None, "messages": [HumanMessage(resposta)]})
        registro = {
            **e,
            "quando": datetime.now(UTC).isoformat(timespec="seconds"),
            "vencimento": ctx.proximo_vencimento.isoformat(),
        }
        if runtime.store is not None:
            runtime.store.put(("decisoes", ctx.id_usuario), uuid.uuid4().hex, registro)
        return Command(goto=END, update={**novo_turno, "escolha": None, "etapa": "decisao_registrada", "messages": [HumanMessage(resposta), AIMessage(texto.decisao_registrada(e))],
                                        "eventos": _evento(estado_evento, "confirmacao", "intencao_registrada", id_proposta=e["id_proposta"])})

    # ---- arestas (os losangos do diagrama)

    def bloqueado(estado: Estado) -> str:
        return END if estado["etapa"] == "bloqueado" else "atualizar_estado"

    def dados_suficientes(estado: Estado, runtime: Runtime[Contexto]) -> str:
        if estado.get("origem") and not aberturas.precisa_calculo(estado["origem"]):
            return "responder_origem"
        if estado.get("pendencias") and estado.get("pendencias_novas"):
            return "perguntar_cliente"
        pronta = "valor_fatura" in estado["dados"] or calculos.prever_fatura(runtime.context.carregar())["pronta"]
        return "calcular_opcoes" if pronta else "perguntar_cliente"

    def escolheu(estado: Estado) -> str:
        if estado.get("erro_calculo") or estado.get("revisao", {}).get("status") != "pode_apresentar":
            return END
        if estado.get("origem"):
            return "responder_origem"
        return "pedir_confirmacao" if estado.get("escolha") else "conversa"

    def escolha_valida(estado: Estado) -> str:
        return "registrar_decisao" if estado.get("escolha") else END

    def numeros_ok(estado: Estado) -> str:
        return "conversa" if estado.get("correcao") else END

    g = StateGraph(Estado, context_schema=Contexto)
    for no in (guardrail, atualizar_estado, perguntar_cliente, calcular_opcoes, revisar_calculo, responder_origem, conversa, validar_numeros, pedir_confirmacao):
        g.add_node(no.__name__, _com_log(no))
    g.add_node("registrar_decisao", _com_log(registrar_decisao), destinations=("guardrail", END))
    g.add_edge(START, "guardrail")
    g.add_conditional_edges("guardrail", bloqueado, ["atualizar_estado", END])
    g.add_conditional_edges("atualizar_estado", dados_suficientes, ["calcular_opcoes", "perguntar_cliente", "responder_origem"])
    g.add_edge("perguntar_cliente", END)
    g.add_edge("calcular_opcoes", "revisar_calculo")
    g.add_conditional_edges("revisar_calculo", escolheu, ["pedir_confirmacao", "responder_origem", "conversa", END])
    g.add_edge("responder_origem", END)
    g.add_edge("conversa", "validar_numeros")
    g.add_conditional_edges("validar_numeros", numeros_ok, ["conversa", END])
    g.add_conditional_edges("pedir_confirmacao", escolha_valida, ["registrar_decisao", END])
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
    versao_contexto: int
    turno_id: str
    eventos: list[dict[str, Any]]
    revisao: dict[str, Any]
    modo_resposta: str
    pendencias: list[str]
    sugestoes: list[str]
    ancora: dict[str, Any] | None
    pergunta: str | None  # o que aparece como fala do cliente quando o chat abre por aviso ou valor ✦


def conversar(grafo: Any, ctx: ContextoCliente, sessao: str, mensagem: str | None = None, origem: dict[str, str] | None = None) -> Turno:
    """Roda um turno. Se o grafo está parado pedindo confirmação, a mensagem retoma o interrupt.

    `origem` abre o chat por um aviso ou valor ✦; alguns chips (ex.: "Minha fatura") equivalem a uma origem.
    """
    origem = origem or aberturas.origem_do_atalho(mensagem)
    pergunta = aberturas.pergunta(origem) if origem else None
    mensagem = pergunta or mensagem
    chave = json.dumps([ctx.id_usuario, sessao], ensure_ascii=False)
    # Os metadados vão para o LangSmith: dá para achar o turno pela sessão, pelo cliente ou pelo trace do log.
    metadados = {"sessao": sessao, "id_usuario": ctx.id_usuario, "trace": logs.contexto.get().get("trace")}
    config = {"configurable": {"thread_id": hashlib.sha256(chave.encode()).hexdigest()}, "recursion_limit": 30, "metadata": metadados}
    contexto = Contexto(id_usuario=ctx.id_usuario, data_ref=ctx.data_ref, cliente=ctx)
    pendente = grafo.get_state(config).interrupts
    entrada = Command(resume=mensagem, update={"origem": origem}) if pendente else {"messages": [HumanMessage(mensagem)], "origem": origem}
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
        versao_contexto=estado.get("versao_contexto", 0),
        turno_id=estado.get("turno_id", ""),
        eventos=estado.get("eventos", []),
        revisao=estado.get("revisao", {}),
        modo_resposta=estado.get("modo_resposta", "deterministico"),
        pendencias=estado.get("pendencias", []),
        sugestoes=["Sim", "Não"] if pedido else (estado.get("sugestoes") or texto.SUGESTOES.get(estado.get("etapa", ""), [])),
        ancora=estado.get("ancora"),
        pergunta=pergunta,
    )
