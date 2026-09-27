"""Checagens determinísticas de um roteiro (sem LLM). Também são os asserts `python` do promptfoo.

- estado: etapa, dados extraídos, recálculo, confirmação pendente, números sem fonte, trechos, decisão final
- trajetória: tools chamadas em cada turno, comparadas com o agentevals (strict/unordered/subset/superset)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # o promptfoo carrega este arquivo solto

from agentevals.trajectory.match import create_trajectory_match_evaluator  # noqa: E402


def _resultado(falhas: list[str], total: int, ok_msg: str) -> dict[str, Any]:
    score = 1.0 if total == 0 else (total - len(falhas)) / total
    return {"pass": not falhas, "score": round(score, 3), "reason": "; ".join(falhas) if falhas else ok_msg}


def avaliar_deterministico(roteiro: dict[str, Any], ex: dict[str, Any]) -> dict[str, Any]:
    falhas: list[str] = []
    total = 0
    for i, (passo, t) in enumerate(zip(roteiro["turnos"], ex["turnos"]), 1):
        e = passo.get("espera") or {}
        pre = f"turno {i}"
        checks: list[tuple[bool, str]] = []
        if t.get("erro"):
            checks.append((False, f"{pre}: erro na execução ({t['erro']})"))
        if t.get("resposta_fixa"):
            checks.append((False, f"{pre}: o agente usou a resposta fixa (LLM fora do ar ou número sem fonte duas vezes)"))
        if "etapa" in e:
            aceitas = e["etapa"] if isinstance(e["etapa"], list) else [e["etapa"]]
            checks.append((t["etapa"] in aceitas, f"{pre}: etapa '{t['etapa']}', esperada {' ou '.join(aceitas)}"))
        for campo, valor in (e.get("dados") or {}).items():
            obtido = t["dados"].get(campo)
            ok = obtido is not None and abs(float(obtido) - float(valor)) <= 0.01
            checks.append((ok, f"{pre}: dado {campo}={obtido}, esperado {valor}"))
        if "recalcula" in e:
            checks.append((t["dados_mudaram"] == e["recalcula"], f"{pre}: recalculou={t['dados_mudaram']}, esperado {e['recalcula']}"))
        if "pendente" in e:
            pendente = t["pendente_confirmacao"] is not None
            checks.append((pendente == e["pendente"], f"{pre}: aguardando confirmação={pendente}, esperado {e['pendente']}"))
        checks.append((not t["numeros_sem_fonte"], f"{pre}: números sem fonte {t['numeros_sem_fonte']}"))
        resposta = t["resposta"].lower()
        for trecho in e.get("contem") or []:
            checks.append((trecho.lower() in resposta, f"{pre}: resposta sem '{trecho}'"))
        for padrao in e.get("nao_contem") or []:
            checks.append((not re.search(re.escape(padrao.lower()), resposta), f"{pre}: resposta contém '{padrao}'"))
        total += len(checks)
        falhas += [msg for ok, msg in checks if not ok]
    final = roteiro.get("espera_final") or {}
    if "decisao_registrada" in final:
        total += 1
        registrada = bool(ex["decisoes"])
        if registrada != final["decisao_registrada"]:
            falhas.append(f"fim: decisão registrada={registrada}, esperado {final['decisao_registrada']}")
    return _resultado(falhas, total, f"{total} checagens de estado ok")


def _mensagens(mensagem: str, nomes_args: list[tuple[str, dict]], resposta: str) -> list[dict[str, Any]]:
    """Formato OpenAI que o agentevals compara: user → assistant(tool_calls) → tool... → assistant."""
    msgs: list[dict[str, Any]] = [{"role": "user", "content": mensagem}]
    if nomes_args:
        msgs.append({
            "role": "assistant",
            "content": "",
            "tool_calls": [{"function": {"name": n, "arguments": json.dumps(a)}} for n, a in nomes_args],
        })
        msgs += [{"role": "tool", "content": ""} for _ in nomes_args]
    msgs.append({"role": "assistant", "content": resposta})
    return msgs


def avaliar_trajetoria(roteiro: dict[str, Any], ex: dict[str, Any]) -> dict[str, Any]:
    falhas: list[str] = []
    total = 0
    for i, (passo, t) in enumerate(zip(roteiro["turnos"], ex["turnos"]), 1):
        esperado = (passo.get("espera") or {}).get("tools")
        if esperado is None:
            continue
        total += 1
        avaliador = create_trajectory_match_evaluator(trajectory_match_mode=esperado["modo"], tool_args_match_mode="ignore")
        chamadas = [(tool["nome"], tool["args"]) for tool in t["tools"]]
        r = avaliador(
            outputs=_mensagens(t["mensagem"], chamadas, t["resposta"]),
            reference_outputs=_mensagens(t["mensagem"], [(n, {}) for n in esperado["lista"]], ""),
        )
        if not r["score"]:
            obtidas = [n for n, _ in chamadas] or ["nenhuma"]
            falhas.append(f"turno {i}: tools {obtidas}, esperado {esperado['modo']} de {esperado['lista'] or '[] (nenhuma)'}")
    return _resultado(falhas, total, f"{total} turnos com trajetória ok" if total else "roteiro sem expectativa de tools")


# ------------------------------------------------------------------ asserts do promptfoo


def _do_contexto(context: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    roteiro = json.loads(context["vars"]["roteiro"])
    meta = (context.get("providerResponse") or {}).get("metadata") or {}
    return roteiro, meta.get("execucao")


def assert_estado(output: str, context: dict[str, Any]) -> dict[str, Any]:
    roteiro, ex = _do_contexto(context)
    if ex is None:
        return {"pass": False, "score": 0, "reason": "o provider não devolveu a execução"}
    return avaliar_deterministico(roteiro, ex)


def assert_trajetoria(output: str, context: dict[str, Any]) -> dict[str, Any]:
    roteiro, ex = _do_contexto(context)
    if ex is None:
        return {"pass": False, "score": 0, "reason": "o provider não devolveu a execução"}
    return avaliar_trajetoria(roteiro, ex)
