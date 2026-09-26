"""Único ponto de atualização dos fatos confirmados de uma sessão.

Os especialistas recebem cópias desses fatos. Resultados e escolhas antigos não
atravessam uma mudança de versão.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import asdict
from datetime import date
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from app.agente.extracao import Extracao
from app.features import ContextoCliente


def referencia(ctx: ContextoCliente) -> str:
    # O resumo omite transações que também determinam as projeções.
    dados = json.dumps(asdict(ctx), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(dados.encode()).hexdigest()


def atualizar_fatos(estado: dict[str, Any], e: Extracao, ctx: ContextoCliente) -> dict[str, Any]:
    dados = dict(estado.get("dados") or {})
    despesas = deepcopy(estado.get("despesas") or [])
    origens = dict(estado.get("origens") or {})
    for campo in ("valor_fatura", "saldo_atual", "reserva_desejada", "essenciais_informados", "proxima_renda", "objetivo"):
        valor = getattr(e, campo)
        if valor is not None:
            dados[campo] = valor.isoformat() if isinstance(valor, date) else valor
            origens[campo] = "informado_pelo_cliente"

    incompletas = [d for d in despesas if d.get("adicional") is not False and
                  (d.get("data") is None or d.get("adicional") is None or date.fromisoformat(d["data"]) < ctx.data_ref)]
    if len(incompletas) == 1 and not e.despesas:
        despesa = incompletas[0]
        if e.data_despesa_pendente is not None:
            despesa["data"] = e.data_despesa_pendente.isoformat()
        if e.adicional_pendente is not None:
            despesa["adicional"] = e.adicional_pendente

    for nova in e.despesas:
        item = nova.model_dump(mode="json")
        candidatas = [d for d in incompletas if d["descricao"] == item["descricao"] and d["valor"] == item["valor"]]
        if len(candidatas) == 1:
            for campo in ("data", "adicional"):
                if item[campo] is not None:
                    candidatas[0][campo] = item[campo]
            continue
        # Repetir o mesmo fato completo não adiciona o gasto pela segunda vez.
        iguais = [d for d in despesas if all(d.get(k) == item[k] for k in ("descricao", "valor", "data"))]
        if iguais:
            if item["adicional"] is not None:
                iguais[0]["adicional"] = item["adicional"]
            continue
        chave = json.dumps(item, sort_keys=True, ensure_ascii=False)
        despesas.append({**item, "id": uuid5(NAMESPACE_URL, chave).hex, "origem": "informado_pelo_cliente"})

    pendencias = []
    for d in despesas:
        if d.get("adicional") is False:
            continue  # Já está no histórico: não somar novamente.
        if d.get("adicional") is None:
            pendencias.append("Essa despesa é adicional aos gastos já considerados? Responda, por exemplo, 'sim, é adicional'.")
        if d.get("data") is None:
            pendencias.append("Em qual data essa despesa vence? Informe dia, mês e ano, por exemplo 20/12/2025.")
        elif date.fromisoformat(d["data"]) < ctx.data_ref:
            pendencias.append("A despesa informada é anterior à data da simulação. Informe o compromisso futuro correto.")
    pergunta_aberta = estado.get("pergunta_aberta")
    campo_aberto = estado.get("campo_pergunta_aberta")
    if e.esclarecimento:
        pergunta_aberta, campo_aberto = e.esclarecimento, e.campo_esclarecimento
    elif pergunta_aberta and (
        (campo_aberto == "despesas" and e.despesas)
        or (campo_aberto and campo_aberto != "despesas" and getattr(e, campo_aberto, None) is not None)
    ):
        pergunta_aberta, campo_aberto = None, None
    if pergunta_aberta:
        pendencias.append(pergunta_aberta)
    if len(incompletas) > 1 and (e.data_despesa_pendente is not None or e.adicional_pendente is not None):
        pendencias.insert(0, "Há mais de uma despesa incompleta. Repita a despesa com valor, data e se ela é adicional.")

    ref = referencia(ctx)
    mudou = (
        dados != (estado.get("dados") or {})
        or despesas != (estado.get("despesas") or [])
        or bool(estado.get("referencia_dados") and estado["referencia_dados"] != ref)
        or pendencias != (estado.get("pendencias") or [])
    )
    versao = estado.get("versao_contexto", 0)
    versao = versao + 1 if mudou or not versao else versao
    escolha = {"opcao": e.opcao_escolhida, "valor": e.valor_escolhido} if e.opcao_escolhida else None
    return {
        "dados": dados, "despesas": despesas, "origens": origens,
        "pendencias": list(dict.fromkeys(pendencias)), "pergunta_aberta": pergunta_aberta, "campo_pergunta_aberta": campo_aberto,
        "versao_contexto": versao, "referencia_dados": ref,
        "dados_mudaram": mudou, "escolha": escolha,
        "comparacao": None if mudou else estado.get("comparacao"),
    }


def despesas_confirmadas(estado: dict[str, Any]) -> list[dict[str, Any]]:
    return deepcopy([d for d in estado.get("despesas", []) if d.get("adicional") is True and d.get("data")])
