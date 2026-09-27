"""API do agente de fatura: FastAPI + grafo LangGraph (app/agente) com Gemini.

Rodar local:  uv run uvicorn main:app --reload --port 8080
Modo do LLM em MODO_LLM (vertex | gemini | simulado), ver app/agente/modelos.py.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date
from functools import lru_cache
from pathlib import Path
from threading import RLock
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from pydantic import BaseModel, Field, model_validator

from app import calculos, logs, painel, personas, plano
from app.agente import construir_grafo, conversar
from app.agente.grafo import ConflitoSessao
from app.agente.modelos import extrator, modelo_chat, modo_llm
from app.dados import repositorio
from app.features import ContextoCliente, montar_contexto
from app.guardrails import mascarar

logs.configurar()
log = logging.getLogger("agente")

RAIZ = Path(__file__).resolve().parent

# Memória de sessão (checkpointer, um thread por conversa) e de perfil (store: decisões registradas).
# Em produção: checkpointer persistente e store no BigQuery/Firestore.
STORE = InMemoryStore()
_LOCK_GRAFO = RLock()


@lru_cache(maxsize=1)
def _grafo_cache() -> Any:
    modelo = modelo_chat()
    return construir_grafo(modelo=modelo, extrator=extrator(modelo), checkpointer=InMemorySaver(), store=STORE)


def grafo() -> Any:
    # lru_cache sozinho pode construir duas instâncias no primeiro acesso concorrente.
    with _LOCK_GRAFO:
        return _grafo_cache()


def _limpar_grafo() -> None:
    with _LOCK_GRAFO:
        _grafo_cache.cache_clear()


grafo.cache_clear = _limpar_grafo


def contexto_do_cliente(id_usuario: str, data_ref: date | None = None) -> ContextoCliente:
    transacoes = repositorio().transacoes(id_usuario)
    if not transacoes:
        raise HTTPException(404, f"cliente {id_usuario} não encontrado")
    return montar_contexto(transacoes, data_ref)


# ---------------------------------------------------------------- API

@asynccontextmanager
async def _aquecer(_: FastAPI):
    # Achar as personas percorre a base (~15 s no BigQuery): começa antes do primeiro acesso.
    threading.Thread(target=lambda: personas.resolver(repositorio()), daemon=True).start()
    yield


app = FastAPI(title="Agente de Fatura", version="0.1.0", lifespan=_aquecer)


@app.middleware("http")
async def registrar_request(request: Request, call_next):
    """Uma linha por request; o trace do Cloud Run (ou um novo) acompanha todas as linhas dela."""
    trace = request.headers.get("x-cloud-trace-context", "").split("/")[0] or uuid.uuid4().hex
    token = logs.contexto.set({"trace": trace})
    inicio = time.perf_counter()
    status = 500
    try:
        resposta = await call_next(request)
        status = resposta.status_code
        return resposta
    finally:
        ms = round((time.perf_counter() - inicio) * 1000)
        rota = getattr(request.scope.get("route"), "path", "rota_nao_encontrada")
        try:
            logs.evento(log, f"[API] {request.method} {rota} {status} em {ms} ms", metodo=request.method,
                        rota=rota, status=status, trace=trace, ms=ms,
                        **getattr(request.state, "log_campos", {}))
        finally:
            logs.contexto.reset(token)


class Origem(BaseModel):
    """Aviso ou valor ✦ que abriu o chat. O texto de abertura fica no backend."""

    tipo: Literal["aviso", "ancora"]
    id: Literal["fatura_vence", "sem_folga", "imprevisto", "plano"] | None = None
    campo: Literal["saldo", "fatura", "gasto_por_dia", "juros_por_dia", "parcelas"] | None = None

    @model_validator(mode="after")
    def _completa(self) -> Origem:
        if (self.tipo == "aviso") != (self.id is not None) or (self.tipo == "ancora") != (self.campo is not None):
            raise ValueError("aviso precisa de id; ancora precisa de campo")
        return self


class PedidoChat(BaseModel):
    """Uma mensagem do cliente ou uma origem (aviso/valor ✦). Com as duas, vale a origem."""

    id_usuario: str
    mensagem: str | None = Field(None, min_length=1, max_length=2000)
    origem: Origem | None = None
    sessao_id: str | None = None
    data_ref: date | None = None
    request_id: str | None = Field(None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")

    @model_validator(mode="after")
    def _mensagem_ou_origem(self) -> PedidoChat:
        if not self.mensagem and not self.origem:
            raise ValueError("envie uma mensagem ou uma origem")
        return self


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
    sugestoes: list[str]
    visuais: list[dict[str, Any]] = Field(default_factory=list)
    ancora: dict[str, Any] | None
    pergunta: str | None
    request_id: str = ""
    resultados_especialistas: dict[str, dict[str, Any]] = Field(default_factory=dict)
    pendencias_impeditivas: list[str] = Field(default_factory=list)
    pendencias_informativas: list[str] = Field(default_factory=list)


# Web app (web/, React): build estático servido aqui. Sem build, cai na tela de teste antiga.
WEB = RAIZ / "web" / "dist"
if (WEB / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")


@app.get("/", include_in_schema=False)
@app.get("/admin", include_in_schema=False)
def tela() -> FileResponse:
    index = WEB / "index.html"
    return FileResponse(index if index.exists() else RAIZ / "app" / "static" / "index.html")


@app.get("/v1/personas")
def listar_personas() -> list[dict[str, Any]]:
    """Personas do modo demonstração, cada uma ligada a um cliente real da base."""
    return personas.resolver(repositorio())


@app.get("/v1/clientes/{id_usuario}/painel")
def painel_do_cliente(id_usuario: str, data_ref: date | None = None) -> dict[str, Any]:
    """Tudo o que a Home e o Raio-X mostram, com os mesmos números do chat."""
    return painel.montar(contexto_do_cliente(id_usuario, data_ref))


@app.get("/v1/clientes/{id_usuario}/avisos")
def avisos_do_cliente(id_usuario: str, data_ref: date | None = None) -> list[dict[str, Any]]:
    ctx = contexto_do_cliente(id_usuario, data_ref)
    return painel.avisos(ctx, _plano_ativo(id_usuario))


def _plano_ativo(id_usuario: str) -> dict[str, Any] | None:
    item = STORE.get(("planos", id_usuario), "ativo")
    return item.value if item else None


@app.get("/v1/clientes/{id_usuario}/plano")
def plano_do_cliente(id_usuario: str, data_ref: date | None = None) -> dict[str, Any] | None:
    """Plano aceito pelo cliente, com o progresso até a data da simulação (ou null)."""
    p = _plano_ativo(id_usuario)
    if p is None:
        return None
    return {**p, "progresso": plano.progresso(p, contexto_do_cliente(id_usuario, data_ref))}


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
def transacoes(id_usuario: str, limite: int = Query(50, le=1000), data_ref: date | None = None) -> list[dict[str, Any]]:
    """Extrato até a data de referência da simulação (o "hoje" do app)."""
    tx = sorted(contexto_do_cliente(id_usuario, data_ref).transacoes, key=lambda t: (t.data, t.ordem), reverse=True)
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
def chat(pedido: PedidoChat, request: Request = None) -> RespostaChat:
    request_id = pedido.request_id or uuid.uuid4().hex
    sessao = pedido.sessao_id or uuid.uuid4().hex
    correlacao = {"request_id": request_id, "sessao": sessao, "id_usuario": pedido.id_usuario}
    # O endpoint síncrono roda em outro contexto; state leva só metadados ao middleware.
    if request is not None:
        request.state.log_campos = correlacao
    token = logs.contexto.set({**logs.contexto.get(), **correlacao})
    inicio = time.perf_counter()
    try:
        ctx = contexto_do_cliente(pedido.id_usuario, pedido.data_ref)
        origem = pedido.origem.model_dump(exclude_none=True) if pedido.origem else None
        try:
            turno = conversar(grafo(), ctx, sessao, pedido.mensagem, origem, request_id=request_id)
        except ConflitoSessao as erro:
            raise HTTPException(409, str(erro)) from erro
        ms = round((time.perf_counter() - inicio) * 1000)
        # Só a fala pública entra com opt-in; contexto, prompts e tools ficam fora.
        # Mesmo com conteúdo ligado, o log leva a fala já mascarada (cartão, CPF, senha).
        conteudo = ({"mensagem": mascarar(pedido.mensagem)[0] if pedido.mensagem else None, "resposta": turno.resposta}
                    if os.getenv("LOG_CONTEUDO") == "1" else {})
        logs.evento(log, f"[API][TURNO] {turno.etapa} · resposta {turno.modo_resposta} · {ms} ms", etapa=turno.etapa,
                    modo_resposta=turno.modo_resposta, origem=origem, tools=turno.tools, reescritas=turno.reescritas,
                    versao_contexto=turno.versao_contexto, turno_id=turno.turno_id, ms=ms, **correlacao, **conteudo)
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
            sugestoes=turno.sugestoes,
            visuais=turno.visuais,
            ancora=turno.ancora,
            pergunta=turno.pergunta,
            request_id=turno.request_id,
            resultados_especialistas=turno.resultados_especialistas,
            pendencias_impeditivas=turno.pendencias_impeditivas,
            pendencias_informativas=turno.pendencias_informativas,
        )
    finally:
        logs.contexto.reset(token)
