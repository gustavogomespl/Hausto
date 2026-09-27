"""Backend do web app: personas, painel (Home + Raio-X), avisos e chat aberto por aviso ou valor ✦."""

from dataclasses import replace
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from test_agente import IDS, REPO, ctx_padrao, novo_grafo

from app import calculos, painel, personas
from app.agente import conversar, texto
from app.features import Transacao


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("MODO_LLM", "simulado")
    import main

    return TestClient(main.app)


# ------------------------------------------------------------------ personas


def test_personas_apontam_para_clientes_distintos_da_base():
    ps = personas.resolver(REPO)
    assert [p["id"] for p in ps] == ["maria", "carla", "jonas"]
    assert len({p["id_usuario"] for p in ps}) == 3 and all(p["id_usuario"] in IDS for p in ps)


def test_renda_vem_da_categoria_da_entrada():
    base = REPO.transacoes(IDS[0])
    def com(micro):
        return [replace(t, micro=micro) if t.tipo == "E" else t for t in base]
    assert painel.renda_do(com("Beneficio INSS")) == "INSS"
    assert painel.renda_do(com("Salario CLT")) == "CLT"
    assert painel.renda_do(com("Recebimentos diversos")) == "MEI"


# ------------------------------------------------------------------ painel


def test_painel_traz_home_e_raio_x_com_numeros_das_regras():
    ctx = ctx_padrao()
    p = painel.montar(ctx)
    c = calculos.comparar_opcoes(ctx)
    assert p["conta"]["saldo"] == round(ctx.saldo_atual, 2)
    assert p["cartao"]["fatura"] == c["valor_fatura"] and p["cartao"]["vencimento"] == ctx.proximo_vencimento.isoformat()
    juros = p["raio_x"]["juros_por_dia"]
    assert juros["custo_30_dias"] == c["opcoes"]["minimo"]["custo_total"]
    assert juros["valor"] == round(juros["custo_30_dias"] / 30, 2)
    gasto = p["raio_x"]["gasto_por_dia"]
    assert gasto["valor"] == round(gasto["total"] / gasto["dias"], 2)
    valores = [x["valor"] for x in p["raio_x"]["categorias"]]
    assert valores == sorted(valores, reverse=True)


def test_parcelas_do_mes_agrupam_a_compra_parcelada():
    ctx = ctx_padrao()
    ano, m = painel.mes_da_fatura(ctx)
    mes = ctx.data_ref.replace(year=ano, month=m, day=1)
    tv = Transacao(ctx.id_usuario, mes, mes.year * 100 + mes.month, "S", "TV Loja X", 190.0, "Lojas e sites", "Eletronicos", 0.0, parcela_atual=6, parcela_total=10)
    ctx = replace(ctx, transacoes=[*ctx.transacoes, tv])
    parcelas = painel.montar(ctx)["raio_x"]["parcelas"]
    assert parcelas["total_mes"] == 190.0
    assert parcelas["itens"] == [{"descricao": "TV Loja X", "valor": 190.0, "atual": 6, "total": 10}]


def test_parcela_vem_das_colunas_do_extrato():
    linha = {"id_usuario": "x", "anomesdia": "2025-12-01", "anomes": 202512, "tipo": "S", "descr": "TV", "vlr": "190",
             "nom_cate_macro": "Lojas e sites", "nom_cate_micro": "Eletronicos", "saldo_apos": "0", "parcela_atual": "6", "parcela_total": "10"}
    t = Transacao.de_linha(linha)
    assert (t.parcela_atual, t.parcela_total) == (6, 10)
    assert Transacao.de_linha({**linha, "parcela_atual": "", "parcela_total": None}).parcela_total == 0


# ------------------------------------------------------------------ avisos


def test_avisos_de_quem_tem_folga_e_de_quem_nao_tem():
    ok = {a["id"]: a for a in painel.avisos(ctx_padrao())}
    sem = {a["id"]: a for a in painel.avisos(ctx_padrao("insuficiente"))}
    assert "fatura_vence" in ok and "sem_folga" not in ok
    assert "sem_folga" in sem and "fatura_vence" not in sem
    assert ok["imprevisto"]["tela"] == "raiox" and ok["fatura_vence"]["tela"] == "home"
    deficit = calculos.comparar_opcoes(ctx_padrao("insuficiente"))["deficit_para_o_minimo"]
    assert texto.brl(deficit) in sem["sem_folga"]["texto"]


# ------------------------------------------------------------------ chat aberto por origem


def test_valor_da_fatura_abre_o_chat_com_a_explicacao_na_hora():
    ctx = ctx_padrao()
    grafo, _ = novo_grafo()
    t = conversar(grafo, ctx, "s1", origem={"tipo": "ancora", "campo": "fatura"})
    fatura = calculos.comparar_opcoes(ctx)["valor_fatura"]
    assert t.pergunta == "Por que esse valor?"
    assert t.ancora == {"rotulo": "Fatura aberta", "valor": fatura}
    assert texto.brl(fatura) in t.resposta and t.sugestoes


def test_aviso_de_fatura_abre_com_as_opcoes_e_sugestoes():
    ctx = ctx_padrao()
    grafo, _ = novo_grafo()
    t = conversar(grafo, ctx, "s1", origem={"tipo": "aviso", "id": "fatura_vence"})
    assert t.pergunta == "Ver meu plano"
    assert texto.brl(calculos.comparar_opcoes(ctx)["valor_fatura"]) in t.resposta
    assert "Quero pagar tudo" in t.sugestoes


def test_imprevisto_pede_o_gasto_e_a_resposta_curta_vira_despesa():
    ctx = ctx_padrao()
    grafo, _ = novo_grafo()
    t = conversar(grafo, ctx, "s1", origem={"tipo": "aviso", "id": "imprevisto"})
    assert "quanto custa" in t.resposta
    dia = (ctx.data_ref + timedelta(days=3)).strftime("%d/%m/%Y")
    t = conversar(grafo, ctx, "s1", f"dentista R$ 150 no dia {dia}, é extra")
    assert t.dados_mudaram and not t.pendencias


def test_compra_pede_o_que_e_e_entra_como_despesa_extra():
    ctx = ctx_padrao()
    grafo, _ = novo_grafo()
    t = conversar(grafo, ctx, "s1", origem={"tipo": "aviso", "id": "compra"})
    assert t.pergunta == "Posso comprar?" and "quanto custa" in t.resposta
    dia = (ctx.data_ref + timedelta(days=3)).strftime("%d/%m/%Y")
    # Sem dizer "é extra": uma compra é sempre um gasto novo.
    t = conversar(grafo, ctx, "s1", f"celular R$ 1.200 no dia {dia}")
    assert t.dados_mudaram and not t.pendencias


def test_chip_posso_comprar_abre_a_compra():
    grafo, _ = novo_grafo()
    t = conversar(grafo, ctx_padrao(), "s1", "Posso comprar?")
    assert t.pergunta == "Posso comprar?" and "quanto custa" in t.resposta


def test_meta_da_persona_no_painel_e_no_chat(api):
    for p in api.get("/v1/personas").json():
        meta = api.get(f"/v1/clientes/{p['id_usuario']}/painel").json()["meta"]
        assert meta["pct"] == round(meta["guardado"] / meta["alvo"] * 100)
        assert meta["falta"] == meta["alvo"] - meta["guardado"]
        r = api.post("/v1/chat", json={"id_usuario": p["id_usuario"], "origem": {"tipo": "ancora", "campo": "meta"}}).json()
        assert r["ancora"] == {"rotulo": "Já guardado para a meta", "valor": meta["guardado"]}
        assert f"{meta['pct']}% do caminho" in r["resposta"] and texto.brl(meta["falta"]) in r["resposta"]
        assert not r["numeros_sem_fonte"]


def test_cliente_sem_persona_nao_tem_meta():
    # A base de exemplo só tem os clientes das personas; um id fora delas não tem meta.
    assert personas.meta_do_cliente(REPO, "cliente-sem-persona") is None


def test_chip_de_imprevisto_abre_o_mesmo_fluxo_do_aviso():
    grafo, _ = novo_grafo()
    t = conversar(grafo, ctx_padrao(), "s1", "Aconteceu um imprevisto")
    assert "quanto custa" in t.resposta


def test_sugestoes_seguem_a_etapa():
    ctx = ctx_padrao()
    grafo, _ = novo_grafo()
    assert conversar(grafo, ctx, "s1", "oi").sugestoes
    assert conversar(grafo, ctx, "s1", "quero pagar o mínimo").sugestoes == ["Sim", "Não"]


# ------------------------------------------------------------------ API


def test_api_do_web_app(api):
    ps = api.get("/v1/personas").json()
    uid = ps[0]["id_usuario"]
    assert api.get(f"/v1/clientes/{uid}/painel").json()["conta"]["saldo"] is not None
    assert any(a["id"] == "imprevisto" for a in api.get(f"/v1/clientes/{uid}/avisos").json())
    r = api.post("/v1/chat", json={"id_usuario": uid, "origem": {"tipo": "ancora", "campo": "saldo"}}).json()
    assert r["pergunta"] == "Por que esse valor?" and r["ancora"]["rotulo"] == "Saldo" and r["sugestoes"]


def test_chat_sem_mensagem_nem_origem_e_recusado(api):
    uid = api.get("/v1/personas").json()[0]["id_usuario"]
    assert api.post("/v1/chat", json={"id_usuario": uid}).status_code == 422


def test_nome_da_compra_parcelada_sai_limpo():
    assert painel.nome_da_compra("cart credito pass aerea parc 1/6") == "Pass aerea"
    assert painel.nome_da_compra("TV Loja X") == "TV Loja X"


def test_extrato_para_na_data_de_referencia_da_simulacao(api):
    uid = api.get("/v1/personas").json()[0]["id_usuario"]
    data_ref = api.get(f"/v1/clientes/{uid}/painel").json()["data_ref"]
    datas = [t["data"] for t in api.get(f"/v1/clientes/{uid}/transacoes?limite=1000").json()]
    assert datas and max(datas) <= data_ref


def test_abrir_por_origem_nao_chama_o_extrator():
    from langgraph.checkpoint.memory import InMemorySaver

    from app.agente import construir_grafo

    def extrator_que_nao_deve_rodar(_):
        raise AssertionError("abertura por origem não precisa extrair nada")

    grafo = construir_grafo(extrator=extrator_que_nao_deve_rodar, checkpointer=InMemorySaver())
    t = conversar(grafo, ctx_padrao(), "s1", origem={"tipo": "aviso", "id": "fatura_vence"})
    assert t.etapa == "explicar_opcoes" and t.sugestoes


# ------------------------------------------------------------------ revisão: imprevisto não prende o cliente


def test_imprevisto_nao_vira_pendencia_se_o_cliente_muda_de_assunto():
    grafo, _ = novo_grafo()
    ctx = ctx_padrao()
    conversar(grafo, ctx, "s1", origem={"tipo": "aviso", "id": "imprevisto"})
    t = conversar(grafo, ctx, "s1", "quero pagar o mínimo")
    assert t.etapa == "confirmar_decisao" and not t.pendencias
    t = conversar(grafo, ctx, "s1", "não")
    assert "Ponto em aberto" not in t.resposta and not t.pendencias


def test_pagamento_apos_imprevisto_nao_vira_despesa():
    grafo, _ = novo_grafo()
    ctx = ctx_padrao()
    conversar(grafo, ctx, "s1", origem={"tipo": "aviso", "id": "imprevisto"})
    t = conversar(grafo, ctx, "s1", "quero pagar R$ 200 da fatura")
    assert t.pendente_confirmacao and t.pendente_confirmacao["opcao"] == "parcial" and not t.pendencias


def test_exemplo_do_imprevisto_usa_uma_data_futura():
    ctx = ctx_padrao()
    grafo, _ = novo_grafo()
    t = conversar(grafo, ctx, "s1", origem={"tipo": "aviso", "id": "imprevisto"})
    exemplo = (ctx.data_ref + timedelta(days=7)).strftime("%d/%m/%Y")
    assert exemplo in t.resposta


# ------------------------------------------------------------------ revisão: mesmos números do card


def _abrir(ctx, origem, antes=None):
    grafo, _ = novo_grafo()
    if antes:
        conversar(grafo, ctx, "s1", antes)
    return conversar(grafo, ctx, "s1", origem=origem)


def test_ancoras_abrem_com_o_valor_do_card():
    ctx = ctx_padrao()
    p = painel.montar(ctx)
    card = {"saldo": p["conta"]["saldo"], "fatura": p["cartao"]["fatura"],
            "gasto_por_dia": p["raio_x"]["gasto_por_dia"]["valor"], "juros_por_dia": p["raio_x"]["juros_por_dia"]["valor"]}
    for campo, valor in card.items():
        t = _abrir(ctx, {"tipo": "ancora", "campo": campo})
        assert t.ancora["valor"] == valor, campo
        assert texto.brl(valor) in t.resposta, campo


def test_fatura_informada_na_sessao_nao_muda_o_numero_do_card():
    ctx = ctx_padrao()
    card = painel.montar(ctx)["cartao"]["fatura"]
    t = _abrir(ctx, {"tipo": "ancora", "campo": "fatura"}, antes="minha fatura é R$ 900")
    assert t.ancora["valor"] == card and texto.brl(card) in t.resposta
    assert "R$ 900,00" in t.resposta  # o valor informado aparece como observação


def test_aviso_sem_folga_abre_com_o_deficit_do_card():
    ctx = ctx_padrao("insuficiente")
    [aviso] = [a for a in painel.avisos(ctx) if a["id"] == "sem_folga"]
    deficit = texto.brl(calculos.comparar_opcoes(ctx)["deficit_para_o_minimo"])
    t = _abrir(ctx, {"tipo": "aviso", "id": "sem_folga"})
    assert deficit in aviso["texto"] and deficit in t.resposta and t.sugestoes


def test_parcelas_sem_compra_parcelada_nao_inventa_valor():
    t = _abrir(ctx_padrao(), {"tipo": "ancora", "campo": "parcelas"})
    assert t.ancora is None and "Não há compras parceladas" in t.resposta


def test_origem_com_fatura_desconhecida_pergunta_o_valor():
    from test_ajustes_evals import _ctx_sem_fatura

    t = _abrir(_ctx_sem_fatura(), {"tipo": "ancora", "campo": "fatura"})
    assert t.etapa == "perguntar_cliente" and t.ancora is None


def test_origem_sem_calculo_nao_expoe_etapa_interna():
    ctx = ctx_padrao()
    grafo, _ = novo_grafo()
    conversar(grafo, ctx, "s1", "oi")
    assert conversar(grafo, ctx, "s1", origem={"tipo": "ancora", "campo": "saldo"}).etapa == "abertura"


def test_origem_durante_confirmacao_descarta_a_proposta():
    ctx = ctx_padrao()
    grafo, store = novo_grafo()
    assert conversar(grafo, ctx, "s1", "quero pagar o mínimo").pendente_confirmacao
    t = conversar(grafo, ctx, "s1", origem={"tipo": "ancora", "campo": "saldo"})
    assert t.pendente_confirmacao is None and t.ancora["rotulo"] == "Saldo"
    assert store.search(("decisoes", ctx.id_usuario)) == []


# ------------------------------------------------------------------ revisão: painel, personas, API


def test_painel_sem_fatura_so_tem_o_aviso_de_imprevisto():
    from test_ajustes_evals import _ctx_sem_fatura

    ctx = _ctx_sem_fatura()
    p = painel.montar(ctx)
    assert p["cartao"]["fatura"] is None and p["raio_x"]["juros_por_dia"] is None
    assert [a["id"] for a in painel.avisos(ctx)] == ["imprevisto"]


def test_raio_x_usa_o_mes_de_consumo_da_fatura_e_so_compras_a_vista():
    ctx = ctx_padrao()
    ano, mes = painel.mes_da_fatura(ctx)
    anomes = ano * 100 + mes
    dia = ctx.data_ref.replace(year=ano, month=mes, day=1)
    antiga = Transacao(ctx.id_usuario, dia.replace(year=ano - 1), anomes - 100, "S", "Sofa parc 2/5", 90.0, "Lojas e sites", "Moveis", 0.0, parcela_atual=2, parcela_total=5)
    atual = Transacao(ctx.id_usuario, dia, anomes, "S", "Celular parc 8/12", 150.0, "Lojas e sites", "Eletronicos", 0.0, parcela_atual=8, parcela_total=12)
    base = painel.montar(ctx)["raio_x"]["categorias"]
    rx = painel.montar(replace(ctx, transacoes=[*ctx.transacoes, antiga, atual]))["raio_x"]
    assert rx["parcelas"]["itens"] == [{"descricao": "Celular", "valor": 150.0, "atual": 8, "total": 12}]
    assert rx["categorias"] == base  # parcela não entra em "compras desta fatura, sem as parcelas"
    assert len(rx["categorias"]) <= 7


def test_mes_da_fatura_vira_o_ano_em_janeiro():
    ctx = replace(ctx_padrao(), proximo_vencimento=ctx_padrao().proximo_vencimento.replace(year=2026, month=1, day=10))
    assert painel.mes_da_fatura(ctx) == (2025, 12)


def test_aviso_de_fatura_no_singular():
    ctx = ctx_padrao()
    ctx = replace(ctx, data_ref=ctx.proximo_vencimento - timedelta(days=1))
    [aviso] = [a for a in painel.avisos(ctx) if a["id"] == "fatura_vence"] or [None]
    assert aviso is None or aviso["titulo"].endswith("1 dia")


def test_personas_com_poucos_clientes_nao_quebram():
    from app.dados import RepositorioMock

    class DoisClientes(RepositorioMock):
        def listar_clientes(self, limite=50):
            return super().listar_clientes(limite)[:2]

    ps = personas.resolver(DoisClientes())
    assert len(ps) == 2 and len({p["id_usuario"] for p in ps}) == 2


def test_renda_da_persona_e_a_do_cliente_escolhido():
    for p in personas.resolver(REPO):
        assert p["renda"] == painel.renda_do(REPO.transacoes(p["id_usuario"]))
        assert "tags" not in p


def test_origem_do_atalho_ignora_caixa_e_pontuacao():
    from app.agente import aberturas

    assert aberturas.origem_do_atalho("  Minha Fatura? ") == {"tipo": "ancora", "campo": "fatura"}
    assert aberturas.origem_do_atalho("quero pagar tudo") is None
    assert aberturas.precisa_calculo({"tipo": "aviso", "id": "sem_folga"})
    assert not aberturas.precisa_calculo({"tipo": "ancora", "campo": "saldo"})


@pytest.mark.parametrize("origem", [
    {"tipo": "aviso"}, {"tipo": "ancora", "id": "fatura_vence"}, {"tipo": "ancora"},
    {"tipo": "ancora", "campo": "limite"}, {"tipo": "aviso", "id": "promocao"}, {"tipo": "aviso", "id": "imprevisto", "campo": "saldo"},
])
def test_origem_invalida_e_recusada(api, origem):
    uid = api.get("/v1/personas").json()[0]["id_usuario"]
    assert api.post("/v1/chat", json={"id_usuario": uid, "origem": origem}).status_code == 422


def test_raiz_e_admin_servem_o_app(api):
    for rota in ("/", "/admin"):
        r = api.get(rota)
        assert r.status_code == 200 and "text/html" in r.headers["content-type"]


def test_parcela_com_ponto_decimal():
    linha = {"id_usuario": "x", "anomesdia": "2025-12-01", "anomes": 202512, "tipo": "S", "descr": "TV", "vlr": "190",
             "nom_cate_macro": "Lojas e sites", "nom_cate_micro": "Eletronicos", "saldo_apos": "0", "parcela_atual": "6.0", "parcela_total": "10.0"}
    assert (Transacao.de_linha(linha).parcela_atual, Transacao.de_linha(linha).parcela_total) == (6, 10)
