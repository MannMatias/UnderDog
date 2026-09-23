"""Seed de source-db: copia la European Soccer Database (SQLite de Kaggle) a
PostgreSQL una única vez.

NO es parte del DAG. Representa el paso de infraestructura que deja "la base
que ya existe": después de correrlo, el pipeline solo consulta PostgreSQL.

    astro dev bash
    python -m include.src.source_loader             # carga lo que falte
    python -m include.src.source_loader --force     # recrea todas las tablas
    python -m include.src.source_loader --download  # si falta database.sqlite, la baja de Kaggle

La conexión es la misma Airflow Connection que usa el DAG (`soccer_source_db`):
el seed tampoco conoce credenciales.

Mapeo SQLite -> PostgreSQL:
- tablas y columnas en minúscula (Match -> match, B365H -> b365h, igual que
  hace pgloader), para no tener que citar identificadores en las consultas;
- el tipo sale del contenido real de cada columna (SQLite no lo impone): solo
  enteros -> BIGINT, con decimales -> DOUBLE PRECISION, texto -> TEXT;
- `date` y `birthday` -> TIMESTAMP;
- se conservan la PK (`id`) y las columnas UNIQUE del original. No se crean
  foreign keys: la fuente no garantiza integridad referencial.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sqlite3
import tempfile
import time
from contextlib import closing
from pathlib import Path

from include.config import KAGGLE_DATASET_SLUG, SOCCER_DB_PATH

logger = logging.getLogger(__name__)

# La base descomprimida pesa ~300 MB; si el archivo es mucho más chico está
# truncado o a medio bajar.
MIN_EXPECTED_BYTES = 250_000_000
DATE_COLUMNS = {"date", "birthday"}
NULL_MARKER = r"\N"
# Índices que tendría una base real para las consultas del pipeline.
EXTRA_INDEXES = {
    "match": ["league_id", "date"],
    "player_attributes": ["player_api_id, date"],
}


# -----------------------------------------------------------------------------
# Descarga (solo si falta el SQLite)
# -----------------------------------------------------------------------------


def download_soccer_db(force: bool = False) -> Path:
    """Descarga y descomprime `database.sqlite` desde Kaggle.

    Requiere un token de https://www.kaggle.com/settings/api en la variable de
    entorno KAGGLE_API_TOKEN (en el `.env` del proyecto si corre bajo Astro).
    """
    if not force and SOCCER_DB_PATH.exists() and SOCCER_DB_PATH.stat().st_size >= MIN_EXPECTED_BYTES:
        logger.info("Ya existe %s (%.0f MB), no descargo de nuevo.", SOCCER_DB_PATH, SOCCER_DB_PATH.stat().st_size / 1e6)
        return SOCCER_DB_PATH
    if not os.environ.get("KAGGLE_API_TOKEN") and not (Path.home() / ".kaggle" / "access_token").exists():
        raise RuntimeError(
            "No se encontraron credenciales de Kaggle. Generá un token en https://www.kaggle.com/settings/api "
            "y exportalo como KAGGLE_API_TOKEN (en el '.env' del proyecto si corre bajo Astro)."
        )
    import kaggle  # import perezoso: solo hace falta si hay que descargar

    SOCCER_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Descargando dataset de Kaggle %s ...", KAGGLE_DATASET_SLUG)
    try:
        kaggle.api.authenticate()
        kaggle.api.dataset_download_files(KAGGLE_DATASET_SLUG, path=str(SOCCER_DB_PATH.parent), unzip=True)
    except (Exception, SystemExit) as exc:
        raise RuntimeError("Falló la autenticación o la descarga contra la API de Kaggle: revisá KAGGLE_API_TOKEN.") from exc
    if not SOCCER_DB_PATH.exists():
        raise RuntimeError(f"La descarga terminó pero no apareció {SOCCER_DB_PATH}.")
    return SOCCER_DB_PATH


# -----------------------------------------------------------------------------
# Esquema
# -----------------------------------------------------------------------------


def _quote(identifier: str) -> str:
    # "cross" es palabra reservada en PostgreSQL: se citan todos los nombres.
    return '"' + identifier.lower() + '"'


def sqlite_tables(con: sqlite3.Connection) -> list[str]:
    rows = con.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    return [name for (name,) in rows]


def _stored_kinds(con: sqlite3.Connection, table: str, columns: list[str]) -> dict[str, set[str]]:
    """Qué tipos de valor hay realmente guardados en cada columna (un solo
    recorrido de la tabla)."""
    kinds = ("integer", "real", "text")
    exprs = [f"MAX(typeof(\"{col}\") = '{kind}')" for col in columns for kind in kinds]
    flags = con.execute(f'SELECT {", ".join(exprs)} FROM "{table}"').fetchone()
    return {col: {kind for j, kind in enumerate(kinds) if flags[i * len(kinds) + j]} for i, col in enumerate(columns)}


def _pg_type(column: str, declared: str, stored: set[str]) -> str:
    if column.lower() in DATE_COLUMNS:
        return "TIMESTAMP"
    if "text" in stored or (not stored and declared.upper() == "TEXT"):
        return "TEXT"
    if "real" in stored or (not stored and declared.upper() in ("NUMERIC", "REAL")):
        return "DOUBLE PRECISION"
    return "BIGINT"


def table_ddl(con: sqlite3.Connection, table: str) -> tuple[str, list[str]]:
    info = con.execute(f'PRAGMA table_info("{table}")').fetchall()  # cid, name, type, notnull, default, pk
    columns = [row[1] for row in info]
    stored = _stored_kinds(con, table, columns)
    unique = set()
    for _, index_name, is_unique, origin, *_ in con.execute(f'PRAGMA index_list("{table}")'):
        if is_unique and origin == "u":
            unique.update(row[2] for row in con.execute(f'PRAGMA index_info("{index_name}")'))
    parts = []
    for _, name, declared, _, _, pk in info:
        constraint = " PRIMARY KEY" if pk else (" UNIQUE" if name in unique else "")
        parts.append(f"    {_quote(name)} {_pg_type(name, declared, stored[name])}{constraint}")
    ddl = f"CREATE TABLE {_quote(table)} (\n" + ",\n".join(parts) + "\n)"
    return ddl, columns


# -----------------------------------------------------------------------------
# Carga
# -----------------------------------------------------------------------------


def _pg_row_count(cursor, table: str) -> int | None:
    cursor.execute("SELECT to_regclass(%s)", (f"public.{table.lower()}",))
    if cursor.fetchone()[0] is None:
        return None
    cursor.execute(f"SELECT COUNT(*) FROM {_quote(table)}")
    return cursor.fetchone()[0]


def _copy_from_file(cursor, sql: str, fh) -> None:
    """COPY ... FROM STDIN con el driver que entregue el hook: psycopg 3
    (provider postgres >= 6 por defecto) o psycopg2."""
    if hasattr(cursor, "copy_expert"):
        cursor.copy_expert(sql, fh)
        return
    with cursor.copy(sql) as copy:
        while chunk := fh.read(1 << 20):
            copy.write(chunk)


def _dump_csv(con: sqlite3.Connection, table: str, columns: list[str], path: Path) -> int:
    select = ", ".join(f'"{c}"' for c in columns)
    rows = 0
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        cursor = con.execute(f'SELECT {select} FROM "{table}" ORDER BY rowid')
        while batch := cursor.fetchmany(10_000):
            writer.writerows([NULL_MARKER if value is None else value for value in row] for row in batch)
            rows += len(batch)
    return rows


def load_table(sqlite_con: sqlite3.Connection, pg_con, table: str, force: bool) -> dict:
    expected = sqlite_con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    with closing(pg_con.cursor()) as cursor:
        current = _pg_row_count(cursor, table)
        if current == expected and not force:
            logger.info("%s: ya cargada (%d filas), la salteo.", table.lower(), current)
            return {"tabla": table.lower(), "filas": current, "accion": "sin cambios"}

        started = time.time()
        ddl, columns = table_ddl(sqlite_con, table)
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / f"{table}.csv"
            dumped = _dump_csv(sqlite_con, table, columns, csv_path)
            cursor.execute(f"DROP TABLE IF EXISTS {_quote(table)} CASCADE")
            cursor.execute(ddl)
            column_list = ", ".join(_quote(c) for c in columns)
            with open(csv_path, encoding="utf-8") as fh:
                _copy_from_file(cursor, f"COPY {_quote(table)} ({column_list}) FROM STDIN WITH (FORMAT csv, NULL '{NULL_MARKER}')", fh)
        for index_cols in EXTRA_INDEXES.get(table.lower(), []):
            name = f"{table.lower()}_{index_cols.replace(', ', '_')}_idx"
            cursor.execute(f"CREATE INDEX {name} ON {_quote(table)} ({index_cols})")
        cursor.execute(f"ANALYZE {_quote(table)}")
        loaded = _pg_row_count(cursor, table)
    pg_con.commit()

    if loaded != expected or dumped != expected:
        raise RuntimeError(f"{table}: se esperaban {expected} filas y se cargaron {loaded}.")
    logger.info("%s: %d filas cargadas en %.1f s.", table.lower(), loaded, time.time() - started)
    return {"tabla": table.lower(), "filas": loaded, "accion": "recreada" if current is not None else "creada"}


def seed_source_db(force: bool = False, download: bool = False) -> list[dict]:
    if not SOCCER_DB_PATH.exists():
        if not download:
            raise FileNotFoundError(f"Falta {SOCCER_DB_PATH}. Copiala ahí o corré el seed con --download.")
        download_soccer_db()

    from include.src.database import get_source_hook

    hook = get_source_hook()
    with closing(sqlite3.connect(f"file:{SOCCER_DB_PATH.as_posix()}?mode=ro", uri=True)) as sqlite_con, closing(hook.get_conn()) as pg_con:
        return [load_table(sqlite_con, pg_con, table, force) for table in sqlite_tables(sqlite_con)]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Carga la European Soccer Database en source-db (PostgreSQL).")
    parser.add_argument("--force", action="store_true", help="recrea todas las tablas aunque ya estén cargadas")
    parser.add_argument("--download", action="store_true", help="si falta database.sqlite, la descarga de Kaggle")
    args = parser.parse_args()
    for row in seed_source_db(force=args.force, download=args.download):
        logger.info("  %-18s %8d filas  (%s)", row["tabla"], row["filas"], row["accion"])


if __name__ == "__main__":
    main()
