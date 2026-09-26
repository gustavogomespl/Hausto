"""API do agente de fatura: FastAPI + grafo LangGraph (app/agente) com Gemini.

Rodar local:  uv run uvicorn main:app --reload --port 8080
Modo do LLM em MODO_LLM (vertex | gemini | simulado), ver app/agente/modelos.py.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from pydantic import BaseModel, Field

from app import calculos
from app.agente import construir_grafo, conversar
from app.agente.modelos import extrator, modelo_chat, modo_llm
from app.dados import repositorio
from app.features import ContextoCliente, montar_contexto

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("agente")

RAIZ = Path(__file__).resolve().parent

# Memória de sessão (checkpointer, um thread por conversa) e de perfil (store: decisões registradas).
# Em produção: checkpointer persistente e store no BigQuery/Firestore.
STORE = InMemoryStore()


@lru_cache(maxsize=1)
def grafo() -> Any:
    modelo = modelo_chat()
    return construir_grafo(modelo=modelo, extrator=extrator(modelo), checkpointer=InMemorySaver(), store=STORE)


def contexto_do_cliente(id_usuario: str, data_ref: date | None = None) -> ContextoCliente:
    transacoes = repositorio().transacoes(id_usuario)
    if not transacoes:
        raise HTTPException(404, f"cliente {id_usuario} não encontrado")
    return montar_contexto(transacoes, data_ref)


# ---------------------------------------------------------------- API

app = FastAPI(title="Agente de Fatura", version="0.1.0")


class PedidoChat(BaseModel):
    id_usuario: str
    mensagem: str = Field(min_length=1, max_length=2000)
    sessao_id: str | None = None
    data_ref: date | None = None


class RespostaChat(BaseModel):
    sessao_id: str
    resposta: str
    modo: str
    etapa: str
    pendente_confirmacao: dict[str, Any] | None
    tools_chamadas: list[str]
    numeros_sem_fonte: list[str]
    versao_contexto: int
    turno_id: str
    eventos: list[dict[str, Any]]
    revisao: dict[str, Any]
    modo_resposta: str
    pendencias: list[str]


@app.get("/", include_in_schema=False)
def tela() -> FileResponse:
    return FileResponse(RAIZ / "app" / "static" / "index.html")


@app.get("/saude")
def saude() -> dict[str, str]:
    return {"status": "ok", "modo_llm": modo_llm(), "fonte_dados": os.getenv("FONTE_DADOS", "mock")}


@app.get("/v1/clientes")
def listar_clientes(limite: int = Query(50, le=500)) -> list[dict[str, Any]]:
    repo = repositorio()
    extratos = repo.transacoes_em_lote(repo.listar_clientes(limite))  # uma consulta para todos
    saida = []
    for id_usuario, transacoes in extratos.items():
        ctx = montar_contexto(transacoes)
        saida.append({"id_usuario": id_usuario, "persona": ctx.persona, "gatilho": calculos.avaliar_gatilho(ctx)["dispara"]})
    return saida


@app.get("/v1/clientes/{id_usuario}/contexto")
def contexto(id_usuario: str, data_ref: date | None = None) -> dict[str, Any]:
    """A "linha da feature store" do cliente na data de referência."""
    return contexto_do_cliente(id_usuario, data_ref).resumo()


@app.get("/v1/clientes/{id_usuario}/transacoes")
def transacoes(id_usuario: str, limite: int = Query(50, le=1000)) -> list[dict[str, Any]]:
    tx = sorted(repositorio().transacoes(id_usuario), key=lambda t: (t.data, t.ordem), reverse=True)
    return [
        {"data": t.data.isoformat(), "tipo": t.tipo, "descr": t.descr, "vlr": t.vlr,
         "categoria": t.macro, "subcategoria": t.micro, "saldo_apos": t.saldo_apos}
        for t in tx[:limite]
    ]


@app.get("/v1/clientes/{id_usuario}/gatilho")
def gatilho(id_usuario: str, data_ref: date | None = None) -> dict[str, Any]:
    """Regra do scheduler D-7: decide se o agente entra em contato."""
    return calculos.avaliar_gatilho(contexto_do_cliente(id_usuario, data_ref))


@app.get("/v1/clientes/{id_usuario}/simulacao")
def simulacao(id_usuario: str, valor_fatura: float | None = None, data_ref: date | None = None) -> dict[str, Any]:
    """As 4 tools de uma vez, sem LLM: o que o agente usaria para explicar."""
    return calculos.comparar_opcoes(contexto_do_cliente(id_usuario, data_ref), valor_fatura)


@app.get("/v1/clientes/{id_usuario}/decisoes")
def decisoes(id_usuario: str) -> list[dict[str, Any]]:
    """Decisões declaradas pelo cliente e registradas pelo agente (nenhum pagamento é feito)."""
    return [item.value for item in STORE.search(("decisoes", id_usuario), limit=50)]


@app.post("/v1/chat", response_model=RespostaChat)
def chat(pedido: PedidoChat) -> RespostaChat:
    sessao = pedido.sessao_id or uuid.uuid4().hex
    ctx = contexto_do_cliente(pedido.id_usuario, pedido.data_ref)
    turno = conversar(grafo(), ctx, sessao, pedido.mensagem)
    log.info(
        "turno usuario=%s sessao=%s etapa=%s tools=%s reescritas=%d",
        ctx.id_usuario, sessao, turno.etapa, turno.tools, turno.reescritas,
    )
    return RespostaChat(
        sessao_id=sessao,
        resposta=turno.resposta,
        modo=modo_llm(),
        etapa=turno.etapa,
        pendente_confirmacao=turno.pendente_confirmacao,
        tools_chamadas=turno.tools,
        numeros_sem_fonte=turno.numeros_sem_fonte,
        versao_contexto=turno.versao_contexto,
        turno_id=turno.turno_id,
        eventos=turno.eventos,
        revisao=turno.revisao,
        modo_resposta=turno.modo_resposta,
        pendencias=turno.pendencias,
    )
