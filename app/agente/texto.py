"""Textos montados só com números das tools: resposta sem LLM, resposta segura e confirmação."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.features import ContextoCliente

ROTULOS = {"integral": "pagar a fatura inteira", "parcial": "pagar parte", "minimo": "pagar o mínimo"}


def brl(v: float) -> str:
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def origem_da_fatura(c: dict[str, Any]) -> str:
    """Como o cliente entende a origem do valor; a calibração da estimativa fica fora da conversa."""
    if c["fonte_fatura"] == "informada pelo cliente":
        return "informada por você"
    mes = re.search(r"\d{2}/\d{4}", c["fonte_fatura"])
    return f"estimada pelo seu consumo de {mes.group(0)}" if mes else "estimada pelo seu consumo no cartão"


def linha_deficit(c: dict[str, Any]) -> str:
    return f"Pelas contas da simulação, faltam {brl(c['deficit_para_o_minimo'])} para pagar o mínimo sem apertar os essenciais."


def escolha_incompativel(opcao: str, valor: float, c: dict[str, Any]) -> str:
    minimo = c["opcoes"]["minimo"]["valor_pago"]
    if opcao == "parcial" and valor < minimo:
        motivo = f"{brl(valor)} fica abaixo do mínimo de {brl(minimo)}"
    else:
        falta = c["deficit_para_o_minimo"] if opcao == "minimo" and "deficit_para_o_minimo" in c else valor - c["disponivel_para_fatura"]
        motivo = f"para {ROTULOS[opcao]} ({brl(valor)}), faltam {brl(falta)} para cobrir os essenciais até a próxima renda"
    return (
        f"Pelas contas da simulação, {motivo}, então não registro essa escolha. "
        "Podemos rever a reserva, algum gasto essencial ou confirmar seu saldo de hoje. Por onde quer começar?"
    )


def linhas_opcoes(c: dict[str, Any]) -> list[str]:
    op = c["opcoes"]
    linhas = []
    for nome, rotulo in (("integral", "Pagar tudo"), ("parcial_viavel", f"Pagar {brl(op['parcial_viavel']['valor_pago'])}"), ("minimo", "Pagar o mínimo")):
        if nome == "parcial_viavel" and op[nome]["valor_pago"] >= c["valor_fatura"]:
            continue  # o caixa cobre tudo: o parcial é o próprio integral
        ok = "cabe no seu caixa" if op[nome]["atende_restricoes"] else "aperta os essenciais"
        linhas.append(f"- {rotulo}: custo de {brl(op[nome]['custo_total'])} ({ok}).")
    return linhas


SUGESTOES = {
    "explicar_opcoes": ["Quero pagar tudo", "E se eu pagar o mínimo?", "Aconteceu um imprevisto"],
    "informar_deficit": ["Conferir meu saldo", "Rever a reserva", "Aconteceu um imprevisto"],
    "escolha_incompativel": ["Conferir meu saldo", "Rever a reserva"],
    "decisao_registrada": ["Minha fatura"],
    "decisao_cancelada": ["Minha fatura", "Aconteceu um imprevisto"],
}


def resposta_padrao(ctx: ContextoCliente, c: dict[str, Any], dados_mudaram: bool = False) -> str:
    """O fluxo do diagrama em texto fixo: usada no modo simulado e como resposta segura."""
    venc = ctx.proximo_vencimento.strftime("%d/%m")
    linhas = ["Com o dado que você trouxe, refiz as contas."] if dados_mudaram else []
    linhas += [
        f"Sua fatura com vencimento em {venc} deve ficar em {brl(c['valor_fatura'])} ({origem_da_fatura(c)}).",
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
    linhas += linhas_opcoes(c)
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


def pergunta_plano(p: dict[str, Any]) -> str:
    fim = date.fromisoformat(p["fim"]).strftime("%d/%m")
    reserva = f", guardar {brl(p['reserva'])}" if p.get("reserva") else ""
    return (f"Aceita este plano até {fim}? Pagar {brl(p['pagamento_fatura'])} da fatura{reserva} e gastar até "
            f"{brl(p['limite_diario'])} por dia no dia a dia. Se aceitar, eu te aviso quando os gastos passarem do combinado. (sim/não)")


def plano_aceito(p: dict[str, Any]) -> str:
    fim = date.fromisoformat(p["fim"]).strftime("%d/%m")
    return (f"Plano ativo até {fim}. Vou acompanhar seus gastos do dia a dia e te aviso se passarem de "
            f"{brl(p['limite_diario'])} por dia. Nada foi pago: o pagamento da fatura continua com você.")


PLANO_RECUSADO = "Tudo bem, não ativei o plano. Quer ajustar algum valor?"

DECISAO_CANCELADA = "Tudo bem, não registrei nada. Quer rever as opções ou mudar algum valor?"
