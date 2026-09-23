"""Reglas de negocio de include/src/transform.py sobre datos sintéticos."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from conftest import make_bronze, make_match, run_pipeline

from include import config
from include.src import transform
from include.src.columns import LEAKAGE_COLUMNS, SILVER_COLUMN_NAMES


def _prepared(bronze):
    prepared, _, _ = transform.prepare_matches(bronze["matches"], bronze["teams"])
    return prepared


# --- prepare_matches ----------------------------------------------------------


def test_prepare_matches_applies_each_inclusion_filter():
    rows = [
        make_match(1, "2012-09-01"),
        make_match(2, "2012-09-02", league=config.EXCLUDED_LEAGUES[0]),
        make_match(3, "2012-09-03"),
        make_match(4, "2012-09-04", odds={"psh": 2.0, "psd": np.nan, "psa": 3.0}),  # tripleta incompleta
        make_match(5, "2012-09-05", odds={"psh": 4.0, "psd": 2.2, "psa": 4.0}),  # empate implícito 1/2.2 = 0.45
    ]
    rows[2]["home_player_7"] = np.nan  # alineación incompleta
    bronze = make_bronze(rows)

    prepared, excluded, funnel = transform.prepare_matches(bronze["matches"], bronze["teams"])

    assert prepared["match_api_id"].tolist() == [1]
    assert dict(zip(excluded["match_api_id"], excluded["motivo"])) == {
        2: "liga_sin_cuotas",
        3: "alineacion_incompleta",
        4: "sin_cuotas_1x2",
        5: "cuota_empate_incoherente",
    }
    assert list(funnel.values()) == [5, 4, 3, 2, 1]


def test_one_bookmaker_per_match_in_preference_order():
    both = {"psh": 2.0, "psd": 3.4, "psa": 3.6, "b365h": 1.9, "b365d": 3.5, "b365a": 3.8}
    only_b365 = {"b365h": 1.9, "b365d": 3.5, "b365a": 3.8}
    bronze = make_bronze([make_match(1, "2012-09-01", odds=both), make_match(2, "2012-09-02", odds=only_b365)])

    prepared = _prepared(bronze)

    assert prepared["odds_source"].tolist() == ["PS", "B365"]
    assert prepared.loc[0, "odds_home"] == 2.0
    assert prepared.loc[1, "odds_home"] == 1.9


def test_implied_probabilities_remove_overround_and_sum_to_one(small_bronze):
    prepared = _prepared(small_bronze)
    total = prepared[["prob_home", "prob_draw", "prob_away"]].sum(axis=1)

    assert np.allclose(total, 1.0)
    assert (prepared["overround"] > 1).all()
    expected_home = (1 / prepared["odds_home"]) / prepared["overround"]
    assert np.allclose(prepared["prob_home"], expected_home)


# --- define_underdog_and_target ----------------------------------------------


def test_underdog_is_the_team_with_lower_win_probability(small_bronze):
    with_target = transform.define_underdog_and_target(_prepared(small_bronze)).set_index("match_api_id")

    assert with_target["equipo_favorito"].to_dict() == {1: "local", 2: "local", 3: "visitante", 4: "visitante"}
    assert (with_target["prob_favorito"] > with_target["prob_no_favorito"]).all()
    # 1: ganó el favorito; 2: ganó el underdog visitante; 3: empate; 4: ganó el underdog local.
    assert with_target[config.TARGET_COLUMN].to_dict() == {1: False, 2: True, 3: False, 4: True}
    assert with_target["resultado_no_favorito"].to_dict() == {1: "perdio", 2: "gano", 3: "empato", 4: "gano"}


def test_equal_probabilities_leave_no_underdog_and_are_removed():
    bronze = make_bronze([
        make_match(1, "2012-09-01", odds={"psh": 2.8, "psd": 3.2, "psa": 2.8}),  # sin underdog
        make_match(2, "2012-09-02", odds={"psh": 1.5, "psd": 4.0, "psa": 7.0}),
    ])
    with_target = transform.define_underdog_and_target(_prepared(bronze))
    tie = with_target[with_target["match_api_id"] == 1].iloc[0]
    assert pd.isna(tie["equipo_favorito"]) and pd.isna(tie[config.TARGET_COLUMN])

    valid, excluded, counts = transform.filter_valid_underdogs(with_target, min_gap=0.0)

    assert valid["match_api_id"].tolist() == [2]
    assert excluded.set_index("match_api_id")["motivo"].to_dict() == {1: "sin_underdog_identificable"}
    assert valid[config.TARGET_COLUMN].notna().all()
    assert valid["equipo_favorito"].notna().all()


# --- filter_valid_underdogs: umbral según config -------------------------------


def _candidates_with_gaps(gaps: list[float]) -> pd.DataFrame:
    rows = []
    for i, gap in enumerate(gaps, start=1):
        prob_draw = 0.25
        prob_away = (1 - prob_draw - gap) / 2
        rows.append({"match_api_id": i, "prob_home": prob_away + gap, "prob_draw": prob_draw, "prob_away": prob_away,
                     "home_team_goal": 1, "away_team_goal": 0})
    return transform.define_underdog_and_target(pd.DataFrame(rows))


@pytest.mark.parametrize("threshold", [0.0, 0.03, config.UNDERDOG_MIN_PROB_GAP, 0.10])
def test_threshold_filter_keeps_only_gaps_strictly_above_threshold(threshold):
    # Sin valores exactamente iguales a un umbral: la resta en punto flotante
    # los dejaría de cualquier lado.
    gaps = [0.0, 0.01, 0.029, 0.031, 0.049, 0.051, 0.074, 0.12, 0.30]
    candidates = _candidates_with_gaps(gaps)

    valid, excluded, counts = transform.filter_valid_underdogs(candidates, min_gap=threshold)

    kept_gaps = transform.underdog_gap(valid)
    assert (kept_gaps > threshold).all()
    assert len(valid) == sum(g > threshold for g in gaps)
    assert counts["salida"] + counts["sin_underdog_identificable"] + counts["partido_parejo"] == len(gaps)


def test_default_threshold_comes_from_config():
    candidates = _candidates_with_gaps([0.02, 0.06, 0.2])
    default_valid, _, default_counts = transform.filter_valid_underdogs(candidates)
    assert default_counts["umbral"] == config.UNDERDOG_MIN_PROB_GAP
    assert (transform.underdog_gap(default_valid) > config.UNDERDOG_MIN_PROB_GAP).all()


def test_negative_threshold_is_rejected():
    with pytest.raises(ValueError):
        transform.filter_valid_underdogs(_candidates_with_gaps([0.1]), min_gap=-0.01)


# --- build_lineup_features: snapshots temporales -------------------------------


def _single_player_attrs(bronze, player_id, snapshots):
    attrs = bronze["player_attributes"]
    attrs = attrs[attrs["player_api_id"] != player_id]
    template = bronze["player_attributes"][bronze["player_attributes"]["player_api_id"] == player_id].iloc[0]
    extra = []
    for date, rating in snapshots:
        row = template.copy()
        row["date"] = pd.Timestamp(date)
        row["overall_rating"] = rating
        if rating is None:
            row[transform.PLAYER_ATTRS] = np.nan
        extra.append(row)
    bronze["player_attributes"] = pd.concat([attrs, pd.DataFrame(extra)], ignore_index=True)
    return bronze


def test_player_snapshots_are_strictly_before_the_match():
    bronze = make_bronze([make_match(1, "2012-09-01")])
    best_home_player = 111  # home_player_11: el de mayor overall del once local
    bronze = _single_player_attrs(bronze, best_home_player, [
        ("2012-08-01", 60),   # el último estrictamente anterior -> el que vale
        ("2012-09-01", 99),   # mismo día del partido: podría ser posterior al pitazo
        ("2012-09-20", 95),   # posterior al partido
    ])
    prepared = _prepared(bronze)
    lineups = transform.attach_player_snapshots(transform.build_lineups(prepared), bronze["players"], bronze["player_attributes"])

    player = lineups[lineups["player_api_id"] == best_home_player].iloc[0]
    assert player["overall_rating"] == 60
    assert (lineups["snapshot_date"] < lineups["date"]).all()

    features, stats = transform.build_lineup_features(prepared, bronze["players"], bronze["player_attributes"])
    assert features.loc[0, "home_best_overall"] < 95
    assert stats["snapshot_mas_reciente_vs_partido_dias_min"] >= 1


def test_empty_duplicate_snapshot_is_ignored():
    """La fuente repite (jugador, fecha) con una fila vacía: no debe dejar al
    titular sin atributos."""
    bronze = make_bronze([make_match(1, "2012-09-01")])
    bronze = _single_player_attrs(bronze, 101, [("2012-08-01", 72), ("2012-08-01", None)])

    features, stats = transform.build_lineup_features(_prepared(bronze), bronze["players"], bronze["player_attributes"])

    assert features.loc[0, "home_xi_sin_atributos"] == 0
    assert stats["pct_titulares_sin_snapshot"] == 0


def test_snapshot_guard_detects_temporal_leakage():
    lineups = pd.DataFrame({"date": pd.to_datetime(["2012-09-01", "2012-09-01"]),
                            "snapshot_date": pd.to_datetime(["2012-08-01", "2012-09-01"])})
    with pytest.raises(ValueError, match="Fuga temporal"):
        transform.assert_snapshots_before_match(lineups)


def test_lines_follow_y_coordinate_and_goalkeeper_is_the_y1_player(small_bronze):
    features, _ = transform.build_lineup_features(_prepared(small_bronze), small_bronze["players"], small_bronze["player_attributes"])
    row = features.iloc[0]

    assert row["home_formacion"] == "4-4-2"
    assert row["home_gk_overall"] == 70 + 1  # el titular con Y=1 es el puesto 1
    assert row["home_def_overall"] == np.mean([72, 73, 74, 75])


# --- build_silver ---------------------------------------------------------------


def test_silver_has_catalog_columns_and_no_post_match_information(small_bronze):
    silver, audit = run_pipeline(small_bronze)

    assert list(silver.columns) == SILVER_COLUMN_NAMES
    assert not set(silver.columns) & set(LEAKAGE_COLUMNS)
    for column in ("goles_local", "goles_visitante", "resultado_ft", "resultado_no_favorito"):
        assert column not in silver.columns
        assert column in audit.columns
    assert silver["match_id"].tolist() == audit["match_id"].tolist()


def test_underdog_gaps_are_oriented_underdog_minus_favourite(small_bronze):
    silver, _ = run_pipeline(small_bronze)
    by_match = silver.set_index("match_id")

    # Los locales tienen overall +5 respecto de los visitantes en todos los puestos.
    assert by_match.loc[1, "nofav_xi_overall_mean_gap"] == -5  # underdog visitante, peor
    assert by_match.loc[4, "nofav_xi_overall_mean_gap"] == 5   # underdog local, mejor
