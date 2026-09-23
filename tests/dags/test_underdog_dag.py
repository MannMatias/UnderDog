"""El DAG importa sin errores, tiene schedule y tiene las tareas y
dependencias esperadas. Necesita Airflow: corre dentro del contenedor
(`astro dev pytest`) y se saltea en un entorno sin Airflow."""

from __future__ import annotations

import pytest

pytest.importorskip("airflow")

from airflow.models import DagBag  # noqa: E402

DAG_ID = "underdog_pipeline"

EXPECTED_UPSTREAM = {
    "check_source_db": set(),
    "compute_source_fingerprint": {"check_source_db"},
    "detect_source_changes": {"compute_source_fingerprint"},
    "extract_matches_bronze": {"detect_source_changes"},
    "extract_teams_bronze": {"detect_source_changes"},
    "extract_players_bronze": {"detect_source_changes"},
    "extract_player_attributes_bronze": {"detect_source_changes"},
    "prepare_matches": {"extract_matches_bronze", "extract_teams_bronze"},
    "build_lineup_features": {"prepare_matches", "extract_players_bronze", "extract_player_attributes_bronze"},
    "define_underdog_and_target": {"prepare_matches"},
    "filter_valid_underdogs": {"define_underdog_and_target"},
    "build_silver_dataset": {"filter_valid_underdogs", "build_lineup_features"},
    "quality_checks": {"build_silver_dataset"},
    "generate_dataset_profile": {"build_silver_dataset", "quality_checks"},
    "save_run_manifest": {"compute_source_fingerprint", "build_silver_dataset", "generate_dataset_profile"},
}


@pytest.fixture(scope="module")
def dagbag() -> DagBag:
    return DagBag(include_examples=False)


@pytest.fixture(scope="module")
def dag(dagbag):
    # `dagbag.dags` es lo que se acaba de parsear; `get_dag()` consultaría la base
    # de metadata, que no existe en el contenedor de `astro dev pytest`.
    return dagbag.dags[DAG_ID]


def test_dags_import_without_errors(dagbag):
    assert not dagbag.import_errors, dagbag.import_errors


def test_dag_is_scheduled_without_catchup(dag):
    assert type(dag.timetable).__name__ == "CronTriggerTimetable"
    assert dag.timetable.expression == "0 6 * * *"
    assert dag.catchup is False
    assert dag.max_active_runs == 1
    assert dag.params["force_rebuild"] is False  # se puede forzar desde la UI
    assert dag.tags


def test_dag_has_expected_tasks(dag):
    assert set(dag.task_ids) == set(EXPECTED_UPSTREAM)


@pytest.mark.parametrize("task_id", sorted(EXPECTED_UPSTREAM))
def test_task_dependencies(dag, task_id):
    assert dag.get_task(task_id).upstream_task_ids == EXPECTED_UPSTREAM[task_id]


def test_source_db_is_reached_through_the_airflow_connection(dag):
    check = dag.get_task("check_source_db")
    assert type(check).__name__ == "SQLCheckOperator"
    assert check.conn_id == "soccer_source_db"


def test_changes_are_detected_with_a_short_circuit(dag):
    detect = dag.get_task("detect_source_changes")
    assert "ShortCircuit" in type(detect).__name__


def test_retries_are_reasonable(dag):
    for task in dag.tasks:
        expected = 0 if task.task_id == "quality_checks" else 2
        assert task.retries == expected, task.task_id
