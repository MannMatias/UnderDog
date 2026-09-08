"""El chequeo de calidad de la Entrega: los 7 criterios del PDF, verificados
con un número a mano sobre el CSV final. Se corre como último task del DAG y
falla la corrida si algún criterio duro no se cumple.
"""

from __future__ import annotations

import logging

import pandas as pd

from include.config import FINAL_DATASET_PATH
from include.src.transform import NULL_REASONS

logger = logging.getLogger(__name__)

MIN_ROWS = 1000
MIN_COLS = 5


def run_checks(df: pd.DataFrame) -> dict:
    report = {}

    report["clave_sin_duplicados"] = bool(df["match_id"].is_unique)

    n_rows = len(df)
    report["volumen_suficiente"] = n_rows > MIN_ROWS
    report["_n_rows"] = n_rows

    n_cols = df.shape[1]
    report["ancho_suficiente"] = n_cols >= MIN_COLS
    report["_n_cols"] = n_cols

    dtype_counts = df.dtypes.astype(str).value_counts()
    report["mezcla_de_tipos"] = dtype_counts.shape[0] >= 2
    report["_dtype_counts"] = dtype_counts.to_dict()

    null_share = df.isna().mean().sort_values(ascending=False)
    columns_with_nulls = null_share[null_share > 0].index.tolist()
    undocumented = [c for c in columns_with_nulls if c not in NULL_REASONS]
    report["nulos_conocidos"] = len(undocumented) == 0
    report["_null_share"] = null_share.to_dict()
    report["_columnas_sin_documentar"] = undocumented

    empty_columns = df.columns[df.isna().all()].tolist()
    report["sin_columnas_vacias"] = len(empty_columns) == 0
    report["_columnas_vacias"] = empty_columns

    report["clave_primaria_es_match_id"] = "match_id" in df.columns

    return report


def print_report(report: dict) -> None:
    print(f"Filas: {report['_n_rows']}  |  Columnas: {report['_n_cols']}")
    print(f"Tipos de dato presentes: {report['_dtype_counts']}")
    print("Nulos por columna (top 10):")
    for col, share in list(report["_null_share"].items())[:10]:
        if share > 0:
            razon = NULL_REASONS.get(col, "SIN DOCUMENTAR")
            print(f"  {col}: {share:.1%}  -> {razon}")
    if report["_columnas_sin_documentar"]:
        print(f"  ATENCION - columnas con nulos sin explicar: {report['_columnas_sin_documentar']}")
    if report["_columnas_vacias"]:
        print(f"  ATENCION - columnas 100% nulas: {report['_columnas_vacias']}")

    print()
    criterios = [
        "clave_sin_duplicados",
        "volumen_suficiente",
        "ancho_suficiente",
        "mezcla_de_tipos",
        "nulos_conocidos",
        "sin_columnas_vacias",
        "clave_primaria_es_match_id",
    ]
    for criterio in criterios:
        estado = "OK" if report[criterio] else "FALLA"
        print(f"  [{estado}] {criterio}")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    if not FINAL_DATASET_PATH.exists():
        raise FileNotFoundError(
            f"Falta {FINAL_DATASET_PATH}. Corré src/transform.py primero."
        )
    df = pd.read_csv(FINAL_DATASET_PATH)
    report = run_checks(df)
    print_report(report)

    hard_criteria = [
        "clave_sin_duplicados",
        "volumen_suficiente",
        "ancho_suficiente",
        "mezcla_de_tipos",
        "nulos_conocidos",
        "sin_columnas_vacias",
    ]
    if not all(report[c] for c in hard_criteria):
        raise AssertionError("El dataset no pasa el chequeo de calidad. Ver detalle arriba.")


if __name__ == "__main__":
    main()
