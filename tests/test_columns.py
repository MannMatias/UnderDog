"""El catálogo de columnas es consistente y cubre todas las columnas del
dataset de la Entrega 1."""

from __future__ import annotations

import pandas as pd
import pytest

from include.config import TARGET_COLUMN
from include.src import columns as C

# Las 82 columnas del CSV de la Entrega 1: cada una tiene que terminar en una
# decisión documentada (entra, se transforma, sale o va a auditoría).
ENTREGA_1_COLUMNS = (
    "match_id liga pais temporada jornada fecha equipo_local equipo_visitante goles_local goles_visitante "
    "resultado_ft odds_source odds_home odds_draw odds_away overround prob_home prob_draw prob_away prob_gap "
    "equipo_favorito prob_favorito prob_no_favorito es_partido_parejo resultado_no_favorito gano_no_favorito "
    + " ".join(f"{side}_{m}" for side in ("home", "away") for m in [
        "best_overall", "worst_overall", "xi_overall_mean", "overall_std", "best_reactions", "fastest_sprint_speed",
        "strongest_strength", "best_finishing", "best_marking", "xi_age_mean", "xi_height_mean", "xi_sin_atributos",
        "top3_overall", "gk_overall", "gk_reflexes", "gk_diving", "gk_handling", "def_overall", "mid_overall",
        "att_overall", "formacion"])
    + " xi_overall_mean_gap top3_overall_gap worst_overall_gap gk_overall_gap def_overall_gap mid_overall_gap "
    "att_overall_gap fastest_sprint_speed_gap best_finishing_gap xi_age_mean_gap nofav_xi_overall_mean_gap "
    "nofav_top3_overall_gap nofav_gk_overall_gap nofav_fastest_sprint_speed_gap"
).split()


def test_every_entrega_1_column_has_a_documented_decision():
    assert len(ENTREGA_1_COLUMNS) == 82
    documented = set(C.catalog_frame()["name"])
    assert not set(ENTREGA_1_COLUMNS) - documented


def test_features_exist_before_the_match():
    for spec in C.SILVER_COLUMNS:
        if spec.is_feature:
            assert spec.available == C.PRE, spec.name


def test_known_leakage_columns_are_flagged():
    for column in ("goles_local", "goles_visitante", "resultado_ft", "resultado_no_favorito", "home_team_goal", "away_team_goal"):
        assert column in C.LEAKAGE_COLUMNS
    assert not set(C.SILVER_COLUMN_NAMES) & set(C.LEAKAGE_COLUMNS)


def test_target_is_in_silver_but_never_a_feature():
    assert TARGET_COLUMN in C.SILVER_COLUMN_NAMES
    assert TARGET_COLUMN not in C.FEATURE_COLUMNS


def test_split_features_target_never_puts_result_information_in_x(silver_frame):
    X, y = C.split_features_target(silver_frame)

    assert list(X.columns) == C.FEATURE_COLUMNS
    assert TARGET_COLUMN not in X.columns
    assert not set(X.columns) & set(C.LEAKAGE_COLUMNS)
    assert y.dtype == bool and y.notna().all()


def test_split_features_target_rejects_a_leaking_feature(monkeypatch, silver_frame):
    monkeypatch.setattr(C, "FEATURE_COLUMNS", [*C.FEATURE_COLUMNS, "goles_local"])
    with pytest.raises(ValueError, match="resultado"):
        C.split_features_target(silver_frame.assign(goles_local=1))


def test_nullable_columns_explain_why():
    for name, reason in C.NULLABLE_SILVER_COLUMNS.items():
        assert len(reason) > 20, name


def test_leakage_audit_marks_no_silver_column_as_leaking(silver_frame):
    audit = C.leakage_audit_frame(list(silver_frame.columns))
    assert not audit["leakage"].any()
    assert audit.loc[audit["columna"] == TARGET_COLUMN, "target"].item()


def test_leakage_audit_flags_an_undocumented_column():
    audit = C.leakage_audit_frame(["match_id", "columna_nueva"])
    assert audit.set_index("columna").loc["columna_nueva", "leakage"]


def test_catalog_frame_has_one_row_per_column_and_location():
    frame = C.catalog_frame()
    assert not frame.duplicated(["name", "location"]).any()
    assert isinstance(frame, pd.DataFrame)
