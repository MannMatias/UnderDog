"""
# underdog_pipeline

Construye el dataset para responder: **¿ganará el underdog, dadas las
probabilidades implícitas pre-partido y los atributos de sus 22 titulares?**
Una fila = un partido.

```
source-db (PostgreSQL) --Connection soccer_source_db--> consultas SQL (include/sql)
   -> Bronze (resultado crudo de cada consulta) -> transformaciones -> Silver
   -> quality checks -> perfil del dataset
```

1. `check_source_db`: SQLCheckOperator; la base fuente responde y tiene datos.
2. `compute_source_fingerprint` + `detect_source_changes`: si la fuente y el
   código no cambiaron desde la última corrida exitosa, se saltea el resto
   (ShortCircuit). `force_rebuild=true` al disparar a mano fuerza la corrida.
3. `extract_*_bronze`: una consulta SQL por tabla, vía PostgresHook, a
   `include/data/bronze/*.parquet`.
4. `prepare_matches` -> `define_underdog_and_target` -> `filter_valid_underdogs`
   y, en paralelo, `build_lineup_features`.
5. `build_silver_dataset`: Silver sin columnas post-partido + auditoría aparte.
6. `quality_checks` (hard checks: fallan la corrida) -> `generate_dataset_profile`
   -> `save_run_manifest` (registra la huella procesada).

**Schedule**: todos los días a las 06:00 UTC, después de la última jornada
europea del día anterior. La fuente cambia a lo sumo una vez por jornada (fines
de semana y fechas de mitad de semana): una corrida diaria detecta una jornada
nueva en menos de 24 h, y si no hubo cambios la corrida cuesta una consulta y
termina en `detect_source_changes`.
"""

from __future__ import annotations

import logging
from datetime import timedelta

import pendulum
from airflow.providers.common.sql.operators.sql import SQLCheckOperator
from airflow.sdk import Param, dag, get_current_context, task

from include.config import BRONZE_QUERIES, SOURCE_DB_CONN_ID, SQL_DIR

logger = logging.getLogger(__name__)

DEFAULT_ARGS = {
    "owner": "underdog",
    # Reintentos para fallas transitorias (la base no responde, un lock). Los
    # errores de datos son determinísticos: quality_checks no reintenta.
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "execution_timeout": timedelta(minutes=30),
}


@dag(
    dag_id="underdog_pipeline",
    description="source-db -> Bronze -> Silver: partidos para predecir si gana el underdog",
    schedule="0 6 * * *",
    start_date=pendulum.datetime(2026, 9, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(hours=2),
    default_args=DEFAULT_ARGS,
    template_searchpath=[str(SQL_DIR)],
    params={
        "force_rebuild": Param(
            False,
            type="boolean",
            description="Reconstruir Bronze y Silver aunque la fuente no haya cambiado.",
        ),
    },
    tags=["entrega-2", "underdog", "source-db"],
    doc_md=__doc__,
)
def underdog_pipeline():
    check_source_db = SQLCheckOperator(
        task_id="check_source_db",
        conn_id=SOURCE_DB_CONN_ID,
        sql="check_source_db.sql",
        doc_md="La base fuente responde por la Connection y sus tablas tienen filas. Si falla, falta el seed.",
    )

    @task
    def compute_source_fingerprint() -> dict:
        """Huella de la fuente (filas, fecha máxima y hash por tabla, por SQL)
        combinada con la versión del código del pipeline."""
        from include.src.change_detection import build_fingerprint
        from include.src.database import fetch_source_fingerprint

        fingerprint = build_fingerprint(fetch_source_fingerprint())
        for table in fingerprint["source"]:
            logger.info("Fuente %-18s filas=%s max_fecha=%s", table["tabla"], table["filas"], table["max_fecha"])
        return fingerprint

    @task.short_circuit
    def detect_source_changes(fingerprint: dict) -> bool:
        """True = hay algo nuevo y la corrida sigue; False = se saltean todas
        las tareas siguientes."""
        from include.src.change_detection import needs_rebuild

        force = bool(get_current_context()["params"]["force_rebuild"])
        rebuild, reason = needs_rebuild(fingerprint, force=force)
        logger.info("%s: %s", "Reconstruir" if rebuild else "Sin cambios, se saltea", reason)
        return rebuild

    @task
    def extract_bronze(table_name: str) -> dict:
        """Corre la consulta de include/sql/ contra source-db y guarda el
        resultado tal cual en include/data/bronze/<tabla>.parquet."""
        from include.src.extract import extract_to_bronze

        return extract_to_bronze(table_name)

    @task
    def prepare_matches(matches: dict, teams: dict) -> dict:
        """Filtros de inclusión, una casa de apuestas por partido y
        probabilidades implícitas normalizadas."""
        from include.config import AUDIT_DIR, INTERMEDIATE_DIR
        from include.src import storage, transform

        prepared, excluded, funnel = transform.prepare_matches(storage.read_parquet(matches["path"]), storage.read_parquet(teams["path"]))
        storage.write_parquet(excluded, AUDIT_DIR / "excluded_prepare_matches.parquet")
        return {**storage.write_parquet(prepared, INTERMEDIATE_DIR / "matches_prepared.parquet"), "embudo": funnel}

    @task
    def build_lineup_features(prepared: dict, players: dict, player_attributes: dict) -> dict:
        """Features de los 22 titulares con el snapshot de atributos
        estrictamente anterior a cada partido."""
        from include.config import INTERMEDIATE_DIR
        from include.src import storage, transform

        features, stats = transform.build_lineup_features(
            storage.read_parquet(prepared["path"]),
            storage.read_parquet(players["path"]),
            storage.read_parquet(player_attributes["path"]),
        )
        return {**storage.write_parquet(features, INTERMEDIATE_DIR / "lineup_features.parquet"), **stats}

    @task
    def define_underdog_and_target(prepared: dict) -> dict:
        """Favorito/underdog por probabilidad implícita y la columna objetivo.
        Acá se usan los goles por única vez."""
        from include.config import INTERMEDIATE_DIR
        from include.src import storage, transform

        with_target = transform.define_underdog_and_target(storage.read_parquet(prepared["path"]))
        return storage.write_parquet(with_target, INTERMEDIATE_DIR / "matches_with_target.parquet")

    @task
    def filter_valid_underdogs(with_target: dict) -> dict:
        """Saca los partidos sin underdog identificable (gap <= umbral) y
        guarda la sensibilidad del dataset a cada umbral candidato."""
        from include.config import AUDIT_DIR, INTERMEDIATE_DIR, REPORTS_DIR
        from include.src import profiling, storage, transform

        candidates = storage.read_parquet(with_target["path"])
        valid, excluded, counts = transform.filter_valid_underdogs(candidates)
        storage.write_csv(profiling.threshold_sensitivity(candidates), REPORTS_DIR / "threshold_sensitivity.csv")
        storage.write_parquet(excluded, AUDIT_DIR / "excluded_filter_underdogs.parquet")
        return {**storage.write_parquet(valid, INTERMEDIATE_DIR / "matches_valid.parquet"), **counts}

    @task
    def build_silver_dataset(valid: dict, lineup_features: dict) -> dict:
        """Silver = candidatas a feature + target, sin nada post-partido.
        Goles, resultado y cuotas crudas van a include/data/audit/."""
        import pandas as pd

        from include.config import AUDIT_DIR, SILVER_CSV_PATH, SILVER_DATASET_PATH
        from include.src import storage, transform

        silver, audit = transform.build_silver(storage.read_parquet(valid["path"]), storage.read_parquet(lineup_features["path"]))
        storage.write_parquet(audit, AUDIT_DIR / "match_audit.parquet")
        excluded = pd.concat(
            [storage.read_parquet(AUDIT_DIR / f"excluded_{step}.parquet") for step in ("prepare_matches", "filter_underdogs")],
            ignore_index=True,
        )
        storage.write_parquet(excluded, AUDIT_DIR / "excluded_matches.parquet")
        storage.write_csv(silver, SILVER_CSV_PATH)
        meta = storage.write_parquet(silver, SILVER_DATASET_PATH)
        logger.info("Silver: %d filas x %d columnas. Excluidos por motivo: %s", meta["rows"], meta["columns"], excluded["motivo"].value_counts().to_dict())
        return meta

    @task(retries=0)
    def quality_checks(silver: dict) -> dict:
        """Hard checks (Entrega 1 + Entrega 2): si alguno falla, la corrida
        falla. Las métricas informativas solo se reportan."""
        from include.config import REPORTS_DIR
        from include.src import quality_check, storage

        report = quality_check.run_quality_checks(storage.read_parquet(silver["path"]))
        storage.write_json(report, REPORTS_DIR / "quality_report.json")
        quality_check.log_report(report)
        quality_check.assert_quality(report)
        return {"passed": report["passed"], "hard_checks": len(report["hard_checks"])}

    @task
    def generate_dataset_profile(silver: dict, _quality: dict) -> dict:
        """Perfil de la Entrega 2 (shape, tipos, nulos, constantes,
        duplicados, target, asimetría) y la auditoría de fuga."""
        from include.config import REPORTS_DIR
        from include.src import profiling, storage

        df = storage.read_parquet(silver["path"])
        profile = profiling.dataset_profile(df)
        storage.write_json(profile, REPORTS_DIR / "dataset_profile.json")
        (REPORTS_DIR / "dataset_profile.md").write_text(profiling.profile_markdown(profile), encoding="utf-8")
        leakage = profiling.leakage_audit(df)
        storage.write_csv(leakage, REPORTS_DIR / "leakage_audit.csv")
        return {"filas": profile["filas"], "columnas": profile["columnas"], "target": profile["target"], "columnas_con_fuga": int(leakage["leakage"].sum())}

    @task
    def save_run_manifest(fingerprint: dict, silver: dict, profile: dict) -> dict:
        """Registra la huella procesada: la próxima corrida la compara."""
        from include.src.change_detection import write_manifest

        manifest = write_manifest(fingerprint, {**silver, **profile}, get_current_context()["run_id"])
        return {"fingerprint": manifest["fingerprint"], "built_at_utc": manifest["built_at_utc"]}

    fingerprint = compute_source_fingerprint()
    changed = detect_source_changes(fingerprint)
    check_source_db >> fingerprint

    bronze = {name: extract_bronze.override(task_id=f"extract_{name}_bronze")(name) for name in BRONZE_QUERIES}
    changed >> list(bronze.values())

    prepared = prepare_matches(bronze["matches"], bronze["teams"])
    lineups = build_lineup_features(prepared, bronze["players"], bronze["player_attributes"])
    valid = filter_valid_underdogs(define_underdog_and_target(prepared))
    silver = build_silver_dataset(valid, lineups)
    quality = quality_checks(silver)
    profile = generate_dataset_profile(silver, quality)
    save_run_manifest(fingerprint, silver, profile)


underdog_pipeline()
