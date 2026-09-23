"""Controles sobre el Silver REAL que produjo el DAG
(include/data/silver/underdog_dataset.parquet). Se saltean si todavía no se
corrió el pipeline."""

from __future__ import annotations

import pandas as pd
import pytest

from include.config import AUDIT_DIR, BRONZE_DIR, INTERMEDIATE_DIR, SILVER_DATASET_PATH, TARGET_COLUMN, UNDERDOG_MIN_PROB_GAP
from include.src.columns import LEAKAGE_COLUMNS, SILVER_COLUMN_NAMES
from include.src.quality_check import ROUNDING_TOLERANCE, run_quality_checks

pytestmark = pytest.mark.skipif(not SILVER_DATASET_PATH.exists(), reason="Silver no generado: correr el DAG primero")


@pytest.fixture(scope="module")
def silver() -> pd.DataFrame:
    return pd.read_parquet(SILVER_DATASET_PATH)


def test_match_id_is_unique(silver):
    assert silver["match_id"].is_unique


def test_target_has_no_nulls_and_is_binary(silver):
    assert silver[TARGET_COLUMN].notna().all()
    assert set(silver[TARGET_COLUMN].unique()) <= {True, False}
    assert silver[TARGET_COLUMN].dtype == bool


def test_every_match_has_an_underdog(silver):
    assert silver["equipo_favorito"].isin(["local", "visitante"]).all()
    assert silver["prob_no_favorito"].notna().all()
    gap = silver["prob_favorito"] - silver["prob_no_favorito"]
    assert (gap > UNDERDOG_MIN_PROB_GAP - ROUNDING_TOLERANCE).all()


def test_no_goals_and_no_leakage_columns(silver):
    for column in ("goles_local", "goles_visitante", "home_team_goal", "away_team_goal", "resultado_ft", "resultado_no_favorito"):
        assert column not in silver.columns
    assert not set(silver.columns) & set(LEAKAGE_COLUMNS)
    assert list(silver.columns) == SILVER_COLUMN_NAMES


def test_probabilities_sum_to_one(silver):
    total = silver["prob_home"] + silver["prob_draw"] + silver["prob_away"]
    assert (total - 1).abs().max() <= 1e-3


def test_no_column_is_completely_empty(silver):
    assert not silver.isna().all().any()


def test_quality_report_passes(silver):
    assert run_quality_checks(silver)["passed"]


def test_audit_dataset_joins_one_to_one_with_silver(silver):
    audit = pd.read_parquet(AUDIT_DIR / "match_audit.parquet")
    assert audit["match_id"].is_unique
    assert set(audit["match_id"]) == set(silver["match_id"])
    assert {"goles_local", "goles_visitante", "resultado_ft"} <= set(audit.columns)


def test_target_matches_the_audited_result(silver):
    """El target es exactamente 'el underdog ganó' según los goles guardados en auditoría."""
    audit = pd.read_parquet(AUDIT_DIR / "match_audit.parquet")
    merged = silver[["match_id", "equipo_favorito", TARGET_COLUMN]].merge(audit, on="match_id")
    underdog_goals = merged["goles_local"].where(merged["equipo_favorito"] == "visitante", merged["goles_visitante"])
    favourite_goals = merged["goles_visitante"].where(merged["equipo_favorito"] == "visitante", merged["goles_local"])
    assert (merged[TARGET_COLUMN] == (underdog_goals > favourite_goals)).all()


def test_real_lineup_snapshots_are_strictly_before_each_match():
    """Sobre los datos reales de Bronze: cada uno de los titulares recibe un
    snapshot de atributos de un día anterior al partido, nunca del mismo día
    ni posterior."""
    from include.src import transform

    bronze = {name: pd.read_parquet(BRONZE_DIR / f"{name}.parquet") for name in ("matches", "teams", "players", "player_attributes")}
    prepared, _, _ = transform.prepare_matches(bronze["matches"], bronze["teams"])
    lineups = transform.attach_player_snapshots(transform.build_lineups(prepared), bronze["players"], bronze["player_attributes"])

    matched = lineups["snapshot_date"].notna()
    assert (lineups.loc[matched, "snapshot_date"] < lineups.loc[matched, "date"]).all()
    assert len(lineups) == 22 * len(prepared)


def test_lineup_features_cover_every_silver_match(silver):
    lineups = pd.read_parquet(INTERMEDIATE_DIR / "lineup_features.parquet")
    assert set(silver["match_id"]) <= set(lineups["match_api_id"])
