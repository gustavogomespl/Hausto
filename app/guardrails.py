"""Guardrails locais (versão mínima). Em produção, somar o Model Armor na entrada e na saída."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

_INJECAO = re.compile(
    r"ignor[ea]\w* (as |todas as )?(suas |as )?(instru|regra)|"
    r"voc[eê] agora [eé]|a partir de agora,? voc[eê]|finja (ser|que)|aja como|prompt do sistema|system prompt|"
    r"(mostr|revel|repit)\w* (as |suas |o seu |seu )?(instru|regra|prompt)|"
    r"dados? d[eo] (outro|outra) (cliente|pessoa|cpf|conta)|"
    r"esque[cç]a (tudo|as instru)|developer mode|modo desenvolvedor|jailbreak",
    re.IGNORECASE,
)
# Dado sensível: mascarado antes do LLM, dos logs e do histórico. Cartão e CPF só com dígito verificador
# válido, para não confundir valor, telefone ou data.
_CARTAO = re.compile(r"(?<![\d.,])\d(?:[ .-]?\d){12,18}(?!\d|[.,]\d)")
_CPF = re.compile(r"(?<![\d.,])\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d|[.,]\d)")
_SEGREDO = re.compile(r"\b(senha|cvv|cvc|c[oó]digo de seguran[cç]a|token|pin)\b(\W{0,3}(?:[ée]|era)?\W{0,3})((?=[^\s.,;!?]*\d)[^\s.,;!?]{3,20})", re.IGNORECASE)
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


# Saída: o que o agente não pode dizer ao cliente. Frase negada ("não recomendo empréstimo") passa.
_SAIDA = {
    "produto": re.compile(r"\b(recomendo|sugiro|indico|contrat\w*|peg(?:ue|ar)|fa[çc]a|fazer|vale a pena)\b[^.\n]{0,40}?"
                          r"\b(empr[eé]stimo|consignado|cr[eé]dito pessoal|investi\w*|cons[oó]rcio|seguro|previd[eê]ncia|cdb|tesouro)\b",
                          re.IGNORECASE),
    "promessa": re.compile(r"\b(garant(?:o|imos|id[oa]s?)|com certeza (?:vai|vão|será|terá)|sem (?:nenhum )?risco)\b|"
                           r"cr[eé]dito[^.\n]{0,20}aprovad", re.IGNORECASE),
    "segredo": re.compile(r"\b(inform\w*|pass\w*|envi\w*|digit\w*|diga|dizer|mand\w*|confirm\w*)\b[^.\n]{0,25}?"
                          r"\b(senha|cvv|c[oó]digo de seguran[cç]a|token|n[uú]mero (?:completo )?do (?:seu )?cart[aã]o)\b",
                          re.IGNORECASE),
    # Nome de campo (custo_total) ou marcador do prompt na fala ao cliente.
    "vazamento": re.compile(r"CÁLCULO DO TURNO|\{fatos\}|prompt do sistema|minhas instru[çc][õo]es|\b[a-z]+_[a-z_]+\b"),
}
CORRECOES = {
    "produto": "Não recomende produtos financeiros (empréstimo, investimento, seguro).",
    "promessa": "Não prometa resultado, aprovação ou ausência de risco.",
    "segredo": "Nunca peça senha, código ou número do cartão.",
    "vazamento": "Não mostre nomes internos do sistema; fale em português simples.",
    "dado_sensivel": "Não repita dados sensíveis do cliente.",
}


def _negada(texto: str, inicio: int) -> bool:
    return bool(re.search(r"\b(n[ãa]o|nunca|nem|jamais)\b[^.\n]{0,25}$", texto[max(0, inicio - 40):inicio], re.IGNORECASE))


def problemas_na_resposta(texto: str) -> list[str]:
    """Códigos do que a resposta não pode ter (chaves de CORRECOES), na ordem de CORRECOES."""
    achados = {nome for nome, padrao in _SAIDA.items()
               if any(not _negada(texto, m.start()) for m in padrao.finditer(texto))}
    if mascarar(texto)[1]:
        achados.add("dado_sensivel")
    return [nome for nome in CORRECOES if nome in achados]


def _luhn(digitos: str) -> bool:
    soma = 0
    for i, d in enumerate(reversed(digitos)):
        n = int(d) * (2 if i % 2 else 1)
        soma += n - 9 if n > 9 else n
    return soma % 10 == 0


def _cpf_valido(digitos: str) -> bool:
    if len(set(digitos)) == 1:
        return False
    for tamanho in (9, 10):
        soma = sum(int(d) * (tamanho + 1 - i) for i, d in enumerate(digitos[:tamanho]))
        if (soma * 10 % 11) % 10 != int(digitos[tamanho]):
            return False
    return True


def mascarar(texto: str) -> tuple[str, bool]:
    """Troca número de cartão, CPF e senha/código por marcadores. Devolve o texto e se algo foi ocultado."""
    def cartao(m: re.Match[str]) -> str:
        return "[cartão ocultado]" if _luhn(re.sub(r"\D", "", m.group())) else m.group()

    def cpf(m: re.Match[str]) -> str:
        return "[CPF ocultado]" if _cpf_valido(re.sub(r"\D", "", m.group())) else m.group()

    novo = _SEGREDO.sub(lambda m: f"{m.group(1)}{m.group(2)}[ocultado]", _CPF.sub(cpf, _CARTAO.sub(cartao, texto)))
    return novo, novo != texto


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
