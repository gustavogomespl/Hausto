"""Plano até a próxima renda: quanto pagar da fatura, quanto guardar e o limite diário do dia a dia.

O LLM propõe os números; `simular` confere contra o caixa. Só vale depois que o cliente aceita.
`progresso` compara os gastos reais do dia a dia desde a aceitação com o combinado (base dos avisos).
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from app.agente.texto import brl
from app.calculos import CATEGORIAS_CARTAO, CATEGORIAS_ESSENCIAIS
from app.features import MICRO_FATURA, ContextoCliente, Transacao

# Fora do "dia a dia": essenciais, fatura e movimentações financeiras (não são consumo).
FORA_DO_DIA_A_DIA = CATEGORIAS_ESSENCIAIS | {"Produtos financeiros", "Transferencias diversas", "Saque"}
# Onde dá para cortar: consumo que não é essencial (delivery, lazer, lojas...). Veículo ou saúde
# também ficam fora do essencial, mas não são corte do dia a dia.
CORTAVEIS = CATEGORIAS_CARTAO - CATEGORIAS_ESSENCIAIS
JANELA_NORMAL_DIAS = 90  # o "normal" do cliente: média diária dos últimos 90 dias
TOLERANCIA = 1.10  # avisa acima de 10% do previsto, para um gasto pontual não virar alarme


def do_dia_a_dia(t: Transacao) -> bool:
    return t.tipo == "S" and t.macro not in FORA_DO_DIA_A_DIA and t.micro != MICRO_FATURA


def normal_diario(ctx: ContextoCliente) -> float:
    inicio = ctx.data_ref - timedelta(days=JANELA_NORMAL_DIAS)
    total = sum(t.vlr for t in ctx.transacoes if inicio < t.data <= ctx.data_ref and do_dia_a_dia(t))
    return round(total / JANELA_NORMAL_DIAS, 2)


def onde_da_para_cortar(ctx: ContextoCliente, quantas: int = 4) -> list[dict[str, Any]]:
    """Os maiores gastos cortáveis do dia a dia, em média por mês nos últimos 90 dias."""
    inicio = ctx.data_ref - timedelta(days=JANELA_NORMAL_DIAS)
    soma: dict[str, float] = defaultdict(float)
    for t in ctx.transacoes:
        if inicio < t.data <= ctx.data_ref and do_dia_a_dia(t) and t.macro in CORTAVEIS:
            soma[t.macro] += t.vlr
    meses = JANELA_NORMAL_DIAS / 30
    return [{"categoria": k, "por_mes": round(v / meses, 2)} for k, v in sorted(soma.items(), key=lambda kv: -kv[1])[:quantas]]


def simular(ctx: ContextoCliente, c: dict[str, Any], pagamento_fatura: float, reserva: float | None = None,
            limite_diario: float | None = None) -> dict[str, Any]:
    """Confere um plano contra o caixa até a próxima renda.

    A projeção até o vencimento já inclui o gasto normal; depois dele só entram os essenciais.
    Por isso o normal dos dias após o vencimento sai da folga antes de virar limite diário.
    """
    reserva = c.get("reserva_desejada", 0.0) if reserva is None else reserva
    renda = date.fromisoformat(c.get("proxima_renda") or ctx.proxima_renda.isoformat())
    dias = max((renda - ctx.data_ref).days, 1)
    dias_depois = max((renda - ctx.proximo_vencimento).days, 0)
    normal = normal_diario(ctx)
    folga = (c["disponivel_para_fatura"] + c.get("reserva_desejada", 0.0) - reserva - pagamento_fatura
             - normal * dias_depois)
    maximo = round(normal + folga / dias, 2)
    limite = round(maximo if limite_diario is None else limite_diario, 2)
    base = {"pagamento_fatura": round(pagamento_fatura, 2), "reserva": round(reserva, 2), "limite_diario": limite,
            "limite_maximo": maximo, "normal_diario": normal, "dias": dias,
            "inicio": ctx.data_ref.isoformat(), "fim": renda.isoformat()}
    minimo = c["opcoes"]["minimo"]["valor_pago"]
    if pagamento_fatura < minimo:
        return {**base, "cabe": False, "motivo": f"O pagamento fica abaixo do mínimo de {brl(minimo)}."}
    if pagamento_fatura > c["valor_fatura"]:
        return {**base, "cabe": False, "motivo": f"O pagamento passa do valor da fatura, {brl(c['valor_fatura'])}."}
    if maximo < 0:
        return {**base, "cabe": False,
                "motivo": f"Mesmo sem gastos do dia a dia, faltam {brl(-maximo * dias)} até {renda.strftime('%d/%m')}."}
    if limite > maximo:
        return {**base, "cabe": False,
                "motivo": f"Com {brl(limite)} por dia, faltam {brl((limite - maximo) * dias)} até {renda.strftime('%d/%m')}."}
    # O que o limite escolhido deixa de gastar até a renda, somado à reserva: a regra faz a conta, não o LLM.
    # Arredonda para baixo: guardando tudo, o mesmo limite continua cabendo.
    sobra = math.floor((normal + folga / dias - limite) * dias * 100) / 100
    return {**base, "cabe": True, **({"reserva_com_sobra": round(reserva + sobra, 2)} if limite < maximo else {})}


def caixa_do_plano(ctx: ContextoCliente, c: dict[str, Any], s: dict[str, Any]) -> dict[str, Any]:
    """Divisão do dinheiro fechando com o plano (no limite máximo, sobra zero)."""
    from app import visuais  # import tardio: app.visuais também usa app.agente.texto

    dias_antes = max((ctx.proximo_vencimento - ctx.data_ref).days, 0)
    extra = round(s["limite_diario"] * s["dias"] - s["normal_diario"] * dias_antes, 2)
    return visuais.caixa_ate_renda(ctx, c, s["pagamento_fatura"], reserva=s["reserva"], dia_a_dia=extra,
                                   titulo=f"Seu dinheiro com o plano até {date.fromisoformat(s['fim']).strftime('%d/%m')}")


def progresso(p: dict[str, Any], ctx: ContextoCliente) -> dict[str, Any]:
    """Gasto real do dia a dia desde a aceitação até o "hoje" da simulação, contra o combinado."""
    inicio, fim = date.fromisoformat(p["inicio"]), date.fromisoformat(p["fim"])
    dias_totais = max((fim - inicio).days, 1)
    dias = min(max((ctx.data_ref - inicio).days, 0), dias_totais)
    real = round(sum(t.vlr for t in ctx.transacoes if inicio < t.data <= ctx.data_ref and do_dia_a_dia(t)), 2)
    previsto = round(p["limite_diario"] * dias, 2)
    acima = dias > 0 and real > previsto * TOLERANCIA
    return {"limite_diario": p["limite_diario"], "dias_decorridos": dias, "dias_totais": dias_totais,
            "gasto_real": real, "gasto_previsto": previsto, "status": "acima" if acima else "dentro"}


def visual(p: dict[str, Any], prog: dict[str, Any]) -> dict[str, Any]:
    situacao = "acima do plano" if prog["status"] == "acima" else "dentro do plano"
    return {
        "tipo": "progresso_plano",
        "titulo": f"Seu plano até {date.fromisoformat(p['fim']).strftime('%d/%m')}",
        "resumo": (f"Em {prog['dias_decorridos']} dias foram {brl(prog['gasto_real'])} no dia a dia; "
                   f"o plano previa {brl(prog['gasto_previsto'])}. Você está {situacao}."),
        "dados": prog,
    }
