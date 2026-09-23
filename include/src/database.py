"""Acceso a la base fuente (`source-db`) a través de la Airflow Connection.

Es el único módulo que habla con la base. El pipeline no conoce host, usuario
ni contraseña: pide un `PostgresHook` para el conn_id `soccer_source_db` y
Airflow resuelve la conexión desde la variable de entorno
`AIRFLOW_CONN_SOCCER_SOURCE_DB` (ver README).

Las consultas viven en `include/sql/` y se leen de ahí; acá no hay SQL de
negocio escrito como string.
"""

from __future__ import annotations

import logging
from contextlib import closing
from dataclasses import dataclass
from typing import Any, Protocol

from include.config import SOURCE_DB_CONN_ID, SQL_DIR

logger = logging.getLogger(__name__)


class DBAPIConnection(Protocol):
    def cursor(self) -> Any: ...


@dataclass(frozen=True)
class QueryResult:
    """Lo que devolvió una consulta, sin tocar: nombres de columna y filas."""

    columns: list[str]
    rows: list[tuple]

    def __len__(self) -> int:
        return len(self.rows)


def get_source_hook():
    """Hook de Airflow a la base fuente, resuelto desde la Connection."""
    # Import perezoso: el provider solo existe dentro de la imagen de Airflow,
    # y así los módulos de transformación se pueden testear sin Airflow.
    from airflow.providers.postgres.hooks.postgres import PostgresHook

    return PostgresHook(postgres_conn_id=SOURCE_DB_CONN_ID)


def read_sql(filename: str) -> str:
    path = SQL_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"No existe la consulta {path}")
    return path.read_text(encoding="utf-8")


def run_query(connection: DBAPIConnection, sql: str) -> QueryResult:
    """Ejecuta `sql` sobre una conexión DB-API y devuelve el resultado crudo.

    Se usa el cursor directamente (y no `pandas.read_sql`) para no depender de
    la combinación de versiones pandas/SQLAlchemy de la imagen, y para que
    Bronze reciba exactamente los valores que entregó el driver.
    """
    with closing(connection.cursor()) as cursor:
        cursor.execute(sql)
        columns = [description[0] for description in cursor.description]
        rows = [tuple(row) for row in cursor.fetchall()]
    return QueryResult(columns=columns, rows=rows)


def fetch_from_source(sql_file: str) -> QueryResult:
    """Corre una consulta de `include/sql/` contra source-db."""
    sql = read_sql(sql_file)
    hook = get_source_hook()
    with closing(hook.get_conn()) as connection:
        result = run_query(connection, sql)
    logger.info("%s -> %d filas x %d columnas", sql_file, len(result), len(result.columns))
    return result


def fetch_source_fingerprint() -> list[dict]:
    """Filas, fecha máxima y hash de contenido de cada tabla fuente."""
    result = fetch_from_source("source_fingerprint.sql")
    return [dict(zip(result.columns, row)) for row in result.rows]
