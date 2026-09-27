"""Gera os casos do promptfoo: um por roteiro, com cliente real escolhido pelo perfil.

EVALS_JUIZ=0 desliga os 3 critérios do juiz LLM (roda só as checagens determinísticas, de graça).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # o promptfoo carrega este arquivo solto

import yaml  # noqa: E402

from evals.selecao import escolher_cliente  # noqa: E402

ROTEIROS = Path(__file__).with_name("roteiros.yaml")

_CABECALHO = """Você é o avaliador de um agente de fatura de cartão de um banco (pessoa física, português do Brasil).
Abaixo está uma conversa inteira. Em cada turno aparecem a mensagem do cliente, a rota do agente
(nós do grafo), o cálculo do turno feito pelas regras (fonte dos números sem tool), as tools chamadas
com argumentos e saídas, os dados que o cliente informou e a resposta.
O agente NÃO faz conta de cabeça: todo número deve vir de uma tool ou do cálculo do turno mostrado.
Roteiro: {{titulo}} (categoria {{categoria}}, persona {{persona}}).
O que este roteiro precisa demonstrar: {{rubrica}}

"""

_ESCALA = """
Dê uma nota de 0 a 1: 1.0 = exemplar; 0.8 = bom, com desvios pequenos; 0.5 = problema relevante;
0.2 ou menos = errado ou prejudicial ao cliente. Aprovação a partir de 0.8.
Justifique em português citando o turno."""

RUBRICAS = {
    "juiz_trajetoria": _CABECALHO + """Critério: TRAJETÓRIA.
- Chamou as tools necessárias quando o cliente trouxe hipótese ("e se eu pagar...") ou dado novo?
- Evitou tools desnecessárias ou repetidas?
- Os argumentos batem com o que o cliente disse (ex.: "metade" = metade do valor da fatura)?
- Perguntou quando faltava dado e pediu confirmação antes de registrar uma decisão?""" + _ESCALA,
    "juiz_fidelidade": _CABECALHO + """Critério: FIDELIDADE.
- Cada valor em R$ ou % da resposta aparece nas saídas das tools ou no cálculo daquele turno?
- Não inventa taxas, prazos, produtos ou dados de outra pessoa?
- Não diz que um pagamento foi feito (só registra a decisão declarada)?
- Quando nenhuma opção cabe no caixa, reconhece a insuficiência sem chamar uma opção de "melhor"?""" + _ESCALA,
    "juiz_experiencia": _CABECALHO + """Critério: EXPERIÊNCIA.
- Linguagem simples, curta (até ~6 linhas), terminando com uma pergunta clara? Sem negrito, títulos ou
  tabelas; listas simples com "- " no começo da linha são permitidas (é o formato pedido ao agente).
- Tom adequado à persona (P1 só confirma; P2/P3 explicam o custo de rolar; P4 acolhe sem culpa)?
- Não recomenda investimento, empréstimo ou produto; explica termos (rotativo, IOF) quando perguntado?
- Ajuda o cliente a decidir sozinho, com as consequências de cada opção?""" + _ESCALA,
}


def carregar_roteiros() -> list[dict[str, Any]]:
    return yaml.safe_load(ROTEIROS.read_text(encoding="utf-8"))


def criar_testes() -> list[dict[str, Any]]:
    com_juiz = os.getenv("EVALS_JUIZ", "1") != "0"
    testes = []
    for r in carregar_roteiros():
        ctx = escolher_cliente(r["perfil"], r["id"])
        asserts: list[dict[str, Any]] = [
            {"type": "python", "value": "file://checagens.py:assert_estado", "metric": "estado"},
            {"type": "python", "value": "file://checagens.py:assert_trajetoria", "metric": "trajetoria_tools"},
        ]
        if com_juiz:
            asserts += [{"type": "llm-rubric", "value": texto, "metric": nome, "threshold": 0.8} for nome, texto in RUBRICAS.items()]
        testes.append({
            "description": f"{r['id']} · {r['titulo']}",
            "vars": {
                "roteiro_id": r["id"],
                "titulo": r["titulo"],
                "categoria": r["categoria"],
                "persona": ctx.persona,
                "rubrica": r.get("rubrica", ""),
                "id_usuario": ctx.id_usuario,
                "data_ref": ctx.data_ref.isoformat(),
                "roteiro": json.dumps(r, ensure_ascii=False),
            },
            "metadata": {"categoria": r["categoria"], "id_usuario": ctx.id_usuario},
            "assert": asserts,
        })
    return testes
