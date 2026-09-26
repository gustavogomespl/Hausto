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
# pt-BR (2.173,51), ponto decimal cru do JSON (2173.51) ou inteiro/vírgula (2173 / 2173,5)
_NUMERO = re.compile(r"(?:R\$\s*)?(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+\.\d{1,2}(?!\d)|\d+(?:,\d{1,2})?)(\s*%)?")

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
        saida.add(round(abs(float(obj)), 2))
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
            for m in re.findall(r"-?\d+(?:\.\d+)?", obj):
                saida.add(round(abs(float(m)), 2))


def numeros_das_tools(saidas_tools: list[Any]) -> set[float]:
    valores: set[float] = set()
    for s in saidas_tools:
        _valores(s, valores)
    # percentuais aparecem na resposta como 14% (vindo de 0.14 nas tools)
    valores |= {round(v * 100, 2) for v in valores if v < 1}
    return valores


def numeros_sem_fonte(resposta: str, saidas_tools: list[Any]) -> list[str]:
    """Números em R$ ou % na resposta que não vieram de nenhuma tool desta conversa."""
    fontes = numeros_das_tools(saidas_tools)
    suspeitos = []
    for m in _NUMERO.finditer(resposta):
        bruto, pct = m.group(1), m.group(2)
        eh_dinheiro = m.group(0).startswith("R$")
        if not (eh_dinheiro or pct):
            continue  # datas, dias e contagens pequenas não são checados
        if re.fullmatch(r"\d+\.\d{1,2}", bruto):
            valor = float(bruto)
        else:
            valor = round(float(bruto.replace(".", "").replace(",", ".")), 2)
        if not any(abs(valor - f) <= 0.011 or (not eh_dinheiro and abs(valor - round(f)) < 0.6) for f in fontes):
            suspeitos.append(m.group(0).strip())
    return suspeitos
