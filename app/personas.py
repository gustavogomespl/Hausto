"""Personas do modo demonstração, cada uma ligada a um cliente real da base com história parecida.

Maria recebe INSS e costuma pagar só o que dá; Carla é CLT e rola a fatura tendo caixa;
Jonas não tem salário fixo e o mês não fecha. Sem candidato ideal, vale o mais próximo.
"""

from __future__ import annotations

import threading
from functools import lru_cache
from typing import Any

from app import calculos
from app.dados import Repositorio
from app.features import ContextoCliente, montar_contexto
from app.painel import renda_do

AMOSTRA = 200  # clientes avaliados para achar cada persona

# `renda` aqui é a da história; a API devolve a renda real do cliente escolhido.
# `meta` também é da história: a base não tem metas de poupança, então cada persona traz a sua.
PERSONAS: list[dict[str, Any]] = [
    {"id": "maria", "nome": "Dona Maria Aparecida", "iniciais": "MA", "idade": 67, "cidade": "Guarulhos (SP)",
     "frase": "Eu pago o que dá. Todo mês parece que a fatura é a mesma.", "renda": "INSS", "cor": "#8E4FBF",
     "meta": {"rotulo": "Reserva", "nome": "reserva para imprevistos", "icone": "reserva", "alvo": 1000.0, "guardado": 350.0}},
    {"id": "carla", "nome": "Carla Menezes", "iniciais": "CM", "idade": 34, "cidade": "Recife (PE)",
     "frase": "Quando o salário cai eu acho que dá pra tudo. No dia 15 já tô no vermelho.", "renda": "CLT", "cor": "#1F8A6E",
     "meta": {"rotulo": "Casa", "nome": "entrada da casa própria", "icone": "casa", "alvo": 10000.0, "guardado": 3200.0}},
    {"id": "jonas", "nome": "Jonas Ferreira", "iniciais": "JF", "idade": 31, "cidade": "Belo Horizonte (MG)",
     "frase": "Tem mês que entra bem, tem mês que não entra nada. O cartão segura as pontas.", "renda": "MEI", "cor": "#2F6FD6",
     "meta": {"rotulo": "Carro", "nome": "entrada do carro novo", "icone": "carro", "alvo": 8000.0, "guardado": 2000.0}},
]


def _afinidade(p: dict[str, Any], ctx: ContextoCliente, renda: str) -> int:
    """Quanto o cliente combina com a história da persona (maior é melhor)."""
    c = calculos.comparar_opcoes(ctx)
    pontos = 10 if renda == p["renda"] else 0
    persona = p["id"]
    if persona == "maria":
        pontos += 3 if ctx.persona in {"P3", "P4"} else 0
    elif persona == "carla":
        pontos += 3 if calculos.avaliar_gatilho(ctx)["dispara"] else 0
    else:
        pontos += 3 if c.get("status") == "insuficiente" else 0
    return pontos + (1 if c.get("status") in {"ok", "insuficiente"} else -20)


@lru_cache(maxsize=4)
def _resolver(repo: Repositorio) -> tuple[tuple[str, str], ...]:
    """(id_usuario, renda real) de cada persona, na ordem de PERSONAS. Base pequena: menos personas."""
    extratos = repo.transacoes_em_lote(repo.listar_clientes(AMOSTRA))
    candidatos = [(montar_contexto(tx), renda_do(tx)) for tx in extratos.values() if tx]
    escolhidos: list[tuple[str, str]] = []
    for p in PERSONAS:
        livres = [(ctx, renda) for ctx, renda in candidatos if ctx.id_usuario not in {uid for uid, _ in escolhidos}]
        if not livres:
            break
        ctx, renda = max(livres, key=lambda cr: (_afinidade(p, *cr), cr[0].id_usuario))
        escolhidos.append((ctx.id_usuario, renda))
    return tuple(escolhidos)


_TRAVA = threading.Lock()  # o aquecimento da API e o primeiro acesso não calculam em dobro


def resolver(repo: Repositorio) -> list[dict[str, Any]]:
    with _TRAVA:
        escolhidos = _resolver(repo)
    return [{**p, "id_usuario": uid, "renda": renda} for p, (uid, renda) in zip(PERSONAS, escolhidos)]


def meta_do_cliente(repo: Repositorio, id_usuario: str) -> dict[str, Any] | None:
    """Meta de poupança da persona ligada ao cliente, com quanto falta e o % já guardado (ou None)."""
    for p in resolver(repo):
        if p["id_usuario"] == id_usuario and (m := p.get("meta")):
            return {**m, "falta": round(m["alvo"] - m["guardado"], 2), "pct": round(m["guardado"] / m["alvo"] * 100)}
    return None
