"""Features do cliente a partir do extrato (o papel da "Feature Store" no BigQuery).

Tudo aqui é determinístico: recebe as transações de um usuário e uma data de referência
("hoje" da simulação) e devolve o contexto que as tools usam. Nada olha para o futuro:
só entram transações com data <= data_ref.
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any

MICRO_FATURA = "Pagamento de fatura"
JANELA_FLUXO_MESES = 3


def _inteiro(valor: Any) -> int:
    """Colunas opcionais do extrato: vazio, None ou "6.0" viram inteiro."""
    return int(float(valor)) if valor not in (None, "") else 0


@dataclass(frozen=True)
class Transacao:
    id_usuario: str
    data: date
    anomes: int
    tipo: str  # "E" entrada | "S" saída
    descr: str
    vlr: float
    macro: str
    micro: str
    saldo_apos: float
    ordem: int = 0  # posição original (desempate dentro do mesmo dia)
    parcela_atual: int = 0  # 0 = compra à vista
    parcela_total: int = 0

    @classmethod
    def de_linha(cls, linha: dict[str, Any], ordem: int = 0) -> Transacao:
        bruto = str(linha["anomesdia"])[:10]
        return cls(
            id_usuario=str(linha["id_usuario"]),
            data=date.fromisoformat(bruto),
            anomes=int(linha["anomes"]),
            tipo=str(linha["tipo"]),
            descr=str(linha["descr"]),
            vlr=float(linha["vlr"]),
            macro=str(linha["nom_cate_macro"]),
            micro=str(linha["nom_cate_micro"]),
            saldo_apos=float(linha["saldo_apos"]),
            ordem=ordem,
            parcela_atual=_inteiro(linha.get("parcela_atual")),
            parcela_total=_inteiro(linha.get("parcela_total")),
        )


@dataclass(frozen=True)
class PagamentoFatura:
    anomes: int
    data: date
    valor: float
    modo: str  # integral | parcial | minimo


@dataclass
class ContextoCliente:
    id_usuario: str
    data_ref: date
    dia_vencimento: int
    proximo_vencimento: date
    dia_renda: int
    proxima_renda: date
    saldo_atual: float
    renda_mensal_media: float
    persona: str
    persona_descricao: str
    meses_nao_integrais_ult3: int
    historico_faturas: list[PagamentoFatura] = field(default_factory=list)
    transacoes: list[Transacao] = field(default_factory=list, repr=False)

    def resumo(self) -> dict[str, Any]:
        """O que o agente pode ver sobre o cliente (minimização: sem descrições de compras)."""
        return {
            "id_usuario": self.id_usuario,
            "data_ref": self.data_ref.isoformat(),
            "persona": self.persona,
            "persona_descricao": self.persona_descricao,
            "saldo_atual": round(self.saldo_atual, 2),
            "renda_mensal_media": round(self.renda_mensal_media, 2),
            "dia_vencimento": self.dia_vencimento,
            "proximo_vencimento": self.proximo_vencimento.isoformat(),
            "proxima_renda": self.proxima_renda.isoformat(),
            "meses_nao_integrais_ult3": self.meses_nao_integrais_ult3,
            "historico_faturas": [
                {**asdict(p), "data": p.data.isoformat(), "valor": round(p.valor, 2)}
                for p in self.historico_faturas[-6:]
            ],
        }


PERSONAS = {
    "P1": "Paga integral: quitou todas as faturas do último ano.",
    "P2": "Oscilante: pagou parcial ou mínimo em 1 a 3 meses do último ano.",
    "P3": "Rolador frequente: pagou parcial ou mínimo em 4 a 6 meses do último ano.",
    "P4": "Rolador crônico: pagou parcial ou mínimo em 7 ou mais meses do último ano.",
}


def modo_pagamento(descr: str) -> str:
    d = descr.lower()
    if d.endswith("integral"):
        return "integral"
    if d.endswith("parcial"):
        return "parcial"
    return "minimo"


def classificar_persona(historico: list[PagamentoFatura]) -> str:
    nao_integrais = sum(p.modo != "integral" for p in historico[-12:])
    if nao_integrais == 0:
        return "P1"
    if nao_integrais <= 3:
        return "P2"
    if nao_integrais <= 6:
        return "P3"
    return "P4"


def somar_meses(d: date, meses: int, dia: int) -> date:
    ano, mes = divmod(d.month - 1 + meses, 12)
    ano += d.year
    mes += 1
    for tentativa in (dia, 30, 29, 28):
        try:
            return date(ano, mes, tentativa)
        except ValueError:
            continue
    raise ValueError(f"data inválida: {ano}-{mes}-{dia}")


def proxima_ocorrencia(data_ref: date, dia: int) -> date:
    """Próxima data (estritamente depois de data_ref) com esse dia do mês."""
    candidata = somar_meses(data_ref, 0, dia)
    return candidata if candidata > data_ref else somar_meses(data_ref, 1, dia)


def historico_faturas(transacoes: list[Transacao]) -> list[PagamentoFatura]:
    pags = [
        PagamentoFatura(t.anomes, t.data, t.vlr, modo_pagamento(t.descr))
        for t in transacoes
        if t.micro == MICRO_FATURA
    ]
    return sorted(pags, key=lambda p: p.data)


def dia_vencimento(pagamentos: list[PagamentoFatura]) -> int:
    if not pagamentos:
        return 10
    return Counter(p.data.day for p in pagamentos).most_common(1)[0][0]


def dia_renda(transacoes: list[Transacao]) -> int:
    """Dia do mês da principal fonte de renda recorrente (maior macro de entrada)."""
    entradas = [t for t in transacoes if t.tipo == "E"]
    if not entradas:
        return 5
    por_macro: Counter[str] = Counter()
    for t in entradas:
        por_macro[t.macro] += t.vlr
    principal = por_macro.most_common(1)[0][0]
    return Counter(t.data.day for t in entradas if t.macro == principal).most_common(1)[0][0]


def data_ref_padrao(transacoes: list[Transacao]) -> date:
    """D-7 do vencimento do último mês com dados: o momento em que o gatilho rodaria."""
    pags = historico_faturas(transacoes)
    ultima = max(t.data for t in transacoes)
    venc = date(ultima.year, ultima.month, dia_vencimento(pags))
    return venc - timedelta(days=7)


def montar_contexto(transacoes: list[Transacao], data_ref: date | None = None) -> ContextoCliente:
    if not transacoes:
        raise ValueError("cliente sem transações")
    data_ref = data_ref or data_ref_padrao(transacoes)
    passado = sorted((t for t in transacoes if t.data <= data_ref), key=lambda t: (t.data, t.ordem))
    if not passado:
        raise ValueError("nenhuma transação até a data de referência")

    pags = historico_faturas(passado)
    dia_venc = dia_vencimento(historico_faturas(transacoes))
    dia_rend = dia_renda(passado)

    meses = sorted({t.anomes for t in passado})
    ultimos = meses[-(JANELA_FLUXO_MESES + 1) : -1] or meses[-1:]  # meses fechados
    renda = statistics.fmean(
        sum(t.vlr for t in passado if t.tipo == "E" and t.anomes == m) for m in ultimos
    )

    persona = classificar_persona(pags)
    return ContextoCliente(
        id_usuario=passado[0].id_usuario,
        data_ref=data_ref,
        dia_vencimento=dia_venc,
        proximo_vencimento=proxima_ocorrencia(data_ref, dia_venc),
        dia_renda=dia_rend,
        proxima_renda=proxima_ocorrencia(proxima_ocorrencia(data_ref, dia_venc) - timedelta(days=1), dia_rend),
        saldo_atual=passado[-1].saldo_apos,
        renda_mensal_media=renda,
        persona=persona,
        persona_descricao=PERSONAS[persona],
        meses_nao_integrais_ult3=sum(p.modo != "integral" for p in pags[-3:]),
        historico_faturas=pags,
        transacoes=passado,
    )
