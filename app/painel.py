"""O que as telas do app mostram (Home, Raio-X e avisos), calculado pelas mesmas regras do chat.

Nada aqui usa LLM: o número do card é o mesmo que o agente explica quando o cliente toca nele.
"""

from __future__ import annotations

import calendar
import re
from collections import defaultdict
from typing import Any

from app import calculos
from app.agente import texto
from app.features import ContextoCliente, Transacao, somar_meses

RENDAS = {"Beneficio INSS": "INSS", "Salario CLT": "CLT"}  # sem salário nem benefício: PJ (recebimentos avulsos)


def renda_do(transacoes: list[Transacao]) -> str:
    micros = {t.micro for t in transacoes if t.tipo == "E"}
    return next((renda for micro, renda in RENDAS.items() if micro in micros), "PJ")


def mes_da_fatura(ctx: ContextoCliente) -> tuple[int, int]:
    """Mês de consumo da próxima fatura (o anterior ao vencimento): o Raio-X inteiro fala dele."""
    ref = somar_meses(ctx.proximo_vencimento, -1, 1)
    return ref.year, ref.month


def nome_da_compra(descr: str) -> str:
    """"cart credito pass aerea parc 1/6" -> "Pass aerea": o app já mostra a parcela ao lado."""
    nome = re.sub(r"\s+parc\s*\d+/\d+$", "", re.sub(r"^cart(?:ao)?\s+credito\s+", "", descr.strip(), flags=re.IGNORECASE), flags=re.IGNORECASE)
    return nome[:1].upper() + nome[1:]


def _gasto_por_dia(ctx: ContextoCliente) -> dict[str, Any] | None:
    """Compras no cartão no mês de consumo da fatura, divididas pelos dias do mês."""
    ano, mes = mes_da_fatura(ctx)
    total = calculos.consumo_cartao(ctx, ano * 100 + mes)
    if total <= 0:
        return None
    dias = calendar.monthrange(ano, mes)[1]
    return {"valor": round(total / dias, 2), "dias": dias, "total": round(total, 2), "mes_ref": f"{mes:02d}/{ano}"}


def _juros_por_dia(c: dict[str, Any]) -> dict[str, Any] | None:
    """Quanto custa, por dia, pagar só o mínimo e rolar o resto por 30 dias."""
    if "opcoes" not in c:
        return None
    minimo = c["opcoes"]["minimo"]
    return {"valor": round(minimo["custo_total"] / 30, 2), "pagando": minimo["valor_pago"], "custo_30_dias": minimo["custo_total"]}


def _parcelas(ctx: ContextoCliente) -> dict[str, Any]:
    """Parcelas cobradas no mês de consumo da fatura (as que entram nela)."""
    ano, mes = mes_da_fatura(ctx)
    itens = [{"descricao": nome_da_compra(t.descr), "valor": round(t.vlr, 2), "atual": t.parcela_atual, "total": t.parcela_total}
             for t in ctx.transacoes if t.parcela_total > 0 and t.anomes == ano * 100 + mes]
    return {"total_mes": round(sum(i["valor"] for i in itens), 2), "itens": sorted(itens, key=lambda i: -i["valor"])}


def _categorias(ctx: ContextoCliente) -> list[dict[str, Any]]:
    """Compras à vista no cartão, por categoria, no mês de consumo da fatura."""
    ano, mes = mes_da_fatura(ctx)
    soma: dict[str, float] = defaultdict(float)
    for t in ctx.transacoes:
        if t.tipo == "S" and t.anomes == ano * 100 + mes and t.parcela_total == 0 and t.macro in calculos.CATEGORIAS_CARTAO:
            soma[t.macro] += t.vlr
    return [{"categoria": k, "valor": round(v, 2)} for k, v in sorted(soma.items(), key=lambda kv: -kv[1])][:7]


def montar(ctx: ContextoCliente, meta_configurada: dict[str, Any] | None = None) -> dict[str, Any]:
    c = calculos.comparar_opcoes(ctx)
    return {
        "id_usuario": ctx.id_usuario,
        "data_ref": ctx.data_ref.isoformat(),
        "perfil": ctx.persona,
        "conta": {"saldo": round(ctx.saldo_atual, 2)},
        "cartao": {
            "fatura": c.get("valor_fatura"),
            "vencimento": ctx.proximo_vencimento.isoformat(),
            "origem": texto.origem_da_fatura(c) if "fonte_fatura" in c else "o consumo do mês ainda não fechou",
            "mes_ref": calculos.prever_fatura(ctx).get("mes_ref"),
        },
        "raio_x": {
            "gasto_por_dia": _gasto_por_dia(ctx),
            "juros_por_dia": _juros_por_dia(c),
            "parcelas": _parcelas(ctx),
            "categorias": _categorias(ctx),
            "meta": _meta(ctx, meta_configurada),
            "faturas": [{"mes": f"{p.data.year}-{p.data.month:02d}", "modo": p.modo}
                        for p in ctx.historico_faturas if p.data.year == ctx.data_ref.year],
        },
    }


# ------------------------------------------------------------------ avisos

# Um imprevisto que combina com a renda do cliente, com valor proporcional a ela (≈5%, mínimo R$ 50).
IMPREVISTOS = {
    "INSS": ("O médico passou um remédio novo", "Custa {v} por mês. Veja como fica a conta da fatura."),
    "CLT": ("A geladeira quebrou", "O conserto custa {v}. Veja como fica a conta da fatura."),
    "PJ": ("O pneu do carro furou", "A troca custa {v}. Sem carro não tem trabalho. Veja como fica a conta."),
}


def valor_do_imprevisto(ctx: ContextoCliente) -> float:
    return max(50.0, float(round(ctx.renda_mensal_media * 0.05, -1)))


def _aviso_imprevisto(ctx: ContextoCliente) -> dict[str, Any]:
    titulo, frase = IMPREVISTOS[renda_do(ctx.transacoes)]
    return {"id": "imprevisto", "tela": "raiox", "rotulo": "SIMULAR IMPREVISTO", "cta": "Simular meu imprevisto",
            "titulo": titulo, "texto": frase.format(v=texto.brl(valor_do_imprevisto(ctx)))}


def _meta(ctx: ContextoCliente, configurada: dict[str, Any] | None = None) -> dict[str, Any]:
    """A meta que o cliente definiu, com o saldo como guardado. Sem meta: conta no vermelho, sair dele;
    senão, reserva de três rendas."""
    if configurada:
        guardado = round(max(ctx.saldo_atual, 0.0), 2)
        return {"tipo": "personalizada", "nome": configurada["nome"], "alvo": float(configurada["valor"]),
                "guardado": guardado, "pct": round(min(guardado / configurada["valor"], 1.0), 2)}
    if ctx.saldo_atual < 0:
        return {"tipo": "sair_do_vermelho", "falta": round(-ctx.saldo_atual, 2)}
    alvo = round(3 * ctx.renda_mensal_media, 2)
    return {"tipo": "reserva", "alvo": alvo, "guardado": round(ctx.saldo_atual, 2),
            "pct": round(min(ctx.saldo_atual / alvo, 1.0), 2) if alvo else 0.0}


def avisos(ctx: ContextoCliente, plano_ativo: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Avisos da Home e do Raio-X; o desvio do plano aceito vem primeiro."""
    from app import plano  # import tardio: app.plano também usa app.agente.texto

    c = calculos.comparar_opcoes(ctx)
    lista = []
    dias = (ctx.proximo_vencimento - ctx.data_ref).days
    if c.get("status") == "ok":
        lista.append({
            "id": "fatura_vence", "tela": "home", "rotulo": "HAUSTO", "cta": "Ver meu plano",
            "titulo": f"Sua fatura vence em {dias} {'dia' if dias == 1 else 'dias'}",
            "texto": f"Veja quanto custa cada forma de pagar os {texto.brl(c['valor_fatura'])} sem apertar o essencial.",
        })
    elif c.get("status") == "insuficiente":
        lista.append({
            "id": "sem_folga", "tela": "home", "rotulo": "HAUSTO", "cta": "Ver o que dá pra fazer",
            "titulo": "Este mês o caixa não fecha",
            "texto": f"Até a próxima renda, faltam {texto.brl(c['deficit_para_o_minimo'])} para pagar o mínimo sem apertar o essencial.",
        })
    if plano_ativo and (prog := plano.progresso(plano_ativo, ctx))["status"] == "acima":
        lista.insert(0, {
            "id": "plano", "tela": "home", "rotulo": "SEU PLANO", "cta": "Ver o que fazer",
            "titulo": "Você saiu do plano",
            "texto": f"Nos últimos {prog['dias_decorridos']} dias foram {texto.brl(prog['gasto_real'])} no dia a dia; "
                     f"o plano previa {texto.brl(prog['gasto_previsto'])}.",
        })
    return [*lista, _aviso_imprevisto(ctx)]
