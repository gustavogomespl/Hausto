"""Raio-X: balões do topo (imprevisto, posso comprar, meta) que fazem sentido com o cliente."""

from dataclasses import replace

import pytest
from test_agente import ctx_padrao

from app import painel
from app.agente.texto import brl


def _com_renda(ctx, micro):
    return replace(ctx, transacoes=[replace(t, micro=micro) if t.tipo == "E" else t for t in ctx.transacoes])


@pytest.mark.parametrize("micro, historia", [
    ("Beneficio INSS", "remédio"), ("Salario CLT", "geladeira"), ("Recebimentos diversos", "pneu"),
])
def test_imprevisto_conta_uma_historia_da_renda_do_cliente(micro, historia):
    ctx = _com_renda(ctx_padrao(), micro)
    aviso = next(a for a in painel.avisos(ctx) if a["id"] == "imprevisto")
    assert historia in aviso["titulo"].lower() and aviso["tela"] == "raiox"
    assert brl(painel.valor_do_imprevisto(ctx)) in aviso["texto"]


def test_valor_do_imprevisto_acompanha_a_renda_e_tem_piso():
    ctx = ctx_padrao()
    assert painel.valor_do_imprevisto(replace(ctx, renda_mensal_media=3000.0)) == 150.0
    assert painel.valor_do_imprevisto(replace(ctx, renda_mensal_media=200.0)) == 50.0


def test_conta_negativa_tem_meta_de_sair_do_vermelho():
    ctx = replace(ctx_padrao(), saldo_atual=-1234.5)
    assert painel.montar(ctx)["raio_x"]["meta"] == {"tipo": "sair_do_vermelho", "falta": 1234.5}


def test_saldo_positivo_tem_meta_de_reserva_de_tres_rendas():
    ctx = replace(ctx_padrao(), saldo_atual=1500.0, renda_mensal_media=1000.0)
    assert painel.montar(ctx)["raio_x"]["meta"] == {"tipo": "reserva", "alvo": 3000.0, "guardado": 1500.0, "pct": 0.5}


def test_meta_configurada_pelo_cliente_usa_o_saldo_como_guardado():
    ctx = replace(ctx_padrao(), saldo_atual=2000.0)
    meta = painel.montar(ctx, meta_configurada={"nome": "Casa", "valor": 8000.0})["raio_x"]["meta"]
    assert meta == {"tipo": "personalizada", "nome": "Casa", "alvo": 8000.0, "guardado": 2000.0, "pct": 0.25}
    no_vermelho = painel.montar(replace(ctx, saldo_atual=-50.0), meta_configurada={"nome": "Casa", "valor": 8000.0})
    assert no_vermelho["raio_x"]["meta"]["guardado"] == 0.0 and no_vermelho["raio_x"]["meta"]["pct"] == 0.0


def test_api_salva_a_meta_e_o_painel_mostra(monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("MODO_LLM", "simulado")
    import main
    cli = TestClient(main.app)
    uid = cli.get("/v1/personas").json()[0]["id_usuario"]
    try:
        assert cli.put(f"/v1/clientes/{uid}/meta", json={"nome": "Carro", "valor": 30000}).status_code == 200
        meta = cli.get(f"/v1/clientes/{uid}/painel").json()["raio_x"]["meta"]
        assert meta["tipo"] == "personalizada" and meta["nome"] == "Carro" and meta["alvo"] == 30000
        assert cli.put(f"/v1/clientes/{uid}/meta", json={"nome": "", "valor": -1}).status_code == 422
        assert cli.put(f"/v1/clientes/{uid}/meta", json={"nome": "   ", "valor": 10}).status_code == 422  # só espaços
    finally:
        main.STORE.delete(("metas", uid), "ativa")
