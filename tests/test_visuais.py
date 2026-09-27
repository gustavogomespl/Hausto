"""Visuais do chat: especificação montada pelo código a partir dos fatos; o LLM só escolhe qual mostrar."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from test_agente import ModeloFalso, ctx_padrao, novo_grafo

from app import calculos, visuais
from app.agente import conversar
from app.agente.contexto_financeiro import comparar_contexto


def _soma(etapas):
    return round(sum(e["valor"] for e in etapas if e["tipo"] != "resultado"), 2)


# ------------------------------------------------------------------ cascata do caixa


def test_cascata_fecha_no_que_sobra_depois_de_pagar_tudo():
    ctx = ctx_padrao()
    c = calculos.comparar_opcoes(ctx)
    v = visuais.caixa_ate_renda(ctx, c, "integral")
    etapas = v["dados"]["etapas"]
    assert v["tipo"] == "caixa_ate_renda" and etapas[0]["tipo"] == "inicio" and etapas[-1]["tipo"] == "resultado"
    assert etapas[-1]["valor"] == round(c["disponivel_para_fatura"] - c["valor_fatura"], 2)
    assert abs(_soma(etapas) - etapas[-1]["valor"]) <= 0.02
    assert v["resumo"] and v["titulo"].startswith("Para onde vai o seu dinheiro até ")


def test_cascata_do_minimo_sem_folga_mostra_o_mesmo_deficit_do_texto():
    ctx = ctx_padrao("insuficiente")
    c = calculos.comparar_opcoes(ctx)
    v = visuais.caixa_ate_renda(ctx, c, "minimo")
    assert v["dados"]["etapas"][-1]["valor"] == -c["deficit_para_o_minimo"]
    assert v["dados"]["etapas"][-1]["rotulo"].startswith("Até ")  # o front já escreve "Sobra"/"Falta" junto do valor
    assert "faltam" in v["resumo"]


def test_cascata_usa_saldo_informado_despesas_e_reserva_da_sessao():
    ctx = ctx_padrao()
    dia = (ctx.data_ref + timedelta(days=1)).isoformat()
    despesa = {"id": "d1", "descricao": "Dentista", "valor": 150.0, "data": dia, "adicional": True}
    c = comparar_contexto(ctx, {"saldo_atual": 2000.0, "reserva_desejada": 300.0}, [despesa])
    etapas = visuais.caixa_ate_renda(ctx, c, "minimo")["dados"]["etapas"]
    rotulos = [e["rotulo"] for e in etapas]
    assert etapas[0]["valor"] == 2000.0
    assert any("Despesas informadas" in r for r in rotulos) and any("Reserva" in r for r in rotulos)
    assert abs(_soma(etapas) - etapas[-1]["valor"]) <= 0.02


def test_cascata_com_valor_escolhido_pelo_cliente():
    ctx = ctx_padrao()
    c = calculos.comparar_opcoes(ctx)
    etapas = visuais.caixa_ate_renda(ctx, c, 500.0)["dados"]["etapas"]
    assert any(e["valor"] == -500.0 and "Fatura" in e["rotulo"] for e in etapas)


# ------------------------------------------------------------------ opções e linha do tempo


def test_comparacao_destaca_a_mais_barata_que_cabe_sem_selo():
    ctx = ctx_padrao()
    c = calculos.comparar_opcoes(ctx)
    opcoes = visuais.comparar_opcoes(c)["dados"]["opcoes"]
    assert [o for o in opcoes if o["destaque"]][0]["rotulo"] == "Pagar tudo" if c["recomendada"] == "integral" else True
    minimo = next(o for o in opcoes if o["rotulo"] == "Pagar o mínimo")
    assert minimo["custo"] == c["opcoes"]["minimo"]["custo_total"]
    assert minimo["divida_restante"] == c["opcoes"]["minimo"]["valor_rolado"]


def test_comparacao_sem_folga_nao_destaca_nada_e_marca_o_que_aperta():
    c = calculos.comparar_opcoes(ctx_padrao("insuficiente"))
    opcoes = visuais.comparar_opcoes(c)["dados"]["opcoes"]
    assert not any(o["destaque"] for o in opcoes) and not any(o["cabe"] for o in opcoes)


def test_linha_do_tempo_em_ordem_com_fatura_despesa_e_renda():
    ctx = ctx_padrao()
    dia = (ctx.data_ref + timedelta(days=2)).isoformat()
    c = comparar_contexto(ctx, {}, [{"id": "d1", "descricao": "Dentista", "valor": 150.0, "data": dia, "adicional": True}])
    eventos = visuais.linha_do_tempo(ctx, c)["dados"]["eventos"]
    assert [e["tipo"] for e in eventos][0] == "hoje" and eventos[-1]["tipo"] == "renda"
    assert [e["data"] for e in eventos] == sorted(e["data"] for e in eventos)
    assert {"fatura", "despesa"} <= {e["tipo"] for e in eventos}


# ------------------------------------------------------------------ no chat


def test_aviso_sem_folga_abre_com_a_cascata_do_deficit():
    ctx = ctx_padrao("insuficiente")
    grafo, _ = novo_grafo()
    t = conversar(grafo, ctx, "s1", origem={"tipo": "aviso", "id": "sem_folga"})
    [v] = t.visuais
    assert v["tipo"] == "caixa_ate_renda"
    assert v["dados"]["etapas"][-1]["valor"] == -calculos.comparar_opcoes(ctx)["deficit_para_o_minimo"]


def test_aviso_da_fatura_abre_com_a_comparacao_das_opcoes():
    grafo, _ = novo_grafo()
    t = conversar(grafo, ctx_padrao(), "s1", origem={"tipo": "aviso", "id": "fatura_vence"})
    assert [v["tipo"] for v in t.visuais] == ["comparar_opcoes"]  # um visual por mensagem


def test_llm_pede_um_visual_pela_tool_e_ele_chega_na_resposta():
    modelo = ModeloFalso(responses=[
        AIMessage("", tool_calls=[{"name": "mostrar_visual", "args": {"tipo": "comparar_opcoes"}, "id": "v1"}]),
        AIMessage("Veja no gráfico quanto custa cada forma de pagar. Qual prefere?"),
    ])
    grafo, _ = novo_grafo(modelo)
    t = conversar(grafo, ctx_padrao(), "s1", "me mostra as opções")
    assert [v["tipo"] for v in t.visuais] == ["comparar_opcoes"] and t.numeros_sem_fonte == []


def test_turno_sem_pedido_de_visual_nao_repete_o_visual_anterior():
    grafo, _ = novo_grafo()
    ctx = ctx_padrao()
    assert conversar(grafo, ctx, "s1", origem={"tipo": "aviso", "id": "fatura_vence"}).visuais
    assert conversar(grafo, ctx, "s1", "quero pagar o mínimo").visuais == []


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("MODO_LLM", "simulado")
    import main

    return TestClient(main.app)


def test_api_devolve_visuais(api):
    uid = api.get("/v1/personas").json()[0]["id_usuario"]
    r = api.post("/v1/chat", json={"id_usuario": uid, "origem": {"tipo": "aviso", "id": "fatura_vence"}}).json()
    assert r["visuais"] and {"tipo", "titulo", "resumo", "dados"} <= set(r["visuais"][0])
    assert api.post("/v1/chat", json={"id_usuario": uid, "mensagem": "oi"}).json()["visuais"] is not None
