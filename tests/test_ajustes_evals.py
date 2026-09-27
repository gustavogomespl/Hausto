"""Regressões achadas pelas evals (roteiros f02, x02, i02, c03, d04) no grafo com contexto versionado."""

from datetime import date

from langchain_core.messages import AIMessage

from app import calculos
from app.agente import conversar, texto
from app.agente.extracao import Extracao, extrair_por_regras
from app.features import montar_contexto
from test_agente import IDS, REPO, ModeloFalso, ctx_padrao, novo_grafo


def _ctx_sem_fatura():
    return next(
        c for c in (montar_contexto(REPO.transacoes(u), date(2025, 11, 28)) for u in IDS)
        if not calculos.prever_fatura(c)["pronta"]
    )


# f02: resposta curta à pergunta do valor da fatura não pode virar loop


def test_resposta_curta_preenche_a_fatura_que_foi_perguntada():
    grafo, _ = novo_grafo()
    ctx = _ctx_sem_fatura()
    assert conversar(grafo, ctx, "s1", "quero pagar o mínimo da fatura").etapa == "perguntar_cliente"
    t = conversar(grafo, ctx, "s1", "é R$ 900")
    assert t.etapa != "perguntar_cliente"
    assert "R$ 900,00" in t.resposta


def test_numero_solto_sem_pergunta_aberta_nao_vira_fatura():
    grafo, _ = novo_grafo()
    ctx = ctx_padrao()
    conversar(grafo, ctx, "s1", "oi")
    t = conversar(grafo, ctx, "s1", "é R$ 900")
    assert "R$ 900,00" not in t.resposta


# x02: objetivo declarado não é dado financeiro novo


def test_objetivo_novo_nao_diz_que_refez_as_contas():
    respostas = iter([Extracao(), Extracao(objetivo="quitar fatura com empréstimo")])
    grafo, _ = novo_grafo()
    from app.agente import construir_grafo
    from langgraph.checkpoint.memory import InMemorySaver

    grafo = construir_grafo(extrator=lambda _: next(respostas), checkpointer=InMemorySaver())
    ctx = ctx_padrao()
    conversar(grafo, ctx, "s1", "oi")
    t = conversar(grafo, ctx, "s1", "consigo um empréstimo pra quitar essa fatura?")
    assert not t.dados_mudaram and "refiz as contas" not in t.resposta


# i02/x02: insuficiência responde à pergunta, mas o déficit vem sempre da regra


def test_insuficiencia_responde_a_pergunta_com_o_llm_e_mantem_o_deficit():
    ctx = ctx_padrao("insuficiente")
    deficit = texto.brl(calculos.comparar_opcoes(ctx)["deficit_para_o_minimo"])
    modelo = ModeloFalso(responses=[AIMessage("Não consigo oferecer empréstimo por aqui. Dá para procurar o banco e negociar a fatura.")])
    grafo, _ = novo_grafo(modelo)
    t = conversar(grafo, ctx, "s1", "consigo um empréstimo pra quitar essa fatura?")
    assert t.etapa == "informar_deficit" and t.modo_resposta == "llm"
    assert "empréstimo" in t.resposta and f"faltam {deficit}" in t.resposta


def test_insuficiencia_descarta_texto_que_fala_em_sobra():
    ctx = ctx_padrao("insuficiente")
    modelo = ModeloFalso(responses=[AIMessage("Sobra dinheiro, pode pagar o mínimo tranquilo.")])
    grafo, _ = novo_grafo(modelo)
    t = conversar(grafo, ctx, "s1", "e se eu pagar só o mínimo, dá?")
    assert t.modo_resposta == "deterministico_insuficiencia"
    assert "Sobra" not in t.resposta and "faltam" in t.resposta


# c03: escolha que fura a restrição explica o motivo e oferece caminho


def test_escolha_incompativel_mostra_quanto_falta_e_proximo_passo():
    ctx = ctx_padrao("insuficiente")
    c = calculos.comparar_opcoes(ctx)
    grafo, _ = novo_grafo()
    conversar(grafo, ctx, "s1", "oi")
    t = conversar(grafo, ctx, "s1", "vou pagar o mínimo mesmo")
    assert t.etapa == "escolha_incompativel"
    assert texto.brl(c["opcoes"]["minimo"]["valor_pago"]) in t.resposta
    assert f"faltam {texto.brl(c['deficit_para_o_minimo'])}" in t.resposta
    assert "?" in t.resposta


# i02/d04: o texto ao cliente não expõe o modelo interno da estimativa


def test_resposta_padrao_nao_expoe_a_calibracao_da_estimativa():
    ctx = ctx_padrao()
    r = texto.resposta_padrao(ctx, calculos.comparar_opcoes(ctx))
    assert "correlação" not in r and "0.945" not in r
    assert "estimada pelo seu consumo de" in r


def test_resposta_padrao_com_fatura_informada_diz_que_veio_do_cliente():
    ctx = ctx_padrao()
    r = texto.resposta_padrao(ctx, calculos.comparar_opcoes(ctx, valor_fatura=1000))
    assert "informada por você" in r


def test_extrator_de_regras_segue_igual_para_frase_com_fatura():
    assert extrair_por_regras("a fatura veio R$ 1.200").valor_fatura == 1200
