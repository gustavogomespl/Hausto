"""O que está sendo avaliado. Um alvo roda um roteiro multiturno e devolve a trajetória de cada turno.

Contrato para novos alvos (ex.: a versão multiagente): implementar `rodar(ctx, mensagens) -> Execucao`
e registrar em ALVOS. Os roteiros avaliam comportamento (etapa, dados, tools, números), não nomes de nós.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from app.agente import Contexto, construir_grafo, texto
from app.agente.grafo import entrada_segura, resposta_segura
from app.agente.modelos import extrator as extrator_do_modelo
from app.agente.modelos import modelo_chat
from app.features import ContextoCliente

_DO_AMBIENTE = object()


@dataclass
class TurnoTrace:
    mensagem: str
    resposta: str = ""
    etapa: str = ""
    nos: list[str] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)  # {nome, args, saida}
    pendente_confirmacao: dict[str, Any] | None = None
    numeros_sem_fonte: list[str] = field(default_factory=list)
    reescritas: int = 0
    dados: dict[str, float] = field(default_factory=dict)
    dados_mudaram: bool = False
    calculo: dict[str, Any] | None = None  # comparar_opcoes do turno: fonte dos números fora das tools
    escolha: dict[str, Any] | None = None  # valor e custo calculados pela regra ao pedir confirmação
    latencia_ms: int = 0
    erro: str | None = None
    resposta_fixa: bool = False  # com LLM ligado: o modelo falhou e o grafo usou o texto fixo
    modo_resposta: str = ""  # llm | fallback | fallback_validacao | deterministico... (quando o grafo informa)


@dataclass
class Execucao:
    id_usuario: str
    turnos: list[TurnoTrace]
    decisoes: list[dict[str, Any]]

    def para_dict(self) -> dict[str, Any]:
        return asdict(self)

    def transcricao(self) -> str:
        """O que o juiz LLM lê: a conversa com a rota e as tools de cada turno."""
        return transcricao(self.para_dict())


def transcricao(ex: dict[str, Any]) -> str:
    blocos = []
    for i, t in enumerate(ex["turnos"], 1):
        linhas = [f"[Turno {i}]", f"Cliente: {t['mensagem']}", f"  rota: {' → '.join(t['nos']) or '(nenhuma)'}"]
        if t.get("calculo"):
            linhas.append(f"  cálculo do turno (regras determinísticas): {json.dumps(t['calculo'], ensure_ascii=False)}")
        if t.get("escolha"):
            linhas.append(f"  escolha calculada (regra, ao pedir confirmação): {json.dumps(t['escolha'], ensure_ascii=False)}")
        for tool in t["tools"]:
            saida = json.dumps(tool["saida"], ensure_ascii=False) if not isinstance(tool["saida"], str) else tool["saida"]
            linhas.append(f"  tool: {tool['nome']}({json.dumps(tool['args'], ensure_ascii=False)}) → {saida[:400]}")
        if t["dados"]:
            linhas.append(f"  dados informados até aqui: {json.dumps(t['dados'], ensure_ascii=False)}")
        linhas.append(f"  etapa: {t['etapa']}" + ("  (aguardando confirmação)" if t["pendente_confirmacao"] else ""))
        if t["erro"]:
            linhas.append(f"  ERRO: {t['erro']}")
        linhas.append(f"Agente: {t['resposta']}")
        blocos.append("\n".join(linhas))
    blocos.append(f"[Fim] decisões registradas: {json.dumps(ex['decisoes'], ensure_ascii=False) or '[]'}")
    return "\n\n".join(blocos)


class Alvo(Protocol):
    def rodar(self, ctx: ContextoCliente, mensagens: list[str]) -> Execucao: ...


def _saida(conteudo: Any) -> Any:
    if isinstance(conteudo, str):
        try:
            return json.loads(conteudo)
        except ValueError:
            return conteudo
    return conteudo


class AlvoGrafo:
    """O grafo LangGraph de app/agente, rodado em processo com a trajetória capturada via stream."""

    def __init__(self, modelo: Any = _DO_AMBIENTE, extrator: Any = None) -> None:
        self.modelo = modelo_chat() if modelo is _DO_AMBIENTE else modelo
        self.extrator = extrator or extrator_do_modelo(self.modelo)

    def rodar(self, ctx: ContextoCliente, mensagens: list[str]) -> Execucao:
        store = InMemoryStore()
        grafo = construir_grafo(modelo=self.modelo, extrator=self.extrator, checkpointer=InMemorySaver(), store=store)
        config = {"configurable": {"thread_id": f"eval:{ctx.id_usuario}"}}
        contexto = Contexto(id_usuario=ctx.id_usuario, data_ref=ctx.data_ref, cliente=ctx)
        turnos = [self._turno(grafo, config, contexto, m) for m in mensagens]
        decisoes = [item.value for item in store.search(("decisoes", ctx.id_usuario))]
        return Execucao(id_usuario=ctx.id_usuario, turnos=turnos, decisoes=decisoes)

    def _turno(self, grafo: Any, config: dict, contexto: Contexto, mensagem: str) -> TurnoTrace:
        t = TurnoTrace(mensagem=mensagem)
        inicio = time.perf_counter()
        mensagem, ocultou = entrada_segura(mensagem)  # os mesmos guardrails de entrada da API
        retomada = bool(grafo.get_state(config).interrupts)
        entrada = Command(resume=mensagem) if retomada else {"messages": [HumanMessage(mensagem)]}
        chamadas: dict[str, dict[str, Any]] = {}
        interrupcao = None
        try:
            for ns, atualizacao in grafo.stream(entrada, config, context=contexto, stream_mode="updates", subgraphs=True):
                for no, valor in (atualizacao or {}).items():
                    if no == "__interrupt__":
                        interrupcao = valor[0].value
                    elif not ns:
                        t.nos.append(no)
                    elif isinstance(valor, dict):  # dentro do subgrafo da conversa: tool calls e resultados
                        for m in valor.get("messages", []):
                            if isinstance(m, AIMessage):
                                for tc in m.tool_calls:
                                    chamadas[tc["id"]] = {"nome": tc["name"], "args": tc["args"]}
                            elif isinstance(m, ToolMessage):
                                item = chamadas.pop(m.tool_call_id, {"nome": m.name, "args": {}})
                                t.tools.append({**item, "saida": _saida(m.content)})
        except Exception as e:  # o eval registra a falha em vez de derrubar a execução inteira
            t.erro = f"{type(e).__name__}: {e}"
        estado = grafo.get_state(config).values
        t.latencia_ms = int((time.perf_counter() - inicio) * 1000)
        t.etapa = estado.get("etapa", "")
        t.pendente_confirmacao = interrupcao
        t.numeros_sem_fonte = estado.get("numeros_sem_fonte", [])
        t.reescritas = estado.get("reescritas", 0)
        t.dados = dict(estado.get("dados") or {})
        t.dados_mudaram = estado.get("dados_mudaram", False)
        if "calcular_opcoes" in t.nos:
            t.calculo = estado.get("comparacao")
        if "pedir_confirmacao" in t.nos:
            t.escolha = estado.get("escolha")
        t.modo_resposta = estado.get("modo_resposta", "")
        if t.modo_resposta:  # o grafo informa de onde veio a resposta
            t.resposta_fixa = self.modelo is not None and t.modo_resposta in {"fallback", "fallback_validacao"}
        elif self.modelo is not None and "conversa" in t.nos and estado.get("comparacao"):
            fixa = texto.resposta_padrao(contexto.carregar(), estado["comparacao"], t.dados_mudaram)
            t.resposta_fixa = any(isinstance(m, AIMessage) and m.text == fixa for m in estado.get("messages", [])[-1:])
        if interrupcao:
            t.resposta = interrupcao["pergunta"]
        elif not t.erro:  # com erro, a última AIMessage seria a do turno anterior
            t.resposta = next((m.text for m in reversed(estado.get("messages", [])) if isinstance(m, AIMessage)), "")
        t.resposta = resposta_segura(t.resposta, estado, retomada=retomada, ocultou=ocultou) if t.resposta else t.resposta
        return t


ALVOS: dict[str, type] = {"grafo": AlvoGrafo}
