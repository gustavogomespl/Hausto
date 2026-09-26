"""Regressões de sinal e unidade na conferência de números da resposta."""

import json

import pytest

from app.guardrails import numeros_das_tools, numeros_sem_fonte


@pytest.mark.parametrize("valor", ["R$-24", "R$ -24", "R$ -24,00", "-R$ 24", "R$ −24"])
def test_saldo_negativo_com_sinal_preservado_tem_fonte(valor):
    assert numeros_sem_fonte(f"O saldo final é {valor}.", [{"saldo_final": -24}]) == []


@pytest.mark.parametrize("valor", ["R$24", "R$ 24", "R$ 24,00"])
def test_saldo_negativo_nao_autoriza_sobra_positiva(valor):
    assert numeros_sem_fonte(f"Sobram {valor}.", [{"saldo_final": -24}]) == [valor]


@pytest.mark.parametrize("valor", ["R$-24", "R$ -24", "R$ -24,00"])
def test_saldo_positivo_nao_autoriza_numero_negativo(valor):
    assert numeros_sem_fonte(f"O saldo final é {valor}.", [{"saldo_final": 24}]) == [valor]


def test_deficit_positivo_explicito_pode_ser_apresentado():
    fontes = [{"saldo_final": -24, "deficit_para_zerar": 24}]
    assert numeros_sem_fonte("Saldo de R$ -24; faltam R$ 24 para zerar.", fontes) == []


def test_json_aninhado_e_texto_nao_perdem_sinal():
    fontes = [json.dumps({"resultado": [{"saldo_final": -24}]}), "Saldo de R$ -12,50"]
    assert numeros_das_tools(fontes) == {-24, -12.5}
    assert numeros_sem_fonte("Sobram R$ 24 e R$ 12,50.", fontes) == ["R$ 24", "R$ 12,50"]


def test_taxa_decimal_aceita_percentual_sem_autorizar_valor_em_reais():
    fontes = [{"taxa_mensal": 0.14}]
    assert numeros_sem_fonte("A taxa é 14%.", fontes) == []
    assert numeros_sem_fonte("O custo é R$ 14.", fontes) == ["R$ 14"]


def test_taxa_negativa_preserva_sinal_e_precisao():
    assert numeros_sem_fonte("A variação é -1,23%.", [{"variacao": -0.0123}]) == []
    assert numeros_sem_fonte("A variação é 14%.", [{"variacao": -0.14}]) == ["14%"]


def test_tolerancia_de_arredondamento_nao_troca_sinal():
    assert numeros_sem_fonte("A variação é 0,4%.", [{"variacao": -0.004}]) == ["0,4%"]
    assert numeros_sem_fonte("Saldo de R$ 0,01.", [{"saldo_final": -0.001}]) == ["R$ 0,01"]


def test_valores_monetarios_originais_continuam_validos():
    fontes = [{"valor_fatura": 1234.50, "custo_total": 145.83}]
    assert numeros_sem_fonte("A fatura é R$ 1.234,50 e o custo é R$ 145,83.", fontes) == []
    assert numeros_sem_fonte("A fatura é R$ 1234.50 e o custo é R$ 145.83.", fontes) == []
    assert numeros_sem_fonte("O custo é R$ 999,50.", fontes) == ["R$ 999,50"]
