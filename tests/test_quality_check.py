"""Quality checks: un Silver válido pasa, y cada tipo de defecto hace fallar
el hard check que corresponde."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from conftest import make_bronze, make_match, run_pipeline

from include.config import TARGET_COLUMN, UNDERDOG_MIN_PROB_GAP
from include.src.quality_check import run_quality_checks, single_feature_auc


@pytest.fixture(scope="module")
def valid_silver():
    """Silver sintético con más filas que el mínimo de la Entrega 1."""
    rng = np.random.default_rng(7)
    matches = []
    for i in range(1, 1201):
        home_odds = float(np.round(rng.uniform(1.3, 6.0), 2))
        away_odds = float(np.round(max(1.25, 1 / max(0.05, 0.94 - 1 / home_odds - 0.27)), 2))
        home_goals, away_goals = int(rng.integers(0, 4)), int(rng.integers(0, 4))
        date = (pd.Timestamp("2012-08-15") + pd.Timedelta(days=i % 270)).strftime("%Y-%m-%d")  # temporada 2012/2013
        matches.append(make_match(i, date, home_goals=home_goals, away_goals=away_goals,
                                  odds={"psh": home_odds, "psd": 3.6, "psa": away_odds}))
    silver, _ = run_pipeline(make_bronze(matches))
    assert len(silver) > 1000
    return silver


def _failed(df) -> set[str]:
    return {c["name"] for c in run_quality_checks(df)["hard_checks"] if not c["passed"]}


def test_valid_silver_passes_every_hard_check(valid_silver):
    report = run_quality_checks(valid_silver)
    assert report["passed"], [c for c in report["hard_checks"] if not c["passed"]]


def test_duplicated_match_id_fails(valid_silver):
    df = valid_silver.copy()
    df.loc[1, "match_id"] = df.loc[0, "match_id"]
    assert "clave_sin_duplicados" in _failed(df)


def test_null_target_fails(valid_silver):
    df = valid_silver.copy()
    df[TARGET_COLUMN] = df[TARGET_COLUMN].astype(object)
    df.loc[0, TARGET_COLUMN] = None
    assert {"target_sin_nulos", "target_binario"} <= _failed(df)


def test_goal_columns_in_silver_fail_as_leakage(valid_silver):
    df = valid_silver.copy()
    df["goles_local"] = 1
    assert {"sin_columnas_de_fuga", "columnas_documentadas"} <= _failed(df)


def test_feature_that_encodes_the_result_is_detected(valid_silver):
    df = valid_silver.copy()
    df["jornada"] = df[TARGET_COLUMN].astype(int)  # una feature "inocente" con el resultado adentro
    assert "sin_predictor_perfecto" in _failed(df)


def test_probabilities_that_do_not_sum_to_one_fail(valid_silver):
    df = valid_silver.copy()
    df.loc[0, "prob_draw"] = df.loc[0, "prob_draw"] + 0.05
    assert "probabilidades_suman_uno" in _failed(df)


def test_match_below_underdog_threshold_fails(valid_silver):
    df = valid_silver.copy()
    df.loc[0, "prob_no_favorito"] = df.loc[0, "prob_favorito"] - UNDERDOG_MIN_PROB_GAP / 2
    assert "umbral_underdog_respetado" in _failed(df)


def test_match_without_underdog_fails(valid_silver):
    df = valid_silver.copy()
    df.loc[0, "equipo_favorito"] = None
    assert "underdog_definido" in _failed(df)


def test_undocumented_nulls_and_empty_columns_fail(valid_silver):
    df = valid_silver.copy()
    df.loc[0, "prob_no_favorito"] = np.nan
    assert "nulos_conocidos" in _failed(df)
    df["nofav_xi_height_mean_gap"] = np.nan
    assert "sin_columnas_vacias" in _failed(df)


def test_dates_outside_their_season_fail(valid_silver):
    df = valid_silver.copy()
    df.loc[0, "temporada"] = "2005/2006"
    assert "fechas_validas" in _failed(df)


def test_imbalanced_target_is_informative_not_a_failure(valid_silver):
    report = run_quality_checks(valid_silver)
    distribution = report["informativas"]["distribucion_target"]
    assert distribution["pct_true"] < 50  # desbalanceado...
    assert report["passed"]               # ...y aun así no falla


def test_single_feature_auc_detects_perfect_separation():
    target = pd.Series([True, False] * 50)
    assert single_feature_auc(target.astype(int), target) == 1.0
    assert 0.4 < single_feature_auc(pd.Series(np.random.default_rng(0).normal(size=100)), target) < 0.7
