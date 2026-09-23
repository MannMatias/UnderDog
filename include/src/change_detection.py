"""Detección de cambios: decide si una corrida programada tiene que
reconstruir Bronze/Silver o si puede saltearse todo.

La huella del pipeline combina dos cosas:

1. La huella de la FUENTE (`include/sql/source_fingerprint.sql`): filas, fecha
   máxima y hash del contenido de cada tabla que lee el pipeline.
2. La versión del CÓDIGO: hash de las consultas SQL, de `config.py` (reglas de
   negocio) y de los módulos de `include/src/`. Si cambia el umbral del
   underdog o una consulta, Silver ya no corresponde al código aunque la
   fuente sea la misma.

Al final de cada corrida exitosa (después de los quality checks) se guarda la
huella en `silver/_manifest.json`. La corrida siguiente compara contra ese
archivo: si es igual y Silver existe, no hay nada nuevo.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from include.config import INCLUDE_DIR, SILVER_DATASET_PATH, SILVER_MANIFEST_PATH, SQL_DIR
from include.src.storage import read_json, write_json

CODE_PATHS = [INCLUDE_DIR / "config.py", *sorted(SQL_DIR.glob("*.sql")), *sorted((INCLUDE_DIR / "src").glob("*.py"))]


def code_version() -> str:
    digest = hashlib.sha256()
    for path in CODE_PATHS:
        digest.update(path.relative_to(INCLUDE_DIR).as_posix().encode("utf-8"))
        # Sin \r: la misma versión da el mismo hash en Windows y en el contenedor.
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()


def build_fingerprint(source_tables: list[dict]) -> dict:
    """Huella combinada fuente + código. `source_tables` es el resultado de
    `source_fingerprint.sql` (una fila por tabla)."""
    source = sorted(source_tables, key=lambda row: row["tabla"])
    version = code_version()
    payload = json.dumps({"source": source, "code_version": version}, sort_keys=True, default=str)
    return {
        "fingerprint": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "source": source,
        "code_version": version,
    }


def read_manifest() -> dict | None:
    if not SILVER_MANIFEST_PATH.exists():
        return None
    return read_json(SILVER_MANIFEST_PATH)


def needs_rebuild(current: dict, force: bool = False) -> tuple[bool, str]:
    """(hay_que_reconstruir, motivo)."""
    if force:
        return True, "force_rebuild=True en los parámetros de la corrida"
    if not SILVER_DATASET_PATH.exists():
        return True, f"no existe {SILVER_DATASET_PATH.name}"
    manifest = read_manifest()
    if manifest is None:
        return True, "no hay manifest de una corrida exitosa anterior"
    if manifest.get("fingerprint") != current["fingerprint"]:
        if manifest.get("code_version") != current["code_version"]:
            return True, "cambió el código del pipeline (SQL, config o src)"
        return True, "cambió el contenido de la fuente"
    return False, "la fuente y el código son los mismos que en la última corrida exitosa"


def write_manifest(fingerprint: dict, silver_meta: dict, run_id: str | None) -> dict:
    manifest = {
        **fingerprint,
        "silver": silver_meta,
        "run_id": run_id,
        "built_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    write_json(manifest, SILVER_MANIFEST_PATH)
    return manifest
