"""O mapeamento da Resolução Conjunta nº 8 (docs/educacao_financeira.md) não pode citar o que não existe.

Todo roteiro de eval (`e01`, `pl03`...) e todo arquivo (`app/plano.py`) citado entre crases precisa existir,
e os artigos 2º a 4º precisam estar cobertos.
"""

import re
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
DOC = (RAIZ / "docs" / "educacao_financeira.md").read_text(encoding="utf-8")
CITADOS = re.findall(r"`([^`]+)`", DOC)


def test_roteiros_citados_existem():
    ids = {r["id"] for r in yaml.safe_load((RAIZ / "evals" / "roteiros.yaml").read_text(encoding="utf-8"))}
    citados = {c for c in CITADOS if re.fullmatch(r"[a-z]{1,2}\d{2}", c)}
    assert citados and citados <= ids, citados - ids


def test_arquivos_citados_existem():
    arquivos = [c for c in CITADOS if "/" in c and re.search(r"\.(py|md|tsx|ts|ya?ml)$", c)]
    assert arquivos and all((RAIZ / a).exists() for a in arquivos), [a for a in arquivos if not (RAIZ / a).exists()]


def test_artigos_2_a_4_estao_mapeados():
    for trecho in ("Art. 2º, § 1º, I", "Art. 2º, § 1º, II", "Art. 2º, § 1º, III", "Art. 3º, I", "Art. 3º, II",
                   "Art. 3º, III", "Art. 4º, I", "Art. 4º, II", "Art. 4º, III"):
        assert trecho in DOC, trecho
