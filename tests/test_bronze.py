"""Bronze no modifica lo que devuelve SQL: mismas columnas, mismo orden,
mismos valores, mismos nulos y mismos tipos."""

from __future__ import annotations

import sqlite3
from datetime import datetime

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from include.src.database import QueryResult, run_query
from include.src.extract import query_result_to_arrow
from include.src.storage import write_arrow_table


@pytest.fixture
def sql_source():
    """Una base DB-API real (SQLite en memoria) con los casos incómodos:
    enteros con nulos, decimales, texto con comas y comillas."""
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE match (match_api_id INTEGER, season TEXT, home_player_1 INTEGER, b365h REAL)")
    con.executemany(
        "INSERT INTO match VALUES (?, ?, ?, ?)",
        [(10, "2008/2009", 501, 1.57), (11, "2008/2009", None, None), (12, 'texto, con "comillas"', 503, 2.1)],
    )
    yield con
    con.close()


def _roundtrip(result: QueryResult, tmp_path) -> pa.Table:
    meta = write_arrow_table(query_result_to_arrow(result), tmp_path / "bronze.parquet")
    assert meta["rows"] == len(result)
    return pq.read_table(tmp_path / "bronze.parquet")


def test_bronze_keeps_exactly_the_rows_returned_by_sql(sql_source, tmp_path):
    result = run_query(sql_source, "SELECT match_api_id, season, home_player_1, b365h FROM match ORDER BY match_api_id")

    table = _roundtrip(result, tmp_path)

    assert table.column_names == result.columns
    assert [tuple(row.values()) for row in table.to_pylist()] == result.rows


def test_bronze_keeps_integer_columns_with_nulls_as_integers(sql_source, tmp_path):
    result = run_query(sql_source, "SELECT match_api_id, home_player_1 FROM match")

    table = _roundtrip(result, tmp_path)

    # pandas los convertiría a float (501.0); Bronze los deja como enteros.
    assert table.schema.field("home_player_1").type == pa.int64()
    assert table.column("home_player_1").null_count == 1


def test_bronze_keeps_timestamps_from_the_driver(tmp_path):
    rows = [(1, datetime(2008, 8, 17)), (2, None)]
    table = _roundtrip(QueryResult(columns=["match_api_id", "date"], rows=rows), tmp_path)

    assert pa.types.is_timestamp(table.schema.field("date").type)
    assert [tuple(r.values()) for r in table.to_pylist()] == rows


def test_empty_query_result_is_an_error():
    with pytest.raises(ValueError, match="no devolvió filas"):
        query_result_to_arrow(QueryResult(columns=["match_api_id"], rows=[]))


def test_extraction_queries_select_explicit_columns_only():
    """Las consultas de Bronze no usan SELECT * y no traen las columnas de
    eventos del partido (post-partido)."""
    from include.config import BRONZE_QUERIES
    from include.src.database import read_sql

    post_match_events = ("goal", "shoton", "shotoff", "foulcommit", "card", "cross", "corner", "possession")
    for sql_file in BRONZE_QUERIES.values():
        sql = read_sql(sql_file).lower()
        body = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
        assert "select *" not in body and ".*" not in body, sql_file
        for column in post_match_events:
            assert f"m.{column}," not in body and f"m.{column}\n" not in body, (sql_file, column)
