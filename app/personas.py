"""Personas do modo demonstração: aposentado, CLT e PJ, cada uma ligada ao cliente mais negativado do grupo.

A renda vem da categoria da entrada no extrato (INSS, salário CLT; sem nenhum dos dois, PJ: vive de
recebimentos avulsos). O cliente de cada persona foi escolhido na base inteira pelo maior valor que falta para
pagar o mínimo da fatura sem apertar o essencial (`id_preferido`). Varrer os 1.000 clientes na subida custaria
~70 s de BigQuery, então o escolhido fica fixo aqui; se ele não estiver na base (ex.: mock dos testes), vale o
cliente mais parecido e mais negativado de uma amostra.
"""

from __future__ import annotations

import threading
from functools import lru_cache
from typing import Any

from app import calculos
from app.dados import Repositorio
from app.features import ContextoCliente, montar_contexto
from app.painel import renda_do

AMOSTRA = 200  # clientes avaliados quando o escolhido não está na base

# `renda` aqui é a da história; a API devolve a renda real do cliente escolhido.
PERSONAS: list[dict[str, Any]] = [
    {"id": "maria", "nome": "Dona Maria Aparecida", "iniciais": "MA", "idade": 67, "cidade": "Guarulhos (SP)",
     "frase": "A aposentadoria cai e já vai quase toda pra fatura. Não sei mais o que cortar.", "renda": "INSS",
     "cor": "#8E4FBF", "id_preferido": "32f9a871-7ecd-4399-a664-e374a1e8953d"},
    {"id": "carla", "nome": "Carla Menezes", "iniciais": "CM", "idade": 34, "cidade": "Recife (PE)",
     "frase": "Tô no vermelho faz meses. Pago o mínimo e a fatura só cresce.", "renda": "CLT",
     "cor": "#1F8A6E", "id_preferido": "8fbc8ba3-7d20-4382-ba8d-ffd070e836a1"},
    {"id": "jonas", "nome": "Jonas Ferreira", "iniciais": "JF", "idade": 31, "cidade": "Belo Horizonte (MG)",
     "frase": "Sou PJ: tem mês que entra bem, tem mês que não entra nada. O limite da conta virou salário.", "renda": "PJ",
     "cor": "#2F6FD6", "id_preferido": "704b64f3-75e3-46cb-a2ec-3cf28f6213fe"},
]


def _negativado(ctx: ContextoCliente) -> float:
    """Quanto falta para pagar o mínimo sem apertar o essencial (0 se cabe)."""
    return float(calculos.comparar_opcoes(ctx).get("deficit_para_o_minimo") or 0.0)


def _afinidade(p: dict[str, Any], ctx: ContextoCliente, renda: str) -> tuple[int, float]:
    """Mesma renda da história, sem folga e o mais negativado (maior é melhor)."""
    c = calculos.comparar_opcoes(ctx)
    pontos = (10 if renda == p["renda"] else 0) + (3 if c.get("status") == "insuficiente" else 0)
    return pontos + (0 if c.get("status") in {"ok", "insuficiente"} else -20), _negativado(ctx)


@lru_cache(maxsize=4)
def _resolver(repo: Repositorio) -> tuple[tuple[str, str], ...]:
    """(id_usuario, renda real) de cada persona, na ordem de PERSONAS. Base pequena: menos personas."""
    extratos = repo.transacoes_em_lote(repo.listar_clientes(AMOSTRA))
    faltam = [p["id_preferido"] for p in PERSONAS if p["id_preferido"] not in extratos]
    extratos = {**extratos, **(repo.transacoes_em_lote(faltam) if faltam else {})}
    candidatos = {uid: (montar_contexto(tx), renda_do(tx)) for uid, tx in extratos.items() if tx}
    reservados = {p["id_preferido"] for p in PERSONAS if p["id_preferido"] in candidatos}  # a busca não os toma
    escolhidos: list[tuple[str, str]] = []
    for p in PERSONAS:
        usados = {uid for uid, _ in escolhidos} | (reservados - {p["id_preferido"]})
        if p["id_preferido"] in candidatos and p["id_preferido"] not in usados:
            escolhidos.append((p["id_preferido"], candidatos[p["id_preferido"]][1]))
            continue
        livres = [(ctx, renda) for uid, (ctx, renda) in candidatos.items() if uid not in usados]
        if not livres:
            break
        ctx, renda = max(livres, key=lambda cr: (_afinidade(p, *cr), cr[0].id_usuario))
        escolhidos.append((ctx.id_usuario, renda))
    return tuple(escolhidos)


_TRAVA = threading.Lock()  # o aquecimento da API e o primeiro acesso não calculam em dobro


def resolver(repo: Repositorio) -> list[dict[str, Any]]:
    with _TRAVA:
        escolhidos = _resolver(repo)
    return [{**{k: v for k, v in p.items() if k != "id_preferido"}, "id_usuario": uid, "renda": renda}
            for p, (uid, renda) in zip(PERSONAS, escolhidos)]
