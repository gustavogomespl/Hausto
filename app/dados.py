"""Acesso ao extrato do cliente: mock (CSV local) ou BigQuery, escolhido por FONTE_DADOS."""

from __future__ import annotations

import csv
import os
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from app.features import Transacao

CSV_MOCK = Path(__file__).resolve().parent.parent / "data" / "mock" / "transacoes.csv"

COLUNAS = (
    "id_usuario, anomesdia, anomes, tipo, descr, vlr, nom_cate_macro, nom_cate_micro, "
    "saldo_apos, parcela_atual, parcela_total"
)


class Repositorio(Protocol):
    def transacoes(self, id_usuario: str) -> list[Transacao]: ...
    def transacoes_em_lote(self, ids: list[str]) -> dict[str, list[Transacao]]: ...
    def listar_clientes(self, limite: int = 50) -> list[str]: ...


class RepositorioMock:
    def __init__(self, caminho: Path = CSV_MOCK) -> None:
        self._por_usuario: dict[str, list[Transacao]] = defaultdict(list)
        with caminho.open(newline="") as f:
            for i, linha in enumerate(csv.DictReader(f)):
                self._por_usuario[linha["id_usuario"]].append(Transacao.de_linha(linha, i))

    def transacoes(self, id_usuario: str) -> list[Transacao]:
        return list(self._por_usuario.get(id_usuario, []))

    def transacoes_em_lote(self, ids: list[str]) -> dict[str, list[Transacao]]:
        return {i: list(self._por_usuario.get(i, [])) for i in ids}

    def listar_clientes(self, limite: int = 50) -> list[str]:
        return sorted(self._por_usuario)[:limite]


class RepositorioBigQuery:
    """Lê a tabela do extrato no BigQuery (ex.: projeto.dataset.transacoes).

    O extrato de cada cliente fica em cache no processo: é histórico (não muda durante a conversa)
    e evita ~2 s de consulta a cada turno. Reiniciar a instância limpa o cache.
    """

    def __init__(self, tabela: str, projeto: str | None = None, cliente: Any = None) -> None:
        from google.cloud import bigquery  # import tardio: o modo mock não precisa da lib

        self._bq = bigquery
        self._cliente = cliente or bigquery.Client(project=projeto)
        self._tabela = tabela
        self._cache: dict[str, list[Transacao]] = {}

    def transacoes(self, id_usuario: str) -> list[Transacao]:
        return self.transacoes_em_lote([id_usuario])[id_usuario]

    def transacoes_em_lote(self, ids: list[str]) -> dict[str, list[Transacao]]:
        """Uma consulta só para todos os ids que ainda não estão no cache."""
        faltam = [i for i in dict.fromkeys(ids) if i not in self._cache]
        if faltam:
            sql = f"SELECT {COLUNAS} FROM `{self._tabela}` WHERE id_usuario IN UNNEST(@ids) ORDER BY id_usuario, anomesdia"  # noqa: S608
            config = self._bq.QueryJobConfig(query_parameters=[self._bq.ArrayQueryParameter("ids", "STRING", faltam)])
            novos: dict[str, list[Transacao]] = {i: [] for i in faltam}
            for linha in self._cliente.query(sql, job_config=config).result():
                lista = novos[linha["id_usuario"]]
                lista.append(Transacao.de_linha(dict(linha.items()), len(lista)))
            self._cache.update(novos)
        return {i: list(self._cache[i]) for i in ids}

    def listar_clientes(self, limite: int = 50) -> list[str]:
        sql = f"SELECT DISTINCT id_usuario FROM `{self._tabela}` ORDER BY id_usuario LIMIT {int(limite)}"  # noqa: S608
        return [linha["id_usuario"] for linha in self._cliente.query(sql).result()]


@lru_cache(maxsize=1)
def repositorio() -> Repositorio:
    if os.getenv("FONTE_DADOS", "mock") == "bigquery":
        return RepositorioBigQuery(os.environ["BQ_TABELA"], os.getenv("GOOGLE_CLOUD_PROJECT"))
    return RepositorioMock()
