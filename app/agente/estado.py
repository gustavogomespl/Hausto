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

    def carregar(self) -> ContextoCliente:
        if self.cliente is None:
            self.cliente = montar_contexto(repositorio().transacoes(self.id_usuario), self.data_ref)
        return self.cliente


class Estado(MessagesState):
    # persistem na sessão
    dados: dict[str, float]  # informados pelo cliente: valor_fatura, saldo_atual, reserva_desejada
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


class EstadoConversa(AgentState):
    """Estado do subgrafo `create_agent`: as mensagens + os fatos do turno para o prompt."""

    comparacao: NotRequired[dict[str, Any] | None]
    etapa: NotRequired[str]
    dados_mudaram: NotRequired[bool]
    correcao: NotRequired[str | None]
