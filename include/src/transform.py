"""De Bronze a Silver: reglas de negocio e ingeniería de features.

Funciones puras sobre DataFrames (no leen la base ni archivos), una por etapa
del DAG:

    prepare_matches            filtros de inclusión, una casa de apuestas por
                               partido y probabilidades implícitas normalizadas
    build_lineup_features      features de los 22 titulares, con el snapshot de
                               atributos ESTRICTAMENTE anterior al partido
    define_underdog_and_target favorito / underdog y la columna objetivo
    filter_valid_underdogs     saca los partidos sin underdog identificable
    build_silver               dataset final, sin columnas post-partido, más
                               un dataset de auditoría aparte

Decisiones que hay que poder defender:

1. Nada de promedios de plantel: los features salen de la alineación titular
   real de ese partido (el arquero titular, el mejor, el peor, la línea
   defensiva que salió a jugar...).
2. Sin fuga temporal: `merge_asof(direction="backward",
   allow_exact_matches=False)` toma, para cada titular, el snapshot más
   reciente estrictamente anterior a la fecha del partido; además se verifica.
3. Probabilidades, no cuotas: 1/cuota normalizado por el overround.
4. El empate es False: si empató, el underdog no ganó.
5. Los goles solo existen para construir el target: no llegan a Silver.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from include.config import (
    EXCLUDED_LEAGUES,
    FLOAT_DECIMALS,
    LINEUP_Y_BINS,
    LINEUP_Y_LABELS,
    MAX_PROB_EMPATE_IMPLICITA,
    ODDS_BOOKMAKERS,
    TARGET_COLUMN,
    UNDERDOG_MIN_PROB_GAP,
)
from include.src.columns import AUDIT_COLUMN_NAMES, GAP_METRICS, SILVER_COLUMN_NAMES

logger = logging.getLogger(__name__)

HOME_PLAYER_COLS = [f"home_player_{i}" for i in range(1, 12)]
AWAY_PLAYER_COLS = [f"away_player_{i}" for i in range(1, 12)]
HOME_Y_COLS = [f"home_player_y{i}" for i in range(1, 12)]
AWAY_Y_COLS = [f"away_player_y{i}" for i in range(1, 12)]

# Atributos de Player_Attributes que alimentan algún feature.
PLAYER_ATTRS = [
    "overall_rating",
    "reactions",
    "sprint_speed",
    "strength",
    "finishing",
    "marking",
    "gk_reflexes",
    "gk_diving",
    "gk_handling",
]


def _as_datetime(values: pd.Series) -> pd.Series:
    # Misma unidad en todos los lados: merge_asof no acepta claves con
    # resoluciones distintas (pandas 2 lee Parquet en ns, pandas 3 en us).
    return pd.to_datetime(values).astype("datetime64[ns]")


def _exclude(df: pd.DataFrame, keep: pd.Series, reason: str, excluded: list[pd.DataFrame]) -> pd.DataFrame:
    excluded.append(df.loc[~keep, ["match_api_id"]].assign(motivo=reason))
    return df[keep]


# -----------------------------------------------------------------------------
# prepare_matches
# -----------------------------------------------------------------------------


def select_bookmaker_odds(matches: pd.DataFrame) -> pd.DataFrame:
    """Elige UNA casa de apuestas por partido (la primera de ODDS_BOOKMAKERS
    con las tres cuotas completas) y registra cuál en `odds_source`."""
    matches = matches.copy()
    matches[["odds_home", "odds_draw", "odds_away"]] = np.nan
    matches["odds_source"] = None

    for home_col, draw_col, away_col in ODDS_BOOKMAKERS:
        triple = [home_col, draw_col, away_col]
        if not set(triple).issubset(matches.columns):
            continue
        fillable = matches["odds_home"].isna() & matches[triple].notna().all(axis=1)
        matches.loc[fillable, ["odds_home", "odds_draw", "odds_away"]] = matches.loc[fillable, triple].to_numpy(dtype=float)
        matches.loc[fillable, "odds_source"] = home_col[:-1].upper()
    return matches


def add_implied_probabilities(matches: pd.DataFrame) -> pd.DataFrame:
    """1/cuota de cada resultado, normalizado por el overround (margen de la
    casa) para que prob_home + prob_draw + prob_away = 1."""
    matches = matches.copy()
    inverse = 1 / matches[["odds_home", "odds_draw", "odds_away"]]
    matches["overround"] = inverse.sum(axis=1)
    matches["prob_home"] = inverse["odds_home"] / matches["overround"]
    matches["prob_draw"] = inverse["odds_draw"] / matches["overround"]
    matches["prob_away"] = inverse["odds_away"] / matches["overround"]
    return matches


def prepare_matches(matches: pd.DataFrame, teams: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Aplica los filtros de inclusión y calcula las probabilidades.

    Devuelve (partidos preparados, partidos excluidos con motivo, embudo de
    conteos). Un partido sin cuotas no puede definir favorito y uno sin
    alineación completa no tiene features de jugadores: en ambos casos la fila
    no puede responder la pregunta.
    """
    df = matches.rename(columns={"league_name": "liga"}).copy()
    df["date"] = _as_datetime(df["date"])
    excluded: list[pd.DataFrame] = []
    funnel = {"partidos_en_fuente": len(df)}

    df = _exclude(df, ~df["liga"].isin(EXCLUDED_LEAGUES), "liga_sin_cuotas", excluded)
    funnel["tras_excluir_ligas_sin_cuotas"] = len(df)

    df = _exclude(df, df[HOME_PLAYER_COLS + AWAY_PLAYER_COLS].notna().all(axis=1), "alineacion_incompleta", excluded)
    funnel["con_alineacion_titular_completa"] = len(df)

    df = select_bookmaker_odds(df)
    df = _exclude(df, df["odds_home"].notna(), "sin_cuotas_1x2", excluded)
    funnel["con_cuotas_1x2_completas"] = len(df)

    # La tripleta tiene que ser un mercado 1X2 coherente (ver config.py).
    df = _exclude(df, 1 / df["odds_draw"] <= MAX_PROB_EMPATE_IMPLICITA, "cuota_empate_incoherente", excluded)
    funnel["con_cuotas_coherentes"] = len(df)

    names = teams.set_index("team_api_id")["team_long_name"]
    df["equipo_local"] = df["home_team_api_id"].map(names)
    df["equipo_visitante"] = df["away_team_api_id"].map(names)

    df = add_implied_probabilities(df).reset_index(drop=True)
    logger.info(
        "Filtros de inclusión: %s. Ligas excluidas: %s. Tope de empate implícito: %.0f%%.",
        " -> ".join(f"{step}={n}" for step, n in funnel.items()),
        ", ".join(EXCLUDED_LEAGUES),
        MAX_PROB_EMPATE_IMPLICITA * 100,
    )
    return df, pd.concat(excluded, ignore_index=True), funnel


# -----------------------------------------------------------------------------
# build_lineup_features
# -----------------------------------------------------------------------------


def build_lineups(matches: pd.DataFrame) -> pd.DataFrame:
    """Formato largo: una fila por (partido, lado, puesto) con el jugador, su
    coordenada Y y la línea que ocupa según esa coordenada."""
    frames = []
    for side, player_cols, y_cols in (("home", HOME_PLAYER_COLS, HOME_Y_COLS), ("away", AWAY_PLAYER_COLS, AWAY_Y_COLS)):
        players = matches.melt(id_vars=["match_api_id", "date"], value_vars=player_cols, var_name="slot", value_name="player_api_id")
        players["slot_n"] = players["slot"].str.extract(r"(\d+)$", expand=False).astype(int)
        coords = matches.melt(id_vars=["match_api_id"], value_vars=y_cols, var_name="y_slot", value_name="y")
        coords["slot_n"] = coords["y_slot"].str.extract(r"(\d+)$", expand=False).astype(int)
        side_lineup = players.merge(coords[["match_api_id", "slot_n", "y"]], on=["match_api_id", "slot_n"])
        side_lineup["side"] = side
        frames.append(side_lineup[["match_api_id", "date", "side", "slot_n", "player_api_id", "y"]])

    lineups = pd.concat(frames, ignore_index=True)
    lineups["player_api_id"] = lineups["player_api_id"].astype("int64")
    # Un titular sin coordenada queda como "nan" y no cae en ninguna línea.
    lineups["line"] = pd.cut(lineups["y"], bins=list(LINEUP_Y_BINS), labels=list(LINEUP_Y_LABELS)).astype(str)
    return lineups


def attach_player_snapshots(lineups: pd.DataFrame, players: pd.DataFrame, player_attributes: pd.DataFrame) -> pd.DataFrame:
    """Agrega a cada titular su último snapshot de atributos ESTRICTAMENTE
    anterior al partido, más edad y altura."""
    attrs = player_attributes[["player_api_id", "date", *PLAYER_ATTRS]].rename(columns={"date": "snapshot_date"})
    attrs["snapshot_date"] = _as_datetime(attrs["snapshot_date"])
    attrs["player_api_id"] = attrs["player_api_id"].astype("int64")
    # La fuente repite 835 pares (jugador, fecha): siempre una fila completa y
    # otra con todos los atributos vacíos. Un snapshot vacío no es un
    # snapshot; si quedara, merge_asof podría elegirlo y el titular figuraría
    # "sin atributos" al azar.
    attrs = attrs[attrs[PLAYER_ATTRS].notna().any(axis=1)]

    # merge_asof exige ambos lados ordenados por la clave temporal (orden
    # estable: el resultado no depende del orden de llegada de las filas).
    # allow_exact_matches=False evita un snapshot del mismo día del partido,
    # que podría haberse publicado después del pitazo inicial.
    lineups = pd.merge_asof(
        lineups.sort_values(["date", "match_api_id", "side", "slot_n"], kind="mergesort"),
        attrs.sort_values(["snapshot_date", "player_api_id"], kind="mergesort"),
        left_on="date",
        right_on="snapshot_date",
        by="player_api_id",
        direction="backward",
        allow_exact_matches=False,
    )
    assert_snapshots_before_match(lineups)

    bio = players[["player_api_id", "birthday", "height"]].copy()
    bio["player_api_id"] = bio["player_api_id"].astype("int64")
    bio["birthday"] = _as_datetime(bio["birthday"])
    lineups = lineups.merge(bio, on="player_api_id", how="left")
    lineups["age"] = (lineups["date"] - lineups["birthday"]).dt.days / 365.25
    return lineups


def assert_snapshots_before_match(lineups: pd.DataFrame) -> None:
    """Falla si algún titular recibió atributos publicados el día del partido
    o después (sería fuga temporal)."""
    matched = lineups["snapshot_date"].notna()
    late = lineups.loc[matched, "snapshot_date"] >= lineups.loc[matched, "date"]
    if late.any():
        raise ValueError(f"Fuga temporal: {int(late.sum())} titulares con snapshot de atributos no anterior al partido.")


def aggregate_side_features(lineups: pd.DataFrame) -> pd.DataFrame:
    """Colapsa los 11 titulares de cada lado en features individuales: una
    fila por (partido, lado)."""
    grouped = lineups.groupby(["match_api_id", "side"])
    features = grouped.agg(
        best_overall=("overall_rating", "max"),
        worst_overall=("overall_rating", "min"),
        xi_overall_mean=("overall_rating", "mean"),
        overall_std=("overall_rating", "std"),
        best_reactions=("reactions", "max"),
        fastest_sprint_speed=("sprint_speed", "max"),
        strongest_strength=("strength", "max"),
        best_finishing=("finishing", "max"),
        best_marking=("marking", "max"),
        xi_age_mean=("age", "mean"),
        xi_height_mean=("height", "mean"),
        xi_sin_atributos=("overall_rating", lambda s: int(s.isna().sum())),
    )

    # Los 3 mejores individuos del once (no el promedio de los 11).
    top3 = (
        lineups.sort_values("overall_rating", ascending=False)
        .groupby(["match_api_id", "side"])["overall_rating"]
        .apply(lambda s: s.head(3).mean())
        .rename("top3_overall")
    )
    features = features.join(top3)

    # El arquero titular concreto. En unas pocas alineaciones las coordenadas
    # vienen en cero y dos titulares caen en la franja de arquero: se toma el
    # de mejores reflejos (un arquero real tiene gk_* muy por encima de un
    # jugador de campo) en vez de promediar dos jugadores. `drop_duplicates`
    # deja una fila entera (un jugador); `groupby().first()` mezclaría
    # columnas de jugadores distintos.
    gk = (
        lineups[lineups["line"] == "gk"]
        .sort_values("gk_reflexes", ascending=False)
        .drop_duplicates(subset=["match_api_id", "side"], keep="first")
        .set_index(["match_api_id", "side"])[["overall_rating", "gk_reflexes", "gk_diving", "gk_handling"]]
        .rename(columns={"overall_rating": "gk_overall"})
    )
    features = features.join(gk)

    # Cada línea según la formación real de ese partido. `reindex` deja
    # exactamente las tres líneas: un titular sin clasificar ("nan") crearía
    # una columna espuria, y garantiza las tres aunque una no aparezca.
    outfield = lineups[lineups["line"].isin(["def", "mid", "att"])]
    by_line = (
        outfield.groupby(["match_api_id", "side", "line"])["overall_rating"]
        .mean()
        .unstack("line")
        .reindex(columns=["def", "mid", "att"])
        .rename(columns={"def": "def_overall", "mid": "mid_overall", "att": "att_overall"})
    )
    features = features.join(by_line)

    # Forma de la alineación: titulares por línea (defensa-medio-ataque).
    shape = (
        outfield.groupby(["match_api_id", "side"])["line"]
        .value_counts()
        .unstack("line")
        .reindex(columns=["def", "mid", "att"])
        .fillna(0)
        .astype(int)
    )
    features["formacion"] = shape["def"].astype(str) + "-" + shape["mid"].astype(str) + "-" + shape["att"].astype(str)
    return features.reset_index()


def build_lineup_features(matches: pd.DataFrame, players: pd.DataFrame, player_attributes: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Features de los titulares en formato ancho: una fila por partido con
    columnas home_<métrica> y away_<métrica>."""
    lineups = build_lineups(matches)
    lineups = attach_player_snapshots(lineups, players, player_attributes)
    side_features = aggregate_side_features(lineups)

    wide = matches[["match_api_id"]]
    for side in ("home", "away"):
        part = side_features[side_features["side"] == side].drop(columns="side")
        part = part.rename(columns={c: f"{side}_{c}" for c in part.columns if c != "match_api_id"})
        wide = wide.merge(part, on="match_api_id", how="left")

    stats = {
        "titulares": len(lineups),
        "pct_titulares_sin_snapshot": round(float(lineups["overall_rating"].isna().mean() * 100), 3),
        "snapshot_mas_reciente_vs_partido_dias_min": int((lineups["date"] - lineups["snapshot_date"]).dt.days.min()),
    }
    logger.info(
        "Alineaciones: %d titulares (22 por partido). Sin snapshot previo de atributos: %.3f%%. "
        "El snapshot usado más cercano es de %d día(s) antes del partido.",
        stats["titulares"], stats["pct_titulares_sin_snapshot"], stats["snapshot_mas_reciente_vs_partido_dias_min"],
    )
    return wide, stats


# -----------------------------------------------------------------------------
# define_underdog_and_target / filter_valid_underdogs
# -----------------------------------------------------------------------------


def define_underdog_and_target(matches: pd.DataFrame) -> pd.DataFrame:
    """Favorito = equipo con mayor probabilidad implícita de ganar;
    underdog = el de menor. El empate no es un equipo: no participa.

    Si prob_home == prob_away no hay underdog: esas filas quedan con
    equipo_favorito y target nulos y las saca filter_valid_underdogs.
    """
    df = matches.copy()
    home_goals, away_goals = df["home_team_goal"], df["away_team_goal"]
    df["resultado_ft"] = np.select([home_goals > away_goals, home_goals < away_goals], ["H", "A"], default="D")

    favorito_local = df["prob_home"] > df["prob_away"]
    favorito_visitante = df["prob_home"] < df["prob_away"]
    hay_underdog = favorito_local | favorito_visitante

    df["equipo_favorito"] = pd.Series(np.where(favorito_local, "local", "visitante"), index=df.index).where(hay_underdog)
    df["prob_favorito"] = df[["prob_home", "prob_away"]].max(axis=1).where(hay_underdog)
    df["prob_no_favorito"] = df[["prob_home", "prob_away"]].min(axis=1).where(hay_underdog)

    gano = (favorito_local & (df["resultado_ft"] == "A")) | (favorito_visitante & (df["resultado_ft"] == "H"))
    df[TARGET_COLUMN] = gano.astype("boolean").where(hay_underdog, pd.NA)

    resultado = np.select([gano, df["resultado_ft"] == "D"], ["gano", "empato"], default="perdio")
    df["resultado_no_favorito"] = pd.Series(resultado, index=df.index).where(hay_underdog)
    return df


def underdog_gap(df: pd.DataFrame) -> pd.Series:
    """|prob_home - prob_away|: cuán claro es quién es el favorito."""
    return (df["prob_home"] - df["prob_away"]).abs()


def filter_valid_underdogs(df: pd.DataFrame, min_gap: float = UNDERDOG_MIN_PROB_GAP) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Deja solo partidos con un underdog identificable:
    |prob_home - prob_away| > min_gap (estricto). Con min_gap = 0 se sacan
    únicamente los empates exactos de probabilidad.
    """
    if min_gap < 0:
        raise ValueError("El umbral del underdog no puede ser negativo.")
    gap = underdog_gap(df)
    sin_underdog = df["equipo_favorito"].isna()
    parejo = ~sin_underdog & (gap <= min_gap)
    keep = ~sin_underdog & ~parejo

    excluded = pd.concat(
        [
            df.loc[sin_underdog, ["match_api_id"]].assign(motivo="sin_underdog_identificable"),
            df.loc[parejo, ["match_api_id"]].assign(motivo="partido_parejo"),
        ],
        ignore_index=True,
    )
    kept = df[keep].copy()
    kept[TARGET_COLUMN] = kept[TARGET_COLUMN].astype(bool)

    counts = {
        "entrada": len(df),
        "sin_underdog_identificable": int(sin_underdog.sum()),
        "partido_parejo": int(parejo.sum()),
        "salida": len(kept),
        "umbral": min_gap,
    }
    logger.info(
        "Underdog: %d partidos -> %d sin underdog (probabilidades iguales) -> %d parejos (gap <= %.3f) -> quedan %d.",
        counts["entrada"], counts["sin_underdog_identificable"], counts["partido_parejo"], min_gap, counts["salida"],
    )
    return kept.reset_index(drop=True), excluded, counts


# -----------------------------------------------------------------------------
# build_silver
# -----------------------------------------------------------------------------

_RENAMES = {
    "match_api_id": "match_id",
    "date": "fecha",
    "season": "temporada",
    "stage": "jornada",
    "home_team_goal": "goles_local",
    "away_team_goal": "goles_visitante",
}


def build_silver(valid: pd.DataFrame, lineup_features: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Arma (silver, auditoría).

    Silver tiene exactamente las columnas de `columns.SILVER_COLUMNS`: nada
    que se conozca recién después del partido. Goles, resultado y cuotas
    crudas van al dataset de auditoría, que se une por match_id.
    """
    df = valid.merge(lineup_features, on="match_api_id", how="left", validate="one_to_one")
    underdog_is_home = df["equipo_favorito"] == "visitante"

    for metric in GAP_METRICS:
        home, away = df[f"home_{metric}"], df[f"away_{metric}"]
        df[f"nofav_{metric}_gap"] = (home - away).where(underdog_is_home, away - home)
    df["nofav_formacion"] = df["home_formacion"].where(underdog_is_home, df["away_formacion"])
    df["fav_formacion"] = df["away_formacion"].where(underdog_is_home, df["home_formacion"])

    df = df.rename(columns=_RENAMES).sort_values(["fecha", "match_id"]).reset_index(drop=True)
    float_cols = df.select_dtypes(include="float").columns
    df[float_cols] = df[float_cols].round(FLOAT_DECIMALS)

    silver = df[SILVER_COLUMN_NAMES].copy()
    audit = df[AUDIT_COLUMN_NAMES].copy()
    return silver, audit
