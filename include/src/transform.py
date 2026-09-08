"""Capa plata: convierte la European Soccer Database en el CSV final,
una fila por partido.

Una fila es **un partido** con (a) cuotas pre-partido convertidas en
probabilidades implícitas normalizadas, (b) features construidos a partir de
los **atributos intrínsecos de cada uno de los 22 jugadores que efectivamente
fueron titulares**, tomados de su último snapshot ANTERIOR a la fecha del
partido, y (c) el resultado real, para poder evaluar si ganó el no favorito.

Decisiones de diseño (las que hay que poder defender):

1. **Nada de promedios de plantel.** Los features salen de la alineación
   titular real de ese partido, no del promedio de los 30+ jugadores del
   club. Cada columna se puede rastrear a jugadores concretos: el arquero
   titular, el mejor jugador de la cancha, el eslabón más débil, el más
   rápido, el mejor definidor, la línea defensiva que salió a jugar.
2. **Sin fuga de información temporal.** Los atributos se cruzan con
   `merge_asof(..., direction="backward", allow_exact_matches=False)`: para
   cada jugador se toma su snapshot más reciente ESTRICTAMENTE anterior al
   partido. Nunca entra un rating publicado después de que el partido se
   jugó.
3. **Probabilidades, no cuotas crudas.** Se invierte cada cuota, se suma el
   overround de la casa y se normaliza para que las tres probabilidades
   sumen 1.0. El `overround` queda como columna (es el margen que cobra la
   casa y sirve para justificar la elección de casa).
4. **El empate es un `False`.** La pregunta es "¿ganará el no favorito?": si
   empató, no ganó. Poner nulo tiraría a la basura ~25% de las filas. La
   información del empate no se pierde: queda en `resultado_no_favorito`.
5. **La línea de cada titular sale de su coordenada Y en la cancha**, no de
   su posición nominal, así que es sensible a la formación real de ese
   partido.
"""

from __future__ import annotations

import logging
import sqlite3

import pandas as pd

from include.config import (
    EXCLUDED_LEAGUES,
    FINAL_DATASET_PATH,
    ODDS_BOOKMAKERS,
    PARTIDO_PAREJO_MAX_GAP,
    PROCESSED_DIR,
    SOCCER_DB_PATH,
)

logger = logging.getLogger(__name__)

HOME_PLAYER_COLS = [f"home_player_{i}" for i in range(1, 12)]
AWAY_PLAYER_COLS = [f"away_player_{i}" for i in range(1, 12)]
HOME_Y_COLS = [f"home_player_Y{i}" for i in range(1, 12)]
AWAY_Y_COLS = [f"away_player_Y{i}" for i in range(1, 12)]

# Atributos individuales que se leen de Player_Attributes (linaje FIFA/sofifa).
PLAYER_ATTRS = [
    "overall_rating",
    "potential",
    "reactions",
    "sprint_speed",
    "strength",
    "finishing",
    "marking",
    "standing_tackle",
    "gk_reflexes",
    "gk_diving",
    "gk_handling",
]

# Features por lado, todos derivados de jugadores individuales de la
# alineación titular. La clave es el nombre de la columna (sin prefijo
# home_/away_) y el valor, la explicación de por qué puede quedar nula.
SIDE_FEATURES = {
    # el arquero titular concreto
    "gk_overall": "Partido sin slot de arquero identificable (ninguno de los 11 titulares tiene coordenada Y de arquero) o arquero titular sin snapshot de atributos previo al partido.",
    "gk_reflexes": "Idem gk_overall.",
    "gk_diving": "Idem gk_overall.",
    "gk_handling": "Idem gk_overall.",
    # individuos destacados dentro del once
    "best_overall": "Ninguno de los 11 titulares tiene snapshot de atributos anterior a la fecha del partido.",
    "top3_overall": "Idem best_overall.",
    "worst_overall": "Idem best_overall.",
    "overall_std": "Idem best_overall, o menos de 2 titulares con atributos (la desviación necesita al menos 2).",
    "xi_overall_mean": "Idem best_overall.",
    "fastest_sprint_speed": "Ningún titular de campo con atributos previos (los arqueros no tienen sprint_speed cargado).",
    "best_finishing": "Idem fastest_sprint_speed.",
    "best_reactions": "Idem best_overall.",
    "best_marking": "Idem fastest_sprint_speed.",
    "strongest_strength": "Idem best_overall.",
    # lineas segun la formacion real de ese partido
    "def_overall": "La formación de ese partido no tiene titulares clasificados en esa línea según su coordenada Y, o ninguno tiene atributos previos.",
    "mid_overall": "Idem def_overall.",
    "att_overall": "Idem def_overall.",
    # bio de los titulares
    "xi_age_mean": "Titular sin fecha de nacimiento cargada en la tabla Player.",
    "xi_height_mean": "Titular sin altura cargada en la tabla Player.",
    # control de calidad de la propia fila
    "xi_sin_atributos": "Nunca nula: cuenta cuántos de los 11 titulares no tenían snapshot previo (0 en el 99,9% de las filas).",
    "formacion": "Nunca nula: forma de la alineación (defensores-mediocampistas-delanteros) según coordenadas Y.",
}

# Diferencias local - visitante. Cada una hereda nulo si falta cualquiera de
# los dos lados.
GAP_FEATURES = [
    "xi_overall_mean",
    "top3_overall",
    "worst_overall",
    "gk_overall",
    "def_overall",
    "mid_overall",
    "att_overall",
    "fastest_sprint_speed",
    "best_finishing",
    "xi_age_mean",
]

# Las mismas diferencias pero orientadas a la pregunta: no favorito - favorito.
# Un valor positivo significa que el underdog es superior en esa dimensión.
UNDERDOG_GAP_FEATURES = [
    "xi_overall_mean",
    "top3_overall",
    "gk_overall",
    "fastest_sprint_speed",
]

NULL_REASONS = {
    "prob_home": "Nunca nula: solo entran partidos con las 3 cuotas completas de al menos una casa.",
    "prob_draw": "Idem prob_home.",
    "prob_away": "Idem prob_home.",
    "overround": "Idem prob_home.",
    "odds_home": "Idem prob_home.",
    "odds_draw": "Idem prob_home.",
    "odds_away": "Idem prob_home.",
    "odds_source": "Idem prob_home.",
    "equipo_favorito": "Nula solo si local y visitante tienen exactamente la misma probabilidad implícita (no hay favorito definible).",
    "prob_favorito": "Idem equipo_favorito.",
    "prob_no_favorito": "Idem equipo_favorito.",
    "gano_no_favorito": "Columna objetivo: nula solo cuando no hay favorito definible (probabilidades idénticas).",
    "resultado_no_favorito": "Idem gano_no_favorito.",
    "es_partido_parejo": "Idem equipo_favorito.",
    **{
        f"{side}_{feature}": reason
        for side in ("home", "away")
        for feature, reason in SIDE_FEATURES.items()
    },
    **{
        f"{feature}_gap": "Nula si falta el valor del local o del visitante (ver home_/away_ de esta misma métrica)."
        for feature in GAP_FEATURES
    },
    **{
        f"nofav_{feature}_gap": "Nula si falta el valor de cualquiera de los dos lados, o si no hay favorito definible."
        for feature in UNDERDOG_GAP_FEATURES
    },
    "prob_gap": "Nunca nula: se deriva de las probabilidades implícitas, siempre presentes.",
}


def _connect() -> sqlite3.Connection:
    if not SOCCER_DB_PATH.exists():
        raise FileNotFoundError(
            f"Falta {SOCCER_DB_PATH}. Corré include/src/extract_soccer_db.py primero."
        )
    return sqlite3.connect(str(SOCCER_DB_PATH))


def load_matches(con: sqlite3.Connection) -> pd.DataFrame:
    """Partidos con cuotas completas y alineación titular completa, más las
    probabilidades implícitas normalizadas y la columna objetivo."""
    odds_cols = [c for triple in ODDS_BOOKMAKERS for c in triple]
    cols = [
        "match_api_id",
        "season",
        "stage",
        "date",
        "home_team_api_id",
        "away_team_api_id",
        "home_team_goal",
        "away_team_goal",
    ] + HOME_PLAYER_COLS + AWAY_PLAYER_COLS + HOME_Y_COLS + AWAY_Y_COLS + odds_cols

    matches = pd.read_sql(
        f"""SELECT l.name AS liga, c.name AS pais, {','.join('m.' + c for c in cols)}
            FROM Match m
            JOIN League l ON l.id = m.league_id
            JOIN Country c ON c.id = m.country_id""",
        con,
    )
    matches["date"] = pd.to_datetime(matches["date"])
    n_total = len(matches)

    matches = matches[~matches["liga"].isin(EXCLUDED_LEAGUES)]
    n_ligas = len(matches)

    xi_completo = matches[HOME_PLAYER_COLS + AWAY_PLAYER_COLS].notna().all(axis=1)
    matches = matches[xi_completo]
    n_xi = len(matches)

    matches = _attach_odds(matches)
    matches = matches[matches["odds_home"].notna()]
    n_final = len(matches)

    logger.info(
        "Filtros de inclusión: %d partidos en la base -> %d tras excluir ligas sin cuotas "
        "(%s) -> %d con alineación titular completa -> %d con cuotas 1X2 completas.",
        n_total, n_ligas, ", ".join(EXCLUDED_LEAGUES), n_xi, n_final,
    )

    # equipos por nombre (para que el CSV sea legible, el join es por id)
    teams = pd.read_sql("SELECT team_api_id, team_long_name FROM Team", con)
    for side in ("home", "away"):
        matches = matches.merge(
            teams.rename(
                columns={
                    "team_api_id": f"{side}_team_api_id",
                    "team_long_name": f"equipo_{'local' if side == 'home' else 'visitante'}",
                }
            ),
            on=f"{side}_team_api_id",
            how="left",
        )

    matches = _add_probabilities(matches)
    matches = _add_target(matches)
    return matches


def _attach_odds(matches: pd.DataFrame) -> pd.DataFrame:
    """Elige UNA casa de apuestas por fila, según el orden de preferencia de
    `ODDS_BOOKMAKERS`, y registra cuál se usó."""
    matches = matches.copy()
    matches["odds_home"] = pd.NA
    matches["odds_draw"] = pd.NA
    matches["odds_away"] = pd.NA
    matches["odds_source"] = pd.NA

    for home_col, draw_col, away_col in ODDS_BOOKMAKERS:
        triple = [home_col, draw_col, away_col]
        if not set(triple).issubset(matches.columns):
            continue
        fillable = matches["odds_home"].isna() & matches[triple].notna().all(axis=1)
        matches.loc[fillable, ["odds_home", "odds_draw", "odds_away"]] = matches.loc[
            fillable, triple
        ].values
        matches.loc[fillable, "odds_source"] = home_col[:-1]

    for col in ("odds_home", "odds_draw", "odds_away"):
        matches[col] = pd.to_numeric(matches[col])
    return matches


def _add_probabilities(matches: pd.DataFrame) -> pd.DataFrame:
    """Probabilidades implícitas normalizadas: 1/cuota dividido el overround."""
    matches = matches.copy()
    inverse = 1 / matches[["odds_home", "odds_draw", "odds_away"]]
    matches["overround"] = inverse.sum(axis=1)
    matches["prob_home"] = inverse["odds_home"] / matches["overround"]
    matches["prob_draw"] = inverse["odds_draw"] / matches["overround"]
    matches["prob_away"] = inverse["odds_away"] / matches["overround"]
    matches["prob_gap"] = matches["prob_home"] - matches["prob_away"]
    return matches


def _add_target(matches: pd.DataFrame) -> pd.DataFrame:
    """Favorito por probabilidad implícita y columna objetivo.

    Un empate cuenta como `False`: el no favorito no ganó. El detalle del
    empate se conserva en `resultado_no_favorito`.
    """
    matches = matches.copy()
    matches["resultado_ft"] = "D"
    matches.loc[matches["home_team_goal"] > matches["away_team_goal"], "resultado_ft"] = "H"
    matches.loc[matches["home_team_goal"] < matches["away_team_goal"], "resultado_ft"] = "A"

    hay_favorito = matches["prob_home"] != matches["prob_away"]
    favorito_local = hay_favorito & (matches["prob_home"] > matches["prob_away"])
    favorito_visitante = hay_favorito & (matches["prob_home"] < matches["prob_away"])

    matches["equipo_favorito"] = pd.NA
    matches.loc[favorito_local, "equipo_favorito"] = "local"
    matches.loc[favorito_visitante, "equipo_favorito"] = "visitante"

    matches["prob_favorito"] = matches[["prob_home", "prob_away"]].max(axis=1).where(hay_favorito)
    matches["prob_no_favorito"] = matches[["prob_home", "prob_away"]].min(axis=1).where(hay_favorito)

    gano_no_favorito = (favorito_local & (matches["resultado_ft"] == "A")) | (
        favorito_visitante & (matches["resultado_ft"] == "H")
    )
    matches["gano_no_favorito"] = gano_no_favorito.where(hay_favorito)

    matches["resultado_no_favorito"] = pd.NA
    matches.loc[hay_favorito & gano_no_favorito, "resultado_no_favorito"] = "gano"
    matches.loc[hay_favorito & (matches["resultado_ft"] == "D"), "resultado_no_favorito"] = "empato"
    matches.loc[
        hay_favorito & ~gano_no_favorito & (matches["resultado_ft"] != "D"),
        "resultado_no_favorito",
    ] = "perdio"

    matches["es_partido_parejo"] = (
        matches["prob_gap"].abs() < PARTIDO_PAREJO_MAX_GAP
    ).where(hay_favorito)
    return matches


def load_lineup_attributes(matches: pd.DataFrame, con: sqlite3.Connection) -> pd.DataFrame:
    """Formato largo: una fila por (partido, lado, puesto) con los atributos
    intrínsecos de ese jugador vigentes ANTES del partido."""
    frames = []
    for side, player_cols, y_cols in (
        ("home", HOME_PLAYER_COLS, HOME_Y_COLS),
        ("away", AWAY_PLAYER_COLS, AWAY_Y_COLS),
    ):
        players = matches.melt(
            id_vars=["match_api_id", "date"],
            value_vars=player_cols,
            var_name="slot",
            value_name="player_api_id",
        )
        players["slot_n"] = players["slot"].str.extract(r"(\d+)$").astype(int)

        coords = matches.melt(
            id_vars=["match_api_id"],
            value_vars=y_cols,
            var_name="y_slot",
            value_name="y",
        )
        coords["slot_n"] = coords["y_slot"].str.extract(r"(\d+)$").astype(int)

        side_lineup = players.merge(
            coords[["match_api_id", "slot_n", "y"]], on=["match_api_id", "slot_n"]
        )
        side_lineup["side"] = side
        frames.append(
            side_lineup[["match_api_id", "date", "side", "slot_n", "player_api_id", "y"]]
        )

    lineups = pd.concat(frames, ignore_index=True)
    lineups["player_api_id"] = lineups["player_api_id"].astype("int64")
    lineups["line"] = pd.cut(
        lineups["y"],
        bins=[-1, 1, 3, 7, 99],
        labels=["gk", "def", "mid", "att"],
    ).astype(str)

    attrs = pd.read_sql(
        f"SELECT player_api_id, date, {','.join(PLAYER_ATTRS)} FROM Player_Attributes",
        con,
    )
    attrs["date"] = pd.to_datetime(attrs["date"])

    # merge_asof exige ambos lados ordenados por la clave temporal.
    # allow_exact_matches=False evita tomar un snapshot publicado el mismo
    # día del partido (podría ser posterior al pitazo inicial).
    lineups = pd.merge_asof(
        lineups.sort_values("date"),
        attrs.sort_values("date"),
        on="date",
        by="player_api_id",
        direction="backward",
        allow_exact_matches=False,
    )

    bio = pd.read_sql("SELECT player_api_id, birthday, height FROM Player", con)
    bio["birthday"] = pd.to_datetime(bio["birthday"])
    lineups = lineups.merge(bio, on="player_api_id", how="left")
    lineups["age"] = (lineups["date"] - lineups["birthday"]).dt.days / 365.25

    sin_attrs = lineups["overall_rating"].isna().mean()
    logger.info(
        "Alineaciones: %d filas (22 por partido). Titulares sin snapshot previo de atributos: %.2f%%.",
        len(lineups), sin_attrs * 100,
    )
    return lineups


def build_player_features(lineups: pd.DataFrame) -> pd.DataFrame:
    """Colapsa los 11 titulares de cada lado en features individuales.

    Nada acá es un promedio de plantel: cada columna sale de jugadores
    concretos que salieron a la cancha (el arquero titular, el mejor, el
    peor, el más rápido, la línea defensiva de esa formación).
    """
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

    # los 3 mejores individuos del once (no el promedio de los 11)
    top3 = (
        lineups.sort_values("overall_rating", ascending=False)
        .groupby(["match_api_id", "side"])["overall_rating"]
        .apply(lambda s: s.head(3).mean())
        .rename("top3_overall")
    )
    features = features.join(top3)

    # El arquero titular concreto. En 3 de 39.388 alineaciones las
    # coordenadas vienen en cero y dos titulares caen en la franja de
    # arquero; en ese caso se toma el que tiene mejores reflejos (un arquero
    # real tiene gk_* muy por encima de un jugador de campo) en vez de
    # promediar dos jugadores, que sería un valor sin sentido.
    # `drop_duplicates` deja una fila entera (un jugador), a diferencia de
    # `groupby().first()`, que tomaría el primer valor no nulo de cada
    # columna por separado y podría mezclar datos de dos jugadores.
    gk = (
        lineups[lineups["line"] == "gk"]
        .sort_values("gk_reflexes", ascending=False)
        .drop_duplicates(subset=["match_api_id", "side"], keep="first")
        .set_index(["match_api_id", "side"])[
            ["overall_rating", "gk_reflexes", "gk_diving", "gk_handling"]
        ]
        .rename(columns={"overall_rating": "gk_overall"})
    )
    features = features.join(gk)

    # cada linea segun la formacion real de ese partido.
    # `reindex` deja exactamente las tres lineas reales: si algun titular
    # quedo sin clasificar, `line` vale el string "nan" y el `unstack`
    # crearia una columna espuria (`home_nan`/`away_nan`) casi toda nula.
    # Tambien garantiza las tres columnas aunque una linea no aparezca en
    # ninguna formacion, igual que el guard de `shape` mas abajo.
    by_line = (
        lineups[lineups["line"] != "gk"]
        .groupby(["match_api_id", "side", "line"])["overall_rating"]
        .mean()
        .unstack("line")
        .reindex(columns=["def", "mid", "att"])
        .rename(columns={"def": "def_overall", "mid": "mid_overall", "att": "att_overall"})
    )
    features = features.join(by_line)

    # forma de la alineacion, contando titulares por linea
    shape = (
        lineups[lineups["line"] != "gk"]
        .groupby(["match_api_id", "side"])["line"]
        .value_counts()
        .unstack("line")
        .fillna(0)
        .astype(int)
    )
    for line in ("def", "mid", "att"):
        if line not in shape.columns:
            shape[line] = 0
    features["formacion"] = (
        shape["def"].astype(str) + "-" + shape["mid"].astype(str) + "-" + shape["att"].astype(str)
    )

    return features.reset_index()


def build_dataset() -> pd.DataFrame:
    with _connect() as con:
        matches = load_matches(con)
        lineups = load_lineup_attributes(matches, con)
        features = build_player_features(lineups)

    dataset = matches[
        [
            "match_api_id",
            "liga",
            "pais",
            "season",
            "stage",
            "date",
            "equipo_local",
            "equipo_visitante",
            "home_team_goal",
            "away_team_goal",
            "resultado_ft",
            "odds_source",
            "odds_home",
            "odds_draw",
            "odds_away",
            "overround",
            "prob_home",
            "prob_draw",
            "prob_away",
            "prob_gap",
            "equipo_favorito",
            "prob_favorito",
            "prob_no_favorito",
            "es_partido_parejo",
            "resultado_no_favorito",
            "gano_no_favorito",
        ]
    ].copy()

    for side, prefix in (("home", "home"), ("away", "away")):
        side_features = features[features["side"] == side].drop(columns=["side"])
        side_features = side_features.rename(
            columns={
                c: f"{prefix}_{c}" for c in side_features.columns if c != "match_api_id"
            }
        )
        dataset = dataset.merge(side_features, on="match_api_id", how="left")

    # diferencias local - visitante
    for feature in GAP_FEATURES:
        dataset[f"{feature}_gap"] = dataset[f"home_{feature}"] - dataset[f"away_{feature}"]

    # diferencias orientadas a la pregunta: no favorito - favorito
    no_fav_es_local = dataset["equipo_favorito"] == "visitante"
    for feature in UNDERDOG_GAP_FEATURES:
        home_values = dataset[f"home_{feature}"]
        away_values = dataset[f"away_{feature}"]
        dataset[f"nofav_{feature}_gap"] = (
            (home_values - away_values).where(no_fav_es_local, away_values - home_values)
        ).where(dataset["equipo_favorito"].notna())

    dataset = dataset.rename(
        columns={
            "match_api_id": "match_id",
            "date": "fecha",
            "season": "temporada",
            "stage": "jornada",
            "home_team_goal": "goles_local",
            "away_team_goal": "goles_visitante",
        }
    )
    dataset = dataset.sort_values("fecha").reset_index(drop=True)
    return dataset


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    dataset = build_dataset()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(FINAL_DATASET_PATH, index=False)
    logger.info("Escrito %s (%d filas, %d columnas)", FINAL_DATASET_PATH, *dataset.shape)


if __name__ == "__main__":
    main()
