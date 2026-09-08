"""DAG de Airflow: produce el dataset de partidos para predecir si gana el
equipo no favorito, a partir de los atributos intrínsecos de los 22
jugadores titulares de cada partido, y lo valida contra los 7 criterios de
calidad de la Entrega.

extraer_base descarga la European Soccer Database (SQLite) de Kaggle;
armar_dataset cruza partidos, cuotas y atributos por jugador y escribe el
CSV; chequear_calidad corre al final y falla la corrida si el dataset no
pasa el chequeo.

Pensado para disparo manual (una corrida completa y prolija para mostrar en
los 20 minutos), no para correr en un schedule recurrente.
"""

from __future__ import annotations

from airflow.decorators import dag, task
from pendulum import datetime


@dag(
    dag_id="underdog_pipeline",
    description="Dataset de partidos para predecir triunfos del no favorito desde atributos de jugadores titulares",
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["entrega-1", "underdog"],
    default_args={"retries": 2},
)
def underdog_pipeline():
    @task
    def extraer_base():
        """Capa bronce: baja la base tal como viene, sin transformar."""
        from include.src.extract_soccer_db import download_soccer_db

        path = download_soccer_db()
        return {"sqlite": str(path), "mb": round(path.stat().st_size / 1e6)}

    @task
    def armar_dataset(_base_info):
        """Capa plata: una fila por partido, con features por jugador titular."""
        from include.config import FINAL_DATASET_PATH, PROCESSED_DIR
        from include.src.transform import build_dataset

        dataset = build_dataset()
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        dataset.to_csv(FINAL_DATASET_PATH, index=False)
        return {"filas": len(dataset), "columnas": dataset.shape[1]}

    @task
    def chequear_calidad(_dataset_info):
        """Los 7 criterios de la Entrega, con los números en el log."""
        import pandas as pd

        from include.config import FINAL_DATASET_PATH
        from include.src.quality_check import print_report, run_checks

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
        assert all(report[c] for c in hard_criteria), (
            "El dataset no pasa el chequeo de calidad. Ver logs de este task."
        )

    base_info = extraer_base()
    dataset_info = armar_dataset(base_info)
    chequear_calidad(dataset_info)


underdog_pipeline()
