"""Regressões de proveniência e validade sem executar o motor financeiro."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.agente.contratos import ResultadoEspecialista, referencia_resultado
from app.agente.revisao import revisar_evidencias


def contrato(resultado=None):
    return {
        "especialista": "compromissos_alternativas",
        "request_id": "request-origem",
        "versao_contexto_consumida": 2,
        "referencia_dados": "hash-extrato",
        "status": "ok",
        "evidencias": [{
            "origem": "comparar_contexto",
            "status": "ok",
            "referencia": referencia_resultado(resultado or {"valor_fatura": 100}),
        }],
        "pendencias": [],
    }


def revisar(resultado, **esperado):
    argumentos = {
        "request_id": "request-origem", "versao_contexto": 2,
        "referencia_dados": "hash-extrato", "pendencias_impeditivas": [],
    }
    argumentos.update(esperado)
    return revisar_evidencias(resultado, **argumentos)


def test_resultado_com_evidencia_correspondente_pode_ser_apresentado():
    resultado = {"valor_fatura": 100}
    envelope = contrato(resultado)
    original = deepcopy(envelope)
    revisao = revisar(envelope, referencia_esperada=referencia_resultado(resultado))
    assert revisao == {"status": "pode_apresentar", "motivos": [], "stale": False}
    assert envelope == original


@pytest.mark.parametrize("campo,valor", [
    ("request_id", "request-de-outro-turno"),
    ("versao_contexto_consumida", 1),
    ("referencia_dados", "hash-extrato-anterior"),
])
def test_resultado_de_outro_request_versao_ou_base_exige_recalculo(campo, valor):
    envelope = contrato()
    envelope[campo] = valor
    revisao = revisar(envelope)
    assert revisao["status"] == "recalcular"
    assert revisao["stale"] is True


def test_confirmacao_pode_validar_request_original_explicitamente():
    envelope = contrato()
    assert revisar(envelope, request_id="request-confirmacao")["stale"] is True
    assert revisar(envelope, request_id="request-origem")["status"] == "pode_apresentar"


def test_alteracao_do_resultado_sem_nova_evidencia_exige_recalculo():
    resultado = {"valor_fatura": 100, "opcoes": {"integral": {"valor_pago": 100}}}
    envelope = contrato(resultado)
    resultado["opcoes"]["integral"]["valor_pago"] = 200
    revisao = revisar(envelope, referencia_esperada=referencia_resultado(resultado))
    assert revisao["status"] == "recalcular"
    assert revisao["stale"] is True
    assert "resultado_divergente_da_evidencia" in revisao["motivos"]


def test_pendencia_atual_bloqueia_resultado_que_se_declara_completo():
    revisao = revisar(contrato(), pendencias_impeditivas=["nova data da renda"])
    assert revisao["status"] == "precisa_esclarecer"
    assert revisao["stale"] is False


def test_pendencia_do_especialista_tambem_exige_esclarecimento():
    envelope = contrato()
    envelope["pendencias"] = ["vencimento da despesa"]
    assert revisar(envelope)["status"] == "precisa_esclarecer"


def test_erro_em_uma_tool_nao_e_ocultado_por_evidencia_bem_sucedida():
    envelope = contrato()
    envelope["evidencias"].append({"origem": "tool", "status": "erro", "referencia": "execucao-falhou"})
    assert revisar(envelope)["status"] == "erro_tecnico"


@pytest.mark.parametrize("status,esperado", [
    ("precisa_dados", "precisa_esclarecer"), ("recalcular", "recalcular"),
    ("bloqueado", "bloqueado"), ("erro", "erro_tecnico"),
])
def test_status_impeditivo_do_especialista_nao_e_promovido_a_ok(status, esperado):
    envelope = contrato()
    envelope["status"] = status
    assert revisar(envelope)["status"] == esperado


def test_resultado_ausente_ou_sem_evidencias_nao_pode_ser_apresentado():
    assert revisar(None)["status"] == "bloqueado"
    envelope = contrato()
    envelope["evidencias"] = []
    assert revisar(envelope)["status"] == "bloqueado"


@pytest.mark.parametrize("campo,valor", [
    ("request_id", "  "), ("versao_contexto_consumida", True),
    ("versao_contexto_consumida", -1), ("versao_contexto_consumida", "2"),
    ("referencia_dados", ""), ("especialista", "agente_desconhecido"),
    ("status", "pode_apresentar"),
])
def test_contrato_malformado_falha_fechado(campo, valor):
    envelope = contrato()
    envelope[campo] = valor
    assert revisar(envelope)["status"] == "bloqueado"


def test_evidencia_sem_origem_ou_referencia_falha_fechado():
    envelope = contrato()
    envelope["evidencias"][0]["origem"] = " "
    assert revisar(envelope)["status"] == "bloqueado"
    envelope = contrato()
    envelope["evidencias"][0]["referencia"] = ""
    assert revisar(envelope)["status"] == "bloqueado"


def test_contrato_nao_introduz_copia_de_payload_financeiro():
    envelope = contrato()
    envelope["comparacao"] = {"valor_fatura": 100}
    with pytest.raises(ValidationError):
        ResultadoEspecialista.model_validate(envelope)


def test_hash_independe_da_ordem_das_chaves_mas_preserva_os_valores():
    assert referencia_resultado({"a": 1, "b": {"x": 2, "y": 3}}) == referencia_resultado(
        {"b": {"y": 3, "x": 2}, "a": 1},
    )
    assert referencia_resultado({"saldo": -10}) != referencia_resultado({"saldo": 10})
    with pytest.raises(ValueError):
        referencia_resultado({"saldo": float("nan")})
