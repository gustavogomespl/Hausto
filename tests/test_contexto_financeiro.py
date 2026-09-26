from copy import deepcopy
from datetime import date

import pytest

from app import calculos
from app.agente.contexto_financeiro import comparar_contexto
from app.features import ContextoCliente, Transacao


@pytest.fixture
def bruno():
    return ContextoCliente(
        id_usuario="bruno-sintetico",
        data_ref=date(2026, 10, 18),
        dia_vencimento=25,
        proximo_vencimento=date(2026, 10, 25),
        dia_renda=7,
        proxima_renda=date(2026, 11, 7),
        saldo_atual=7100,
        renda_mensal_media=0,
        persona="P3",
        persona_descricao="Cenário sintético sem outros fluxos",
        meses_nao_integrais_ult3=2,
    )


@pytest.fixture
def dados():
    return {"valor_fatura": 3900, "essenciais_informados": 3600, "reserva_desejada": 100}


@pytest.mark.parametrize("dia", ["2026-10-18", "2026-10-24", "2026-10-25", "2026-10-28"])
def test_despesa_reduz_capacidade_uma_vez_sem_alterar_saldo(bruno, dados, dia):
    despesa = {"id": "conserto", "descricao": "Conserto adicional", "valor": 500, "data": dia}
    originais = deepcopy((bruno, dados, despesa))
    antes = comparar_contexto(bruno, dados, [])
    depois = comparar_contexto(bruno, dados, [despesa])
    assert antes["disponivel_para_fatura"] == 3400
    assert depois["disponivel_para_fatura"] == 2900
    assert depois["simulacao"] is True
    assert "Não são condições contratuais verificadas" in depois["aviso_condicoes"]
    if dia <= "2026-10-25":
        assert depois["saldo_projetado_no_vencimento"] == 6600
        assert depois["essenciais_ate_renda"] == 3600
    else:
        assert depois["saldo_projetado_no_vencimento"] == 7100
        assert depois["essenciais_ate_renda"] == 4100
    assert (bruno, dados, despesa) == originais


def test_essenciais_informados_substituem_media(bruno, dados):
    bruno.transacoes = [
        Transacao("bruno-sintetico", date(2026, mes, 28), 202600 + mes, "S", "Casa", 3000, "Casa", "Aluguel", 0)
        for mes in (7, 8, 9)
    ]
    assert calculos.projetar_essenciais_ate_renda(bruno)["essenciais_ate_renda"] == 3000
    resultado = comparar_contexto(bruno, dados, [])
    assert resultado["essenciais_ate_renda"] == 3600
    assert resultado["contexto_financeiro"]["fonte_essenciais"] == "total informado pelo cliente"
    dados["essenciais_informados"] = 0
    assert comparar_contexto(bruno, dados, [])["essenciais_ate_renda"] == 0


def test_sem_dados_novos_preserva_comparador_e_informa_origem(bruno):
    dados = {"valor_fatura": 3900}
    legado = calculos.comparar_opcoes(bruno, valor_fatura=3900)
    novo = comparar_contexto(bruno, dados, [])
    assert {chave: novo[chave] for chave in legado} == legado
    assert novo["contexto_financeiro"]["fonte_essenciais"] == "estimativa histórica"


def test_deduplica_despesa_pelo_id_e_rejeita_conflito(bruno, dados):
    d = {"id": "conserto", "valor": 500, "data": "2026-10-28"}
    assert comparar_contexto(bruno, dados, [d, dict(d)])["disponivel_para_fatura"] == 2900
    assert comparar_contexto(bruno, dados, [d, {**d, "valor": 600}])["erro"] == "contexto_invalido"


@pytest.mark.parametrize("dia", ["2026-10-17", "2026-11-07", "2026-11-08"])
def test_despesa_fora_janela_nao_entra_no_calculo(bruno, dados, dia):
    d = {"id": "fora", "valor": 500, "data": dia}
    resultado = comparar_contexto(bruno, dados, [d])
    assert resultado["disponivel_para_fatura"] == 3400
    assert resultado["contexto_financeiro"]["despesas_fora_horizonte"][0]["id"] == "fora"


def test_renda_informada_muda_horizonte_sem_mudar_contexto(bruno, dados):
    dados["proxima_renda"] = "2026-11-10"
    resultado = comparar_contexto(bruno, dados, [{"id": "nova", "valor": 500, "data": "2026-11-08"}])
    assert resultado["disponivel_para_fatura"] == 2900
    assert resultado["proxima_renda"] == "2026-11-10"
    assert bruno.proxima_renda == date(2026, 11, 7)


@pytest.mark.parametrize("renda", ["2026-10-24", "2026-10-25"])
def test_renda_antes_ou_no_vencimento_exige_outro_modelo(bruno, dados, renda):
    resultado = comparar_contexto(bruno, {**dados, "proxima_renda": renda}, [])
    assert resultado["erro"] == "contexto_nao_suportado"
    assert "recomendada" not in resultado


@pytest.mark.parametrize("despesa", [
    {"id": "a", "valor": 500},
    {"id": "a", "valor": -500, "data": "2026-10-28"},
    {"id": "a", "valor": float("nan"), "data": "2026-10-28"},
    {"id": "a", "valor": 500, "data": "2026-10-28", "adicional_confirmada": False},
])
def test_despesa_incompleta_ou_invalida_nao_produz_recomendacao(bruno, dados, despesa):
    resultado = comparar_contexto(bruno, dados, [despesa])
    assert resultado["erro"] == "contexto_invalido"
    assert "recomendada" not in resultado


def test_saldo_informado_preserva_saldo_original_e_deficit(bruno, dados):
    resultado = comparar_contexto(bruno, {**dados, "saldo_atual": -24}, [])
    assert resultado["saldo_projetado_no_vencimento"] == -24
    assert resultado["status"] == "insuficiente"
    assert "recomendada" not in resultado
    assert bruno.saldo_atual == 7100
    assert resultado["contexto_financeiro"]["saldo_real_extrato"] == 7100
