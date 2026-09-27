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
import math
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from threading import Lock, RLock
from weakref import WeakKeyDictionary

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
from app.agente.contexto import atualizar_fatos, despesas_confirmadas, pode_contextualizar_despesa, referencia
from app.agente.contexto_financeiro import comparar_contexto
from app.agente.contratos import ResultadoEspecialista, referencia_resultado
from app.agente.estado import Contexto, Estado, EstadoConversa
from app.agente.extracao import Extracao, Extrator, confirmou, extrair_por_regras, negou
from app.agente.ferramentas import FERRAMENTAS
from app.agente.revisao import revisar_comparacao, revisar_evidencias
from app.features import ContextoCliente
from app.guardrails import RESPOSTA_INJECAO, numeros_sem_fonte, parece_injecao

log = logging.getLogger("agente")


class _ErroExtracaoSemConteudo(logging.Filter):
    """O parser do SDK pode incluir a mensagem/prompt na própria exceção."""

    def filter(self, registro: logging.LogRecord) -> bool:
        if registro.msg == "[AGENTE][EXTRACAO] Gemini falhou; usando as regras":
            if registro.exc_info and registro.exc_info[0]:
                registro.campos = {**getattr(registro, "campos", {}), "erro_tipo": registro.exc_info[0].__name__}
            registro.exc_info = registro.exc_text = None
        return True


if not any(f.name == "erro_extracao_sem_conteudo" for f in log.filters):
    log.addFilter(_ErroExtracaoSemConteudo("erro_extracao_sem_conteudo"))

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")
MAX_REESCRITAS = 1  # depois disso, a resposta segura (só números das tools) substitui a do modelo

# Papéis lógicos no mesmo StateGraph; nenhum motor/agente financeiro novo.
ESPECIALISTAS = {
    "contexto_relacionamento": ("guardrail", "contexto", "abertura", "conversa", "seguranca_sessao"),
    "conta_liquidez": ("projetar_saldo_ate_vencimento",),
    "compromissos_alternativas": ("calcular_opcoes", "comparar_contexto", "prever_fatura", "projetar_essenciais_ate_renda", "simular_custo_rolagem", "simular_pagamento_com_negativo", "comparar_opcoes"),
    "revisao_evidencias": ("revisao", "revisao_texto", "revisao_escolha", "confirmacao", "revisar_calculo", "validar_numeros", "pedir_confirmacao", "registrar_decisao"),
}
_SESSOES: WeakKeyDictionary = WeakKeyDictionary()
_LOCK_SESSOES = Lock()


class ConflitoSessao(ValueError):
    """A sessão já pertence a outra identidade neste processo."""


def _impeditivas(estado: Estado) -> list[str]:
    # Snapshots anteriores à classificação falham de forma conservadora.
    return estado.get("pendencias_impeditivas", estado.get("pendencias", []))


def _especialista(no: str) -> str:
    return next((papel for papel, nos in ESPECIALISTAS.items() if no in nos), "contexto_relacionamento")


def _resultado(estado: Estado, especialista: str, origem: str, resultado: dict[str, Any], status: str = "ok") -> dict[str, Any]:
    try:
        referencia_saida = referencia_resultado(resultado)
    except (TypeError, ValueError):
        status = "erro"
        referencia_saida = referencia_resultado({"erro": "resultado_nao_serializavel"})
    return ResultadoEspecialista(
        especialista=especialista, request_id=estado["request_id"],
        versao_contexto_consumida=estado.get("versao_contexto", 0),
        referencia_dados=estado["referencia_dados"], status=status,
        evidencias=[{"origem": origem, "status": "erro" if status == "erro" else "ok", "referencia": referencia_saida}],
        pendencias=_impeditivas(estado),
    ).model_dump()


def _referencia_proposta(escolha: dict[str, Any], texto_apresentado: str) -> str:
    """Consistência entre conteúdo exibido e registrado, sem recalcular valores.

    Inclui identidade, versão, base e request de origem. Não é assinatura nem
    proteção criptográfica contra alteração intencional de todo o checkpoint.
    """
    return referencia_resultado({
        "proposta": {k: v for k, v in escolha.items() if k != "referencia_proposta"},
        "texto_apresentado": texto_apresentado,
    })


ETAPAS = {
    "explicar_opcoes": "explique a simulação, distinguindo capacidade de caixa e comparação com taxas ilustrativas. Não apresente isso como recomendação contratual.",
    "informar_deficit": "nenhuma opção cabe no caixa sem apertar os essenciais. Responda primeiro à pergunta do cliente, "
                        "sem culpa e em até 3 linhas. Nunca diga que sobra dinheiro, que uma opção cabe ou que ele deve pagar algo; "
                        "o sistema acrescenta a frase com o valor que falta.",
}


def _evento(estado: Estado, no: str, status: str, **detalhes: Any) -> list[dict[str, Any]]:
    evento = {"request_id": estado.get("request_id"), "sessao_id": estado.get("sessao_id"),
              "thread_id": estado.get("thread_id"), "turno_id": estado.get("turno_id"),
              "especialista": _especialista(no), "no": no, "status": status,
              "versao_contexto": estado.get("versao_contexto", 0),
              "referencia_dados": estado.get("referencia_dados"), "stale": False,
              "pendencias": {"impeditivas": len(_impeditivas(estado)), "informativas": len(estado.get("pendencias_informativas", []))},
              "revisao": estado.get("revisao", {}).get("status"),
              "quando": datetime.now(UTC).isoformat(timespec="milliseconds"), **detalhes}
    logs.evento(log, "evento_hausto", logging.DEBUG, **evento)
    return [*estado.get("eventos", []), evento]


def _revisao_atual(estado: Estado, ctx: ContextoCliente, request_id: str | None = None) -> dict[str, Any]:
    """Confere vínculo da execução; a validação financeira continua no revisor existente."""
    try:
        referencia_saida = referencia_resultado(estado.get("comparacao") or {})
    except (TypeError, ValueError):
        return {"status": "erro_tecnico", "motivos": ["resultado_nao_serializavel"], "stale": False}
    for papel in ("conta_liquidez", "compromissos_alternativas"):
        resultado = estado.get("resultados_especialistas", {}).get(papel)
        revisao = revisar_evidencias(
            resultado, request_id=request_id or estado["request_id"],
            versao_contexto=estado["versao_contexto"], referencia_dados=referencia(ctx),
            pendencias_impeditivas=_impeditivas(estado),
            referencia_esperada=referencia_saida,
        )
        if revisao["status"] != "pode_apresentar":
            return revisao
        if resultado["especialista"] != papel:
            return {"status": "bloqueado", "motivos": ["especialista_incompativel"], "stale": False}
    for resultado in estado.get("resultados_tools", []):
        revisao = revisar_evidencias(
            resultado, request_id=request_id or estado["request_id"],
            versao_contexto=estado["versao_contexto"], referencia_dados=referencia(ctx),
            pendencias_impeditivas=_impeditivas(estado),
        )
        if revisao["status"] != "pode_apresentar":
            return revisao
    revisao = revisar_comparacao(estado.get("comparacao"), estado["versao_contexto"])
    return {**revisao, "stale": revisao["status"] == "recalcular"}


def _revisado(estado: Estado, revisao: dict[str, Any], no: str) -> dict[str, Any]:
    status = {"pode_apresentar": "ok", "precisa_esclarecer": "precisa_dados", "recalcular": "recalcular", "erro_tecnico": "erro"}.get(revisao["status"], "bloqueado")
    resultado = _resultado(estado, "revisao_evidencias", no, revisao, status)
    return {"revisao": revisao,
            "resultados_especialistas": {**estado.get("resultados_especialistas", {}), "revisao_evidencias": resultado},
            "eventos": _evento({**estado, "revisao": revisao}, no, revisao["status"], stale=revisao.get("stale", False), evidencias=resultado["evidencias"])}


def _recusar_resultado(estado: Estado, revisao: dict[str, Any], no: str, request_id: str | None = None) -> dict[str, Any]:
    estado = {**estado, "request_id": request_id or estado["request_id"]}
    pergunta = _impeditivas(estado)
    mensagem = pergunta[0] if pergunta else "Os resultados precisam ser recalculados antes de comparar ou registrar uma escolha. Confirme os dados para continuarmos."
    return {**_revisado(estado, revisao, no), "request_id": estado["request_id"], "escolha": None, "comparacao": None,
            "etapa": "perguntar_cliente" if pergunta else "falha_revisao", "correcao": None,
            "rascunho": "", "sugestoes": [], "ancora": None, "origem": None, "campo_da_abertura": None,
            "messages": [AIMessage(mensagem)]}


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
        estado = args[0]
        runtime = kwargs.get("runtime") or (args[1] if len(args) > 1 else None)

        def campos(atual: dict[str, Any]) -> dict[str, Any]:
            metadados = {k: atual.get(k) for k in ("request_id", "sessao_id", "thread_id", "turno_id", "versao_contexto", "referencia_dados")}
            if runtime is not None and runtime.context.request_id:
                # Na retomada, o checkpoint ainda contém o request da proposta.
                metadados["request_id"] = runtime.context.request_id
            return {**metadados, "especialista": _especialista(no.__name__), "no": no.__name__, "ms": _ms(inicio)}

        try:
            saida = no(*args, **kwargs)
        except GraphInterrupt:
            logs.evento(log, f"[AGENTE][{rotulo}] aguardando sim/não do cliente", **campos(estado))
            raise
        except Exception as erro:
            logs.evento(log, f"[AGENTE][{rotulo}] falhou", logging.ERROR, erro_tipo=type(erro).__name__, **campos(estado))
            raise
        mudancas = (saida.update if isinstance(saida, Command) else saida) or {}
        atual = {**estado, **mudancas}
        logs.evento(log, f"[AGENTE][{rotulo}] {resumo(atual)}", etapa=atual.get("etapa", ""), **campos(atual))
        return saida

    return rodar


def _numeros_log(dados: Any, campos: tuple[str, ...]) -> dict[str, int | float]:
    """Somente valores numéricos de campos conhecidos; nunca payload/texto livre."""
    if not isinstance(dados, dict):
        return {}
    return {k: dados[k] for k in campos if type(dados.get(k)) in (int, float)
            and (type(dados[k]) is int or math.isfinite(dados[k]))}


def _resumo_saida(conteudo: Any) -> str:
    """Resumo restrito dos resultados; erros podem conter prompts ou credenciais."""
    try:
        dados = json.loads(conteudo) if isinstance(conteudo, str) else conteudo
    except (ValueError, TypeError):
        return "saida_invalida"
    if not isinstance(dados, dict):
        return "saida_invalida"
    if "erro" in dados:
        return "erro_tool"
    valores = _numeros_log(dados, ("custo_total", "valor_pago", "valor_estimado", "saldo_projetado_no_vencimento",
                                  "essenciais_ate_renda", "valor_fatura", "disponivel_para_fatura", "juros", "iof"))
    return ", ".join(f"{k}={v}" for k, v in list(valores.items())[:4]) or "ok"


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
    nomes_ferramentas = {ferramenta.name for ferramenta in FERRAMENTAS}
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

    def guardrail(estado: Estado, runtime: Runtime[Contexto]) -> dict[str, Any]:
        turno = {"dados_mudaram": False, "rascunho": "", "correcao": None, "fontes": [], "tools": [], "reescritas": 0, "numeros_sem_fonte": [],
                 "turno_id": estado["turno_id"] if estado.get("eventos_entrada") else uuid.uuid4().hex,
                 "request_id": runtime.context.request_id or uuid.uuid4().hex,
                 "sessao_id": runtime.context.sessao_id, "thread_id": runtime.context.thread_id,
                 "referencia_dados": estado.get("referencia_dados") or referencia(runtime.context.carregar()),
                 "eventos": estado.get("eventos_entrada", []), "eventos_entrada": [],
                 "resultados_especialistas": {}, "resultados_tools": [],
                 "revisao": {}, "erro_calculo": None, "modo_resposta": "deterministico",
                 "sugestoes": [], "ancora": None}
        turno["eventos"] = _evento({**estado, **turno}, "guardrail", "concluido")
        if parece_injecao(_texto_do_cliente(estado)):
            return {**turno, "eventos": _evento({**estado, **turno, "eventos": []}, "guardrail", "bloqueado"), "etapa": "bloqueado", "messages": [AIMessage(RESPOSTA_INJECAO)]}
        return {**turno, "etapa": "entrada"}

    def atualizar_estado(estado: Estado, runtime: Runtime[Contexto]) -> dict[str, Any]:
        mensagem = _texto_do_cliente(estado)
        # Resposta curta à pergunta sobre um gasto sem repetir o substantivo.
        if (estado.get("campo_pergunta_aberta") == "despesas" and mensagem.lstrip().lower().startswith("r$")
                and pode_contextualizar_despesa(estado, runtime.context.carregar())):
            alvo = estado.get("referencia_pergunta_aberta")
            mensagem = (f"Despesa de {alvo}: " if alvo else "Despesa de ") + mensagem
        # Resposta curta ("é R$ 900") à pergunta sobre o valor da fatura.
        elif estado.get("campo_pergunta_aberta") == "valor_fatura" and re.search(r"\d", mensagem) and "fatura" not in mensagem.lower():
            mensagem = "Valor da fatura: " + mensagem
        elif estado.get("campo_pergunta_aberta") == "proxima_renda" and re.fullmatch(r"\s*(?:\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})\s*", mensagem):
            # A data curta responde à pergunta da renda, não à de uma despesa.
            pergunta_exibida = next((m.text for m in reversed(estado["messages"]) if isinstance(m, AIMessage)), None)
            if pergunta_exibida == estado.get("pergunta_aberta"):
                mensagem = "Próxima renda: " + mensagem
        # O pedido de imprevisto contextualiza só a próxima fala, sem resolver
        # pendências existentes nem transformar intenção de pagamento em despesa.
        elif (estado.get("campo_da_abertura") == "despesas" and not _impeditivas(estado)
              and re.search(r"\d", mensagem)
              and not re.search(r"despesa|gasto|compromisso|pag|fatura|m[ií]nimo|saldo|reserva|guardar|manter|sobrar|essenciais|renda|sal[aá]rio|vou receber|\bna\s+conta\b", mensagem, re.IGNORECASE)):
            mensagem = "Despesa de " + mensagem
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
        atualizacao = {**atualizar_fatos(estado, e, runtime.context.carregar(), mensagem=_texto_do_cliente(estado)),
                       "campo_da_abertura": None}
        atual = {**estado, **atualizacao}
        resultado = _resultado(atual, "contexto_relacionamento", "atualizar_fatos",
                               {"dados": atual["dados"], "despesas": atual["despesas"]},
                               "precisa_dados" if _impeditivas(atual) else "ok")
        atualizacao["resultados_especialistas"] = {"contexto_relacionamento": resultado}
        atualizacao["eventos"] = _evento(atual, "contexto", "atualizado" if atualizacao["dados_mudaram"] else "mantido", evidencias=resultado["evidencias"])
        return atualizacao

    def perguntar_cliente(estado: Estado, runtime: Runtime[Contexto]) -> dict[str, Any]:
        pendencias = _impeditivas(estado)
        pergunta = pendencias[0] if pendencias else texto.pergunta_sem_fatura(runtime.context.carregar())
        # Sem pendência, a pergunta é o valor da fatura: a próxima resposta curta preenche esse campo.
        aberta = {} if pendencias else {"pergunta_aberta": pergunta, "campo_pergunta_aberta": "valor_fatura"}
        revisao = {"status": "precisa_esclarecer", "motivos": pendencias, "stale": False}
        return {**aberta, "etapa": "perguntar_cliente", "escolha": None, "comparacao": None,
                "revisao": revisao,
                "eventos": _evento({**estado, "revisao": revisao}, "contexto", "aguardando_informacao"), "messages": [AIMessage(pergunta)]}

    def calcular_opcoes(estado: Estado, runtime: Runtime[Contexto]) -> dict[str, Any]:
        try:
            c = comparar_contexto(runtime.context.carregar(), estado["dados"], despesas_confirmadas(estado))
        except Exception as erro:
            logs.evento(log, "[AGENTE][CALCULO] falhou", logging.ERROR,
                        turno_id=estado["turno_id"], erro_tipo=type(erro).__name__)
            c = {"erro": "ferramenta_indisponivel"}
        c["versao_contexto"] = estado["versao_contexto"]
        # As duas responsabilidades financeiras usam a mesma execução existente.
        # Não há segunda chamada ao motor nem novos cálculos.
        resultados = {**estado.get("resultados_especialistas", {}), **{
            papel: _resultado(estado, papel, "comparar_contexto", c, "erro" if c.get("erro") else "ok")
            for papel in ("conta_liquidez", "compromissos_alternativas")
        }}
        metadados = {"resultados_especialistas": resultados}
        if c.get("erro"):
            esclarecimento = c["erro"] in {"contexto_invalido", "contexto_nao_suportado", "fatura_desconhecida"}
            mensagem = c.get("motivo", "Precisamos confirmar os dados antes de continuar.") if esclarecimento else "Não consegui concluir o cálculo agora. A orientação anterior não deve ser usada. Tente novamente em instantes."
            revisao = {"status": "precisa_esclarecer" if esclarecimento else "erro_tecnico", "motivos": [c["erro"]], "stale": False}
            return {**metadados, "comparacao": None, "escolha": None, "erro_calculo": c["erro"],
                    "etapa": "perguntar_cliente" if esclarecimento else "falha_calculo",
                    "revisao": revisao,
                    "eventos": _evento({**estado, "revisao": revisao}, "comparar_contexto", "informacao_insuficiente" if esclarecimento else "erro", tool="comparar_contexto", evidencias=resultados["compromissos_alternativas"]["evidencias"]),
                    "messages": [AIMessage(mensagem)]}
        return {**metadados, "comparacao": c, "etapa": "explicar_opcoes" if c["status"] == "ok" else "informar_deficit",
                "eventos": _evento(estado, "comparar_contexto", "concluido", tool="comparar_contexto", evidencias=resultados["compromissos_alternativas"]["evidencias"])}

    def responder_origem(estado: Estado, runtime: Runtime[Contexto]) -> dict[str, Any]:
        origem = estado["origem"]
        ctx = runtime.context.carregar()
        if aberturas.precisa_calculo(origem):
            revisao = _revisao_atual(estado, ctx, request_id=runtime.context.request_id)
        else:
            # As explicações sem comparação também consomem um snapshot atual.
            resultado_contexto = estado.get("resultados_especialistas", {}).get("contexto_relacionamento")
            try:
                referencia_contexto = referencia_resultado({"dados": estado["dados"], "despesas": estado["despesas"]})
                revisao = revisar_evidencias(
                    resultado_contexto, request_id=runtime.context.request_id or estado["request_id"],
                    versao_contexto=estado["versao_contexto"], referencia_dados=referencia(ctx),
                    pendencias_impeditivas=_impeditivas(estado), referencia_esperada=referencia_contexto,
                )
            except (TypeError, ValueError):
                revisao = {"status": "erro_tecnico", "motivos": ["resultado_nao_serializavel"], "stale": False}
            if revisao["status"] == "pode_apresentar" and resultado_contexto["especialista"] != "contexto_relacionamento":
                revisao = {"status": "bloqueado", "motivos": ["especialista_incompativel"], "stale": False}
        if revisao["status"] != "pode_apresentar":
            return _recusar_resultado(estado, revisao, "revisao_texto", request_id=runtime.context.request_id)
        abertura = aberturas.abrir(origem, ctx, estado.get("comparacao"))
        resultado = _resultado(estado, "contexto_relacionamento", "abertura", abertura)
        if resultado["status"] == "erro":
            revisao = {"status": "erro_tecnico", "motivos": ["resultado_nao_serializavel"], "stale": False}
            return _recusar_resultado(estado, revisao, "revisao_texto", request_id=runtime.context.request_id)
        return {"messages": [AIMessage(abertura["resposta"])], "sugestoes": abertura["sugestoes"], "ancora": abertura["ancora"],
                "campo_da_abertura": abertura.get("campo_da_abertura"), "origem": None,
                "etapa": estado["etapa"] if aberturas.precisa_calculo(origem) else "abertura",
                "revisao": revisao,
                "eventos": _evento({**estado, "revisao": revisao}, "abertura", "concluido", origem=origem, evidencias=resultado["evidencias"])}

    def revisar_calculo(estado: Estado, runtime: Runtime[Contexto]) -> dict[str, Any]:
        if estado.get("erro_calculo"):
            return {}
        revisao = _revisao_atual(estado, runtime.context.carregar(), request_id=runtime.context.request_id)
        if revisao["status"] != "pode_apresentar":
            return _recusar_resultado(estado, revisao, "revisao", request_id=runtime.context.request_id)
        return _revisado(estado, revisao, "revisao")

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
                config={"metadata": {"request_id": estado["request_id"], "turno_id": estado["turno_id"],
                                      "sessao_id": estado.get("sessao_id"), "thread_id": estado.get("thread_id"),
                                      "versao_contexto": estado["versao_contexto"], "referencia_dados": estado["referencia_dados"]}},
            )
        except Exception as erro:  # LLM fora do ar (503, cota, timeout): o cliente recebe os mesmos números em texto fixo
            logs.evento(log, "[AGENTE][GEMINI] falhou; usando a resposta fixa", logging.ERROR,
                        etapa=estado["etapa"], ms=_ms(inicio), erro_tipo=type(erro).__name__)
            return {"rascunho": texto.resposta_padrao(ctx, estado["comparacao"], estado["dados_mudaram"]), "correcao": None,
                    "modo_resposta": "fallback", "eventos": _evento(estado, "conversa", "falha_llm")}
        novas = saida["messages"][len(historico):]
        tools = [m for m in novas if isinstance(m, ToolMessage)]
        resultados_tools = list(estado.get("resultados_tools", []))
        eventos = estado.get("eventos", [])
        for mensagem_tool in tools:
            nome_tool = mensagem_tool.name if mensagem_tool.name in nomes_ferramentas else "tool_desconhecida"
            try:
                payload = json.loads(mensagem_tool.content) if isinstance(mensagem_tool.content, str) else mensagem_tool.content
            except (ValueError, TypeError):
                payload = {"erro": "saida_tool_invalida"}
            falhou = not isinstance(payload, dict) or bool(payload.get("erro")) or mensagem_tool.status == "error"
            resultado_tool = _resultado(estado, _especialista(nome_tool), nome_tool,
                                         payload if isinstance(payload, dict) else {"erro": "saida_tool_invalida"}, "erro" if falhou else "ok")
            resultados_tools.append(resultado_tool)
            eventos = _evento({**estado, "eventos": eventos}, nome_tool, "erro" if falhou else "concluido",
                              tool=nome_tool, evidencias=resultado_tool["evidencias"])
        evidencia_tools = {"resultados_tools": resultados_tools, "eventos": eventos}
        final = next((m.text for m in reversed(novas) if isinstance(m, AIMessage) and m.text), "")
        chamadas = {tc["id"]: tc for m in novas if isinstance(m, AIMessage) for tc in m.tool_calls}
        for m in tools:
            tc = chamadas.get(m.tool_call_id, {"name": m.name, "args": {}})
            nome_tool = tc["name"] if tc["name"] in nomes_ferramentas else "tool_desconhecida"
            argumentos = _numeros_log(tc["args"], ("valor_pago", "valor_fatura", "saldo_atual_informado", "reserva_desejada"))
            args = ", ".join(f"{k}={v}" for k, v in argumentos.items())
            logs.evento(log, f"[AGENTE][TOOL] {nome_tool}({args}) → {_resumo_saida(m.content)}", tool=nome_tool, args=argumentos)
        logs.evento(log, f"[AGENTE][GEMINI] respondeu em {_seg(_ms(inicio))} com {len(tools)} tool{'s' if len(tools) != 1 else ''}"
                    + (" (reescrita)" if estado.get("correcao") else ""), etapa=estado["etapa"], ms=_ms(inicio))
        c = estado["comparacao"]
        if c["status"] == "insuficiente":
            # O modelo responde à pergunta; o valor que falta vem sempre da regra.
            if _FALA_EM_SOBRA.search(final):
                return {**evidencia_tools, "rascunho": texto.resposta_padrao(ctx, c, estado["dados_mudaram"]), "correcao": None,
                        "modo_resposta": "deterministico_insuficiencia", "eventos": _evento({**estado, "eventos": eventos}, "conversa", "texto_descartado")}
            deficit = texto.linha_deficit(c)
            final = final if f"faltam {texto.brl(c['deficit_para_o_minimo'])}" in final else f"{final}\n{deficit}"
        return {
            **evidencia_tools,
            "rascunho": final,
            "fontes": estado["fontes"] + [str(m.content) for m in tools],
            "tools": estado["tools"] + [m.name for m in tools],
            "correcao": None,
            "modo_resposta": "llm",
            "eventos": _evento({**estado, "eventos": eventos}, "conversa", "concluido",
                               ferramentas=[m.name if m.name in nomes_ferramentas else "tool_desconhecida" for m in tools]),
        }

    def validar_numeros(estado: Estado, runtime: Runtime[Contexto]) -> dict[str, Any]:
        ctx = runtime.context.carregar()
        revisao = _revisao_atual(estado, ctx, request_id=runtime.context.request_id)
        if revisao["status"] != "pode_apresentar":
            return _recusar_resultado(estado, revisao, "revisao_texto", request_id=runtime.context.request_id)
        fontes = [json.dumps(estado["comparacao"]), json.dumps(ctx.resumo()), json.dumps(estado["dados"]), *estado["fontes"]]
        suspeitos = numeros_sem_fonte(estado["rascunho"], fontes)
        if not suspeitos:
            return {**_revisado(estado, revisao, "revisao_texto"), "messages": [AIMessage(_com_pendencias(estado["rascunho"], estado))], "numeros_sem_fonte": []}
        reescritas = estado["reescritas"] + 1
        logs.evento(log, f"[AGENTE][VALIDACAO] {len(suspeitos)} números sem fonte (tentativa {reescritas})", logging.WARNING,
                    tentativa=reescritas, quantidade_suspeitos=len(suspeitos))
        if reescritas <= MAX_REESCRITAS:
            correcao = f"Sua última resposta usou números que não vieram de nenhuma tool: {', '.join(suspeitos)}. Reescreva usando só os números do cálculo e das tools."
            return {"reescritas": reescritas, "correcao": correcao}
        segura = texto.resposta_padrao(ctx, estado["comparacao"], estado["dados_mudaram"])
        return {"reescritas": reescritas, "messages": [AIMessage(_com_pendencias(segura, estado))], "numeros_sem_fonte": [],
                "modo_resposta": "fallback_validacao", "eventos": _evento(estado, "revisao_texto", "texto_substituido")}

    def pedir_confirmacao(estado: Estado, runtime: Runtime[Contexto]) -> dict[str, Any]:
        revisao = _revisao_atual(estado, runtime.context.carregar(), request_id=runtime.context.request_id)
        if revisao["status"] != "pode_apresentar":
            return _recusar_resultado(estado, revisao, "revisao_escolha", request_id=runtime.context.request_id)
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
            revisao = {"status": "precisa_esclarecer", "motivos": ["escolha_viola_restricoes"], "stale": False}
            return {"escolha": None, "etapa": "escolha_incompativel", "revisao": revisao,
                    "messages": [AIMessage(texto.escolha_incompativel(e["opcao"], valor, c))],
                    "eventos": _evento({**estado, "revisao": revisao}, "revisao_escolha", "restricao_nao_atendida")}
        escolha = {**e, "valor": valor, "custo_total": custo, "atende_restricoes": atende,
                   "versao_contexto": estado["versao_contexto"], "id_proposta": uuid.uuid4().hex,
                   "request_id": estado["request_id"], "referencia_dados": estado["referencia_dados"]}
        pergunta = texto.pergunta_confirmacao(escolha)
        escolha["referencia_proposta"] = _referencia_proposta(escolha, pergunta)
        return {"escolha": escolha, "etapa": "confirmar_decisao", "messages": [AIMessage(pergunta)],
                "eventos": _evento(estado, "revisao_escolha", "aguardando_confirmacao", id_proposta=escolha["id_proposta"], referencia_proposta=escolha["referencia_proposta"])}

    def registrar_decisao(estado: Estado, runtime: Runtime[Contexto]) -> Command:
        e = estado["escolha"]
        resposta = interrupt({"opcao": e["opcao"], "valor": e["valor"], "pergunta": estado["messages"][-1].text,
                              "versao_contexto": e["versao_contexto"], "id_proposta": e["id_proposta"],
                              "request_id_proposta": e["request_id"]})
        if not isinstance(resposta, str):
            resposta = "Não consegui confirmar a resposta."
        novo_turno = {"request_id": runtime.context.request_id or uuid.uuid4().hex,
                      "turno_id": uuid.uuid4().hex, "eventos": [], "tools": [], "dados_mudaram": False, "modo_resposta": "deterministico"}
        estado_evento = {**estado, **novo_turno}
        ctx = runtime.context.carregar()
        # Confirmar é outro request: os resultados devem pertencer ao request da proposta.
        revisao = _revisao_atual(estado, ctx, request_id=e.get("request_id"))
        if e["versao_contexto"] != estado["versao_contexto"] or e.get("referencia_dados") != referencia(ctx):
            revisao = {"status": "recalcular", "motivos": ["proposta_desatualizada"], "stale": True}
        try:
            mesma_proposta = e.get("referencia_proposta") == _referencia_proposta(e, estado["messages"][-1].text)
        except (TypeError, ValueError):
            mesma_proposta = False
        if not mesma_proposta:
            revisao = {"status": "recalcular", "motivos": ["proposta_divergente_da_apresentada"], "stale": True}
        valida = revisao["status"] == "pode_apresentar"
        if not confirmou(resposta) or not valida:
            if negou(resposta) and not _trouxe_fato(resposta):
                return Command(goto=END, update={**novo_turno, "escolha": None, "etapa": "decisao_cancelada", "messages": [HumanMessage(resposta), AIMessage(texto.DECISAO_CANCELADA)],
                                                "eventos": _evento(estado_evento, "confirmacao", "cancelada")})
            # Reentrar pela entrada normal permite extrair uma ressalva/nova despesa.
            # A proposta pendente é descartada, inclusive quando o texto começa com 'sim'.
            eventos = _evento({**estado_evento, "revisao": revisao}, "confirmacao", "proposta_descartada",
                              stale=revisao.get("stale", False), id_proposta=e["id_proposta"])
            return Command(goto="guardrail", update={**novo_turno, "eventos_entrada": eventos, "escolha": None, "messages": [HumanMessage(resposta)]})
        registro = {
            **e,
            "request_id": novo_turno["request_id"], "request_id_proposta": e["request_id"],
            "sessao_id": estado.get("sessao_id"), "thread_id": estado.get("thread_id"), "turno_id": novo_turno["turno_id"],
            "revisao": revisao,
            "evidencias": [*estado["resultados_especialistas"]["compromissos_alternativas"]["evidencias"],
                           {"origem": "proposta_apresentada", "status": "ok", "referencia": e["referencia_proposta"]}],
            "quando": datetime.now(UTC).isoformat(timespec="seconds"),
            "vencimento": ctx.proximo_vencimento.isoformat(),
        }
        if runtime.store is not None:
            runtime.store.put(("decisoes", ctx.id_usuario), e["id_proposta"], registro)
        revisado = _revisado(estado_evento, revisao, "confirmacao")
        return Command(goto=END, update={**novo_turno, **revisado, "escolha": None, "etapa": "decisao_registrada", "messages": [HumanMessage(resposta), AIMessage(texto.decisao_registrada(e))],
                                        "eventos": _evento({**estado_evento, **revisado}, "confirmacao", "intencao_registrada", id_proposta=e["id_proposta"])})

    # ---- arestas (os losangos do diagrama)

    def bloqueado(estado: Estado) -> str:
        return END if estado["etapa"] == "bloqueado" else "atualizar_estado"

    def dados_suficientes(estado: Estado, runtime: Runtime[Contexto]) -> str:
        if _impeditivas(estado):
            return "perguntar_cliente"
        if estado.get("origem") and not aberturas.precisa_calculo(estado["origem"]):
            return "responder_origem"
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
    request_id: str = ""
    resultados_especialistas: dict[str, dict[str, Any]] = field(default_factory=dict)
    pendencias_impeditivas: list[str] = field(default_factory=list)
    pendencias_informativas: list[str] = field(default_factory=list)


def conversar(grafo: Any, ctx: ContextoCliente, sessao: str, mensagem: str | None = None,
              origem: dict[str, str] | None = None, request_id: str | None = None) -> Turno:
    """Associa a sessão à identidade e serializa seus turnos no processo atual."""
    request_id = request_id or uuid.uuid4().hex
    with _LOCK_SESSOES:
        sessoes = _SESSOES.setdefault(grafo, {})
        dono, trava = sessoes.setdefault(sessao, (ctx.id_usuario, RLock()))
        if dono != ctx.id_usuario:
            _evento({"request_id": request_id, "sessao_id": sessao, "turno_id": uuid.uuid4().hex},
                    "seguranca_sessao", "identidade_divergente")
            raise ConflitoSessao("Esta sessão já está associada a outra identidade. Inicie uma nova conversa.")
    with trava:
        return _conversar_serializado(grafo, ctx, sessao, mensagem, origem, request_id)


def _conversar_serializado(grafo: Any, ctx: ContextoCliente, sessao: str, mensagem: str | None,
                          origem: dict[str, str] | None, request_id: str) -> Turno:
    """Roda um turno. Se o grafo está parado pedindo confirmação, a mensagem retoma o interrupt."""
    origem = origem or aberturas.origem_do_atalho(mensagem)
    pergunta = aberturas.pergunta(origem) if origem else None
    mensagem = pergunta or mensagem
    chave = json.dumps([ctx.id_usuario, sessao], ensure_ascii=False)
    thread_id = hashlib.sha256(chave.encode()).hexdigest()
    # A mesma identidade de execução correlaciona checkpoint, evidências,
    # logs estruturados e LangSmith; trace não substitui request_id.
    metadados = {"request_id": request_id, "sessao_id": sessao, "thread_id": thread_id,
                 "sessao": sessao, "id_usuario": ctx.id_usuario, "trace": logs.contexto.get().get("trace")}
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 30,
              "metadata": metadados}
    contexto = Contexto(id_usuario=ctx.id_usuario, data_ref=ctx.data_ref, cliente=ctx,
                        request_id=request_id, sessao_id=sessao, thread_id=thread_id)
    token = logs.contexto.set({**logs.contexto.get(), **metadados})
    try:
        pendente = grafo.get_state(config).interrupts
        entrada = Command(resume=mensagem, update={"origem": origem}) if pendente else {"messages": [HumanMessage(mensagem)], "origem": origem}
        estado = grafo.invoke(entrada, config, context=contexto)
    finally:
        logs.contexto.reset(token)
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
        request_id=estado.get("request_id", request_id),
        resultados_especialistas=estado.get("resultados_especialistas", {}),
        pendencias_impeditivas=_impeditivas(estado),
        pendencias_informativas=estado.get("pendencias_informativas", []),
    )
