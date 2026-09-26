"""Guardrails locais (versão mínima). Em produção, somar o Model Armor na entrada e na saída."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

_INJECAO = re.compile(
    r"ignor[ea]\w* (as |todas as )?(suas |as )?(instru|regra)|"
    r"voc[eê] agora [eé]|finja (ser|que)|aja como|prompt do sistema|system prompt|"
    r"esque[cç]a (tudo|as instru)|developer mode|jailbreak",
    re.IGNORECASE,
)
# pt-BR (2.173,51), ponto decimal cru do JSON (2173.51) ou inteiro/vírgula.
# O sinal pode vir antes ou depois de R$: nunca transformar dívida em sobra.
_NUMERO = re.compile(
    # Sinal colado ao valor: "- R$ 10" num item de lista não é negativo.
    r"(?P<sinal_antes>[+\-−])?(?P<moeda>R\$\s*)?"
    r"(?P<sinal_depois>[+\-−])?\s*"
    r"(?P<numero>\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+\.\d{1,2}(?!\d)|\d+(?:,\d{1,2})?)"
    r"(?P<percentual>\s*%)?"
)

RESPOSTA_INJECAO = (
    "Posso te ajudar com a sua fatura e o seu saldo. Não consigo mudar as minhas regras. "
    "Quer ver as opções de pagamento da sua próxima fatura?"
)


def parece_injecao(texto: str) -> bool:
    return bool(_INJECAO.search(unicodedata.normalize("NFKC", texto)))


def _valores(obj: Any, saida: set[float]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, int | float):
        saida.add(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _valores(v, saida)
    elif isinstance(obj, list | tuple):
        for v in obj:
            _valores(v, saida)
    elif isinstance(obj, str):
        try:
            _valores(json.loads(obj), saida)
        except (ValueError, TypeError):
            for m in _NUMERO.finditer(obj):
                if not (m.group("sinal_antes") and m.group("sinal_depois")):
                    saida.add(_valor_encontrado(m))


def _valor_encontrado(m: re.Match[str]) -> float:
    bruto = m.group("numero")
    valor = float(bruto) if re.fullmatch(r"\d+\.\d{1,2}", bruto) else float(bruto.replace(".", "").replace(",", "."))
    sinal = m.group("sinal_antes") or m.group("sinal_depois")
    return -valor if sinal in ("-", "−") else valor


def numeros_das_tools(saidas_tools: list[Any]) -> set[float]:
    """Valores com seu sinal original; conversão de taxa não gera fonte monetária."""
    valores: set[float] = set()
    for s in saidas_tools:
        _valores(s, valores)
    return valores


def numeros_sem_fonte(resposta: str, saidas_tools: list[Any]) -> list[str]:
    """Confere valor e sinal, não a associação semântica entre frase e campo.

    A revisão estruturada deve validar qual saldo, custo ou déficit cada frase
    representa. Encontrar o mesmo número em outra fonte não prova essa relação.
    """
    fontes = numeros_das_tools(saidas_tools)
    # Só percentuais podem usar 14% como apresentação de uma taxa 0.14.
    fontes_percentuais = fontes | {round(v * 100, 2) for v in fontes if abs(v) < 1}
    suspeitos = []
    for m in _NUMERO.finditer(resposta):
        pct = m.group("percentual")
        eh_dinheiro = m.group("moeda") is not None
        if not (eh_dinheiro or pct):
            continue  # datas, dias e contagens pequenas não são checados
        if m.group("sinal_antes") and m.group("sinal_depois"):
            suspeitos.append(m.group(0).strip())
            continue
        valor = _valor_encontrado(m)
        candidatas = fontes if eh_dinheiro else fontes_percentuais
        if not any(
            (valor < 0) == (f < 0)
            and (abs(valor - f) <= 0.011 or (not eh_dinheiro and abs(valor - round(f)) < 0.6))
            for f in candidatas
        ):
            suspeitos.append(m.group(0).strip())
    return suspeitos
