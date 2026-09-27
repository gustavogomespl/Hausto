"""Jornada Contexto → ferramentas → Revisão → confirmação, sem serviços externos."""

import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from datetime import date

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from app.agente import construir_grafo, conversar
from app.agente.extracao import confirmou, extrair_por_regras
from app.agente.revisao import revisar_comparacao
from app.features import ContextoCliente, Transacao


INICIO = "Minha fatura é R$ 3.900, meu saldo é R$ 7.100, essenciais R$ 3.600 e reserva R$ 100"
EXTRA = "Nova despesa adicional de R$ 500 em 28/10/2026"


@pytest.fixture
def bruno():
    return ContextoCliente(
        id_usuario="bruno-sintetico", data_ref=date(2026, 10, 18),
        dia_vencimento=25, proximo_vencimento=date(2026, 10, 25),
        dia_renda=7, proxima_renda=date(2026, 11, 7), saldo_atual=7100,
        renda_mensal_media=0, persona="P3", persona_descricao="Cenário sintético",
        meses_nao_integrais_ult3=2,
    )


@pytest.fixture
def fluxo():
    store = InMemoryStore()
    return construir_grafo(checkpointer=InMemorySaver(), store=store), store


def estado(grafo, ctx, sessao="s1"):
    chave = json.dumps([ctx.id_usuario, sessao], ensure_ascii=False)
    return grafo.get_state({"configurable": {"thread_id": hashlib.sha256(chave.encode()).hexdigest()}}).values


def test_despesa_nao_e_saldo():
    e = extrair_por_regras("Tenho uma despesa de R$ 500")
    assert e.saldo_atual is None
    assert e.despesas[0].valor == 500
    assert e.despesas[0].data is None and e.despesas[0].adicional is None


@pytest.mark.parametrize("texto", ["saldo de R$ -24", "saldo -24", "tenho R$ -24 na conta"])
def test_saldo_negativo_preserva_sinal(texto):
    assert extrair_por_regras(texto).saldo_atual == -24


def test_hipotese_nao_atualiza_fatos():
    e = extrair_por_regras("E se meu saldo fosse R$ 10.000 e tivesse uma despesa de R$ 500?")
    assert e.saldo_atual is None and not e.despesas and e.opcao_escolhida is None


@pytest.mark.parametrize("mensagem", ["sim, mas tenho uma despesa de 500", "sim, meu saldo mudou", "ok, só que não"])
def test_ressalva_nao_e_confirmacao(mensagem):
    assert not confirmou(mensagem)


def test_bruno_novo_gasto_recalcula_sem_corromper_saldo(bruno, fluxo):
    g, _ = fluxo
    primeiro = conversar(g, bruno, "s1", INICIO)
    assert estado(g, bruno)["comparacao"]["disponivel_para_fatura"] == 3400
    segundo = conversar(g, bruno, "s1", EXTRA)
    atual = estado(g, bruno)
    assert atual["comparacao"]["disponivel_para_fatura"] == 2900
    assert atual["dados"]["saldo_atual"] == 7100
    assert segundo.versao_contexto == primeiro.versao_contexto + 1
    assert segundo.revisao["status"] == "pode_apresentar"
    assert {e["no"] for e in segundo.eventos} >= {"contexto", "comparar_contexto", "revisao"}
    assert all(e["turno_id"] == segundo.turno_id for e in segundo.eventos)
    assert segundo.turno_id != primeiro.turno_id
    repetido = conversar(g, bruno, "s1", EXTRA)
    assert repetido.versao_contexto == segundo.versao_contexto
    assert estado(g, bruno)["comparacao"]["disponivel_para_fatura"] == 2900


def test_despesa_so_entra_apos_esclarecer_data_e_adicional(bruno, fluxo):
    g, _ = fluxo
    conversar(g, bruno, "s1", INICIO)
    t = conversar(g, bruno, "s1", "Tenho despesa de R$ 500")
    assert t.etapa == "perguntar_cliente" and len(t.pendencias) == 2
    assert estado(g, bruno)["comparacao"] is None
    t = conversar(g, bruno, "s1", "sim, é adicional")
    assert t.etapa == "perguntar_cliente" and len(t.pendencias) == 1
    t = conversar(g, bruno, "s1", "28/10/2026")
    assert not t.pendencias and t.etapa == "explicar_opcoes"
    assert estado(g, bruno)["comparacao"]["disponivel_para_fatura"] == 2900


def test_despesa_ja_incluida_nao_e_contada_novamente(bruno, fluxo):
    g, _ = fluxo
    conversar(g, bruno, "s1", INICIO)
    conversar(g, bruno, "s1", "Tenho despesa de R$ 500")
    t = conversar(g, bruno, "s1", "já está incluída")
    assert not t.pendencias
    assert estado(g, bruno)["comparacao"]["disponivel_para_fatura"] == 3400


def test_sim_com_despesa_descarta_proposta_e_exige_nova_confirmacao(bruno, fluxo):
    g, store = fluxo
    conversar(g, bruno, "s1", INICIO)
    proposta = conversar(g, bruno, "s1", "Quero pagar R$ 3.400")
    assert proposta.pendente_confirmacao
    t = conversar(g, bruno, "s1", "sim, mas tenho " + EXTRA)
    assert t.pendente_confirmacao is None
    assert store.search(("decisoes", bruno.id_usuario)) == []
    assert estado(g, bruno)["comparacao"]["disponivel_para_fatura"] == 2900
    assert t.versao_contexto > proposta.versao_contexto
    recusada = conversar(g, bruno, "s1", "Quero pagar R$ 3.400")
    assert recusada.etapa == "escolha_incompativel" and not recusada.pendente_confirmacao
    nova = conversar(g, bruno, "s1", "Quero pagar R$ 2.900")
    assert nova.pendente_confirmacao
    confirmada = conversar(g, bruno, "s1", "sim")
    [registro] = store.search(("decisoes", bruno.id_usuario))
    assert registro.value["versao_contexto"] == t.versao_contexto
    assert registro.value["valor"] == 2900
    assert confirmada.turno_id != nova.turno_id
    assert confirmada.eventos[-1]["status"] == "intencao_registrada"


def test_contexto_do_extrato_mudou_nao_confirma_proposta_antiga(bruno, fluxo):
    g, store = fluxo
    conversar(g, bruno, "s1", "Fatura de R$ 3.900, essenciais R$ 3.600 e reserva R$ 100")
    antes = conversar(g, bruno, "s1", "Quero pagar R$ 3.400")
    assert antes.pendente_confirmacao
    novo = replace(bruno, saldo_atual=6000)
    t = conversar(g, novo, "s1", "sim")
    assert not t.pendente_confirmacao
    assert store.search(("decisoes", bruno.id_usuario)) == []
    assert t.versao_contexto > antes.versao_contexto
    assert estado(g, novo)["comparacao"]["disponivel_para_fatura"] == 2300


def test_revisor_rejeita_resultado_de_outra_versao(bruno, fluxo):
    g, _ = fluxo
    t = conversar(g, bruno, "s1", INICIO)
    assert revisar_comparacao(estado(g, bruno)["comparacao"], t.versao_contexto + 1)["status"] == "recalcular"


def test_falha_da_ferramenta_nao_reutiliza_comparacao(monkeypatch, bruno, fluxo):
    import app.agente.grafo as modulo
    g, store = fluxo
    conversar(g, bruno, "s1", INICIO)
    def falhar(*args):
        raise RuntimeError("falha simulada")
    monkeypatch.setattr(modulo, "comparar_contexto", falhar)
    t = conversar(g, bruno, "s1", "quero pagar o mínimo")
    assert t.etapa == "falha_calculo" and not t.pendente_confirmacao
    assert estado(g, bruno)["comparacao"] is None
    assert t.revisao["status"] == "erro_tecnico"
    assert store.search(("decisoes", bruno.id_usuario)) == []


def test_sessoes_nao_compartilham_fatos(bruno, fluxo):
    g, _ = fluxo
    conversar(g, bruno, "s1", INICIO)
    conversar(g, bruno, "s1", EXTRA)
    conversar(g, bruno, "s2", INICIO)
    assert estado(g, bruno, "s1")["comparacao"]["disponivel_para_fatura"] == 2900
    assert estado(g, bruno, "s2")["comparacao"]["disponivel_para_fatura"] == 3400


def test_identidade_de_sessao_nao_colide_por_separador(bruno, fluxo):
    g, _ = fluxo
    a, b = replace(bruno, id_usuario="a:b"), replace(bruno, id_usuario="a")
    conversar(g, a, "c", INICIO)
    conversar(g, a, "c", EXTRA)
    conversar(g, b, "b:c", INICIO)
    assert estado(g, a, "c")["comparacao"]["disponivel_para_fatura"] == 2900
    assert estado(g, b, "b:c")["comparacao"]["disponivel_para_fatura"] == 3400


def test_api_expoe_eventos_reais_e_versao(monkeypatch, bruno, fluxo):
    from fastapi.testclient import TestClient
    import main
    monkeypatch.setattr(main, "grafo", lambda: fluxo[0])
    monkeypatch.setattr(main, "contexto_do_cliente", lambda *args: bruno)
    resposta = TestClient(main.app).post("/v1/chat", json={"id_usuario": bruno.id_usuario, "mensagem": INICIO})
    assert resposta.status_code == 200
    payload = resposta.json()
    assert payload["versao_contexto"] == 1
    assert payload["modo_resposta"] == "simulado"
    assert payload["tools_chamadas"] == []  # Nenhuma chamada de LLM foi inventada.
    assert any(e["no"] == "comparar_contexto" for e in payload["eventos"])


@pytest.mark.parametrize("mensagem", ["Quanto devo guardar R$ 500?", "Minha fatura é 20/12/2025?", "Minha fatura é 20/12/2025"])
def test_data_ou_pergunta_nao_vira_valor(mensagem):
    e = extrair_por_regras(mensagem)
    assert e.valor_fatura is None and e.reserva_desejada is None


def test_negativa_explicita_prevalece_sobre_palavra_adicional(bruno, fluxo):
    g, _ = fluxo
    conversar(g, bruno, "s1", INICIO)
    t = conversar(g, bruno, "s1", "Tenho despesa de R$ 500 em 28/10/2026, nao e adicional")
    assert not t.pendencias
    assert estado(g, bruno)["despesas"][0]["adicional"] is False
    assert estado(g, bruno)["comparacao"]["disponivel_para_fatura"] == 3400


def test_correcao_de_data_resolve_pendencia(bruno, fluxo):
    g, _ = fluxo
    conversar(g, bruno, "s1", INICIO)
    t = conversar(g, bruno, "s1", "Minha próxima renda chega em 31/02/2026")
    assert t.etapa == "perguntar_cliente"
    t = conversar(g, bruno, "s1", "Minha próxima renda chega em 10/11/2026")
    assert not t.pendencias
    assert estado(g, bruno)["comparacao"]["proxima_renda"] == "2026-11-10"


def test_resposta_curta_a_despesa_sem_valor_resolve_pendencia(bruno, fluxo):
    g, _ = fluxo
    conversar(g, bruno, "s1", INICIO)
    assert conversar(g, bruno, "s1", "Tenho uma despesa").pendencias
    t = conversar(g, bruno, "s1", "R$ 500 em 28/10/2026, sim, é adicional")
    assert not t.pendencias
    assert estado(g, bruno)["comparacao"]["disponivel_para_fatura"] == 2900


def test_transacoes_alteradas_invalidam_confirmacao_mesmo_com_resumo_igual(bruno, fluxo):
    g, store = fluxo
    transacoes = [Transacao(bruno.id_usuario, date(2026, mes, 28), 202600 + mes, "S", "Casa", 600, "Casa", "Aluguel", 0) for mes in (7, 8, 9)]
    ctx = replace(bruno, transacoes=transacoes)
    conversar(g, ctx, "s1", "Fatura de R$ 3.900 e reserva de R$ 100")
    proposta = conversar(g, ctx, "s1", "quero pagar o mínimo")
    assert proposta.pendente_confirmacao
    novo = replace(ctx, transacoes=[replace(t, vlr=6600) for t in transacoes])
    assert ctx.resumo() == novo.resumo()  # Antes esta alteração escapava da referência.
    t = conversar(g, novo, "s1", "sim")
    assert t.etapa == "informar_deficit"
    assert t.versao_contexto > proposta.versao_contexto
    assert not store.search(("decisoes", ctx.id_usuario))


def test_revisor_confronta_selo_com_capacidade_real(bruno, fluxo):
    g, _ = fluxo
    t = conversar(g, bruno, "s1", INICIO)
    c = deepcopy(estado(g, bruno)["comparacao"])
    c["recomendada"] = "integral"
    c["opcoes"]["integral"]["atende_restricoes"] = True
    assert revisar_comparacao(c, t.versao_contexto)["status"] == "erro_tecnico"


def test_insuficiencia_nao_e_reescrita_como_sobra_pelo_modelo(bruno):
    from langchain_core.messages import AIMessage
    from test_agente import ModeloFalso
    modelo = ModeloFalso(responses=[AIMessage("Sobram R$ 24,00; pague o mínimo.")])
    g = construir_grafo(modelo=modelo, checkpointer=InMemorySaver(), store=InMemoryStore())
    t = conversar(g, bruno, "s1", "Fatura R$ 1.490, saldo R$ 2.300, essenciais R$ 2.100 e reserva R$ 100")
    assert t.etapa == "informar_deficit"
    assert t.modo_resposta == "deterministico_insuficiencia"
    assert "Sobram" not in t.resposta and "faltam" in t.resposta


def test_tool_hipotetica_herda_fatos_confirmados_sem_mutar_estado(bruno, fluxo):
    from langchain.tools import ToolRuntime
    from app.agente.estado import Contexto
    from app.agente.ferramentas import comparar_opcoes
    g, _ = fluxo
    conversar(g, bruno, "s1", INICIO)
    conversar(g, bruno, "s1", EXTRA)
    atual = estado(g, bruno)
    dados = deepcopy(atual["dados"])
    runtime = ToolRuntime(state={"dados_confirmados": dados, "despesas_confirmadas": atual["despesas"]},
                          context=Contexto(bruno.id_usuario, bruno.data_ref, bruno), config={}, stream_writer=lambda _: None, tool_call_id="hipotese", store=None)
    resultado = comparar_opcoes.func(runtime, reserva_desejada=200)
    assert resultado["disponivel_para_fatura"] == 2800
    assert dados["reserva_desejada"] == 100
    assert estado(g, bruno)["comparacao"]["disponivel_para_fatura"] == 2900


def test_resposta_natural_a_data_pendente(bruno, fluxo):
    g, _ = fluxo
    conversar(g, bruno, "s1", INICIO)
    conversar(g, bruno, "s1", "Tenho despesa de R$ 500")
    conversar(g, bruno, "s1", "sim, é adicional")
    t = conversar(g, bruno, "s1", "A despesa vence em 28/10/2026")
    assert not t.pendencias
    assert estado(g, bruno)["comparacao"]["disponivel_para_fatura"] == 2900


def test_negar_escolha_nao_pede_confirmacao(bruno, fluxo):
    g, store = fluxo
    conversar(g, bruno, "s1", INICIO)
    t = conversar(g, bruno, "s1", "Nao quero pagar o minimo")
    assert not t.pendente_confirmacao
    assert not store.search(("decisoes", bruno.id_usuario))


# ------------------------------------------------------------------ confirmação natural e pendências impeditivas


@pytest.mark.parametrize("mensagem", ["Sim, pode registrar", "pode", "isso mesmo", "fechado, pode registrar!"])
def test_confirmacao_natural_confirma(mensagem):
    assert confirmou(mensagem)


@pytest.mark.parametrize("mensagem", ["não, obrigado", "Não quero mais", "cancela"])
def test_negativa_natural_cancela_proposta(bruno, fluxo, mensagem):
    g, store = fluxo
    conversar(g, bruno, "s1", INICIO)
    assert conversar(g, bruno, "s1", "quero pagar o mínimo").pendente_confirmacao
    t = conversar(g, bruno, "s1", mensagem)
    assert t.etapa == "decisao_cancelada" and not t.pendente_confirmacao
    assert not store.search(("decisoes", bruno.id_usuario))


def test_negativa_com_dado_novo_reprocessa(bruno, fluxo):
    g, store = fluxo
    conversar(g, bruno, "s1", INICIO)
    conversar(g, bruno, "s1", "quero pagar o mínimo")
    t = conversar(g, bruno, "s1", "não, minha reserva é R$ 200")
    assert t.etapa != "decisao_cancelada"
    assert estado(g, bruno)["dados"]["reserva_desejada"] == 200
    assert not store.search(("decisoes", bruno.id_usuario))


def test_pendencia_ignorada_continua_bloqueando_ate_resolvida(bruno, fluxo):
    g, store = fluxo
    conversar(g, bruno, "s1", INICIO)
    primeira = conversar(g, bruno, "s1", "Meu salário atrasou")
    assert primeira.etapa == "perguntar_cliente"
    for mensagem in ("ok, e agora?", "quero pagar o mínimo", "sim"):
        t = conversar(g, bruno, "s1", mensagem)
        assert t.etapa == "perguntar_cliente" and not t.pendente_confirmacao
        assert t.versao_contexto == primeira.versao_contexto
        assert estado(g, bruno)["comparacao"] is None
        assert not store.search(("decisoes", bruno.id_usuario))
    resolvida = conversar(g, bruno, "s1", "Meu salário chega em 10/11/2026")
    assert not resolvida.pendencias and resolvida.etapa == "explicar_opcoes"
    assert resolvida.versao_contexto > primeira.versao_contexto
    assert conversar(g, bruno, "s1", "quero pagar o mínimo").pendente_confirmacao
    conversar(g, bruno, "s1", "sim")
    assert len(store.search(("decisoes", bruno.id_usuario))) == 1


def test_valor_de_outro_campo_nao_vira_despesa():
    e = extrair_por_regras("gasto metade do salário no mercado, fatura 1.500")
    assert e.valor_fatura == 1500 and not e.despesas


@pytest.mark.parametrize("mensagem", ["pode ser o parcial", "ok, troca pro parcial", "isso, prefiro o integral", "sim, a fatura é outra"])
def test_troca_de_opcao_nao_confirma_proposta_antiga(mensagem):
    assert not confirmou(mensagem)


def test_duvida_na_confirmacao_nao_cancela(bruno, fluxo):
    g, store = fluxo
    conversar(g, bruno, "s1", INICIO)
    conversar(g, bruno, "s1", "quero pagar o mínimo")
    t = conversar(g, bruno, "s1", "não sei, qual é melhor?")
    assert t.etapa != "decisao_cancelada"
    assert not store.search(("decisoes", bruno.id_usuario))


def test_pendencia_ignorada_reitera_esclarecimento_sem_apresentar_calculo(bruno, fluxo):
    g, _ = fluxo
    conversar(g, bruno, "s1", INICIO)
    conversar(g, bruno, "s1", "Tenho despesa de R$ 500")
    t = conversar(g, bruno, "s1", "ok, e aí?")
    assert t.etapa == "perguntar_cliente"
    assert t.pendencias[0] in t.resposta
    assert estado(g, bruno)["comparacao"] is None
