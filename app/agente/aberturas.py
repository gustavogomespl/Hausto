"""Primeira mensagem quando o cliente abre o chat por um aviso ou tocando num valor ✦.

O front manda só a origem ({tipo, id|campo}); o texto é montado aqui, na hora e sem LLM,
com os MESMOS números do card (a base, sem o que foi informado na conversa). Se o cliente já
informou outro valor na sessão, ele aparece como observação. O modelo entra na resposta seguinte.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app import calculos
from app.agente.texto import brl, linhas_opcoes, origem_da_fatura
from app.features import ContextoCliente

PERGUNTA_ANCORA = "Por que esse valor?"
PERGUNTAS_AVISO = {"fatura_vence": "Ver meu plano", "sem_folga": "Ver o que dá pra fazer", "imprevisto": "Simular meu imprevisto",
                   "plano": "Ver o que fazer"}
ROTULOS = {"saldo": "Saldo", "fatura": "Fatura aberta", "gasto_por_dia": "Gasto no cartão por dia",
           "juros_por_dia": "Juros por dia", "parcelas": "Parcelas deste mês"}

# Chips que abrem o mesmo fluxo de um aviso ou de um valor ✦.
ATALHOS = {
    "aconteceu um imprevisto": {"tipo": "aviso", "id": "imprevisto"},
    "minha fatura": {"tipo": "ancora", "campo": "fatura"},
    "meu saldo": {"tipo": "ancora", "campo": "saldo"},
    "conferir meu saldo": {"tipo": "ancora", "campo": "saldo"},
}


def origem_do_atalho(mensagem: str | None) -> dict[str, str] | None:
    return ATALHOS.get((mensagem or "").strip().lower().rstrip("?!."))


def pergunta(origem: dict[str, str]) -> str:
    return PERGUNTA_ANCORA if origem["tipo"] == "ancora" else PERGUNTAS_AVISO[origem["id"]]


def precisa_calculo(origem: dict[str, str]) -> bool:
    """Saldo, gasto por dia, parcelas e o pedido de imprevisto não dependem da fatura."""
    return origem.get("campo") in {"fatura", "juros_por_dia"} or origem.get("id") in {"fatura_vence", "sem_folga"}


def abrir(origem: dict[str, str], ctx: ContextoCliente, sessao: dict[str, Any] | None,
          plano_ativo: dict[str, Any] | None = None) -> dict[str, Any]:
    """Texto, chips e valor fixado no topo do chat. `sessao` é o cálculo com os dados da conversa."""
    if origem["tipo"] == "aviso" and origem["id"] == "plano":
        return _aviso_plano(ctx, plano_ativo)
    if origem["tipo"] == "aviso":
        return _aviso(origem["id"], ctx, sessao)
    return _ancora(origem["campo"], ctx, sessao)


def _nota_da_sessao(card: dict[str, Any], sessao: dict[str, Any] | None) -> list[str]:
    informada = (sessao or {}).get("valor_fatura")
    if informada is None or informada == card.get("valor_fatura"):
        return []
    return [f"Com o valor que você me informou nesta conversa, a fatura fica em {brl(informada)}."]


def _aviso(aviso: str, ctx: ContextoCliente, sessao: dict[str, Any] | None) -> dict[str, Any]:
    if aviso == "imprevisto":
        exemplo = (ctx.data_ref + timedelta(days=7)).strftime("%d/%m/%Y")
        texto = ("Aconteceu algum gasto fora do previsto? Me conta o que foi, quanto custa e quando vence.\n"
                 f"Por exemplo: \"dentista R$ 150 no dia {exemplo}, é extra\".")
        return {"resposta": texto, "sugestoes": [], "ancora": None, "campo_da_abertura": "despesas"}
    from app import visuais  # import tardio: app.visuais também usa app.agente.texto

    c = calculos.comparar_opcoes(ctx)  # os números do card do aviso
    renda = ctx.proxima_renda.strftime("%d/%m")
    if c["status"] == "insuficiente":
        linhas = [
            f"Pelas contas da simulação, até a próxima renda, em {renda}, faltam {brl(c['deficit_para_o_minimo'])} "
            f"para pagar o mínimo de {brl(c['opcoes']['minimo']['valor_pago'])} sem apertar o essencial.",
            f"Isso considera {brl(c['saldo_projetado_no_vencimento'])} na conta no vencimento e "
            f"{brl(c['essenciais_ate_renda'])} de gastos essenciais.",
            *_nota_da_sessao(c, sessao),
            "Podemos rever a reserva, algum gasto essencial ou confirmar seu saldo de hoje. Por onde quer começar?",
        ]
        return {"resposta": "\n".join(linhas), "sugestoes": ["Conferir meu saldo", "Rever a reserva", "Aconteceu um imprevisto"],
                "ancora": None, "visuais": [visuais.caixa_ate_renda(ctx, c, "minimo")]}
    linhas = [
        f"Sua fatura de {brl(c['valor_fatura'])} vence em {ctx.proximo_vencimento.strftime('%d/%m')}, {origem_da_fatura(c)}.",
        f"Depois dos gastos essenciais até a próxima renda, em {renda}, ficam {brl(c['disponivel_para_fatura'])} para a fatura.",
        *linhas_opcoes(c),
        *_nota_da_sessao(c, sessao),
        "As taxas são ilustrativas. A decisão é sua: qual caminho quer seguir?",
    ]
    return {"resposta": "\n".join(linhas), "sugestoes": ["Quero pagar tudo", "E se eu pagar o mínimo?", "Aconteceu um imprevisto"],
            "ancora": {"rotulo": ROTULOS["fatura"], "valor": c["valor_fatura"]},
            "visuais": [visuais.comparar_opcoes(c)]}  # um por mensagem; o caixa vem quando o cliente pedir


def _aviso_plano(ctx: ContextoCliente, p: dict[str, Any] | None) -> dict[str, Any]:
    from app import plano  # import tardio: app.plano também usa app.agente.texto

    if not p:
        return {"resposta": "Você não tem um plano ativo agora. Quer montar um até a próxima renda?",
                "sugestoes": ["Monta um plano pra mim"], "ancora": None, "visuais": []}
    prog = plano.progresso(p, ctx)
    fim = date.fromisoformat(p["fim"])
    restantes = (fim - ctx.data_ref).days
    linhas = [f"Em {prog['dias_decorridos']} dias do plano foram {brl(prog['gasto_real'])} no dia a dia; "
              f"o combinado era até {brl(p['limite_diario'])} por dia, {brl(prog['gasto_previsto'])} no período."]
    if restantes > 0:
        cabe = max(p["limite_diario"] * prog["dias_totais"] - prog["gasto_real"], 0) / restantes
        linhas.append(f"Para fechar no combinado até {fim.strftime('%d/%m')}, dá para gastar até {brl(cabe)} por dia "
                      f"nos próximos {restantes} dias.")
    linhas.append("Quer seguir assim ou prefere ajustar o plano?")
    return {"resposta": "\n".join(linhas), "sugestoes": ["Ajustar o plano", "Minha fatura"], "ancora": None,
            "visuais": [plano.visual(p, prog)]}


def _ancora(campo: str, ctx: ContextoCliente, sessao: dict[str, Any] | None) -> dict[str, Any]:
    from app import painel, visuais  # import tardio: os dois também usam app.agente.texto

    base = calculos.comparar_opcoes(ctx)
    com_fatura = "valor_fatura" in base

    venc = ctx.proximo_vencimento.strftime("%d/%m")
    if campo == "saldo":
        proj = calculos.projetar_saldo_ate_vencimento(ctx)
        linhas = [f"Hoje sua conta tem {brl(ctx.saldo_atual)}.",
                  f"Até o vencimento da fatura, em {venc}, a projeção é {brl(proj['saldo_projetado_no_vencimento'])}, "
                  "pela média dos mesmos dias nos últimos 3 meses.",
                  "Quer ver como fica a fatura com esse saldo?"]
        return _pronto(linhas, ["Minha fatura", "Aconteceu um imprevisto"], campo, round(ctx.saldo_atual, 2),
                       [visuais.linha_do_tempo(ctx, base)] if com_fatura else [])
    if campo == "fatura":
        c = calculos.comparar_opcoes(ctx)
        linhas = [f"Sua fatura que vence em {venc} deve ficar em {brl(c['valor_fatura'])}, {origem_da_fatura(c)}.",
                  f"Até a próxima renda, em {ctx.proxima_renda.strftime('%d/%m')}, os gastos essenciais somam "
                  f"{brl(c['essenciais_ate_renda'])}.",
                  *_nota_da_sessao(c, sessao),
                  "Quer ver quanto dá para pagar sem apertar?"]
        return _pronto(linhas, ["Quero ver as opções", "Aconteceu um imprevisto"], campo, c["valor_fatura"],
                       [visuais.caixa_ate_renda(ctx, c)])
    raio_x = painel.montar(ctx)["raio_x"]
    if campo == "gasto_por_dia" and (g := raio_x["gasto_por_dia"]):
        linhas = [f"Em {g['mes_ref']} você comprou {brl(g['total'])} no cartão.",
                  f"Dividindo pelos {g['dias']} dias do mês, dá {brl(g['valor'])} por dia.",
                  "Quer ver como isso pesa na fatura?"]
        return _pronto(linhas, ["Minha fatura"], campo, g["valor"])
    if campo == "juros_por_dia" and (j := raio_x["juros_por_dia"]):
        linhas = [f"Se você pagar só o mínimo, de {brl(j['pagando'])}, o resto vai para o rotativo.",
                  f"Em 30 dias isso custa {brl(j['custo_30_dias'])} em juros e IOF, uns {brl(j['valor'])} por dia.",
                  "As taxas são ilustrativas. Quer comparar com outro valor?"]
        return _pronto(linhas, ["E se eu pagar tudo?", "E se eu pagar metade?"], campo, j["valor"],
                       [visuais.comparar_opcoes(base)] if com_fatura else [])
    if campo == "parcelas" and (p := raio_x["parcelas"])["itens"]:
        itens = ", ".join(f"{i['descricao']} ({i['atual']} de {i['total']})" for i in p["itens"][:3])
        linhas = [f"Nesta fatura suas parcelas somam {brl(p['total_mes'])}: {itens}.",
                  "Elas já entram no valor da fatura que estou estimando."]
        return _pronto(linhas, ["Minha fatura"], campo, p["total_mes"])
    if campo == "parcelas":
        return _pronto(["Não há compras parceladas nesta fatura."], ["Minha fatura"], campo, None)
    return _pronto(["Esse valor ainda não tem dados suficientes para eu explicar."], ["Minha fatura"], campo, None)


def _pronto(linhas: list[str], sugestoes: list[str], campo: str, valor: float | None,
            visuais: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    ancora = {"rotulo": ROTULOS[campo], "valor": valor} if valor is not None else None
    return {"resposta": "\n".join(linhas), "sugestoes": sugestoes, "ancora": ancora, "visuais": visuais or []}
