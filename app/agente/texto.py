"""Textos montados só com números das tools: resposta sem LLM, resposta segura e confirmação."""

from __future__ import annotations

from typing import Any

from app.features import ContextoCliente

ROTULOS = {"integral": "pagar a fatura inteira", "parcial": "pagar parte", "minimo": "pagar o mínimo"}


def brl(v: float) -> str:
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def resposta_padrao(ctx: ContextoCliente, c: dict[str, Any], dados_mudaram: bool = False) -> str:
    """O fluxo do diagrama em texto fixo: usada no modo simulado e como resposta segura."""
    op = c["opcoes"]
    venc = ctx.proximo_vencimento.strftime("%d/%m")
    linhas = ["Com o dado que você trouxe, refiz as contas."] if dados_mudaram else []
    linhas += [
        f"Sua fatura com vencimento em {venc} deve ficar em {brl(c['valor_fatura'])} ({c['fonte_fatura']}).",
        f"No vencimento a conta deve ter {brl(c['saldo_projetado_no_vencimento'])}; "
        f"até a próxima renda, os essenciais considerados somam {brl(c['essenciais_ate_renda'])}.",
    ]
    if c['disponivel_para_fatura'] < 0:
        linhas.append("Os compromissos e a reserva já ultrapassam o caixa projetado.")
    else:
        linhas.append(f"A capacidade de caixa para a fatura é {brl(c['disponivel_para_fatura'])}.")
    linhas.append("Esta é uma simulação com taxas e mínimo ilustrativos. As condições do seu cartão precisam ser confirmadas.")
    if c["status"] == "insuficiente":
        linhas.append(f"Não dá para pagar nem o mínimo sem apertar os essenciais: faltam {brl(c['deficit_para_o_minimo'])}.")
        linhas.append("Qual informação precisamos confirmar para rever essa simulação?")
        return "\n".join(linhas)
    for nome, rotulo in (("integral", "Pagar tudo"), ("parcial_viavel", f"Pagar {brl(op['parcial_viavel']['valor_pago'])}"), ("minimo", "Pagar o mínimo")):
        if nome == "parcial_viavel" and op[nome]["valor_pago"] >= c["valor_fatura"]:
            continue  # o caixa cobre tudo: o parcial é o próprio integral
        ok = "cabe no seu caixa" if op[nome]["atende_restricoes"] else "aperta os essenciais"
        linhas.append(f"- {rotulo}: custo de {brl(op[nome]['custo_total'])} ({ok}).")
    linhas.append(
        f"Nas premissas simuladas, {c['recomendada'].replace('_', ' ')} tem o menor custo entre as opções que cabem. "
        "Qual alternativa você quer entender melhor?"
    )
    return "\n".join(linhas)


def pergunta_sem_fatura(ctx: ContextoCliente) -> str:
    venc = ctx.proximo_vencimento.strftime("%d/%m")
    return (
        f"Ainda não consigo estimar sua fatura que vence em {venc}: o consumo do mês ainda não fechou. "
        "Qual é o valor dela? Está no app do cartão."
    )


def pergunta_confirmacao(escolha: dict[str, Any]) -> str:
    texto = (
        f"Só para confirmar: você vai {ROTULOS[escolha['opcao']]}, {brl(escolha['valor'])}, "
        f"com custo simulado de {brl(escolha['custo_total'])}. As condições reais do cartão ainda precisam ser confirmadas."
    )
    if not escolha["atende_restricoes"]:
        texto += " Atenção: com esse valor, falta dinheiro para os essenciais até a próxima renda."
    return texto + " Posso registrar essa decisão? (sim/não)"


def decisao_registrada(escolha: dict[str, Any]) -> str:
    return (
        f"Pronto, registrei: {ROTULOS[escolha['opcao']]}, {brl(escolha['valor'])}. "
        "Registrei apenas sua intenção na simulação. Nenhum pagamento foi feito. Confira as condições reais antes de decidir."
    )


DECISAO_CANCELADA = "Tudo bem, não registrei nada. Quer rever as opções ou mudar algum valor?"
