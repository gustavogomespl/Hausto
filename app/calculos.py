"""As 4 tools determinísticas do diagrama. Só calculam: nenhuma executa pagamento.

Taxas de referência (mesmas do financial_plan):
- rotativo do cartão: ~14% a.m. (média de mercado; configurável)
- cheque especial: teto legal de 8% a.m. (Res. CMN 4.765/2019)
- IOF de crédito PF: 0,38% fixo + 0,0082% ao dia
"""

from __future__ import annotations

import statistics
from datetime import date
from typing import Any

from app.features import (
    JANELA_FLUXO_MESES,
    MICRO_FATURA,
    ContextoCliente,
    somar_meses,
)

TAXA_ROTATIVO_AM = 0.14
TAXA_CHEQUE_ESPECIAL_AM = 0.08
IOF_FIXO = 0.0038
IOF_DIA = 0.000082

# Categorias do extrato que espelham compras no cartão (ver prever_fatura)
CATEGORIAS_CARTAO = frozenset({
    "Mercado", "Restaurantes", "Delivery", "Lojas e sites", "Assinaturas",
    "Posto de combustivel", "Transporte por app", "Lazer", "Viagens", "Cuidados pessoais",
})
CATEGORIAS_ESSENCIAIS = frozenset({
    "Casa", "Mercado", "Emprestimos e financiamentos", "Educacao",
    "Transporte publico", "Posto de combustivel", "Boletos diversos",
})
FATOR_FATURA = 0.945
FAIXA_FATOR = (0.71, 1.05)


def _brl(x: float) -> float:
    return round(x + 0.0, 2)


def _iof(valor: float, dias: int) -> float:
    return valor * (IOF_FIXO + IOF_DIA * min(dias, 365))


def consumo_cartao(ctx: ContextoCliente, anomes: int) -> float:
    return sum(
        t.vlr for t in ctx.transacoes if t.anomes == anomes and t.tipo == "S" and t.macro in CATEGORIAS_CARTAO
    )


def prever_fatura(ctx: ContextoCliente) -> dict[str, Any]:
    """Fatura estimada = 0,945 x consumo de cartão do mês fechado anterior ao vencimento.

    Calibrado na base (1.000 clientes, 2025): a fatura paga integralmente no mês M tem
    correlação 0,987 com o consumo em CATEGORIAS_CARTAO no mês M-1; razão mediana 0,945
    (p5-p95: 0,71-1,05). Funciona também para quem paga parcial/mínimo, cujo pagamento
    não revela o valor cheio da fatura.
    """
    venc = ctx.proximo_vencimento
    ref = somar_meses(venc, -1, 1)
    anomes_ref = ref.year * 100 + ref.month
    consumo = consumo_cartao(ctx, anomes_ref)
    fechado = anomes_ref < ctx.data_ref.year * 100 + ctx.data_ref.month or ctx.data_ref >= venc
    if consumo <= 0 or not fechado:
        return {
            "pronta": False,
            "motivo": "consumo do mês de referência ainda não fechado; pergunte o valor da fatura ao cliente",
            "vencimento": venc.isoformat(),
        }
    valor = FATOR_FATURA * consumo
    return {
        "pronta": True,
        "valor_estimado": _brl(valor),
        "faixa_provavel": [_brl(FAIXA_FATOR[0] * consumo), _brl(FAIXA_FATOR[1] * consumo)],
        "consumo_cartao_mes_ref": _brl(consumo),
        "mes_ref": f"{ref.month:02d}/{ref.year}",
        "base": f"{FATOR_FATURA} x consumo de cartão de {ref.month:02d}/{ref.year} (correlação 0,987 na base)",
        "vencimento": venc.isoformat(),
    }


def projetar_saldo_ate_vencimento(ctx: ContextoCliente) -> dict[str, Any]:
    """Saldo atual + fluxo líquido médio da mesma janela de dias nos 3 meses anteriores.

    O pagamento da própria fatura fica fora do fluxo (é justamente a decisão em jogo).
    """
    inicio, fim = ctx.data_ref, ctx.proximo_vencimento
    entradas: list[float] = []
    saidas: list[float] = []
    for k in range(1, JANELA_FLUXO_MESES + 1):
        ini_k = _mes_antes(inicio, k)
        fim_k = _mes_antes(fim, k)
        janela = [t for t in ctx.transacoes if ini_k < t.data <= fim_k and t.micro != MICRO_FATURA]
        entradas.append(sum(t.vlr for t in janela if t.tipo == "E"))
        saidas.append(sum(t.vlr for t in janela if t.tipo == "S"))
    ent, sai = statistics.fmean(entradas), statistics.fmean(saidas)
    return {
        "saldo_atual": _brl(ctx.saldo_atual),
        "entradas_previstas": _brl(ent),
        "saidas_previstas": _brl(sai),
        "saldo_projetado_no_vencimento": _brl(ctx.saldo_atual + ent - sai),
        "periodo": [inicio.isoformat(), fim.isoformat()],
        "base": f"média dos mesmos dias nos {JANELA_FLUXO_MESES} meses anteriores, sem o pagamento da fatura",
    }


def simular_custo_rolagem(
    valor_fatura: float, valor_pago: float, taxa_am: float = TAXA_ROTATIVO_AM, dias: int = 30
) -> dict[str, Any]:
    """Custo de pagar só parte da fatura e levar o resto no rotativo por `dias`."""
    rolado = max(valor_fatura - valor_pago, 0.0)
    juros = rolado * ((1 + taxa_am) ** (dias / 30) - 1)
    iof = _iof(rolado, dias)
    return {
        "valor_fatura": _brl(valor_fatura),
        "valor_pago": _brl(valor_pago),
        "valor_rolado": _brl(rolado),
        "juros": _brl(juros),
        "iof": _brl(iof),
        "custo_total": _brl(juros + iof),
        "custo_pct_do_rolado": round(100 * (juros + iof) / rolado, 2) if rolado else 0.0,
        "premissas": f"rotativo {taxa_am:.0%} a.m. por {dias} dias + IOF",
    }


def simular_pagamento_com_negativo(
    valor_fatura: float,
    saldo_projetado: float,
    dias_ate_renda: int,
    taxa_am: float = TAXA_CHEQUE_ESPECIAL_AM,
) -> dict[str, Any]:
    """Custo de pagar a fatura inteira mesmo que a conta fique negativa até a próxima renda."""
    saldo_depois = saldo_projetado - valor_fatura
    negativo = max(-saldo_depois, 0.0)
    dias = max(dias_ate_renda, 0)
    juros = negativo * ((1 + taxa_am) ** (dias / 30) - 1)
    iof = _iof(negativo, dias) if negativo else 0.0
    return {
        "valor_fatura": _brl(valor_fatura),
        "saldo_depois_de_pagar": _brl(saldo_depois),
        "valor_no_negativo": _brl(negativo),
        "dias_no_negativo": dias if negativo else 0,
        "juros": _brl(juros),
        "iof": _brl(iof),
        "custo_total": _brl(juros + iof),
        "custo_pct_do_negativo": round(100 * (juros + iof) / negativo, 2) if negativo else 0.0,
        "premissas": f"cheque especial {taxa_am:.0%} a.m. (teto legal) pro rata + IOF",
    }


def projetar_essenciais_ate_renda(ctx: ContextoCliente) -> dict[str, Any]:
    """Gastos essenciais esperados entre o vencimento e a próxima renda (média dos 3 meses anteriores)."""
    inicio, fim = ctx.proximo_vencimento, ctx.proxima_renda
    totais = []
    for k in range(1, JANELA_FLUXO_MESES + 1):
        ini_k, fim_k = _mes_antes(inicio, k), _mes_antes(fim, k)
        totais.append(
            sum(t.vlr for t in ctx.transacoes if ini_k <= t.data < fim_k and t.tipo == "S" and t.macro in CATEGORIAS_ESSENCIAIS)
        )
    return {
        "essenciais_ate_renda": _brl(statistics.fmean(totais)),
        "periodo": [inicio.isoformat(), fim.isoformat()],
        "categorias": sorted(CATEGORIAS_ESSENCIAIS),
    }


def comparar_opcoes(
    ctx: ContextoCliente,
    valor_fatura: float | None = None,
    saldo_atual_informado: float | None = None,
    reserva_desejada: float = 0.0,
) -> dict[str, Any]:
    """Compara integral × parcial viável × mínimo respeitando as restrições confirmadas.

    Restrição: depois de pagar, o caixa precisa cobrir os essenciais até a próxima renda + a
    reserva que o cliente quer manter. Opção que fura a restrição é marcada `atende_restricoes=False`;
    se nenhuma atende, o status é "insuficiente" e o déficit é informado.
    Dados informados pelo cliente (fatura, saldo, reserva) substituem os estimados.
    """
    fatura = prever_fatura(ctx)
    informada = valor_fatura is not None
    if valor_fatura is None:
        if not fatura["pronta"]:
            return {"erro": "fatura_desconhecida", **fatura}
        valor_fatura = float(fatura["valor_estimado"])
    saldo = projetar_saldo_ate_vencimento(ctx)
    caixa = float(saldo["saldo_projetado_no_vencimento"])
    if saldo_atual_informado is not None:
        caixa += saldo_atual_informado - ctx.saldo_atual
    essenciais = float(projetar_essenciais_ate_renda(ctx)["essenciais_ate_renda"])
    disponivel = caixa - essenciais - reserva_desejada
    dias_renda = (ctx.proxima_renda - ctx.proximo_vencimento).days
    valor_minimo = 0.15 * valor_fatura

    integral = simular_pagamento_com_negativo(valor_fatura, caixa, dias_renda)
    integral["atende_restricoes"] = disponivel >= valor_fatura
    pago_viavel = min(max(disponivel, valor_minimo), valor_fatura)
    parcial = simular_custo_rolagem(valor_fatura, pago_viavel)
    parcial["atende_restricoes"] = disponivel >= valor_minimo
    minimo = simular_custo_rolagem(valor_fatura, valor_minimo)
    minimo["atende_restricoes"] = disponivel >= valor_minimo
    opcoes = {"integral": integral, "parcial_viavel": parcial, "minimo": minimo}

    viaveis = {k: v["custo_total"] for k, v in opcoes.items() if v["atende_restricoes"]}
    base = {
        "valor_fatura": _brl(valor_fatura),
        "fonte_fatura": "informada pelo cliente" if informada else fatura["base"],
        "saldo_projetado_no_vencimento": _brl(caixa),
        "essenciais_ate_renda": _brl(essenciais),
        "reserva_desejada": _brl(reserva_desejada),
        "disponivel_para_fatura": _brl(disponivel),
        "proxima_renda": ctx.proxima_renda.isoformat(),
        "opcoes": opcoes,
    }
    if not viaveis:
        return {
            **base,
            "status": "insuficiente",
            "deficit_para_o_minimo": _brl(valor_minimo - disponivel),
            "proximos_passos": [
                "confirmar se algum essencial pode ser adiado",
                "rever a reserva desejada",
                "procurar o banco para negociar parcelamento da fatura",
            ],
        }
    recomendada = min(viaveis, key=lambda k: viaveis[k])
    return {
        **base,
        "status": "ok",
        "recomendada": recomendada,
        "economia_vs_minimo": _brl(minimo["custo_total"] - viaveis[recomendada]),
    }


def avaliar_gatilho(ctx: ContextoCliente) -> dict[str, Any]:
    """Regra do scheduler: fatura pronta + saldo projetado >= fatura + >=2 dos 3 últimos não integrais."""
    fatura = prever_fatura(ctx)
    saldo = projetar_saldo_ate_vencimento(ctx)
    pronta = bool(fatura["pronta"])
    cobre = pronta and saldo["saldo_projetado_no_vencimento"] >= fatura["valor_estimado"]
    habito = ctx.meses_nao_integrais_ult3 >= 2
    dias_para_venc = (ctx.proximo_vencimento - ctx.data_ref).days
    return {
        "dispara": pronta and cobre and habito,
        "criterios": {
            "fatura_estimada_pronta": pronta,
            "saldo_projetado_cobre_fatura": cobre,
            "dois_ou_mais_nao_integrais_ult3": habito,
        },
        "dias_para_vencimento": dias_para_venc,
        "valor_fatura_estimada": fatura.get("valor_estimado"),
        "saldo_projetado_no_vencimento": saldo["saldo_projetado_no_vencimento"],
    }


def _mes_antes(d: date, k: int) -> date:
    return somar_meses(d, -k, d.day)
