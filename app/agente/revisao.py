"""Verificações programadas antes de apresentar ou registrar uma proposta.

Esta primeira camada não é um agente LLM independente nem comprova adequação
contratual. Ela protege versão, restrições de caixa e consistência básica.
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import ValidationError

from app.agente.contratos import ResultadoEspecialista


def revisar_evidencias(
    resultado: dict[str, Any] | None,
    *,
    request_id: str,
    versao_contexto: int,
    referencia_dados: str,
    pendencias_impeditivas: list[str],
    referencia_esperada: str | None = None,
) -> dict[str, Any]:
    """Confere proveniência e atualidade, sem produzir cálculos financeiros.

    O request esperado é explícito: na confirmação pode ser o da proposta
    original. O request que confirma continua identificado separadamente.
    """
    if resultado is None:
        return {"status": "bloqueado", "motivos": ["evidencias_ausentes"], "stale": False}
    try:
        contrato = ResultadoEspecialista.model_validate(resultado)
    except ValidationError:
        return {"status": "bloqueado", "motivos": ["contrato_evidencias_invalido"], "stale": False}

    motivos = []
    if contrato.request_id != request_id:
        motivos.append("request_id_divergente")
    if contrato.versao_contexto_consumida != versao_contexto:
        motivos.append("versao_contexto_desatualizada")
    if contrato.referencia_dados != referencia_dados:
        motivos.append("referencia_dados_desatualizada")
    if motivos:
        return {"status": "recalcular", "motivos": motivos, "stale": True}
    if pendencias_impeditivas or contrato.pendencias or contrato.status == "precisa_dados":
        return {"status": "precisa_esclarecer", "motivos": ["pendencias_impeditivas"], "stale": False}
    if contrato.status == "erro" or any(e.status == "erro" for e in contrato.evidencias):
        return {"status": "erro_tecnico", "motivos": ["execucao_com_erro"], "stale": False}
    if contrato.status == "recalcular":
        return {"status": "recalcular", "motivos": ["especialista_exige_recalculo"], "stale": True}
    if contrato.status == "bloqueado":
        return {"status": "bloqueado", "motivos": ["especialista_bloqueado"], "stale": False}
    if not contrato.evidencias:
        return {"status": "bloqueado", "motivos": ["evidencias_ausentes"], "stale": False}
    if referencia_esperada is not None and not any(
        e.referencia == referencia_esperada for e in contrato.evidencias
    ):
        return {"status": "recalcular", "motivos": ["resultado_divergente_da_evidencia"], "stale": True}
    return {"status": "pode_apresentar", "motivos": [], "stale": False}


def revisar_comparacao(comparacao: dict[str, Any] | None, versao: int) -> dict[str, Any]:
    if not comparacao or comparacao.get("erro"):
        return {"status": "erro_tecnico", "motivos": ["calculo_ausente_ou_falhou"]}
    if comparacao.get("versao_contexto") != versao:
        return {"status": "recalcular", "motivos": ["resultado_desatualizado"]}
    campos = ("valor_fatura", "saldo_projetado_no_vencimento", "essenciais_ate_renda", "reserva_desejada", "disponivel_para_fatura")
    if any(not isinstance(comparacao.get(k), (float, int)) or not math.isfinite(comparacao[k]) for k in campos):
        return {"status": "erro_tecnico", "motivos": ["resultado_financeiro_invalido"]}
    esperado = comparacao["saldo_projetado_no_vencimento"] - comparacao["essenciais_ate_renda"] - comparacao["reserva_desejada"]
    if abs(esperado - comparacao["disponivel_para_fatura"]) > 0.03:
        return {"status": "erro_tecnico", "motivos": ["capacidade_inconsistente"]}
    opcoes = comparacao.get("opcoes", {})
    # Não aceitar apenas um selo produzido pela ferramenta: conferir o caixa.
    viaveis = []
    for nome in ("integral", "parcial_viavel", "minimo"):
        opcao = opcoes.get(nome, {})
        pago = comparacao["valor_fatura"] if nome == "integral" else opcao.get("valor_pago")
        custo = opcao.get("custo_total")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in (pago, custo)):
            return {"status": "erro_tecnico", "motivos": ["opcao_financeira_invalida"]}
        cabe = pago <= comparacao["disponivel_para_fatura"] + 0.005 and pago <= comparacao["valor_fatura"] + 0.005
        if opcao.get("atende_restricoes") and not cabe:
            return {"status": "erro_tecnico", "motivos": ["opcao_viola_restricoes"]}
        if opcao.get("atende_restricoes"):
            viaveis.append(nome)
    if comparacao.get("status") == "ok":
        recomendada = opcoes.get(comparacao.get("recomendada"), {})
        if not recomendada.get("atende_restricoes"):
            return {"status": "erro_tecnico", "motivos": ["opcao_viola_restricoes"]}
    elif comparacao.get("status") == "insuficiente":
        if viaveis or comparacao.get("recomendada"):
            return {"status": "erro_tecnico", "motivos": ["insuficiencia_contraditoria"]}
    else:
        return {"status": "erro_tecnico", "motivos": ["status_desconhecido"]}
    return {"status": "pode_apresentar", "motivos": [], "limite": "simulacao_com_premissas_nao_contratuais"}
