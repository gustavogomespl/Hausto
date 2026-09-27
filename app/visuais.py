"""Visuais do chat (para onde vai o dinheiro, comparação das opções, linha do tempo).

Cada função devolve uma especificação {tipo, titulo, resumo, dados} montada SÓ a partir do cálculo
(`comparar_opcoes`/`comparar_contexto`); o front desenha no padrão do app. O LLM escolhe qual visual
mostrar pela tool `mostrar_visual`, mas nunca escreve os números dele.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.agente.texto import brl
from app.features import ContextoCliente

OPCOES = {"integral": "pagar tudo", "parcial_viavel": "pagar parte", "minimo": "pagar o mínimo"}


def _r(v: float) -> float:
    return round(v, 2)


def _dm(iso: str | date) -> str:
    d = date.fromisoformat(iso) if isinstance(iso, str) else iso
    return d.strftime("%d/%m")


def _contexto(ctx: ContextoCliente, c: dict[str, Any]) -> dict[str, Any]:
    """Saldo de hoje, despesas e renda da sessão (quando o cálculo veio de comparar_contexto)."""
    cf = c.get("contexto_financeiro") or {}
    saldo = cf.get("saldo_atual_informado")
    return {
        "saldo_hoje": _r(saldo if saldo is not None else ctx.saldo_atual),
        "despesas_antes": _r(cf.get("total_adicional_antes_vencimento") or 0.0),
        "despesas": [*cf.get("despesas_antes_ou_no_vencimento", []), *cf.get("despesas_apos_vencimento", [])],
        "renda": cf.get("proxima_renda") or c.get("proxima_renda") or ctx.proxima_renda.isoformat(),
    }


def _pagamento(c: dict[str, Any], pagamento: str | float | None) -> tuple[str, float]:
    if isinstance(pagamento, int | float) and not isinstance(pagamento, bool):
        return f"pagar {brl(pagamento)}", _r(pagamento)
    nome = pagamento or c.get("recomendada") or "minimo"
    valor = c["valor_fatura"] if nome == "integral" else c["opcoes"][nome]["valor_pago"]
    return OPCOES[nome], _r(valor)


def caixa_ate_renda(ctx: ContextoCliente, c: dict[str, Any], pagamento: str | float | None = None,
                    reserva: float | None = None, dia_a_dia: float | None = None, titulo: str | None = None) -> dict[str, Any]:
    """Etapas do dinheiro até a renda: saldo de hoje → movimento até o vencimento → fatura → essenciais → reserva → sobra/falta.

    Para um plano: `reserva` substitui a da sessão e `dia_a_dia` é o gasto do dia a dia que o plano libera
    além do normal já contado no movimento até o vencimento.
    """
    x = _contexto(ctx, c)
    rotulo, pago = _pagamento(c, pagamento)
    venc, renda = _dm(ctx.proximo_vencimento), _dm(x["renda"])
    movimento = _r(c["saldo_projetado_no_vencimento"] + x["despesas_antes"] - x["saldo_hoje"])
    reserva_sessao = c.get("reserva_desejada") or 0.0
    reserva = reserva_sessao if reserva is None else reserva
    resultado = _r(c["disponivel_para_fatura"] + reserva_sessao - reserva - pago - (dia_a_dia or 0.0))
    etapas = [
        {"rotulo": "Saldo hoje", "valor": x["saldo_hoje"], "tipo": "inicio"},
        {"rotulo": f"Entradas e saídas previstas até {venc}", "valor": movimento, "tipo": "entrada" if movimento >= 0 else "saida"},
    ]
    if x["despesas_antes"]:
        etapas.append({"rotulo": f"Despesas informadas até {venc}", "valor": -x["despesas_antes"], "tipo": "saida"})
    etapas.append({"rotulo": f"Fatura: {rotulo}", "valor": -pago, "tipo": "saida"})
    etapas.append({"rotulo": f"Essenciais até {renda}", "valor": -_r(c["essenciais_ate_renda"]), "tipo": "saida"})
    if reserva:
        etapas.append({"rotulo": "Reserva que você quer manter", "valor": -_r(reserva), "tipo": "saida"})
    if dia_a_dia is not None:
        etapas.append({"rotulo": f"Dia a dia do plano depois de {venc}", "valor": -_r(dia_a_dia),
                       "tipo": "saida" if dia_a_dia >= 0 else "entrada"})
    sobra = resultado >= 0
    etapas.append({"rotulo": f"Até {renda}", "valor": resultado, "tipo": "resultado"})
    return {
        "tipo": "caixa_ate_renda",
        "titulo": titulo or f"Para onde vai o seu dinheiro até {renda}",
        "resumo": f"Para {rotulo} ({brl(pago)}), {'sobram' if sobra else 'faltam'} {brl(abs(resultado))} até {renda}.",
        "dados": {"etapas": etapas},
    }


def comparar_opcoes(c: dict[str, Any]) -> dict[str, Any]:
    """Custo de cada forma de pagar, o que fica devendo e se cabe no caixa (destaque sem selo)."""
    op = c["opcoes"]
    linhas = []
    for nome, rotulo in (("integral", "Pagar tudo"), ("parcial_viavel", f"Pagar {brl(op['parcial_viavel']['valor_pago'])}"),
                         ("minimo", "Pagar o mínimo")):
        if nome == "parcial_viavel" and op[nome]["valor_pago"] >= c["valor_fatura"]:
            continue  # o caixa cobre tudo: o parcial é o próprio integral
        o = op[nome]
        linhas.append({
            "rotulo": rotulo,
            "pago": _r(c["valor_fatura"] if nome == "integral" else o["valor_pago"]),
            "custo": _r(o["custo_total"]),
            "divida_restante": _r(o.get("valor_no_negativo", 0.0) if nome == "integral" else o["valor_rolado"]),
            "cabe": bool(o["atende_restricoes"]),
            "destaque": nome == c.get("recomendada"),
        })
    cabem = [l["rotulo"].lower() for l in linhas if l["cabe"]]
    resumo = (f"Cabem no caixa: {', '.join(cabem)}." if cabem
              else "Nenhuma forma de pagar cabe no caixa sem apertar os essenciais.")
    return {"tipo": "comparar_opcoes", "titulo": "Quanto custa cada forma de pagar", "resumo": resumo, "dados": {"opcoes": linhas}}


def linha_do_tempo(ctx: ContextoCliente, c: dict[str, Any]) -> dict[str, Any]:
    """Hoje, despesas informadas, vencimento da fatura e próxima renda, em ordem."""
    x = _contexto(ctx, c)
    eventos = [
        {"data": ctx.data_ref.isoformat(), "rotulo": "Hoje", "valor": x["saldo_hoje"], "tipo": "hoje"},
        {"data": ctx.proximo_vencimento.isoformat(), "rotulo": "Vencimento da fatura", "valor": _r(c["valor_fatura"]), "tipo": "fatura"},
        *({"data": d["data"], "rotulo": d.get("descricao", "Despesa"), "valor": _r(d["valor"]), "tipo": "despesa"} for d in x["despesas"]),
        {"data": x["renda"], "rotulo": "Próxima renda", "valor": None, "tipo": "renda"},
    ]
    eventos.sort(key=lambda e: e["data"])
    return {
        "tipo": "linha_do_tempo",
        "titulo": "As datas até a próxima renda",
        "resumo": f"A fatura vence em {_dm(ctx.proximo_vencimento)} e a próxima renda cai em {_dm(x['renda'])}.",
        "dados": {"eventos": eventos},
    }


def montar(tipo: str, ctx: ContextoCliente, c: dict[str, Any], pagamento: str | float | None = None) -> dict[str, Any]:
    if tipo == "caixa_ate_renda":
        return caixa_ate_renda(ctx, c, pagamento)
    if tipo == "comparar_opcoes":
        return comparar_opcoes(c)
    if tipo == "linha_do_tempo":
        return linha_do_tempo(ctx, c)
    raise ValueError(f"visual desconhecido: {tipo}")
