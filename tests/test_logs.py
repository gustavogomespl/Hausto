"""Logs para acompanhar um turno passo a passo: `docker logs` e Logs Explorer do Google (JSON)."""

import json
import logging

import pytest
from fastapi.testclient import TestClient
from test_agente import ctx_padrao, novo_grafo

from app import logs
from app.agente import conversar


def _registro(mensagem="teste", campos=None, exc=False):
    r = logging.LogRecord("agente", logging.INFO, __file__, 1, mensagem, None, None)
    if campos:
        r.campos = campos
    if exc:
        try:
            raise ValueError("falhou")
        except ValueError:
            import sys
            r.exc_info = sys.exc_info()
    return r


def _eventos(caplog, prefixo):
    """Campos das linhas cuja mensagem começa com o prefixo (ex.: "[API]", "[AGENTE][TOOL]")."""
    return [getattr(r, "campos", {}) for r in caplog.records if r.getMessage().startswith(prefixo)]


def _mensagens(caplog, prefixo="["):
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith(prefixo)]


# ------------------------------------------------------------------ formatos


def test_json_tem_severidade_mensagem_e_campos():
    linha = json.loads(logs.FormatoJson().format(_registro("no", {"no": "guardrail", "ms": 3})))
    assert linha["severity"] == "INFO" and linha["message"] == "no"
    assert linha["no"] == "guardrail" and linha["ms"] == 3 and "time" in linha


def test_json_liga_a_linha_ao_trace_do_cloud_run(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj")
    token = logs.contexto.set({"trace": "abc123"})
    try:
        linha = json.loads(logs.FormatoJson().format(_registro()))
    finally:
        logs.contexto.reset(token)
    assert linha["logging.googleapis.com/trace"] == "projects/proj/traces/abc123" and linha["trace"] == "abc123"


def test_json_leva_o_stack_trace_do_erro():
    linha = json.loads(logs.FormatoJson().format(_registro("falha", exc=True)))
    assert "ValueError: falhou" in linha["stack_trace"]


def test_texto_legivel_com_campos_no_fim():
    linha = logs.FormatoTexto().format(_registro("no", {"no": "guardrail", "ms": 3}))
    assert linha.endswith("no no=guardrail ms=3")


# ------------------------------------------------------------------ request, grafo, BigQuery


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("MODO_LLM", "simulado")
    import main

    return TestClient(main.app)


def test_cada_request_gera_uma_linha_com_rota_status_e_trace(api, caplog):
    caplog.set_level(logging.INFO, logger="agente")
    api.get("/saude", headers={"X-Cloud-Trace-Context": "abc123/1;o=1"})
    [req] = _eventos(caplog, "[API] GET /saude 200")
    assert req["rota"] == "/saude" and req["status"] == 200 and req["ms"] >= 0 and req["trace"] == "abc123"


def test_turno_conta_o_passo_a_passo_do_agente_em_frases(caplog):
    caplog.set_level(logging.INFO, logger="agente")
    grafo, _ = novo_grafo()
    conversar(grafo, ctx_padrao(), "s1", "oi")
    passos = _mensagens(caplog, "[AGENTE]")
    assert passos[0] == "[AGENTE][GUARDRAIL] mensagem liberada"
    assert any(p.startswith("[AGENTE][CALCULO] fatura R$") for p in passos)
    assert any(p.startswith("[AGENTE][VALIDACAO]") for p in passos)
    nos = [e["no"] for e in _eventos(caplog, "[AGENTE]") if "no" in e]
    assert nos[:2] == ["guardrail", "atualizar_estado"] and all("ms" in e for e in _eventos(caplog, "[AGENTE]") if "no" in e)
    assert "evento_hausto" not in [r.getMessage() for r in caplog.records if r.levelno >= logging.INFO]


def test_tool_aparece_com_argumentos_e_resultado(caplog):
    from langchain_core.messages import AIMessage
    from test_agente import ModeloFalso

    caplog.set_level(logging.INFO, logger="agente")
    modelo = ModeloFalso(responses=[
        AIMessage("", tool_calls=[{"name": "simular_custo_rolagem", "args": {"valor_pago": 500}, "id": "c1"}]),
        AIMessage("Resposta sem números."),
    ])
    grafo, _ = novo_grafo(modelo)
    conversar(grafo, ctx_padrao(), "s1", "e se eu pagar 500?")
    [tool] = _mensagens(caplog, "[AGENTE][TOOL]")
    assert tool.startswith("[AGENTE][TOOL] simular_custo_rolagem(valor_pago=500) →") and "custo_total=" in tool
    [gemini] = _mensagens(caplog, "[AGENTE][GEMINI]")
    assert "1 tool" in gemini


def test_resumo_do_turno_so_leva_o_texto_com_opt_in(api, caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger="agente")
    uid = api.get("/v1/personas").json()[0]["id_usuario"]
    api.post("/v1/chat", json={"id_usuario": uid, "mensagem": "oi"})
    [turno] = _eventos(caplog, "[API][TURNO]")
    assert turno["etapa"] and turno["modo_resposta"] and "mensagem" not in turno
    caplog.clear()
    monkeypatch.setenv("LOG_CONTEUDO", "1")
    api.post("/v1/chat", json={"id_usuario": uid, "mensagem": "oi"})
    [turno] = _eventos(caplog, "[API][TURNO]")
    assert turno["mensagem"] == "oi" and turno["resposta"]


def test_consulta_ao_bigquery_registra_tempo_e_linhas(caplog):
    from test_calculos import IDS, _ClienteBQFalso

    from app.dados import RepositorioBigQuery

    caplog.set_level(logging.INFO, logger="agente")
    repo = RepositorioBigQuery("p.d.t", cliente=_ClienteBQFalso())
    repo.transacoes(IDS[0])
    repo.transacoes(IDS[0])  # segunda vez vem do cache: nenhuma consulta nova
    [consulta] = _eventos(caplog, "[BIGQUERY] extrato")
    assert consulta["clientes"] == 1 and consulta["linhas"] > 0 and consulta["ms"] >= 0


def test_turno_leva_sessao_e_usuario_como_metadados_do_langsmith():
    grafo, _ = novo_grafo()
    ctx = ctx_padrao()
    conversar(grafo, ctx, "s1", "oi")
    config = next(iter(grafo.checkpointer.list(None))).config
    metadados = grafo.get_state(config).metadata
    assert metadados["sessao"] == "s1" and metadados["id_usuario"] == ctx.id_usuario


def test_ruido_do_sdk_do_gemini_fica_de_fora():
    logs.configurar()
    assert logging.getLogger("google_genai").getEffectiveLevel() >= logging.ERROR
    assert logging.getLogger("httpx").getEffectiveLevel() <= logging.INFO  # chamadas ao Gemini seguem visíveis
