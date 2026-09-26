"""Verificações programadas antes de apresentar ou registrar uma proposta.

Esta primeira camada não é um agente LLM independente nem comprova adequação
contratual. Ela protege versão, restrições de caixa e consistência básica.
"""

from __future__ import annotations

import math
from typing import Any


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
