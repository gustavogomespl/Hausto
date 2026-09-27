"""Quando nem o mínimo fecha: caminhos com menos juros e onde dá para cortar, com números de fonte."""

from dataclasses import replace

from langchain_core.messages import AIMessage
from test_agente import ModeloFalso, ctx_padrao, novo_grafo
from test_plano import _gasto

from app import calculos, plano, visuais
from app.agente import texto
from app.agente import conversar
from app.agente.texto import brl

CHIPS = ["Como pagar menos juros?", "Onde dá para cortar?"]


def test_onde_da_para_cortar_em_media_mensal_so_com_gastos_cortaveis():
    ctx = ctx_padrao()
    gastos = [_gasto(ctx, -10, 90, "Delivery"), _gasto(ctx, -40, 60, "Delivery"), _gasto(ctx, -5, 30, "Lazer"),
              _gasto(ctx, -3, 500, "Mercado"),  # essencial não entra
              _gasto(ctx, -4, 900, "Veiculos"),  # não essencial, mas não é corte do dia a dia
              _gasto(ctx, -100, 1000, "Delivery")]  # fora dos 90 dias
    assert plano.onde_da_para_cortar(replace(ctx, transacoes=gastos)) == [
        {"categoria": "Delivery", "por_mes": 50.0}, {"categoria": "Lazer", "por_mes": 10.0}]


def test_onde_cortar_vem_do_contexto_e_vira_fonte_na_falta_de_dinheiro():
    base = ctx_padrao("insuficiente")
    ctx = replace(base, transacoes=[*base.transacoes, _gasto(base, -10, 300, "Delivery")])  # gasto passado: só piora o caixa
    [maior, *_] = plano.onde_da_para_cortar(ctx)
    final = f"Dá para começar por {maior['categoria']}: {brl(maior['por_mes'])} por mês."
    modelo = ModeloFalso(responses=[
        AIMessage("", tool_calls=[{"name": "obter_contexto_cliente", "args": {}, "id": "c1"}]),
        AIMessage(final),
    ])
    grafo, _ = novo_grafo(modelo)
    t = conversar(grafo, ctx, "s1", "onde dá para cortar?")
    assert t.etapa == "informar_deficit" and t.modo_resposta == "llm"  # a resposta não foi descartada
    assert t.numeros_sem_fonte == [] and brl(maior["por_mes"]) in t.resposta


def test_aviso_sem_folga_oferece_menos_juros_e_cortes_em_linguagem_simples():
    ctx = ctx_padrao("insuficiente")
    grafo, _ = novo_grafo()
    t = conversar(grafo, ctx, "s1", origem={"tipo": "aviso", "id": "sem_folga"})
    assert t.sugestoes[:2] == CHIPS
    assert "R$ -" not in t.resposta  # "negativa em R$ 1.025,52", não "R$ -1.025,52"
    if calculos.comparar_opcoes(ctx)["saldo_projetado_no_vencimento"] < 0:
        assert "negativa" in t.resposta


def test_conversa_na_falta_de_dinheiro_mantem_os_atalhos():
    grafo, _ = novo_grafo()
    t = conversar(grafo, ctx_padrao("insuficiente"), "s1", "oi")
    assert t.etapa == "informar_deficit" and t.sugestoes[:2] == CHIPS


# ------------------------------------------------------------------ quanto custa cada forma de pagar, sem folga


def _sem_folga():
    ctx = ctx_padrao("insuficiente")
    c = calculos.comparar_opcoes(ctx, saldo_atual_informado=-2000.0)  # o cliente contou que a conta está negativa
    assert c["saldo_projetado_no_vencimento"] < c["opcoes"]["minimo"]["valor_pago"]  # a conta fica negativa até no mínimo
    return ctx, c


def test_minimo_soma_os_juros_da_conta_que_fica_negativa():
    ctx, c = _sem_folga()
    m, tudo = c["opcoes"]["minimo"], c["opcoes"]["integral"]
    dias = (ctx.proxima_renda - ctx.proximo_vencimento).days
    cartao = calculos.simular_custo_rolagem(c["valor_fatura"], m["valor_pago"])
    conta = calculos.simular_pagamento_com_negativo(m["valor_pago"], c["saldo_projetado_no_vencimento"], dias)
    assert m["juros_cartao"] == cartao["custo_total"] and m["juros_conta"] == conta["custo_total"] > 0
    assert m["custo_total"] == round(cartao["custo_total"] + conta["custo_total"], 2)
    assert m["divida_total"] == tudo["divida_total"] > 0  # a dívida é a mesma; muda onde fica e quanto custa
    assert tudo["custo_total"] < m["custo_total"]  # os juros da conta são menores que os do cartão


def test_com_folga_os_custos_continuam_so_os_do_cartao():
    c = calculos.comparar_opcoes(ctx_padrao())
    m = c["opcoes"]["minimo"]
    assert m["juros_conta"] == 0 and m["custo_total"] == calculos.simular_custo_rolagem(c["valor_fatura"], m["valor_pago"])["custo_total"]


def test_visual_sem_folga_nao_repete_o_minimo_e_mostra_a_mesma_divida():
    _, c = _sem_folga()
    v = visuais.comparar_opcoes(c)
    tudo, minimo = v["dados"]["opcoes"]  # o parcial igual ao mínimo não aparece duas vezes
    assert [tudo["rotulo"], minimo["rotulo"]] == ["Pagar tudo", "Pagar o mínimo"]
    assert tudo["divida_restante"] == minimo["divida_restante"] > 0
    assert minimo["juros_cartao"] > 0 and minimo["juros_conta"] > 0 and tudo["juros_cartao"] == 0
    assert "de qualquer jeito" in v["resumo"]
    assert len(texto.linhas_opcoes(c)) == 2  # o texto fixo também não repete
