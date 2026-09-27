"""Estado do grafo (o que atravessa os nós) e contexto de execução (quem é o cliente)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, NotRequired

from langchain.agents import AgentState
from langgraph.graph import MessagesState

from app.dados import repositorio
from app.features import ContextoCliente, montar_contexto


@dataclass
class Contexto:
    """Contexto de execução (`context=` no invoke). O modelo não escolhe de quem são os dados."""

    id_usuario: str
    data_ref: date | None = None
    cliente: ContextoCliente | None = None  # já montado pela API/testes; no Studio é carregado pelo id
    request_id: str | None = None
    sessao_id: str | None = None
    thread_id: str | None = None

    def carregar(self) -> ContextoCliente:
        if self.cliente is None:
            self.cliente = montar_contexto(repositorio().transacoes(self.id_usuario), self.data_ref)
        return self.cliente


class Estado(MessagesState):
    # persistem na sessão
    dados: dict[str, Any]
    despesas: list[dict[str, Any]]
    pendencias: list[str]
    pendencias_impeditivas: list[str]
    pendencias_informativas: list[str]
    pendencias_novas: bool
    pergunta_aberta: str | None
    campo_pergunta_aberta: str | None
    referencia_pergunta_aberta: str | None
    perguntas_abertas: dict[str, str]
    origens: dict[str, str]
    versao_contexto: int
    referencia_dados: str
    escolha: dict[str, Any] | None
    comparacao: dict[str, Any] | None
    # do turno (zerados pelo guardrail)
    etapa: str
    dados_mudaram: bool
    rascunho: str
    correcao: str | None
    fontes: list[str]
    tools: list[str]
    reescritas: int
    numeros_sem_fonte: list[str]
    turno_id: str
    request_id: str
    sessao_id: str | None
    thread_id: str | None
    eventos: list[dict[str, Any]]
    eventos_entrada: list[dict[str, Any]]
    resultados_especialistas: dict[str, dict[str, Any]]
    resultados_tools: list[dict[str, Any]]
    revisao: dict[str, Any]
    modo_resposta: str
    erro_calculo: str | None
    origem: dict[str, str] | None  # aviso ou valor ✦ que abriu o chat neste turno
    campo_da_abertura: str | None  # a abertura pediu um dado: vale só para a próxima mensagem
    sugestoes: list[str]
    visuais: list[dict[str, Any]]  # gráficos do turno, montados pelo código (app.visuais)
    plano_proposto: dict[str, Any] | None  # plano que cabe e espera o aceite do cliente
    risco: str | None  # classificação da fala do cliente pelos guardrails de entrada
    # checagem de compreensão: quantas vezes já perguntou "ficou claro?" e se espera a resposta
    compreensao_tentativas: int
    aguardando_compreensao: bool
    reexplicar: bool  # turno: o cliente pediu para explicar de novo
    perguntar_compreensao: bool  # turno: a resposta termina perguntando se ficou claro
    ancora: dict[str, Any] | None


class EstadoConversa(AgentState):
    """Estado do subgrafo `create_agent`: as mensagens + os fatos do turno para o prompt."""

    comparacao: NotRequired[dict[str, Any] | None]
    etapa: NotRequired[str]
    dados_mudaram: NotRequired[bool]
    correcao: NotRequired[str | None]
    dados_confirmados: NotRequired[dict[str, Any]]
    despesas_confirmadas: NotRequired[list[dict[str, Any]]]
    acolher: NotRequired[bool]
    reexplicar: NotRequired[bool]
    perguntar_compreensao: NotRequired[bool]
