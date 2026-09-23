"""Lectura/escritura de las capas en disco.

Todas las escrituras son atómicas: se escribe a un archivo temporal y se
renombra al final. Si una tarea falla a mitad de camino, el archivo anterior
queda intacto y un reintento arranca de un estado limpio (idempotencia).
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def _atomic_target(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.with_name(f".{path.name}.tmp")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_arrow_table(table: pa.Table, path: Path) -> dict:
    tmp = _atomic_target(path)
    pq.write_table(table, tmp)
    os.replace(tmp, path)
    return {"path": str(path), "rows": table.num_rows, "columns": table.num_columns, "sha256": file_sha256(path)}


def write_parquet(df: pd.DataFrame, path: Path) -> dict:
    return write_arrow_table(pa.Table.from_pandas(df, preserve_index=False), path)


def read_parquet(path: str | Path) -> pd.DataFrame:
    """Acepta la ruta como texto porque así viaja por XCom entre tareas."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Falta {path}: corré la tarea que lo genera primero.")
    return pd.read_parquet(path)


def write_csv(df: pd.DataFrame, path: Path) -> None:
    tmp = _atomic_target(path)
    df.to_csv(tmp, index=False)
    os.replace(tmp, path)


def write_json(data: Any, path: Path) -> None:
    tmp = _atomic_target(path)
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
