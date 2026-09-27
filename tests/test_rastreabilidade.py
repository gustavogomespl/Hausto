"""Regressões de correlação, evidências e resultados antigos, sem serviços externos."""

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from threading import Event

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langchain.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

import main
import app.agente.grafo as modulo
from app.agente import Contexto, construir_grafo, conversar
from app.agente.contratos import ResultadoEspecialista
from app.agente.extracao import extrair_por_regras
from app.agente.grafo import ConflitoSessao
from test_agente import ModeloFalso
from test_contexto_e_confirmacao import bruno, fluxo, estado, INICIO, EXTRA


def config(ctx, sessao="s1"):
    chave = json.dumps([ctx.id_usuario, sessao], ensure_ascii=False)
    return {"configurable": {"thread_id": hashlib.sha256(chave.encode()).hexdigest()}}


@pytest.mark.parametrize("request_id", [None, "pedido-123:cliente"])
def test_api_request_id_e_campos_da_interface(monkeypatch, bruno, fluxo, request_id):
    monkeypatch.setattr(main, "grafo", lambda: fluxo[0])
    monkeypatch.setattr(main, "contexto_do_cliente", lambda *args: bruno)
    pedido = {"id_usuario": bruno.id_usuario, "mensagem": INICIO}
    if request_id:
        pedido["request_id"] = request_id
    resposta = TestClient(main.app).post("/v1/chat", json=pedido)
    assert resposta.status_code == 200
    payload = resposta.json()
    rid = payload["request_id"]
    assert rid and (request_id is None or rid == request_id)
    assert rid not in (payload["sessao_id"], payload["turno_id"])
    for nome in ("sessao_id", "resposta", "modo", "etapa", "pendente_confirmacao", "tools_chamadas", "numeros_sem_fonte"):
        assert nome in payload
    assert set(payload["resultados_especialistas"]) == set(modulo.ESPECIALISTAS)
    for resultado in payload["resultados_especialistas"].values():
        contrato = ResultadoEspecialista.model_validate(resultado)
        assert contrato.request_id == rid
        assert contrato.versao_contexto_consumida == payload["versao_contexto"]
        assert contrato.evidencias
    for evento in payload["eventos"]:
        assert evento["request_id"] == rid
        assert evento["sessao_id"] == payload["sessao_id"]
        assert evento["turno_id"] == payload["turno_id"]
        assert evento["thread_id"] and evento["referencia_dados"]
        assert "stale" in evento and "pendencias" in evento and "revisao" in evento


@pytest.mark.parametrize("request_id", ["", "quebra\nlinha", "x" * 129])
def test_request_id_invalido_nao_executa_grafo(monkeypatch, request_id):
    def proibido(*args):
        pytest.fail("entrada inválida não deve carregar dados")
    monkeypatch.setattr(main, "contexto_do_cliente", proibido)
    resposta = TestClient(main.app).post("/v1/chat", json={"id_usuario": "cliente", "mensagem": "oi", "request_id": request_id})
    assert resposta.status_code == 422


def test_request_id_chega_ao_trace_do_modelo(bruno):
    metadados = []
    class Observador(BaseCallbackHandler):
        def on_chat_model_start(self, serialized, messages, **kwargs):
            metadados.append(kwargs.get("metadata", {}))
    modelo = ModeloFalso(responses=[AIMessage("Vamos conferir as opções.")], callbacks=[Observador()])
    g = construir_grafo(modelo=modelo, checkpointer=InMemorySaver())
    turno = conversar(g, bruno, "s1", INICIO, request_id="trace-123")
    assert metadados and all(m["request_id"] == "trace-123" for m in metadados)
    assert all(m["turno_id"] == turno.turno_id for m in metadados)


@pytest.mark.parametrize("fronteira", ["calcular_opcoes", "revisar_calculo", "conversa"])
@pytest.mark.parametrize("adulteracao", ["versao", "request", "hash_base", "payload", "sem_evidencias"])
def test_resultado_antigo_ou_sem_evidencia_nao_e_apresentado_nem_proposto(bruno, fluxo, fronteira, adulteracao):
    g, store = fluxo
    t = conversar(g, bruno, "s1", INICIO, request_id="request-atual")
    atual = deepcopy(estado(g, bruno))
    contrato = atual["resultados_especialistas"]["compromissos_alternativas"]
    if adulteracao == "versao":
        contrato["versao_contexto_consumida"] = t.versao_contexto - 1
    elif adulteracao == "request":
        contrato["request_id"] = "request-antigo"
    elif adulteracao == "hash_base":
        contrato["referencia_dados"] = "base-antiga"
    elif adulteracao == "payload":
        atual["comparacao"]["disponivel_para_fatura"] = 999999
    else:
        contrato["evidencias"] = []
    atual.update(escolha={"opcao": "minimo", "valor": None}, rascunho="Resposta antiga: R$ 999.999,00.")
    g.update_state(config(bruno), atual, as_node=fronteira)
    saida = g.invoke(None, config(bruno), context=Contexto(bruno.id_usuario, bruno.data_ref, bruno, request_id="request-atual"))
    assert saida["etapa"] == "falha_revisao"
    assert saida["escolha"] is None and saida["comparacao"] is None
    assert not saida.get("__interrupt__")
    assert "999.999" not in saida["messages"][-1].text
    assert not store.search(("decisoes", bruno.id_usuario))
    assert any(e["stale"] for e in saida["eventos"]) == (adulteracao != "sem_evidencias")


def test_stale_na_confirmacao_descarta_proposta_e_registra_evento(bruno, fluxo):
    g, store = fluxo
    conversar(g, bruno, "s1", INICIO)
    proposta = conversar(g, bruno, "s1", "quero pagar o mínimo", request_id="proposta")
    resultados = deepcopy(estado(g, bruno)["resultados_especialistas"])
    resultados["compromissos_alternativas"]["versao_contexto_consumida"] -= 1
    g.update_state(config(bruno), {"resultados_especialistas": resultados})
    # update_state recompõe a tarefa pendente; retomar explicitamente o checkpoint
    # injeta o aceite na fronteira de registro, sem executar nova coleta de fatos.
    t = g.invoke(Command(resume="sim"), config(bruno),
                 context=Contexto(bruno.id_usuario, bruno.data_ref, bruno, request_id="confirmacao"))
    assert not t.get("__interrupt__") and t["etapa"] != "decisao_registrada"
    assert not store.search(("decisoes", bruno.id_usuario))
    evento = next(e for e in t["eventos"] if e["stale"])
    assert evento["request_id"] == "confirmacao"
    assert evento["id_proposta"] == proposta.pendente_confirmacao["id_proposta"]


def test_confirmacao_legitima_correlaciona_dois_requests(bruno, fluxo):
    g, store = fluxo
    conversar(g, bruno, "s1", INICIO)
    proposta = conversar(g, bruno, "s1", "quero pagar o mínimo", request_id="escolha-1")
    t = conversar(g, bruno, "s1", "sim", request_id="confirmacao-2")
    assert t.etapa == "decisao_registrada" and t.request_id == "confirmacao-2"
    assert all(e["request_id"] == "confirmacao-2" for e in t.eventos)
    [item] = store.search(("decisoes", bruno.id_usuario))
    assert item.value["request_id"] == "confirmacao-2"
    assert item.value["request_id_proposta"] == "escolha-1"
    assert item.key == proposta.pendente_confirmacao["id_proposta"]
    assert item.value["evidencias"] and item.value["revisao"]["status"] == "pode_apresentar"
    escolha = item.value
    assert escolha["referencia_proposta"]
    assert any(e["origem"] == "proposta_apresentada" and e["referencia"] == escolha["referencia_proposta"] for e in escolha["evidencias"])


@pytest.mark.parametrize("campo,valor", [
    ("valor", 999999), ("custo_total", 0), ("opcao", "integral"),
    ("atende_restricoes", False), ("id_proposta", "outra-proposta"),
    ("request_id", "outro-request"), ("versao_contexto", 999),
    ("referencia_dados", "outra-base"), ("referencia_proposta", None),
])
def test_proposta_alterada_apos_apresentacao_nao_e_registrada(bruno, fluxo, campo, valor):
    g, store = fluxo
    conversar(g, bruno, "s1", INICIO)
    apresentada = conversar(g, bruno, "s1", "quero pagar o mínimo", request_id="origem-proposta")
    escolha = deepcopy(estado(g, bruno)["escolha"])
    fingerprint = escolha["referencia_proposta"]
    assert fingerprint == modulo._referencia_proposta(escolha, apresentada.resposta)
    escolha[campo] = valor
    if campo != "referencia_proposta":
        assert fingerprint != modulo._referencia_proposta(escolha, apresentada.resposta)
    g.update_state(config(bruno), {"escolha": escolha})
    saida = g.invoke(Command(resume="sim"), config(bruno),
                     context=Contexto(bruno.id_usuario, bruno.data_ref, bruno, request_id="confirmacao-atual"))
    assert saida["etapa"] != "decisao_registrada"
    assert not store.search(("decisoes", bruno.id_usuario))
    assert any(e["status"] == "proposta_descartada" and e["stale"] for e in saida["eventos"])


def test_texto_da_proposta_tambem_faz_parte_da_evidencia(bruno, fluxo):
    g, store = fluxo
    conversar(g, bruno, "s1", INICIO)
    conversar(g, bruno, "s1", "quero pagar o mínimo", request_id="origem-proposta")
    mensagem = estado(g, bruno)["messages"][-1]
    g.update_state(config(bruno), {"messages": [AIMessage("Conteúdo diferente do apresentado.", id=mensagem.id)]})
    saida = g.invoke(Command(resume="sim"), config(bruno),
                     context=Contexto(bruno.id_usuario, bruno.data_ref, bruno, request_id="confirmacao-atual"))
    assert saida["etapa"] != "decisao_registrada"
    assert not store.search(("decisoes", bruno.id_usuario))
    assert any(e["status"] == "proposta_descartada" and e["stale"] for e in saida["eventos"])


@pytest.mark.parametrize("fronteira", ["calcular_opcoes", "revisar_calculo", "conversa"])
def test_retomada_de_outro_request_rejeita_snapshot_inteiro_antigo(bruno, fluxo, fronteira):
    g, store = fluxo
    conversar(g, bruno, "s1", INICIO, request_id="request-antigo")
    antigo = deepcopy(estado(g, bruno))
    antigo.update(escolha={"opcao": "minimo", "valor": None}, rascunho="Texto antigo: R$ 3.900,00.")
    g.update_state(config(bruno), antigo, as_node=fronteira)
    saida = g.invoke(None, config(bruno),
                     context=Contexto(bruno.id_usuario, bruno.data_ref, bruno, request_id="request-atual"))
    assert saida["etapa"] == "falha_revisao" and saida["revisao"]["stale"] is True
    assert saida["comparacao"] is None and saida["escolha"] is None
    assert not saida.get("__interrupt__") and not store.search(("decisoes", bruno.id_usuario))
    assert "Texto antigo" not in saida["messages"][-1].text
    assert saida["request_id"] == "request-atual"
    assert saida["eventos"][-1]["request_id"] == "request-atual"


@pytest.mark.parametrize("data", ["10/11/2026", "2026-11-10"])
def test_data_curta_responde_a_pergunta_da_renda(bruno, fluxo, data):
    g, _ = fluxo
    conversar(g, bruno, "s1", INICIO)
    pergunta = conversar(g, bruno, "s1", "Meu salário atrasou.")
    assert pergunta.pendencias_impeditivas
    assert estado(g, bruno)["campo_pergunta_aberta"] == "proxima_renda"
    resposta = conversar(g, bruno, "s1", data)
    atual = estado(g, bruno)
    assert not resposta.pendencias_impeditivas
    assert atual["dados"]["proxima_renda"] == "2026-11-10"
    assert atual["comparacao"]["proxima_renda"] == "2026-11-10"
    assert resposta.revisao["status"] == "pode_apresentar"


def test_erro_de_tool_nao_autoriza_numero_do_erro(monkeypatch, bruno):
    @tool
    def falha_controlada(valor_pago: float) -> dict:
        """Simula uma indisponibilidade de ferramenta."""
        return {"erro": "indisponivel", "custo_total": 999999}
    monkeypatch.setattr(modulo, "FERRAMENTAS", [falha_controlada])
    modelo = ModeloFalso(responses=[
        AIMessage("", tool_calls=[{"name": "falha_controlada", "args": {"valor_pago": 500}, "id": "tool-1"}]),
        AIMessage("Pode pagar R$ 999.999,00."),
    ])
    g = construir_grafo(modelo=modelo, checkpointer=InMemorySaver())
    t = conversar(g, bruno, "s1", INICIO)
    assert t.revisao["status"] == "erro_tecnico"
    assert "999.999" not in t.resposta and not t.pendente_confirmacao
    assert any(e.get("tool") == "falha_controlada" and e["status"] == "erro" for e in t.eventos)


def test_outra_identidade_nao_reutiliza_sessao_nem_apaga_estado(bruno, fluxo, caplog):
    g, _ = fluxo
    conversar(g, bruno, "s1", INICIO)
    antes = deepcopy(estado(g, bruno))
    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="agente"), pytest.raises(ConflitoSessao):
        conversar(g, replace(bruno, id_usuario="outro"), "s1", "sim", request_id="intruso")
    assert estado(g, bruno) == antes
    registros = [r for r in caplog.records if r.getMessage() == "evento_hausto"]
    assert len(registros) == 1 and registros[0].levelno == logging.DEBUG
    evento = registros[0].campos
    assert evento["status"] == "identidade_divergente" and evento["request_id"] == "intruso"
    assert evento["sessao_id"] == "s1" and evento["turno_id"]
    assert evento["no"] == "seguranca_sessao" and evento["especialista"] == "contexto_relacionamento"


def test_api_rejeita_troca_de_identidade(monkeypatch, bruno, fluxo):
    monkeypatch.setattr(main, "grafo", lambda: fluxo[0])
    monkeypatch.setattr(main, "contexto_do_cliente", lambda uid, ref: replace(bruno, id_usuario=uid))
    cliente = TestClient(main.app)
    pedido = {"id_usuario": "primeiro", "sessao_id": "mesma-sessao", "mensagem": INICIO}
    assert cliente.post("/v1/chat", json=pedido).status_code == 200
    resposta = cliente.post("/v1/chat", json={**pedido, "id_usuario": "segundo"})
    assert resposta.status_code == 409 and "primeiro" not in resposta.text


def test_evento_nao_registra_texto_livre_ou_extrato(bruno, fluxo, caplog):
    with caplog.at_level(logging.DEBUG, logger="agente"):
        turno = conversar(fluxo[0], bruno, "s1", INICIO + " Mensagem privada marcadora.", request_id="privacidade")
    registros = [r for r in caplog.records if r.getMessage() == "evento_hausto"]
    assert registros and all(r.levelno == logging.DEBUG and r.exc_info is None for r in registros)
    eventos = [r.campos for r in registros]
    assert eventos == turno.eventos
    obrigatorios = {"request_id", "sessao_id", "thread_id", "turno_id", "versao_contexto", "referencia_dados",
                    "no", "especialista", "status", "stale", "pendencias", "revisao", "quando"}
    permitidos = obrigatorios | {"tool", "evidencias"}
    assert all(obrigatorios <= e.keys() <= permitidos for e in eventos)
    assert all(e["request_id"] == "privacidade" and e["sessao_id"] == "s1"
               and e["thread_id"] == config(bruno)["configurable"]["thread_id"]
               and e["turno_id"] == turno.turno_id and e["referencia_dados"]
               and isinstance(e["versao_contexto"], int) and e["no"]
               and e["especialista"] in modulo.ESPECIALISTAS and e["status"] for e in eventos)
    serializado = json.dumps(eventos, ensure_ascii=False)
    assert "Mensagem privada marcadora" not in serializado
    assert all(f'"{campo}"' not in serializado for campo in (
        "mensagem", "resposta", "messages", "saldo_atual", "transacoes", "extrato", "prompt",
        "chain_of_thought", "credenciais", "api_key", "GOOGLE_API_KEY", "token", "password", "private_key",
    ))


def test_turnos_concorrentes_da_mesma_sessao_sao_serializados(bruno):
    entrou, liberar, segunda_iniciada, segunda_extracao = Event(), Event(), Event(), Event()
    def extrator(mensagem):
        if mensagem == EXTRA:
            entrou.set()
            assert liberar.wait(5)
        elif mensagem == "reserva de R$ 200":
            segunda_extracao.set()
        return extrair_por_regras(mensagem)
    g = construir_grafo(extrator=extrator, checkpointer=InMemorySaver())
    inicial = conversar(g, bruno, "s1", INICIO)
    def segunda():
        segunda_iniciada.set()
        return conversar(g, bruno, "s1", "reserva de R$ 200")
    with ThreadPoolExecutor(max_workers=2) as executor:
        primeira = executor.submit(conversar, g, bruno, "s1", EXTRA)
        assert entrou.wait(5)
        proxima = executor.submit(segunda)
        try:
            assert segunda_iniciada.wait(5)
            assert not segunda_extracao.wait(0.1)
        finally:
            liberar.set()
        a, b = primeira.result(timeout=5), proxima.result(timeout=5)
    assert inicial.versao_contexto < a.versao_contexto < b.versao_contexto
    atual = estado(g, bruno)
    assert atual["dados"]["reserva_desejada"] == 200 and len(atual["despesas"]) == 1


@pytest.mark.parametrize("numero", [float("nan"), float("inf")])
def test_resultado_nao_finito_vira_erro_tecnico(monkeypatch, bruno, fluxo, numero):
    original = modulo.comparar_contexto
    def invalido(*args):
        comparacao = original(*args)
        comparacao["saldo_projetado_no_vencimento"] = numero
        return comparacao
    monkeypatch.setattr(modulo, "comparar_contexto", invalido)
    t = conversar(fluxo[0], bruno, "s1", INICIO)
    assert t.revisao["status"] == "erro_tecnico" and t.etapa == "falha_revisao"
    assert not t.pendente_confirmacao and estado(fluxo[0], bruno)["comparacao"] is None


def test_primeiros_requests_concorrentes_usam_um_grafo(monkeypatch, bruno):
    entrou, liberar, segunda_iniciada, outra_construcao = Event(), Event(), Event(), Event()
    construidos = []
    original = main.construir_grafo
    def construir(**kwargs):
        if entrou.is_set():
            outra_construcao.set()
        entrou.set()
        assert liberar.wait(5)
        g = original(**kwargs)
        construidos.append(g)
        return g
    main.grafo.cache_clear()
    monkeypatch.setattr(main, "construir_grafo", construir)
    monkeypatch.setattr(main, "modelo_chat", lambda: None)
    monkeypatch.setattr(main, "contexto_do_cliente", lambda uid, ref: replace(bruno, id_usuario=uid))
    def enviar(uid):
        if uid == "segundo":
            segunda_iniciada.set()
        return main.chat(main.PedidoChat(id_usuario=uid, sessao_id="cold-start", mensagem=INICIO))
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            primeiro = executor.submit(enviar, "primeiro")
            assert entrou.wait(5)
            segundo = executor.submit(enviar, "segundo")
            try:
                assert segunda_iniciada.wait(5)
                assert not outra_construcao.wait(0.1)
            finally:
                liberar.set()
            assert primeiro.result(timeout=5).resposta
            with pytest.raises(HTTPException) as erro:
                segundo.result(timeout=5)
            assert erro.value.status_code == 409
        assert len(construidos) == 1
    finally:
        liberar.set()
        main.grafo.cache_clear()
