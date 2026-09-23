"""Capa Bronze: el resultado de cada consulta SQL a source-db, persistido sin
transformar.

Bronze NO es el SQLite descargado: es lo que devolvió la base cuando Airflow la
consultó. Cada archivo `include/data/bronze/<tabla>.parquet` tiene exactamente
las columnas, el orden y los valores que entregó el driver (los enteros siguen
siendo enteros, los nulos siguen siendo nulos, las fechas siguen siendo
timestamps). Ninguna regla de negocio se aplica acá.
"""

from __future__ import annotations

import hashlib
import logging

import pyarrow as pa

from include.config import BRONZE_DIR, BRONZE_QUERIES
from include.src.database import QueryResult, fetch_from_source, read_sql
from include.src.storage import write_arrow_table

logger = logging.getLogger(__name__)


def query_result_to_arrow(result: QueryResult) -> pa.Table:
    """Convierte el resultado de la consulta a una tabla Arrow columna por
    columna, dejando que Arrow infiera el tipo desde los objetos Python que
    devolvió el driver. No pasa por pandas, que convertiría a float los
    enteros con nulos."""
    if not result.rows:
        raise ValueError("La consulta no devolvió filas: no hay nada para escribir en Bronze.")
    values_by_column = zip(*result.rows)
    arrays = [pa.array(list(values)) for values in values_by_column]
    return pa.Table.from_arrays(arrays, names=result.columns)


def extract_to_bronze(table_name: str) -> dict:
    """Consulta source-db con `include/sql/<consulta>.sql` y escribe Bronze.

    Devuelve metadata chica (ruta, filas, columnas, hashes) para XCom.
    """
    sql_file = BRONZE_QUERIES[table_name]
    result = fetch_from_source(sql_file)
    table = query_result_to_arrow(result)
    meta = write_arrow_table(table, BRONZE_DIR / f"{table_name}.parquet")
    meta["table"] = table_name
    meta["query"] = sql_file
    meta["query_sha256"] = hashlib.sha256(read_sql(sql_file).encode("utf-8")).hexdigest()
    logger.info("Bronze %s: %d filas x %d columnas -> %s", table_name, meta["rows"], meta["columns"], meta["path"])
    return meta
