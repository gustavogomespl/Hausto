"""Checagem de compreensão (proposta: "explicar impactos e checar a compreensão"; métrica 3 da ficha).

Sem tom professoral: depois da primeira explicação, o agente só pergunta se ficou claro. "Entendi" fecha sem
LLM; "Explica de novo" reexplica mais simples e pergunta mais uma vez. Cada resposta vira indicador.
"""

from langchain_core.messages import AIMessage
from test_agente import ctx_padrao, novo_grafo
from test_planejador import ModeloGravador

from app.agente import conversar, texto
from app.agente.grafo import REEXPLICAR


def _explica(*respostas):
    return ModeloGravador(responses=[AIMessage(r) for r in respostas])


def _registros(store, ctx):
    return [i.value for i in store.search(("compreensao", ctx.id_usuario))]


def test_primeira_explicacao_pergunta_se_ficou_claro():
    modelo = _explica("Sua fatura dá para pagar inteira, sem juros. Pagar só o mínimo custa juros.")
    grafo, _ = novo_grafo(modelo)
    t = conversar(grafo, ctx_padrao(), "s1", "oi, e minha fatura?")
    assert t.resposta.endswith(texto.PERGUNTA_COMPREENSAO) and t.sugestoes == texto.CHIPS_COMPREENSAO


def test_entendi_fecha_sem_llm_e_registra():
    ctx = ctx_padrao()
    modelo = _explica("Sua fatura dá para pagar inteira, sem juros.")
    grafo, store = novo_grafo(modelo)
    conversar(grafo, ctx, "s1", "oi, e minha fatura?")
    t = conversar(grafo, ctx, "s1", "Entendi")
    assert t.resposta == texto.ENTENDEU and len(modelo.vistas) == 1  # nenhuma chamada nova ao LLM
    assert [r["entendeu"] for r in _registros(store, ctx)] == [True]


def test_explica_de_novo_reexplica_mais_simples_e_pergunta_mais_uma_vez():
    ctx = ctx_padrao()
    modelo = _explica("Sua fatura dá para pagar inteira, sem juros.", "Pense assim: pagar tudo agora não custa nada a mais.")
    grafo, store = novo_grafo(modelo)
    conversar(grafo, ctx, "s1", "oi, e minha fatura?")
    t = conversar(grafo, ctx, "s1", "Explica de novo")
    assert REEXPLICAR in modelo.vistas[1][0].text  # o prompt do turno pede a explicação mais simples
    assert t.resposta.endswith(texto.PERGUNTA_COMPREENSAO)
    t = conversar(grafo, ctx, "s1", "Entendi")
    assert [(r["entendeu"], r["tentativa"]) for r in _registros(store, ctx)] == [(False, 1), (True, 2)]


def test_nao_pergunta_de_novo_depois_da_segunda_vez_nem_em_outras_explicacoes():
    ctx = ctx_padrao()
    modelo = _explica("Sua fatura dá para pagar inteira.", "Pense assim: pagar tudo não custa nada.",
                      "Com o mínimo, o resto vira dívida com juros.")
    grafo, _ = novo_grafo(modelo)
    conversar(grafo, ctx, "s1", "oi, e minha fatura?")
    conversar(grafo, ctx, "s1", "Explica de novo")
    t = conversar(grafo, ctx, "s1", "e se eu pagar o mínimo?")
    assert not t.resposta.endswith(texto.PERGUNTA_COMPREENSAO)


def test_outra_mensagem_segue_o_fluxo_normal():
    ctx = ctx_padrao()
    modelo = _explica("Sua fatura dá para pagar inteira.", "Com o mínimo, o resto vira dívida com juros.")
    grafo, store = novo_grafo(modelo)
    conversar(grafo, ctx, "s1", "oi, e minha fatura?")
    t = conversar(grafo, ctx, "s1", "e se eu pagar o mínimo?")
    assert t.modo_resposta == "llm" and _registros(store, ctx) == []


def test_modo_simulado_nao_pergunta():
    grafo, _ = novo_grafo()
    t = conversar(grafo, ctx_padrao(), "s1", "oi, e minha fatura?")
    assert not t.resposta.endswith(texto.PERGUNTA_COMPREENSAO)


def test_indicador_de_compreensao_na_api(monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("MODO_LLM", "simulado")
    import main
    main.STORE.put(("compreensao", "cliente-x"), "a", {"entendeu": False, "tentativa": 1})
    main.STORE.put(("compreensao", "cliente-x"), "b", {"entendeu": True, "tentativa": 2})
    try:
        r = TestClient(main.app).get("/v1/indicadores/compreensao").json()
        assert r["respostas"] >= 2 and r["primeira_vez"]["entenderam"] >= 0 and "depois_de_reexplicar" in r
    finally:
        main.STORE.delete(("compreensao", "cliente-x"), "a")
        main.STORE.delete(("compreensao", "cliente-x"), "b")
