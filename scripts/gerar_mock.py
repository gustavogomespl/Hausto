"""Extrai alguns clientes do export do BigQuery para data/mock/transacoes.csv.

Uso: uv run python scripts/gerar_mock.py <export.csv> <id_usuario> [<id_usuario> ...]
"""

import csv
import sys
from pathlib import Path

DESTINO = Path(__file__).resolve().parent.parent / "data" / "mock" / "transacoes.csv"


def main() -> None:
    origem, ids = sys.argv[1], set(sys.argv[2:])
    with open(origem, newline="") as f_in, DESTINO.open("w", newline="") as f_out:
        leitor = csv.DictReader(f_in)
        escritor = csv.DictWriter(f_out, fieldnames=leitor.fieldnames or [])
        escritor.writeheader()
        n = 0
        for linha in leitor:
            if linha["id_usuario"] in ids:
                escritor.writerow(linha)
                n += 1
    print(f"{n} transações de {len(ids)} clientes em {DESTINO}")


if __name__ == "__main__":
    main()
