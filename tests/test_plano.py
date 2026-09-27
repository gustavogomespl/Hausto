"""Plano até a próxima renda: o LLM propõe, `simular_plano` confere, o cliente aceita e os avisos acompanham."""

from dataclasses import replace
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from test_agente import ModeloFalso, ctx_padrao, novo_grafo

from app import calculos, painel, plano
from app.agente import conversar
from app.features import Transacao


def _gasto(ctx, dias, valor, macro="Delivery"):
    dia = ctx.data_ref + timedelta(days=dias)
    return Transacao(ctx.id_usuario, dia, dia.year * 100 + dia.month, "S", "compra", valor, macro, macro, 0.0)


# ------------------------------------------------------------------ o que é gasto do dia a dia


def test_dia_a_dia_exclui_essenciais_fatura_e_transferencias():
    ctx = ctx_padrao()
    assert plano.do_dia_a_dia(_gasto(ctx, 0, 50, "Delivery"))
    assert not plano.do_dia_a_dia(_gasto(ctx, 0, 50, "Mercado"))
    assert not plano.do_dia_a_dia(_gasto(ctx, 0, 50, "Transferencias diversas"))
    assert not plano.do_dia_a_dia(replace(_gasto(ctx, 0, 50, "Produtos financeiros"), micro="Pagamento de fatura"))


# ------------------------------------------------------------------ simular_plano


def test_limite_maximo_parte_do_normal_e_da_folga_do_caixa():
    ctx = ctx_padrao()
    c = calculos.comparar_opcoes(ctx)
    s = plano.simular(ctx, c, pagamento_fatura=c["valor_fatura"])
    dias = (ctx.proxima_renda - ctx.data_ref).days
    dias_depois = (ctx.proxima_renda - ctx.proximo_vencimento).days
    folga = c["disponivel_para_fatura"] - c["valor_fatura"] - s["normal_diario"] * dias_depois
    assert s["cabe"] and s["dias"] == dias
    assert s["limite_maximo"] == round(s["normal_diario"] + folga / dias, 2)
    assert s["limite_diario"] == s["limite_maximo"]


def test_limite_acima_do_que_o_caixa_aguenta_nao_cabe():
    ctx = ctx_padrao()
    c = calculos.comparar_opcoes(ctx)
    maximo = plano.simular(ctx, c, c["valor_fatura"])["limite_maximo"]
    s = plano.simular(ctx, c, c["valor_fatura"], limite_diario=maximo + 100)
    assert not s["cabe"] and "faltam" in s["motivo"]


def test_pagamento_abaixo_do_minimo_nao_cabe():
    c = calculos.comparar_opcoes(ctx_padrao())
    s = plano.simular(ctx_padrao(), c, pagamento_fatura=1.0)
    assert not s["cabe"] and "mínimo" in s["motivo"]


def test_sem_folga_nem_cortando_tudo_fecha():
    ctx = ctx_padrao("insuficiente")
    c = calculos.comparar_opcoes(ctx)
    s = plano.simular(ctx, c, c["opcoes"]["minimo"]["valor_pago"])
    assert s["limite_maximo"] < 0 and not s["cabe"] and "Mesmo sem" in s["motivo"]


# ------------------------------------------------------------------ progresso


def _plano_ativo(ctx, limite):
    return {"pagamento_fatura": 100.0, "reserva": 0.0, "limite_diario": limite,
            "inicio": ctx.data_ref.isoformat(), "fim": (ctx.data_ref + timedelta(days=20)).isoformat()}


def test_progresso_acima_quando_passa_do_previsto():
    ctx = ctx_padrao()
    p = _plano_ativo(ctx, limite=50.0)
    hoje = replace(ctx, data_ref=ctx.data_ref + timedelta(days=4),
                   transacoes=[*ctx.transacoes, _gasto(ctx, 1, 150), _gasto(ctx, 3, 150), _gasto(ctx, 5, 999)])
    prog = plano.progresso(p, hoje)
    assert prog["dias_decorridos"] == 4 and prog["gasto_previsto"] == 200.0
    assert prog["gasto_real"] == 300.0 and prog["status"] == "acima"  # o gasto do dia 5 ainda não aconteceu


def test_progresso_dentro_com_tolerancia():
    ctx = ctx_padrao()
    hoje = replace(ctx, data_ref=ctx.data_ref + timedelta(days=4), transacoes=[*ctx.transacoes, _gasto(ctx, 2, 210)])
    assert plano.progresso(_plano_ativo(ctx, 50.0), hoje)["status"] == "dentro"


def test_aviso_de_desvio_vem_primeiro():
    ctx = ctx_padrao()
    hoje = replace(ctx, data_ref=ctx.data_ref + timedelta(days=2), transacoes=[*ctx.transacoes, _gasto(ctx, 1, 500)])
    avisos = painel.avisos(hoje, _plano_ativo(ctx, 10.0))
    assert avisos[0]["id"] == "plano" and "R$ 500,00" in avisos[0]["texto"]
    assert [a["id"] for a in painel.avisos(ctx, None)] == [a["id"] for a in painel.avisos(ctx)]


# ------------------------------------------------------------------ no chat: propor, aceitar, acompanhar


def _modelo_que_propoe(ctx):
    c = calculos.comparar_opcoes(ctx)
    s = plano.simular(ctx, c, c["valor_fatura"])
    args = {"pagamento_fatura": c["valor_fatura"], "reserva": 0, "limite_diario": s["limite_maximo"]}
    return ModeloFalso(responses=[
        AIMessage("", tool_calls=[{"name": "propor_plano", "args": args, "id": "p1"}]),
        AIMessage("Montei um plano: pagar a fatura inteira e manter os gastos do dia a dia no limite combinado."),
    ]), s


def test_plano_proposto_so_vale_depois_do_sim():
    ctx = ctx_padrao()
    modelo, s = _modelo_que_propoe(ctx)
    grafo, store = novo_grafo(modelo)
    t = conversar(grafo, ctx, "s1", "monta um plano pra mim")
    assert t.pendente_confirmacao and t.pendente_confirmacao["tipo"] == "plano"
    assert "Aceita" in t.resposta and store.get(("planos", ctx.id_usuario), "ativo") is None
    t = conversar(grafo, ctx, "s1", "sim")
    salvo = store.get(("planos", ctx.id_usuario), "ativo").value
    assert t.etapa == "plano_aceito" and salvo["limite_diario"] == s["limite_maximo"] and salvo["inicio"] == ctx.data_ref.isoformat()


def test_plano_recusado_nao_e_gravado():
    ctx = ctx_padrao()
    modelo, _ = _modelo_que_propoe(ctx)
    grafo, store = novo_grafo(modelo)
    conversar(grafo, ctx, "s1", "monta um plano pra mim")
    t = conversar(grafo, ctx, "s1", "não")
    assert t.etapa == "plano_recusado" and store.get(("planos", ctx.id_usuario), "ativo") is None


def test_plano_que_nao_cabe_nao_vira_proposta():
    ctx = ctx_padrao()
    c = calculos.comparar_opcoes(ctx)
    args = {"pagamento_fatura": c["valor_fatura"], "reserva": 0, "limite_diario": 10_000_000}
    modelo = ModeloFalso(responses=[
        AIMessage("", tool_calls=[{"name": "propor_plano", "args": args, "id": "p1"}]),
        AIMessage("Esse limite não fecha. Quer tentar um valor menor?"),
    ])
    grafo, _ = novo_grafo(modelo)
    t = conversar(grafo, ctx, "s1", "quero gastar 10 milhões por dia")
    assert t.pendente_confirmacao is None


def test_aviso_do_plano_abre_com_o_progresso():
    ctx = ctx_padrao()
    grafo, store = novo_grafo()
    store.put(("planos", ctx.id_usuario), "ativo", _plano_ativo(ctx, 10.0))
    hoje = replace(ctx, data_ref=ctx.data_ref + timedelta(days=2), transacoes=[*ctx.transacoes, _gasto(ctx, 1, 500)])
    t = conversar(grafo, hoje, "s1", origem={"tipo": "aviso", "id": "plano"})
    assert [v["tipo"] for v in t.visuais] == ["progresso_plano"] and "plano" in t.resposta.lower()


# ------------------------------------------------------------------ API


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("MODO_LLM", "simulado")
    import main

    return TestClient(main.app), main


def test_api_plano_e_aviso_de_desvio(api):
    cli, main = api
    uid = cli.get("/v1/personas").json()[0]["id_usuario"]
    assert cli.get(f"/v1/clientes/{uid}/plano").json() is None
    data_ref = cli.get(f"/v1/clientes/{uid}/painel").json()["data_ref"]
    main.STORE.put(("planos", uid), "ativo", {"pagamento_fatura": 100.0, "reserva": 0.0, "limite_diario": 0.01,
                                              "inicio": data_ref, "fim": "2099-01-01"})
    try:
        r = cli.get(f"/v1/clientes/{uid}/plano").json()
        assert r["limite_diario"] == 0.01 and r["progresso"]["dias_totais"] > 0
        assert cli.post("/v1/chat", json={"id_usuario": uid, "origem": {"tipo": "aviso", "id": "plano"}}).status_code == 200
    finally:
        main.STORE.delete(("planos", uid), "ativo")


# ------------------------------------------------------------------ visuais do plano


def _propor(ctx, limite=None, extra=None):
    c = calculos.comparar_opcoes(ctx)
    s = plano.simular(ctx, c, c["valor_fatura"])
    args = {"pagamento_fatura": c["valor_fatura"], "reserva": 0, "limite_diario": limite if limite is not None else s["limite_maximo"]}
    chamadas = [{"name": "propor_plano", "args": args, "id": "p1"}, *(extra or [])]
    return ModeloFalso(responses=[AIMessage("", tool_calls=chamadas), AIMessage("Montei um plano até a renda.")])


def _cascata(t):
    return [v for v in t.visuais if v["tipo"] == "caixa_ate_renda"]


def test_proposta_de_plano_vem_com_a_cascata_que_fecha_no_limite_maximo():
    ctx = ctx_padrao()
    grafo, _ = novo_grafo(_propor(ctx))
    t = conversar(grafo, ctx, "s1", "monta um plano pra mim")
    [v] = _cascata(t)
    etapas = v["dados"]["etapas"]
    assert t.pendente_confirmacao and "plano" in v["titulo"].lower()
    assert any("Dia a dia" in e["rotulo"] for e in etapas)
    dias = (ctx.proxima_renda - ctx.data_ref).days
    assert abs(etapas[-1]["valor"]) <= 0.005 * dias + 0.01  # usa toda a folga (limite arredondado em centavos)


def test_limite_menor_que_o_maximo_deixa_sobra_na_cascata():
    ctx = ctx_padrao()
    c = calculos.comparar_opcoes(ctx)
    maximo = plano.simular(ctx, c, c["valor_fatura"])["limite_maximo"]
    grafo, _ = novo_grafo(_propor(ctx, limite=round(maximo - 10, 2)))
    t = conversar(grafo, ctx, "s1", "monta um plano pra mim")
    [v] = _cascata(t)
    dias = (ctx.proxima_renda - ctx.data_ref).days
    assert abs(v["dados"]["etapas"][-1]["valor"] - 10 * dias) <= 0.005 * dias + 0.01


def test_cascata_do_plano_nao_duplica_se_o_modelo_ja_mostrou_uma():
    ctx = ctx_padrao()
    extra = [{"name": "mostrar_visual", "args": {"tipo": "caixa_ate_renda", "pagamento": "integral"}, "id": "v1"}]
    grafo, _ = novo_grafo(_propor(ctx, extra=extra))
    t = conversar(grafo, ctx, "s1", "monta um plano pra mim")
    assert len(_cascata(t)) == 1


def test_modelo_mostra_o_progresso_do_plano_ativo():
    ctx = ctx_padrao()
    modelo = ModeloFalso(responses=[
        AIMessage("", tool_calls=[{"name": "mostrar_visual", "args": {"tipo": "progresso_plano"}, "id": "v1"}]),
        AIMessage("Veja como está o seu plano."),
    ])
    grafo, store = novo_grafo(modelo)
    store.put(("planos", ctx.id_usuario), "ativo", _plano_ativo(ctx, 50.0))
    t = conversar(grafo, ctx, "s1", "como estou no plano?")
    assert [v["tipo"] for v in t.visuais] == ["progresso_plano"] and t.modo_resposta == "llm"


def test_progresso_sem_plano_ativo_nao_quebra_o_turno():
    modelo = ModeloFalso(responses=[
        AIMessage("", tool_calls=[{"name": "mostrar_visual", "args": {"tipo": "progresso_plano"}, "id": "v1"}]),
        AIMessage("Você ainda não tem um plano ativo. Quer montar um?"),
    ])
    grafo, _ = novo_grafo(modelo)
    t = conversar(grafo, ctx_padrao(), "s1", "como estou no plano?")
    assert t.visuais == [] and t.modo_resposta == "llm" and "plano ativo" in t.resposta
