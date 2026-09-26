"""Gera extratos inteiramente ficticios e reproduziveis, sem rede ou credenciais.

Uso: python scripts/gerar_mock_sintetico.py
Os valores servem para exercitar rotas do prototipo, nao para calibrar modelos.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


DESTINO = Path(__file__).resolve().parent.parent / "data" / "mock" / "transacoes.csv"
COLUNAS = (
    "id_usuario", "anomesdia", "anomes", "tipo", "descr", "vlr",
    "nom_cate_macro", "nom_cate_micro", "saldo_apos", "parcela_atual", "parcela_total",
)

# Todos os valores abaixo foram inventados para testes e estao em centavos.
# id, saldo inicial, renda, moradia, pagamento da fatura, mercado, combustivel.
CLIENTES = (
    ("demo-001", 420_000, 300_000, 150_000, 90_000, 40_000, 20_000),
    ("demo-002", 200_000, 230_000, 100_000, 70_000, 40_000, 20_000),
    ("demo-003", 0, 180_000, 70_000, 10_000, 80_000, 20_000),
)


def decimal_reais(centavos: int) -> str:
    sinal = "-" if centavos < 0 else ""
    inteiro, fracao = divmod(abs(centavos), 100)
    return f"{sinal}{inteiro}.{fracao:02d}"


def gerar(destino: Path = DESTINO) -> int:
    """Recria sempre o mesmo arquivo, com saldos calculados em centavos."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    quantidade = 0
    with destino.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS, lineterminator="\n")
        escritor.writeheader()
        for uid, saldo, renda, moradia, fatura, mercado, combustivel in CLIENTES:
            eventos = (
                (5, "E", "Renda mensal ficticia", renda, "Renda", "Renda mensal"),
                (12, "S", "Moradia ficticia", moradia, "Casa", "Moradia"),
                (25, "S", "Fatura ficticia parcial", fatura, "Cartao", "Pagamento de fatura"),
                (27, "S", "Mercado ficticio", mercado, "Mercado", "Compras de mercado"),
                (28, "S", "Combustivel ficticio", combustivel, "Posto de combustivel", "Combustivel"),
            )
            for mes in range(7, 13):
                for dia, tipo, descricao, valor, macro, micro in eventos:
                    saldo += valor if tipo == "E" else -valor
                    escritor.writerow({
                        "id_usuario": uid,
                        "anomesdia": f"2025-{mes:02d}-{dia:02d}",
                        "anomes": 202500 + mes,
                        "tipo": tipo,
                        "descr": descricao,
                        "vlr": decimal_reais(valor),
                        "nom_cate_macro": macro,
                        "nom_cate_micro": micro,
                        "saldo_apos": decimal_reais(saldo),
                        "parcela_atual": 0,
                        "parcela_total": 0,
                    })
                    quantidade += 1
    return quantidade


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destino", type=Path, default=DESTINO)
    args = parser.parse_args()
    quantidade = gerar(args.destino)
    print(f"{quantidade} transacoes sinteticas de {len(CLIENTES)} clientes em {args.destino}")


if __name__ == "__main__":
    main()
