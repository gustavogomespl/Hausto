"""Pendências do contexto persistem até o campo correspondente ser esclarecido."""

import hashlib
import json
from datetime import date

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from app.agente import construir_grafo, conversar
from app.agente.contexto import atualizar_fatos
from app.agente.extracao import DespesaInformada, Extracao, extrair_por_regras
from app.features import ContextoCliente


@pytest.fixture
def cliente():
    return ContextoCliente(
        id_usuario="pendencias-sintetico", data_ref=date(2026, 10, 18),
        dia_vencimento=25, proximo_vencimento=date(2026, 10, 25),
        dia_renda=7, proxima_renda=date(2026, 11, 7), saldo_atual=7100,
        renda_mensal_media=0, persona="P3", persona_descricao="Cenário sintético",
        meses_nao_integrais_ult3=2,
    )


def test_nova_ambiguidade_nao_apaga_pendencia_financeira_anterior(cliente):
    s = atualizar_fatos({}, extrair_por_regras("Meu salário atrasou"), cliente)
    pergunta_renda = s["pendencias_impeditivas"][0]
    s = atualizar_fatos(s, extrair_por_regras("Tenho uma despesa"), cliente)
    assert len(s["perguntas_abertas"]) == 2
    s = atualizar_fatos(s, extrair_por_regras("Nova despesa adicional de R$ 500 em 28/10/2026"), cliente)
    assert s["pendencias_impeditivas"] == [pergunta_renda]
    assert s["campo_pergunta_aberta"] == "proxima_renda"
    s = atualizar_fatos(s, extrair_por_regras("Meu salário chega em 10/11/2026"), cliente)
    assert not s["pendencias_impeditivas"] and not s["perguntas_abertas"]


def test_checkpoint_com_pergunta_antiga_mantem_pendencia(cliente):
    anterior = {"pergunta_aberta": "Qual é a data da renda?", "campo_pergunta_aberta": "proxima_renda", "versao_contexto": 4}
    atual = atualizar_fatos(anterior, Extracao(opcao_escolhida="minimo"), cliente)
    assert atual["pendencias_impeditivas"] == [anterior["pergunta_aberta"]]
    resolvido = atualizar_fatos(atual, Extracao(proxima_renda=date(2026, 11, 10)), cliente)
    assert not resolvido["pendencias_impeditivas"]


def test_esclarecer_despesa_parcialmente_mantem_bloqueio(cliente):
    s = atualizar_fatos({}, extrair_por_regras("Tenho uma despesa"), cliente)
    s = atualizar_fatos(s, extrair_por_regras("Tenho despesa de R$ 500"), cliente)
    assert len(s["pendencias_impeditivas"]) == 2
    s = atualizar_fatos(s, extrair_por_regras("sim, é adicional"), cliente)
    assert len(s["pendencias_impeditivas"]) == 1
    s = atualizar_fatos(s, extrair_por_regras("28/10/2026"), cliente)
    assert not s["pendencias_impeditivas"]


def test_aviso_informativo_nao_reclassifica_pendencia_financeira(cliente):
    s = atualizar_fatos({}, extrair_por_regras("Meu salário atrasou"), cliente)
    pergunta = s["pendencias_impeditivas"][0]
    s["pendencias_informativas"] = [pergunta]
    s = atualizar_fatos(s, Extracao(), cliente)
    assert s["pendencias_impeditivas"] == [pergunta]


def test_pendencia_informativa_nao_impede_proposta_e_confirmacao(cliente):
    store = InMemoryStore()
    g = construir_grafo(checkpointer=InMemorySaver(), store=store)
    sessao = "informativa"
    conversar(g, cliente, sessao, "Fatura R$ 3.900, essenciais R$ 3.600 e reserva R$ 100")
    chave = json.dumps([cliente.id_usuario, sessao], ensure_ascii=False)
    config = {"configurable": {"thread_id": hashlib.sha256(chave.encode()).hexdigest()}}
    aviso = "Preferência de linguagem ainda não informada."
    g.update_state(config, {"pendencias_informativas": [aviso]})
    proposta = conversar(g, cliente, sessao, "Quero pagar o mínimo")
    assert proposta.pendente_confirmacao
    assert g.get_state(config).values["pendencias_impeditivas"] == []
    assert aviso in proposta.pendencias
    conversar(g, cliente, sessao, "sim")
    assert len(store.search(("decisoes", cliente.id_usuario))) == 1


def _grafo_iniciado(cliente, extrator=extrair_por_regras):
    store = InMemoryStore()
    g = construir_grafo(checkpointer=InMemorySaver(), store=store, extrator=extrator)
    conversar(g, cliente, "correcao", "Fatura R$ 3.900, essenciais R$ 3.600 e reserva R$ 100")
    return g, store


def test_aluguel_pendente_nao_e_resolvido_por_nova_despesa_de_mercado(cliente):
    g, store = _grafo_iniciado(cliente)
    aluguel = conversar(g, cliente, "correcao", "Tenho uma despesa de aluguel")
    assert "aluguel" in aluguel.resposta
    mercado = conversar(g, cliente, "correcao", "Tenho uma nova despesa adicional de R$ 500 de mercado em 28/10/2026")
    assert mercado.etapa == "perguntar_cliente" and "aluguel" in mercado.resposta
    for mensagem in ("Quero pagar o mínimo", "sim"):
        bloqueado = conversar(g, cliente, "correcao", mensagem)
        assert bloqueado.etapa == "perguntar_cliente" and not bloqueado.pendente_confirmacao
        assert not store.search(("decisoes", cliente.id_usuario))
    resolvido = conversar(g, cliente, "correcao", "A despesa de aluguel é R$ 900 em 28/10/2026, é adicional")
    assert resolvido.etapa == "explicar_opcoes" and not resolvido.pendencias_impeditivas
    assert conversar(g, cliente, "correcao", "Quero pagar o mínimo").pendente_confirmacao
    assert conversar(g, cliente, "correcao", "sim").etapa == "decisao_registrada"
    assert len(store.search(("decisoes", cliente.id_usuario))) == 1


def test_duas_despesas_sem_valor_preservam_identidades_e_exigem_resposta_especifica(cliente):
    g, _ = _grafo_iniciado(cliente)
    primeira = conversar(g, cliente, "correcao", "Tenho uma despesa de aluguel")
    segunda = conversar(g, cliente, "correcao", "Tenho outra despesa de mercado")
    assert len(segunda.pendencias_impeditivas) == 2
    assert segunda.versao_contexto > primeira.versao_contexto
    curta = conversar(g, cliente, "correcao", "R$ 500 em 28/10/2026, sim, é adicional")
    assert len(curta.pendencias_impeditivas) == 2
    aluguel = conversar(g, cliente, "correcao", "A despesa de aluguel é R$ 900 em 28/10/2026, é adicional")
    assert len(aluguel.pendencias_impeditivas) == 1 and "mercado" in aluguel.resposta
    mercado = conversar(g, cliente, "correcao", "R$ 500 em 28/10/2026, sim, é adicional")
    assert not mercado.pendencias_impeditivas and mercado.etapa == "explicar_opcoes"


def test_referencia_global_nao_resolve_pergunta_de_outro_item(cliente):
    s = atualizar_fatos({}, extrair_por_regras("Tenho uma despesa de aluguel"), cliente)
    contraditoria = Extracao(referencia_despesa="aluguel", despesas=[DespesaInformada(descricao="mercado", valor=500, data=date(2026, 10, 28), adicional=True)])
    s = atualizar_fatos(s, contraditoria, cliente)
    assert "despesas:aluguel" in s["perguntas_abertas"]


def test_nova_despesa_nao_resolve_pendencia_sem_identidade(cliente):
    s = atualizar_fatos({}, extrair_por_regras("Tenho uma despesa"), cliente)
    mensagem = "Tenho uma nova despesa adicional de R$ 500 em 28/10/2026"
    s = atualizar_fatos(s, extrair_por_regras(mensagem), cliente, mensagem=mensagem)
    assert s["pendencias_impeditivas"] and "despesas" in s["perguntas_abertas"]


def test_resposta_parcial_sem_nome_nao_completa_outro_compromisso(cliente):
    s = atualizar_fatos({}, extrair_por_regras("Tenho uma despesa de aluguel"), cliente)
    s = atualizar_fatos(s, extrair_por_regras("Tenho despesa adicional de mercado de R$ 500"), cliente)
    s = atualizar_fatos(s, extrair_por_regras("28/10/2026"), cliente)
    assert s["despesas"][0]["data"] is None
    assert "despesas:aluguel" in s["perguntas_abertas"]


def test_resposta_parcial_nomeada_atualiza_so_o_item_correspondente(cliente):
    s = atualizar_fatos({}, extrair_por_regras("Tenho despesa adicional de aluguel de R$ 900"), cliente)
    s = atualizar_fatos(s, extrair_por_regras("Tenho despesa adicional de mercado de R$ 500"), cliente)
    assert len(s["pendencias_impeditivas"]) == 2
    assert "aluguel" in s["pendencias_impeditivas"][0] and "mercado" in s["pendencias_impeditivas"][1]
    s = atualizar_fatos(s, extrair_por_regras("A despesa de aluguel vence em 28/10/2026"), cliente)
    assert s["despesas"][0]["data"] == "2026-10-28"
    assert s["despesas"][1]["data"] is None
    assert len(s["pendencias_impeditivas"]) == 1


def test_pergunta_sem_campo_mapeavel_exige_o_campo_correto(cliente):
    s = atualizar_fatos({}, Extracao(esclarecimento="Informe o saldo novamente."), cliente)
    assert s["campo_pergunta_aberta"] == "saldo_atual"
    s = atualizar_fatos(s, Extracao(valor_fatura=3900), cliente)
    assert s["pendencias_impeditivas"]
    s = atualizar_fatos(s, Extracao(saldo_atual=7100), cliente)
    assert not s["pendencias_impeditivas"]


def test_pergunta_generica_nao_some_com_fato_avulso_e_tem_recuperacao_explicita(cliente):
    s = atualizar_fatos({}, Extracao(esclarecimento="Não consegui interpretar. Pode informar novamente?"), cliente)
    assert "A pendência é sobre" in s["pergunta_aberta"]
    s = atualizar_fatos(s, Extracao(saldo_atual=7100), cliente, mensagem="Meu saldo é R$ 7.100")
    assert "__sem_campo__" in s["perguntas_abertas"]
    mensagem = "A pendência é sobre meu saldo"
    s = atualizar_fatos(s, extrair_por_regras(mensagem), cliente, mensagem=mensagem)
    assert "__sem_campo__" not in s["perguntas_abertas"] and "saldo_atual" in s["perguntas_abertas"]
    assert "saldo" in s["pergunta_aberta"]
    s = atualizar_fatos(s, Extracao(valor_fatura=3900), cliente)
    assert s["pendencias_impeditivas"]
    s = atualizar_fatos(s, Extracao(saldo_atual=7100), cliente)
    assert not s["pendencias_impeditivas"]


def test_pergunta_generica_com_campo_e_valor_explicitos_libera_fluxo(cliente):
    def extrator(mensagem):
        return Extracao(esclarecimento="Pode informar novamente?") if mensagem == "ambígua" else extrair_por_regras(mensagem)
    g, _ = _grafo_iniciado(cliente, extrator)
    assert conversar(g, cliente, "correcao", "ambígua").etapa == "perguntar_cliente"
    assert conversar(g, cliente, "correcao", "Meu saldo é R$ 7.100").etapa == "perguntar_cliente"
    resolvido = conversar(g, cliente, "correcao", "A pendência era sobre meu saldo; meu saldo é R$ 7.100")
    assert resolvido.etapa == "explicar_opcoes" and not resolvido.pendencias_impeditivas


def test_pergunta_generica_ambigua_entre_dois_campos_nao_e_apagada(cliente):
    s = atualizar_fatos({}, Extracao(esclarecimento="Pode informar novamente?"), cliente)
    mensagem = "A pendência era sobre meu saldo e minha fatura; saldo R$ 7.100, fatura R$ 3.900"
    s = atualizar_fatos(s, extrair_por_regras(mensagem), cliente, mensagem=mensagem)
    assert "__sem_campo__" in s["perguntas_abertas"]


def test_pergunta_sem_campo_com_duas_informacoes_preserva_ambas(cliente):
    anterior = {"perguntas_abertas": {"__sem_campo__": "Qual é seu saldo e a data da próxima renda?"}}
    mensagem = "A pendência é sobre meu saldo: saldo R$ 7.100"
    s = atualizar_fatos(anterior, extrair_por_regras(mensagem), cliente, mensagem=mensagem)
    assert "saldo_atual" not in s["perguntas_abertas"]
    assert "proxima_renda" in s["perguntas_abertas"]
    s = atualizar_fatos(s, Extracao(proxima_renda=date(2026, 11, 10)), cliente)
    assert not s["pendencias_impeditivas"]


def test_esclarecimento_da_data_do_proprio_item_nao_duplica_obrigacao(cliente):
    e = Extracao(despesas=[DespesaInformada(valor=500, adicional=True)], esclarecimento="Em qual data vence essa despesa?", campo_esclarecimento="despesas")
    s = atualizar_fatos({}, e, cliente)
    assert not s["perguntas_abertas"] and len(s["pendencias_impeditivas"]) == 1
    s = atualizar_fatos(s, extrair_por_regras("28/10/2026"), cliente)
    assert not s["pendencias_impeditivas"]
    assert s["despesas"][0]["data"] == "2026-10-28"


def test_pergunta_de_outro_compromisso_nao_e_descartada_como_redundante(cliente):
    e = Extracao(referencia_despesa="aluguel", despesas=[DespesaInformada(descricao="mercado", valor=500, adicional=True)], esclarecimento="Em qual data vence essa despesa?", campo_esclarecimento="despesas")
    s = atualizar_fatos({}, e, cliente)
    assert "despesas:aluguel" in s["perguntas_abertas"]


def test_nome_na_pergunta_nao_e_descartado_quando_extracao_omite_referencia(cliente):
    e = Extracao(despesas=[DespesaInformada(descricao="mercado", valor=500, adicional=True)], esclarecimento="Em qual data vence essa despesa de aluguel?", campo_esclarecimento="despesas")
    s = atualizar_fatos({}, e, cliente)
    assert "despesas:aluguel" in s["perguntas_abertas"]
    mensagem = "A despesa de mercado é R$ 500 em 28/10/2026, é adicional"
    s = atualizar_fatos(s, extrair_por_regras(mensagem), cliente, mensagem=mensagem)
    assert "despesas:aluguel" in s["perguntas_abertas"]


def test_pergunta_com_complemento_nao_e_descartada_por_palavras_chave(cliente):
    e = Extracao(despesas=[DespesaInformada(descricao="mercado", valor=500, adicional=True)], esclarecimento="Em qual data vence essa despesa referente ao aluguel?", campo_esclarecimento="despesas")
    s = atualizar_fatos({}, e, cliente)
    assert s["perguntas_abertas"]
    mensagem = "A despesa de mercado é R$ 500 em 28/10/2026, é adicional"
    s = atualizar_fatos(s, extrair_por_regras(mensagem), cliente, mensagem=mensagem)
    assert s["perguntas_abertas"]


def test_despesa_nomeada_sem_resposta_explicita_nao_resolve_pergunta_sem_identidade(cliente):
    s = atualizar_fatos({}, extrair_por_regras("Tenho uma despesa"), cliente)
    mensagem = "Tenho despesa de mercado de R$ 500 em 28/10/2026, é adicional"
    s = atualizar_fatos(s, extrair_por_regras(mensagem), cliente, mensagem=mensagem)
    assert "despesas" in s["perguntas_abertas"]
    mensagem = "Essa despesa é a despesa de aluguel de R$ 900 em 28/10/2026, é adicional"
    s = atualizar_fatos(s, extrair_por_regras(mensagem), cliente, mensagem=mensagem)
    assert not s["pendencias_impeditivas"]
