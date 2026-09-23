"""Fixtures compartidos: Bronze sintético con la misma forma que devuelven
las consultas de include/sql/, para testear la lógica sin base de datos."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from include.config import ODDS_BOOKMAKERS  # noqa: E402

# Coordenada Y de cada puesto: 1 arquero, 4 defensores, 4 medios, 2 delanteros.
Y_442 = [1, 3, 3, 3, 3, 7, 7, 7, 7, 10, 10]


def make_match(match_id: int, date: str, *, home_goals: int = 1, away_goals: int = 0,
               odds: dict | None = None, league: str = "England Premier League") -> dict:
    """Un partido con 22 titulares distintos (ids derivados del match_id)."""
    row = {
        "match_api_id": match_id,
        "league_name": league,
        "season": "2012/2013",
        "stage": 5,
        "date": pd.Timestamp(date),
        "home_team_api_id": 1,
        "away_team_api_id": 2,
        "home_team_goal": home_goals,
        "away_team_goal": away_goals,
    }
    for i in range(1, 12):
        row[f"home_player_{i}"] = match_id * 100 + i
        row[f"away_player_{i}"] = match_id * 100 + 50 + i
        row[f"home_player_y{i}"] = Y_442[i - 1]
        row[f"away_player_y{i}"] = Y_442[i - 1]
    for triple in ODDS_BOOKMAKERS:
        for col in triple:
            row[col] = np.nan
    for col, value in (odds or {"psh": 1.80, "psd": 3.60, "psa": 4.50}).items():
        row[col] = value
    return row


def make_bronze(matches: list[dict], home_rating: float = 70.0, away_rating: float = 65.0) -> dict[str, pd.DataFrame]:
    """Bronze completo: partidos, equipos, jugadores y un snapshot de
    atributos 30 días antes de cada partido para cada titular."""
    matches_df = pd.DataFrame(matches)
    players, attrs = [], []
    for m in matches:
        for side, rating in (("home", home_rating), ("away", away_rating)):
            for i in range(1, 12):
                pid = m[f"{side}_player_{i}"]
                players.append({"player_api_id": pid, "birthday": pd.Timestamp("1990-01-01"), "height": 180.0})
                is_gk = i == 1
                attrs.append({
                    "player_api_id": pid,
                    "date": m["date"] - pd.Timedelta(days=30),
                    "overall_rating": rating + i,
                    "reactions": 60, "sprint_speed": 30 if is_gk else 70, "strength": 65,
                    "finishing": 20 if is_gk else 60, "marking": 50,
                    "gk_reflexes": 80 if is_gk else 10, "gk_diving": 78 if is_gk else 10, "gk_handling": 75 if is_gk else 10,
                })
    teams = pd.DataFrame({"team_api_id": [1, 2], "team_long_name": ["Local FC", "Visitante FC"]})
    return {
        "matches": matches_df,
        "teams": teams,
        "players": pd.DataFrame(players).drop_duplicates("player_api_id"),
        "player_attributes": pd.DataFrame(attrs),
    }


def run_pipeline(bronze: dict[str, pd.DataFrame], min_gap: float | None = None):
    """Corre las etapas de transformación del DAG en memoria."""
    from include.src import transform

    prepared, _, _ = transform.prepare_matches(bronze["matches"], bronze["teams"])
    lineups, _ = transform.build_lineup_features(prepared, bronze["players"], bronze["player_attributes"])
    with_target = transform.define_underdog_and_target(prepared)
    kwargs = {} if min_gap is None else {"min_gap": min_gap}
    valid, _, _ = transform.filter_valid_underdogs(with_target, **kwargs)
    return transform.build_silver(valid, lineups)


@pytest.fixture
def small_bronze() -> dict[str, pd.DataFrame]:
    """Cuatro partidos válidos (favorito claro) con resultados distintos."""
    return make_bronze([
        make_match(1, "2012-09-01", home_goals=2, away_goals=0, odds={"psh": 1.50, "psd": 4.00, "psa": 7.00}),   # gana favorito local
        make_match(2, "2012-09-08", home_goals=0, away_goals=1, odds={"psh": 1.60, "psd": 3.80, "psa": 6.00}),   # gana underdog visitante
        make_match(3, "2012-09-15", home_goals=1, away_goals=1, odds={"psh": 5.00, "psd": 3.70, "psa": 1.70}),   # empate
        make_match(4, "2012-09-22", home_goals=3, away_goals=1, odds={"psh": 4.50, "psd": 3.60, "psa": 1.80}),   # gana underdog local
    ])


@pytest.fixture
def silver_frame(small_bronze) -> pd.DataFrame:
    silver, _ = run_pipeline(small_bronze)
    return silver
