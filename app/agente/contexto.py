"""Único ponto de atualização dos fatos confirmados de uma sessão.

Os especialistas recebem cópias desses fatos. Resultados e escolhas antigos não
atravessam uma mudança de versão.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import asdict
from datetime import date
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from app.agente.extracao import Extracao, referencia_nominal_despesa
from app.features import ContextoCliente


def referencia(ctx: ContextoCliente) -> str:
    # O resumo omite transações que também determinam as projeções.
    dados = json.dumps(asdict(ctx), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(dados.encode()).hexdigest()


def _nome_despesa(nome: str | None) -> str | None:
    nome = " ".join((nome or "").casefold().split())
    return nome if nome and nome != "despesa informada" else None


def _incompletas(estado: dict[str, Any], ctx: ContextoCliente) -> list[dict[str, Any]]:
    return [d for d in estado.get("despesas", []) if d.get("adicional") is not False and
            (d.get("data") is None or d.get("adicional") is None or date.fromisoformat(d["data"]) < ctx.data_ref)]


def pode_contextualizar_despesa(estado: dict[str, Any], ctx: ContextoCliente) -> bool:
    """Uma resposta curta só recebe alvo implícito se houver um único compromisso."""
    alvos = {k for k in estado.get("perguntas_abertas", {}) if k == "despesas" or k.startswith("despesas:")}
    for indice, d in enumerate(_incompletas(estado, ctx)):
        nome = _nome_despesa(d.get("descricao"))
        alvos.add(f"despesas:{nome}" if nome else f"item:{d.get('id', indice)}")
    if not alvos and estado.get("campo_pergunta_aberta") == "despesas":
        alvos.add("despesas")
    return len(alvos) == 1


_CAMPOS_PERGUNTA = {
    "valor_fatura": r"\bfatura\b",
    "saldo_atual": r"\bsaldo\b",
    "reserva_desejada": r"\breserva\b",
    "essenciais_informados": r"\bessenciais\b",
    "proxima_renda": r"\brenda\b|\bsal[aá]rio\b",
    "despesas": r"\bdespesa\b|\bgasto\b|\bcompromisso\b",
}
_ORIENTACAO_SEM_CAMPO = "Para esclarecer, diga 'A pendência é sobre meu saldo', por exemplo, e informe o dado completo."
_ROTULOS_CAMPO = {"valor_fatura": "fatura", "saldo_atual": "saldo", "reserva_desejada": "reserva", "essenciais_informados": "essenciais", "proxima_renda": "próxima renda", "despesas": "despesa"}


def _campos_da_pergunta(pergunta: str) -> list[str]:
    return [campo for campo, padrao in _CAMPOS_PERGUNTA.items() if re.search(padrao, pergunta, re.IGNORECASE)]


def _campo_da_pergunta(pergunta: str) -> str | None:
    campos = _campos_da_pergunta(pergunta)
    return campos[0] if len(campos) == 1 else None


def _pergunta_do_campo(campo: str) -> str:
    return f"Confirme o dado de {_ROTULOS_CAMPO[campo]} com o valor ou a data completa."


def _pergunta_coberta_pelo_item(e: Extracao) -> bool:
    """Não duplicar pedido explícito de data/adicional já ausente no próprio item."""
    if e.campo_esclarecimento != "despesas" or len(e.despesas) != 1 or not e.esclarecimento:
        return False
    pergunta = " ".join(e.esclarecimento.casefold().split())
    # Complementos ou perguntas extras não comprovam que se trata do mesmo item.
    data = bool(re.fullmatch(r"(?:em qual data|quando) vence (?:essa|esta) despesa[?.]?", pergunta))
    adicional = bool(re.fullmatch(r"(?:essa|esta) despesa [ée] (?:adicional|extra)(?: aos gastos já considerados)?[?.]?", pergunta))
    item = e.despesas[0]
    nome_pergunta = _nome_despesa(e.referencia_despesa or referencia_nominal_despesa(pergunta))
    if nome_pergunta and nome_pergunta != _nome_despesa(item.descricao):
        return False
    return (data or adicional) and (not data or item.data is None) and (not adicional or item.adicional is None)


def atualizar_fatos(estado: dict[str, Any], e: Extracao, ctx: ContextoCliente, *, mensagem: str | None = None) -> dict[str, Any]:
    """Atualiza fatos e classifica as pendências sem executar cálculos.

    ``pendencias`` preserva a saída legada. O roteamento usa somente
    ``pendencias_impeditivas``; ``pendencias_novas`` não libera bloqueios antigos.
    Perguntas financeiras ficam abertas por campo até serem esclarecidas.
    """
    dados = dict(estado.get("dados") or {})
    despesas = deepcopy(estado.get("despesas") or [])
    origens = dict(estado.get("origens") or {})
    for campo in ("valor_fatura", "saldo_atual", "reserva_desejada", "essenciais_informados", "proxima_renda", "objetivo"):
        valor = getattr(e, campo)
        if valor is not None:
            dados[campo] = valor.isoformat() if isinstance(valor, date) else valor
            origens[campo] = "informado_pelo_cliente"

    incompletas = _incompletas({"despesas": despesas}, ctx)
    nome_referido = _nome_despesa(e.referencia_despesa)
    candidatas_resposta = [d for d in incompletas if _nome_despesa(d.get("descricao")) == nome_referido] if nome_referido else incompletas
    respondeu_item = False
    if len(candidatas_resposta) == 1 and not e.despesas and (nome_referido or pode_contextualizar_despesa(estado, ctx)):
        despesa = candidatas_resposta[0]
        if e.data_despesa_pendente is not None:
            despesa["data"] = e.data_despesa_pendente.isoformat()
            respondeu_item = True
        if e.adicional_pendente is not None:
            despesa["adicional"] = e.adicional_pendente
            respondeu_item = True

    for nova in e.despesas:
        item = nova.model_dump(mode="json")
        if nome_referido and len(e.despesas) == 1 and _nome_despesa(item["descricao"]) is None:
            item["descricao"] = nome_referido
        candidatas = [d for d in incompletas if _nome_despesa(d["descricao"]) == _nome_despesa(item["descricao"]) and d["valor"] == item["valor"]]
        if len(candidatas) == 1:
            for campo in ("data", "adicional"):
                if item[campo] is not None:
                    candidatas[0][campo] = item[campo]
            continue
        # Repetir o mesmo fato completo não adiciona o gasto pela segunda vez.
        iguais = [d for d in despesas if _nome_despesa(d["descricao"]) == _nome_despesa(item["descricao"]) and all(d.get(k) == item[k] for k in ("valor", "data"))]
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
        nome = _nome_despesa(d.get("descricao"))
        inicio = f"Sobre a despesa {nome}: " if nome else ""
        if d.get("adicional") is None:
            pendencias.append(inicio + "Essa despesa é adicional aos gastos já considerados? Responda, por exemplo, 'sim, é adicional'.")
        if d.get("data") is None:
            pendencias.append(inicio + "Em qual data essa despesa vence? Informe dia, mês e ano, por exemplo 20/12/2025.")
        elif date.fromisoformat(d["data"]) < ctx.data_ref:
            pendencias.append(inicio + "A despesa informada é anterior à data da simulação. Informe o compromisso futuro correto.")
    # Uma nova ambiguidade não pode apagar outra ainda não resolvida. Os campos
    # singulares continuam compatíveis com checkpoints e respostas curtas antigos.
    perguntas = dict(estado.get("perguntas_abertas") or {})
    if estado.get("pergunta_aberta"):
        chave = estado.get("campo_pergunta_aberta") or "__sem_campo__"
        if chave == "despesas" and estado.get("referencia_pergunta_aberta"):
            chave = f"despesas:{_nome_despesa(estado['referencia_pergunta_aberta'])}"
        perguntas.setdefault(chave, estado["pergunta_aberta"])
    if "__sem_campo__" in perguntas:
        pergunta = perguntas["__sem_campo__"].replace(_ORIENTACAO_SEM_CAMPO, "").strip()
        campos = _campos_da_pergunta(pergunta)
        campo = campos[0] if len(campos) == 1 else None
        if len(campos) > 1:
            perguntas.pop("__sem_campo__")
            for conhecido in campos:
                perguntas.setdefault(conhecido, _pergunta_do_campo(conhecido))
        if campo is None and mensagem and re.search(r"\b(?:pend[eê]ncia|pergunta|esclarecimento)\s+(?:[ée]|era|se refere)\s+(?:sobre|ao?|à)\b", mensagem, re.IGNORECASE):
            campo = _campo_da_pergunta(mensagem) if not campos else None
            if campo:
                pergunta = _pergunta_do_campo(campo)
        if campo:
            perguntas.pop("__sem_campo__")
            chave = f"despesas:{nome_referido}" if campo == "despesas" and nome_referido else campo
            perguntas.setdefault(chave, pergunta)
        elif len(campos) <= 1:
            perguntas["__sem_campo__"] = f"{pergunta} {_ORIENTACAO_SEM_CAMPO}"
    referencias_recebidas = {_nome_despesa(d.descricao) or (nome_referido if len(e.despesas) == 1 else None) for d in e.despesas}
    nova_despesa = bool(mensagem and re.search(r"\b(?:nov[oa]|outr[oa])\b", mensagem, re.IGNORECASE))
    resposta_explicita = bool(mensagem and (mensagem.lstrip().lower().startswith("r$") or re.search(r"\b(?:essa|esta) despesa\b", mensagem, re.IGNORECASE)))
    perguntas_despesa = [k for k in perguntas if k == "despesas" or k.startswith("despesas:")]
    for campo in list(perguntas):
        if campo.startswith("despesas:"):
            alvo = campo.split(":", 1)[1]
            resolvido = (bool(e.despesas) and alvo in referencias_recebidas) or (respondeu_item and alvo == _nome_despesa(candidatas_resposta[0].get("descricao")))
        elif campo == "despesas":
            resolvido = bool(e.despesas) and len(perguntas_despesa) == 1 and not nova_despesa and (not any(referencias_recebidas) or resposta_explicita)
        else:
            resolvido = getattr(e, campo, None) is not None
        if resolvido:
            perguntas.pop(campo)
    if e.esclarecimento and not (e.campo_esclarecimento == "despesas" and respondeu_item) and not _pergunta_coberta_pelo_item(e):
        campo = e.campo_esclarecimento or _campo_da_pergunta(e.esclarecimento)
        campos = _campos_da_pergunta(e.esclarecimento) if campo is None else [campo]
        if len(campos) > 1:
            for conhecido in campos:
                perguntas[conhecido] = _pergunta_do_campo(conhecido)
        else:
            nome_pergunta = nome_referido or _nome_despesa(referencia_nominal_despesa(e.esclarecimento.casefold()))
            chave = f"despesas:{nome_pergunta}" if campo == "despesas" and nome_pergunta else campo or "__sem_campo__"
            pergunta = f"Sobre a despesa {nome_pergunta}: {e.esclarecimento}" if campo == "despesas" and nome_pergunta else e.esclarecimento
            perguntas[chave] = f"{pergunta} {_ORIENTACAO_SEM_CAMPO}" if chave == "__sem_campo__" else pergunta
    pendencias = [*perguntas.values(), *pendencias]
    primeiro = next(iter(perguntas), None)
    pergunta_aberta = perguntas.get(primeiro)
    campo_aberto = None if primeiro == "__sem_campo__" else primeiro.split(":", 1)[0] if primeiro else None
    referencia_aberta = primeiro.split(":", 1)[1] if primeiro and primeiro.startswith("despesas:") else None
    if len(incompletas) > 1 and not e.despesas and not respondeu_item and (e.data_despesa_pendente is not None or e.adicional_pendente is not None):
        pendencias.insert(0, "Há mais de uma despesa incompleta. Repita a despesa com nome, valor, data e se ela é adicional.")

    # Todas as ambiguidades financeiras atuais impedem apresentar/confirmar uma
    # comparação. Avisos explicitamente informativos não mudam essa classificação.
    impeditivas = list(dict.fromkeys(pendencias))
    informativas = list(dict.fromkeys(estado.get("pendencias_informativas") or []))
    pendencias = list(dict.fromkeys([*impeditivas, *informativas]))
    # Este sinal serve só à observabilidade; a permanência do bloqueio independe dele.
    pendencias_novas = pendencias != (estado.get("pendencias") or [])
    ref = referencia(ctx)
    # O objetivo declarado orienta a conversa, mas não muda o cálculo nem a versão dos fatos.
    def _fatos(d: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in d.items() if k != "objetivo"}

    mudou = (
        _fatos(dados) != _fatos(estado.get("dados") or {})
        or despesas != (estado.get("despesas") or [])
        or bool(estado.get("referencia_dados") and estado["referencia_dados"] != ref)
        or pendencias_novas
        or perguntas != (estado.get("perguntas_abertas") or {})
    )
    versao = estado.get("versao_contexto", 0)
    versao = versao + 1 if mudou or not versao else versao
    escolha = {"opcao": e.opcao_escolhida, "valor": e.valor_escolhido} if e.opcao_escolhida else None
    return {
        "dados": dados, "despesas": despesas, "origens": origens,
        "pendencias": pendencias, "pendencias_novas": pendencias_novas, "pergunta_aberta": pergunta_aberta, "campo_pergunta_aberta": campo_aberto,
        "pendencias_impeditivas": impeditivas, "pendencias_informativas": informativas, "perguntas_abertas": perguntas,
        "referencia_pergunta_aberta": referencia_aberta,
        "versao_contexto": versao, "referencia_dados": ref,
        "dados_mudaram": mudou, "escolha": escolha,
        "comparacao": None if mudou else estado.get("comparacao"),
    }


def despesas_confirmadas(estado: dict[str, Any]) -> list[dict[str, Any]]:
    return deepcopy([d for d in estado.get("despesas", []) if d.get("adicional") is True and d.get("data")])
