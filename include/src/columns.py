"""Catálogo de columnas: la única fuente de verdad sobre qué es cada columna.

Para cada columna responde: qué mide, de dónde sale (fuente o calculada por
nosotros), con qué fórmula, si existiría al momento de predecir, si puede ser
feature y por qué, y por qué puede ser nula.

Lo usan:
- `transform.build_silver`, para armar Silver exactamente con estas columnas;
- `quality_check`, para fallar si aparece una columna no documentada, un nulo
  sin explicar o una columna con fuga;
- `split_features_target`, para construir X/y sin información del resultado;
- `python -m include.src.columns`, que regenera docs/data_dictionary.md y
  docs/column_candidates.{md,csv}.

MOMENTO DE LA PREDICCIÓN: después de publicarse las alineaciones oficiales
(~1 hora antes del partido) y antes del pitazo inicial. Una columna solo puede
ser feature si su valor existe en ese momento.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from include.config import TARGET_COLUMN, UNDERDOG_MIN_PROB_GAP
from include.src.semaforo import NOMBRE, zona

PRE = "pre-partido"
POST = "post-partido"


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    description: str
    dtype: str
    role: str  # identificador | metadata | auxiliar | feature | target | auditoria | descartada
    origin: str  # fuente | calculada
    source: str  # tabla/columna de origen o etapa que la calcula
    formula: str
    available: str  # pre-partido | post-partido
    decision: str  # ENTRA | TRANSFORMAR | SALE | TARGET | AUXILIAR | IDENTIFICADOR | SOLO AUDITORÍA
    zone: str  # semáforo para candidatas: verde | amarillo | rojo | — (no candidata)
    reason: str
    null_reason: str = ""  # vacío = nunca nula
    location: str = "silver"  # silver | audit | intermediate | no se genera

    @property
    def is_feature(self) -> bool:
        """Candidata a feature: existe antes del partido y se evaluó."""
        return self.role == "feature"

    @property
    def enters_model(self) -> bool:
        return self.is_feature and self.decision in ("ENTRA", "TRANSFORMAR")

    @property
    def leaks_outcome(self) -> bool:
        return self.available == POST and self.role != "target"


# -----------------------------------------------------------------------------
# Métricas por lado: se calculan sobre los 11 titulares de cada equipo con el
# último snapshot de atributos ESTRICTAMENTE anterior a la fecha del partido.
# nombre -> (qué mide, fórmula sobre los titulares, por qué puede faltar)
# -----------------------------------------------------------------------------

_SIN_SNAPSHOT = "ningún titular tiene snapshot de atributos anterior al partido"
_FORMACION_NULA = (
    "las coordenadas Y de los titulares de campo vienen vacías o en 0 en la fuente: no se puede "
    "reconstruir la formación (antes figuraba como un falso '0-0-0')"
)
_LINEA = (
    "ningún titular de ese equipo quedó en esa línea según su coordenada Y "
    "(coordenadas mal cargadas en la fuente)"
)

SIDE_METRICS: dict[str, tuple[str, str, str]] = {
    "xi_overall_mean": ("calidad media del once titular", "promedio de overall_rating de los 11 titulares", _SIN_SNAPSHOT),
    "top3_overall": ("calidad de las 3 figuras del once", "promedio de los 3 mayores overall_rating del once", _SIN_SNAPSHOT),
    "best_overall": ("calidad del mejor jugador en cancha", "máximo overall_rating del once", _SIN_SNAPSHOT),
    "worst_overall": ("el eslabón más débil del once", "mínimo overall_rating del once", _SIN_SNAPSHOT),
    "overall_std": ("dispersión del once (equipo parejo vs. dependiente de figuras)", "desvío estándar de overall_rating del once", "menos de 2 titulares con snapshot previo"),
    "gk_overall": ("calidad del arquero titular", "overall_rating del titular con Y=1 (si hay dos, el de mayor gk_reflexes)", "ningún titular tiene coordenada Y de arquero, o el arquero no tiene snapshot previo"),
    "gk_reflexes": ("reflejos del arquero titular", "gk_reflexes del arquero titular", "idem gk_overall"),
    "gk_diving": ("estirada del arquero titular", "gk_diving del arquero titular", "idem gk_overall"),
    "gk_handling": ("manejo de pelota del arquero titular", "gk_handling del arquero titular", "idem gk_overall"),
    "def_overall": ("calidad de la línea defensiva que salió a jugar", "promedio overall de titulares con 1 < Y <= 3", _LINEA),
    "mid_overall": ("calidad del mediocampo que salió a jugar", "promedio overall de titulares con 3 < Y <= 7", _LINEA),
    "att_overall": ("calidad de la línea de ataque que salió a jugar", "promedio overall de titulares con Y > 7", _LINEA),
    "fastest_sprint_speed": ("velocidad del jugador más rápido", "máximo sprint_speed del once", _SIN_SNAPSHOT),
    "best_finishing": ("definición del mejor definidor", "máximo finishing del once", _SIN_SNAPSHOT),
    "best_reactions": ("reacción (reactions) del jugador que mejor la tiene", "máximo reactions del once", _SIN_SNAPSHOT),
    "best_marking": ("marca del mejor marcador", "máximo marking del once", _SIN_SNAPSHOT),
    "strongest_strength": ("fuerza del jugador más fuerte", "máximo strength del once", _SIN_SNAPSHOT),
    "xi_age_mean": ("edad media del once (años)", "promedio de (fecha del partido - birthday) / 365,25", "titular sin fecha de nacimiento en la tabla player"),
    "xi_height_mean": ("altura media del once (cm)", "promedio de height de los 11 titulares", "titular sin altura en la tabla player"),
}

# Métricas que entran a Silver como diferencia underdog - favorito. Los
# subatributos del arquero no entran (hipótesis 3 del EDA).
GAP_METRICS = [m for m in SIDE_METRICS if m not in ("gk_reflexes", "gk_diving", "gk_handling")]

# -----------------------------------------------------------------------------
# Semáforo de cada columna candidata contra el target (consigna del TP2),
# medido sobre el Silver final: separación estandarizada si la columna es
# numérica, η² si es categórica. Regla de decisión:
#     amarillo o verde -> ENTRA al modelo
#     rojo             -> SALE del modelo (queda en Silver para análisis)
# tests/test_silver_dataset.py recalcula estos valores sobre los datos y falla
# si dejaron de coincidir: la tabla de candidatas no puede quedar vieja.
# -----------------------------------------------------------------------------

CANDIDATE_EVIDENCE: dict[str, tuple[str, float]] = {
    "jornada": ("separacion_estandarizada", 0.012),
    "liga": ("eta2", 0.0016),
    "prob_draw": ("separacion_estandarizada", 0.429),
    "equipo_favorito": ("eta2", 0.0016),
    "prob_no_favorito": ("separacion_estandarizada", 0.497),
    "nofav_xi_overall_mean_gap": ("separacion_estandarizada", 0.358),
    "nofav_top3_overall_gap": ("separacion_estandarizada", 0.329),
    "nofav_best_overall_gap": ("separacion_estandarizada", 0.307),
    "nofav_worst_overall_gap": ("separacion_estandarizada", 0.225),
    "nofav_overall_std_gap": ("separacion_estandarizada", -0.005),
    "nofav_gk_overall_gap": ("separacion_estandarizada", 0.160),
    "nofav_def_overall_gap": ("separacion_estandarizada", 0.337),
    "nofav_mid_overall_gap": ("separacion_estandarizada", 0.303),
    "nofav_att_overall_gap": ("separacion_estandarizada", 0.287),
    "nofav_fastest_sprint_speed_gap": ("separacion_estandarizada", 0.144),
    "nofav_best_finishing_gap": ("separacion_estandarizada", 0.218),
    "nofav_best_reactions_gap": ("separacion_estandarizada", 0.276),
    "nofav_best_marking_gap": ("separacion_estandarizada", 0.251),
    "nofav_strongest_strength_gap": ("separacion_estandarizada", 0.105),
    "nofav_xi_age_mean_gap": ("separacion_estandarizada", -0.012),
    "nofav_xi_height_mean_gap": ("separacion_estandarizada", 0.002),
    "nofav_formacion": ("eta2", 0.0004),
    "fav_formacion": ("eta2", 0.0013),
}

# Lo que agrega cada hipótesis o hallazgo del EDA a la decisión.
_CANDIDATE_NOTES = {
    "prob_no_favorito": "Es la línea de base del modelo: el mercado solo.",
    "prob_draw": "Cola larga (asimetría -1,3), pero la relación con el target es recta (brecha Spearman - Pearson 0,013): entra sin transformar.",
    "liga": "Hipótesis 4 (refutada): la tasa de victoria del underdog casi no cambia entre ligas.",
    "equipo_favorito": "La localía ya está en las probabilidades del mercado.",
    "nofav_xi_overall_mean_gap": "Hipótesis 2 (refutada): al controlar por prob_no_favorito la separación cae a 0,08 (rojo). Entra, pero la Entrega 3 tiene que medir si agrega algo sobre el modelo solo-mercado.",
    "nofav_top3_overall_gap": "Correlación 0,96 con nofav_best_overall_gap y 0,93 con nofav_xi_overall_mean_gap: redundancia a resolver en la Entrega 3.",
    "nofav_best_overall_gap": "Correlación 0,96 con nofav_top3_overall_gap: redundancia a resolver en la Entrega 3.",
    "nofav_gk_overall_gap": "Hipótesis 3: los subatributos del arquero salen por redundancia; el propio gk_overall tampoco separa.",
    "nofav_formacion": "12 categorías. Los mediapuntas (Y=8) cuentan como ataque: un 4-2-3-1 aparece como 4-2-4.",
}


def _fmt(valor: float, medida: str) -> str:
    return (f"{valor:.4f}" if medida == "eta2" else f"{valor:.3f}").replace(".", ",")


def _semaforo(name: str, base_reason: str) -> tuple[str, str, str]:
    """(zona, decisión, motivo) de una candidata según su evidencia."""
    medida, valor = CANDIDATE_EVIDENCE[name]
    zone = zona(medida, valor)
    decision = "SALE" if zone == "rojo" else "ENTRA"
    consecuencia = "no va al modelo; queda en Silver para análisis" if decision == "SALE" else "entra al modelo"
    reason = f"{base_reason} Contra el target: {NOMBRE[medida]} = {_fmt(valor, medida)} ({zone}), {consecuencia}."
    if name in _CANDIDATE_NOTES:
        reason += f" {_CANDIDATE_NOTES[name]}"
    return zone, decision, reason


def _candidate(name: str, description: str, dtype: str, origin: str, source: str, formula: str,
               base_reason: str, null_reason: str = "") -> ColumnSpec:
    zone, decision, reason = _semaforo(name, base_reason)
    return ColumnSpec(name, description, dtype, "feature", origin, source, formula, PRE, decision, zone, reason, null_reason)


def _gap_spec(metric: str) -> ColumnSpec:
    what, formula, why_null = SIDE_METRICS[metric]
    return _candidate(
        f"nofav_{metric}_gap",
        f"Ventaja del underdog en {what}. Positivo = el underdog es superior.",
        "decimal",
        "calculada",
        "build_lineup_features + build_silver_dataset",
        f"underdog - favorito, donde cada lado = {formula}",
        "Existe al publicarse las alineaciones: atributos con snapshot anterior al partido.",
        f"nula si en el underdog o en el favorito {why_null}",
    )


# -----------------------------------------------------------------------------
# Silver: columnas en el orden en que se escriben.
# -----------------------------------------------------------------------------

SILVER_COLUMNS: list[ColumnSpec] = [
    ColumnSpec("match_id", "Identificador del partido (clave primaria: una fila = un partido).", "entero", "identificador", "fuente", "match.match_api_id", "", PRE, "IDENTIFICADOR", "—", "Clave, no feature: su valor no dice nada del partido."),
    ColumnSpec("fecha", "Fecha del partido.", "fecha", "metadata", "fuente", "match.date", "", PRE, "AUXILIAR", "—", "Se conserva para separar train/test en el tiempo; no es feature."),
    ColumnSpec("temporada", "Temporada (ej. 2012/2013).", "texto", "metadata", "fuente", "match.season", "", PRE, "AUXILIAR", "—", "Se conserva para cortes temporales; como feature solo identificaría la época."),
    _candidate("jornada", "Número de fecha dentro de la temporada.", "entero", "fuente", "match.stage", "", "Se conoce antes del partido."),
    _candidate("liga", "Liga del partido.", "categórica", "fuente", "league.name", "", "Se conoce antes del partido."),
    ColumnSpec("odds_source", "Casa de apuestas de la que salen las cuotas de la fila (PS = Pinnacle, B365 = Bet365, BW = bwin).", "texto", "metadata", "calculada", "prepare_matches", "primera casa de ODDS_BOOKMAKERS con las 3 cuotas completas", PRE, "AUXILIAR", "—", "Trazabilidad. No es feature: está confundida con la época (B365 hasta 2011/12, PS desde 2012/13)."),
    ColumnSpec("prob_home", "Probabilidad implícita normalizada de victoria local.", "decimal", "auxiliar", "calculada", "prepare_matches", "(1 / odds_home) / overround", PRE, "AUXILIAR", "—", "Define al favorito y valida prob_home + prob_draw + prob_away = 1. Como feature es redundante con prob_favorito/prob_no_favorito + equipo_favorito."),
    _candidate("prob_draw", "Probabilidad implícita normalizada de empate.", "decimal", "calculada", "prepare_matches", "(1 / odds_draw) / overround", "Precio de mercado anterior al partido."),
    ColumnSpec("prob_away", "Probabilidad implícita normalizada de victoria visitante.", "decimal", "auxiliar", "calculada", "prepare_matches", "(1 / odds_away) / overround", PRE, "AUXILIAR", "—", "Idem prob_home."),
    _candidate("equipo_favorito", "Qué equipo es el favorito: 'local' o 'visitante'.", "categórica", "calculada", "define_underdog_and_target", "'local' si prob_home > prob_away, 'visitante' si prob_home < prob_away", "Sale de las cuotas pre-partido."),
    ColumnSpec("prob_favorito", "Probabilidad implícita de victoria del favorito.", "decimal", "auxiliar", "calculada", "define_underdog_and_target", "max(prob_home, prob_away)", PRE, "AUXILIAR", "—", f"Define el umbral (prob_favorito - prob_no_favorito > {UNDERDOG_MIN_PROB_GAP}). Como feature es derivable: 1 - prob_draw - prob_no_favorito."),
    _candidate("prob_no_favorito", "Probabilidad implícita de victoria del underdog.", "decimal", "calculada", "define_underdog_and_target", "min(prob_home, prob_away)", "Precio de mercado anterior al partido."),
    *[_gap_spec(metric) for metric in GAP_METRICS],
    _candidate("nofav_formacion", "Formación del underdog como defensores-medios-delanteros (ej. 4-4-2).", "categórica", "calculada", "build_lineup_features", "conteo de titulares por línea según su coordenada Y", "Existe al publicarse la alineación.", _FORMACION_NULA),
    _candidate("fav_formacion", "Formación del favorito (mismo formato).", "categórica", "calculada", "build_lineup_features", "idem nofav_formacion", "Existe al publicarse la alineación.", _FORMACION_NULA),
    ColumnSpec(TARGET_COLUMN, "True si el underdog ganó el partido. Empate o derrota = False.", "booleano", "target", "calculada", "define_underdog_and_target", "(favorito local y ganó el visitante) o (favorito visitante y ganó el local)", POST, "TARGET", "—", "Es lo que se quiere predecir: nunca puede ser feature."),
]

# -----------------------------------------------------------------------------
# Auditoría: columnas que NO pueden estar en Silver pero sirven para rastrear.
# -----------------------------------------------------------------------------

AUDIT_COLUMNS: list[ColumnSpec] = [
    ColumnSpec("match_id", "Clave para unir con Silver.", "entero", "identificador", "fuente", "match.match_api_id", "", PRE, "IDENTIFICADOR", "—", "", location="audit"),
    ColumnSpec("equipo_local", "Nombre del equipo local.", "texto", "auditoria", "fuente", "team.team_long_name", "", PRE, "SOLO AUDITORÍA", "rojo", "Descriptiva: 299 equipos, no generaliza a partidos nuevos. Solo para leer resultados.", location="audit"),
    ColumnSpec("equipo_visitante", "Nombre del equipo visitante.", "texto", "auditoria", "fuente", "team.team_long_name", "", PRE, "SOLO AUDITORÍA", "rojo", "Idem equipo_local.", location="audit"),
    ColumnSpec("odds_home", "Cuota decimal de victoria local de odds_source.", "decimal", "auditoria", "fuente", "match.<casa>h", "", PRE, "SOLO AUDITORÍA", "rojo", "Derivable: prob_home = (1/odds_home)/overround. Se guarda para reconstruir las probabilidades.", location="audit"),
    ColumnSpec("odds_draw", "Cuota decimal de empate de odds_source.", "decimal", "auditoria", "fuente", "match.<casa>d", "", PRE, "SOLO AUDITORÍA", "rojo", "Idem odds_home.", location="audit"),
    ColumnSpec("odds_away", "Cuota decimal de victoria visitante de odds_source.", "decimal", "auditoria", "fuente", "match.<casa>a", "", PRE, "SOLO AUDITORÍA", "rojo", "Idem odds_home.", location="audit"),
    ColumnSpec("overround", "Margen de la casa: suma de las tres probabilidades sin normalizar.", "decimal", "auditoria", "calculada", "prepare_matches", "1/odds_home + 1/odds_draw + 1/odds_away", PRE, "SOLO AUDITORÍA", "rojo", "Mide a la casa, no al partido: depende casi solo de odds_source (B365 ~1,064, PS ~1,024) y su correlación con el target es -0,02.", location="audit"),
    ColumnSpec("goles_local", "Goles del local al final del partido.", "entero", "auditoria", "fuente", "match.home_team_goal", "", POST, "SOLO AUDITORÍA", "rojo", "FUGA: solo existe después del partido. Se usa únicamente para construir el target.", location="audit"),
    ColumnSpec("goles_visitante", "Goles del visitante al final del partido.", "entero", "auditoria", "fuente", "match.away_team_goal", "", POST, "SOLO AUDITORÍA", "rojo", "FUGA: idem goles_local.", location="audit"),
    ColumnSpec("resultado_ft", "Resultado final: H (local), D (empate), A (visitante).", "texto", "auditoria", "calculada", "define_underdog_and_target", "comparación goles_local vs goles_visitante", POST, "SOLO AUDITORÍA", "rojo", "FUGA: es el resultado del partido.", location="audit"),
    ColumnSpec("resultado_no_favorito", "Resultado del underdog: gano / empato / perdio.", "texto", "auditoria", "calculada", "define_underdog_and_target", "resultado_ft visto desde el underdog", POST, "SOLO AUDITORÍA", "rojo", "FUGA: contiene el target (gano <=> gano_no_favorito).", location="audit"),
    ColumnSpec("home_xi_sin_atributos", "Titulares locales sin snapshot de atributos previo.", "entero", "auditoria", "calculada", "build_lineup_features", "cantidad de titulares sin snapshot anterior al partido", PRE, "SOLO AUDITORÍA", "rojo", "Control de calidad de la fila (0 en casi todas), no describe el partido.", location="audit"),
    ColumnSpec("away_xi_sin_atributos", "Titulares visitantes sin snapshot de atributos previo.", "entero", "auditoria", "calculada", "build_lineup_features", "idem", PRE, "SOLO AUDITORÍA", "rojo", "Idem home_xi_sin_atributos.", location="audit"),
]


def _dropped(name: str, description: str, dtype: str, origin: str, source: str, formula: str,
             available: str, decision: str, reason: str, location: str) -> ColumnSpec:
    return ColumnSpec(name, description, dtype, "descartada", origin, source, formula, available,
                      decision, "rojo" if decision == "SALE" else "amarillo", reason, location=location)


def _side_columns() -> list[ColumnSpec]:
    specs = []
    for side, label in (("home", "local"), ("away", "visitante")):
        for metric, (what, formula, _) in SIDE_METRICS.items():
            if metric in ("gk_reflexes", "gk_diving", "gk_handling"):
                decision, reason = "SALE", "Hipótesis 3 (confirmada, verde): como diferencia underdog - favorito, su correlación con la de gk_overall es de 0,81 a 0,87. Repite la misma información."
            else:
                decision, reason = "TRANSFORMAR", f"Se reemplaza por nofav_{metric}_gap, que es como está planteada la pregunta. La diferencia local - visitante se recupera cambiando el signo, y el nivel de cada lado no agrega información sobre la diferencia (comparación de modelos, p = 0,42)."
            specs.append(_dropped(f"{side}_{metric}", f"{what[0].upper()}{what[1:]}, equipo {label}.", "decimal", "calculada",
                                  "build_lineup_features", formula, PRE, decision, reason, "intermediate"))
        specs.append(_dropped(f"{side}_formacion", f"Formación del equipo {label}.", "categórica", "calculada", "build_lineup_features",
                              "conteo de titulares por línea", PRE, "TRANSFORMAR", "Se orienta a underdog/favorito: nofav_formacion / fav_formacion.", "intermediate"))
    return specs


_LOCAL_VISITANTE_GAPS = ["xi_overall_mean", "top3_overall", "worst_overall", "gk_overall", "def_overall",
                         "mid_overall", "att_overall", "fastest_sprint_speed", "best_finishing", "xi_age_mean"]

DROPPED_COLUMNS: list[ColumnSpec] = [
    _dropped("pais", "País de la liga.", "texto", "fuente", "country.name", "", PRE, "SALE",
             "Redundante: relación 1 a 1 con liga. Ya no se extrae.", "no se genera"),
    _dropped("prob_gap", "prob_home - prob_away.", "decimal", "calculada", "prepare_matches", "prob_home - prob_away", PRE, "SALE",
             "Derivable exactamente de prob_home y prob_away.", "no se genera"),
    _dropped("es_partido_parejo", f"|prob_gap| < {UNDERDOG_MIN_PROB_GAP}.", "booleano", "calculada", "define_underdog_and_target", "", PRE, "SALE",
             "Quedaría constante (False): el umbral ahora filtra esas filas en vez de marcarlas.", "no se genera"),
    *_side_columns(),
    *[
        _dropped(f"{metric}_gap", f"Diferencia local - visitante de {metric}.", "decimal", "calculada", "build_silver_dataset",
                 f"home_{metric} - away_{metric}", PRE, "SALE",
                 f"Derivable exactamente: es nofav_{metric}_gap con el signo invertido cuando el underdog es visitante.", "no se genera")
        for metric in _LOCAL_VISITANTE_GAPS
    ],
]


# -----------------------------------------------------------------------------
# Listas derivadas del catálogo (no editar a mano).
# -----------------------------------------------------------------------------

SILVER_COLUMN_NAMES = [c.name for c in SILVER_COLUMNS]
# Candidatas: todo lo que existe antes del partido y se evaluó con el semáforo.
CANDIDATE_COLUMNS = [c.name for c in SILVER_COLUMNS if c.is_feature]
# Features del modelo: las candidatas que ENTRAN.
FEATURE_COLUMNS = [c.name for c in SILVER_COLUMNS if c.enters_model]
AUDIT_COLUMN_NAMES = [c.name for c in AUDIT_COLUMNS]
NULLABLE_SILVER_COLUMNS = {c.name: c.null_reason for c in SILVER_COLUMNS if c.null_reason}

# Columnas con información del resultado: no pueden aparecer en Silver. Se
# incluyen también los nombres crudos de la fuente, por si una consulta o un
# merge los arrastrara.
LEAKAGE_COLUMNS = sorted(
    {c.name for c in AUDIT_COLUMNS + DROPPED_COLUMNS if c.leaks_outcome}
    | {"home_team_goal", "away_team_goal", "goal", "shoton", "shotoff", "foulcommit", "card", "cross", "corner", "possession"}
)


def split_features_target(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """X (solo features pre-partido) e y (target). Falla si X quedaría con
    información del resultado."""
    leaked = [c for c in FEATURE_COLUMNS if c in LEAKAGE_COLUMNS or c == TARGET_COLUMN]
    if leaked:
        raise ValueError(f"Features con información del resultado: {leaked}")
    missing = [c for c in FEATURE_COLUMNS if c not in df.columns]
    if missing:
        raise KeyError(f"Faltan features en el DataFrame: {missing}")
    return df[FEATURE_COLUMNS].copy(), df[TARGET_COLUMN].astype(bool)


def catalog_frame() -> pd.DataFrame:
    """Todas las columnas consideradas, con su decisión."""
    seen = set()
    rows = []
    for spec in SILVER_COLUMNS + AUDIT_COLUMNS + DROPPED_COLUMNS:
        key = (spec.name, spec.location)
        if key in seen:
            continue
        seen.add(key)
        rows.append(asdict(spec))
    return pd.DataFrame(rows)


def leakage_audit_frame(silver_columns: list[str]) -> pd.DataFrame:
    """Control final de fuga para las columnas de un Silver concreto."""
    by_name = {c.name: c for c in SILVER_COLUMNS}
    rows = []
    for name in silver_columns:
        spec = by_name.get(name)
        if spec is None:
            rows.append({"columna": name, "origen": "SIN DOCUMENTAR", "momento_disponible": "?", "candidata": False, "feature": False,
                         "target": False, "leakage": True, "decision": "REVISAR"})
            continue
        rows.append({
            "columna": name,
            "origen": spec.origin,
            "momento_disponible": spec.available,
            "candidata": spec.is_feature,
            "feature": spec.enters_model,
            "target": spec.role == "target",
            "leakage": spec.leaks_outcome or name in LEAKAGE_COLUMNS or (spec.is_feature and spec.available != PRE),
            "decision": spec.decision,
        })
    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# Documentación generada desde el catálogo (python -m include.src.columns)
# -----------------------------------------------------------------------------


def _md_table(df: pd.DataFrame) -> str:
    def cell(value) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(df.columns) + " |", "|" + "---|" * len(df.columns)]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)


def _column_block(spec: ColumnSpec, nulls: int | None) -> str:
    feature = "sí" if spec.enters_model else ("candidata, no entra" if spec.is_feature else "no")
    null_text = f"sí: {spec.null_reason}" if spec.null_reason else "no"
    rows = [
        ("Descripción", spec.description),
        ("Tipo", spec.dtype),
        ("Rol", spec.role),
        ("Origen", "**calculada por nosotros**" if spec.origin == "calculada" else "fuente original"),
        ("De dónde sale", f"`{spec.source}`"),
        ("Fórmula", spec.formula or "—"),
        ("Disponible", spec.available),
        ("¿Entra al modelo?", f"{feature} ({spec.decision})"),
        ("Motivo", spec.reason),
        ("¿Puede ser nula?", null_text),
    ]
    if nulls is not None:
        rows.append(("Nulos en el Silver actual", str(nulls)))
    return f"### `{spec.name}`\n\n" + "\n".join(f"- **{k}**: {v}" for k, v in rows)


def render_data_dictionary(null_counts: dict[str, int] | None = None) -> str:
    null_counts = null_counts or {}
    summary = pd.DataFrame([
        {"columna": f"`{c.name}`", "rol": c.role, "origen": c.origin, "tipo": c.dtype, "disponible": c.available,
         "entra al modelo": "sí" if c.enters_model else "no", "nulos": null_counts.get(c.name, "—")}
        for c in SILVER_COLUMNS
    ])
    sections = [
        "# Diccionario de datos",
        "",
        "> Generado con `python -m include.src.columns` desde `include/src/columns.py`, el mismo catálogo que usa el "
        "pipeline para construir Silver y los quality checks. No editar a mano.",
        "",
        "**Momento de la predicción**: publicadas las alineaciones (~1 h antes del partido), antes del pitazo. "
        "*Pre-partido* = el valor existe en ese momento. **Calculada** = la construimos nosotros en el pipeline; "
        "**fuente** = viene tal cual de la European Soccer Database.",
        "",
        f"## Silver: `include/data/silver/underdog_dataset.parquet` ({len(SILVER_COLUMNS)} columnas)",
        "",
        _md_table(summary),
        "",
        *[_column_block(c, null_counts.get(c.name, 0) if null_counts else None) + "\n" for c in SILVER_COLUMNS],
        f"## Auditoría: `include/data/audit/match_audit.parquet` ({len(AUDIT_COLUMNS)} columnas)",
        "",
        "Mismas filas que Silver, unidas por `match_id`. Tiene lo que **no puede** ser feature: goles y resultados "
        "(post-partido), nombres de equipos y cuotas crudas. Sirve para rastrear y leer resultados, nunca para entrenar.",
        "",
        *[_column_block(c, None) + "\n" for c in AUDIT_COLUMNS[1:]],
    ]
    return "\n".join(sections)


def render_column_candidates() -> pd.DataFrame:
    frame = catalog_frame()
    return pd.DataFrame({
        "columna": frame["name"],
        "qué mide": frame["description"],
        "origen": frame["origin"],
        "tipo": frame["dtype"],
        "zona": frame["zone"],
        "decisión": frame["decision"],
        "¿existiría al predecir?": frame["available"].map({PRE: "SÍ", POST: "NO"}),
        "dónde queda": frame["location"],
        "motivo": frame["reason"],
    })


def write_docs(docs_dir, silver_path=None) -> None:
    from pathlib import Path

    docs_dir = Path(docs_dir)
    null_counts = None
    if silver_path is not None and Path(silver_path).exists():
        null_counts = pd.read_parquet(silver_path).isna().sum().astype(int).to_dict()
    (docs_dir / "data_dictionary.md").write_text(render_data_dictionary(null_counts), encoding="utf-8")

    candidates = render_column_candidates()
    candidates.to_csv(docs_dir / "column_candidates.csv", index=False, encoding="utf-8")
    counts = candidates["decisión"].value_counts()
    header = [
        "# Columnas candidatas",
        "",
        "> Generado con `python -m include.src.columns` desde `include/src/columns.py`. También en `column_candidates.csv`.",
        "",
        "Todas las columnas consideradas: las 82 del dataset de la Entrega 1 y las nuevas. **Zona** (semáforo): "
        "verde = entra sin reservas, amarillo = entra/se transforma con una reserva documentada, rojo = no puede "
        "o no debe ser feature, — = no es candidata (clave, auxiliar o target).",
        "",
        "Resumen: " + ", ".join(f"{k} {v}" for k, v in counts.items()) + f" (total {len(candidates)}).",
        "",
        "",
    ]
    (docs_dir / "column_candidates.md").write_text("\n".join(header) + _md_table(candidates) + "\n", encoding="utf-8")


def main() -> None:
    from include.config import INCLUDE_DIR, SILVER_DATASET_PATH

    docs_dir = INCLUDE_DIR.parent / "docs"
    docs_dir.mkdir(exist_ok=True)
    write_docs(docs_dir, SILVER_DATASET_PATH)
    print(f"Escritos data_dictionary.md, column_candidates.md y column_candidates.csv en {docs_dir}")


if __name__ == "__main__":
    main()
