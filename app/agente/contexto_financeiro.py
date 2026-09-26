"""Adapta fatos confirmados da sessão aos cálculos, sem alterar o extrato original.

As despesas recebidas devem ter sido confirmadas como adicionais: não constam no
saldo atual, na projeção histórica nem no total de essenciais já informado.
Este módulo não confirma fatos do cliente e não executa pagamentos.
"""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import date
from typing import Any

from app import calculos
from app.features import ContextoCliente


def _numero(valor: Any, campo: str, *, negativo: bool = False) -> float:
    if isinstance(valor, bool):
        raise ValueError(f"{campo}: informe um valor monetário válido")
    try:
        numero = float(valor)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{campo}: informe um valor monetário válido") from exc
    if not math.isfinite(numero) or (not negativo and numero < 0):
        raise ValueError(f"{campo}: informe um valor monetário finito e permitido")
    return round(numero, 2)


def _data(valor: Any, campo: str) -> date:
    if isinstance(valor, date):
        # Rejeita datetime: a aplicação trabalha com dias, sem supor horários.
        if type(valor) is date:
            return valor
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor)
        except ValueError:
            pass
    raise ValueError(f"{campo}: informe a data no formato AAAA-MM-DD")


def comparar_contexto(
    ctx: ContextoCliente, dados: dict, despesas: list[dict]
) -> dict[str, Any]:
    """Compara a simulação com fatos da sessão e evidencia origem e horizonte.

    `essenciais_informados` é o total base entre o vencimento e a próxima renda;
    substitui a média histórica desse período. `despesas` são itens adicionais
    confirmados e identificados, nunca uma segunda cópia daquele total.

    O horizonte é data_ref <= data < proxima_renda. Despesas no dia do vencimento
    reduzem o caixa antes do pagamento, por cautela. Itens no dia da próxima renda
    ficam fora porque essa data encerra a janela, sem supor uma ordem intradiária.
    A primeira versão exige próxima renda estritamente posterior ao vencimento.
    """
    try:
        renda_informada = dados.get("proxima_renda") is not None
        renda = _data(dados["proxima_renda"], "proxima_renda") if renda_informada else ctx.proxima_renda
        if ctx.proximo_vencimento < ctx.data_ref or renda <= ctx.proximo_vencimento:
            return {
                "erro": "contexto_nao_suportado",
                "motivo": "Esta simulação exige vencimento a partir da data de referência e próxima renda depois do vencimento.",
            }
        campos = {}
        for campo in ("valor_fatura", "saldo_atual", "reserva_desejada", "essenciais_informados"):
            if dados.get(campo) is not None:
                campos[campo] = _numero(dados[campo], campo, negativo=campo == "saldo_atual")

        antes, depois, fora = [], [], []
        vistos: dict[str, dict] = {}
        for despesa in despesas:
            if not isinstance(despesa, dict) or not str(despesa.get("id", "")).strip():
                raise ValueError("despesa: cada item precisa de um identificador")
            identificador = str(despesa["id"])
            if despesa.get("adicional_confirmada") is False:
                raise ValueError(f"despesa {identificador}: confirme se é adicional aos valores já considerados")
            dia = _data(despesa.get("data"), f"despesa {identificador}")
            item = {
                "id": identificador,
                "descricao": str(despesa.get("descricao", "Despesa informada")),
                "valor": _numero(despesa.get("valor"), f"despesa {identificador}"),
                "data": dia.isoformat(),
            }
            if identificador in vistos:
                if item != vistos[identificador]:
                    raise ValueError(f"despesa {identificador}: há versões conflitantes do mesmo item")
                continue
            vistos[identificador] = item
            if not ctx.data_ref <= dia < renda:
                fora.append(item)
            elif dia <= ctx.proximo_vencimento:
                antes.append(item)
            else:
                depois.append(item)
    except ValueError as exc:
        return {"erro": "contexto_invalido", "motivo": str(exc)}

    # Copia só o contexto de cálculo; não reescreve o saldo nem o extrato do cliente.
    contexto_calculo = replace(ctx, proxima_renda=renda)
    total_antes = round(sum(d["valor"] for d in antes), 2)
    total_depois = round(sum(d["valor"] for d in depois), 2)
    resultado = calculos.comparar_opcoes(
        contexto_calculo,
        valor_fatura=campos.get("valor_fatura"),
        saldo_atual_informado=campos.get("saldo_atual"),
        reserva_desejada=campos.get("reserva_desejada", 0.0),
        despesas_antes_vencimento=total_antes,
        essenciais_informados=campos.get("essenciais_informados"),
        despesas_apos_vencimento=total_depois,
    )
    resultado["contexto_financeiro"] = {
        "data_ref": ctx.data_ref.isoformat(),
        "vencimento": ctx.proximo_vencimento.isoformat(),
        "proxima_renda": renda.isoformat(),
        "fonte_proxima_renda": "informada pelo cliente" if renda_informada else "inferida do histórico",
        "fonte_essenciais": "total informado pelo cliente" if "essenciais_informados" in campos else "estimativa histórica",
        "periodo_essenciais_base": [ctx.proximo_vencimento.isoformat(), renda.isoformat()],
        "essenciais_informados": campos.get("essenciais_informados"),
        "saldo_real_extrato": ctx.saldo_atual,
        "saldo_atual_informado": campos.get("saldo_atual"),
        "despesas_antes_ou_no_vencimento": antes,
        "despesas_apos_vencimento": depois,
        "despesas_fora_horizonte": fora,
        "total_adicional_antes_vencimento": total_antes,
        "total_adicional_apos_vencimento": total_depois,
        "premissas": [
            "Despesas adicionais confirmadas ainda não incluídas no saldo, no fluxo histórico ou no total de essenciais.",
            "O fluxo até o vencimento mantém a estimativa histórica; essenciais informados substituem a estimativa após o vencimento.",
            "Despesas no vencimento reduzem o caixa antes do pagamento; o dia da próxima renda está fora da janela.",
        ],
    }
    resultado["simulacao"] = True
    resultado["aviso_condicoes"] = (
        "Simulação com as condições fixas do protótipo, incluindo mínimo de 15% e taxas configuradas. "
        "Não são condições contratuais verificadas do cliente. Capacidade de caixa não é recomendação de pagamento; "
        "a opção calculada exige validação das condições reais."
    )
    return resultado
