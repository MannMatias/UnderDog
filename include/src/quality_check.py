"""Quality checks de Silver.

Dos tipos de resultado, a propósito separados:

- HARD CHECKS: si alguno falla, el dataset no sirve y el DAG se detiene (por
  ejemplo, un target nulo o una columna con fuga). Incluyen los 7 criterios de
  la Entrega 1 y los agregados en la Entrega 2.
- MÉTRICAS INFORMATIVAS: se reportan pero no hacen fallar la corrida (por
  ejemplo, el desbalance del target es una propiedad del problema, no un
  error).
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from include.config import FLOAT_DECIMALS, TARGET_COLUMN, UNDERDOG_MIN_PROB_GAP
from include.src.columns import CANDIDATE_COLUMNS, FEATURE_COLUMNS, LEAKAGE_COLUMNS, NULLABLE_SILVER_COLUMNS, SILVER_COLUMN_NAMES
from include.src.profiling import constant_columns, numeric_skewness, target_distribution

logger = logging.getLogger(__name__)

# Criterios de la Entrega 1.
MIN_ROWS = 1000
MIN_COLS = 5
# Las probabilidades se guardan con FLOAT_DECIMALS decimales: una resta o una
# suma de valores redondeados puede correrse hasta 1e-4 del valor exacto.
ROUNDING_TOLERANCE = 10 ** -FLOAT_DECIMALS
PROB_SUM_TOLERANCE = 1e-3
# Con cuotas de mercado la mejor columna sola llega a AUC ~0,65. Una columna
# que sola separe el target con AUC > 0,90 casi seguro codifica el resultado.
MAX_SINGLE_FEATURE_AUC = 0.90


@dataclass
class Check:
    name: str
    passed: bool
    detail: str
    entrega: int


def _check(name: str, entrega: int, fn) -> Check:
    """Corre un check; si explota (ej. falta una columna), cuenta como falla."""
    try:
        passed, detail = fn()
    except Exception as exc:  # noqa: BLE001 - el detalle va al reporte
        passed, detail = False, f"error al evaluar: {type(exc).__name__}: {exc}"
    return Check(name, bool(passed), detail, entrega)


def single_feature_auc(values: pd.Series, target: pd.Series) -> float:
    """AUC de una sola columna numérica como score (Mann-Whitney), en su
    orientación más favorable: max(AUC, 1 - AUC)."""
    mask = values.notna()
    ranks = values[mask].rank()
    y = target[mask].astype(bool)
    n_pos, n_neg = int(y.sum()), int((~y).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    auc = (ranks[y].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)
    return float(max(auc, 1 - auc))


def _season_window_ok(df: pd.DataFrame) -> tuple[bool, str]:
    fecha = pd.to_datetime(df["fecha"])
    start_year = df["temporada"].str[:4].astype(int)
    window_start = pd.to_datetime(start_year.astype(str) + "-07-01")
    window_end = pd.to_datetime((start_year + 1).astype(str) + "-06-30")
    outside = (fecha < window_start) | (fecha > window_end)
    future = fecha > pd.Timestamp.now()
    return (
        fecha.notna().all() and not outside.any() and not future.any(),
        f"nulas={int(fecha.isna().sum())}, fuera de su temporada={int(outside.sum())}, futuras={int(future.sum())}, rango {fecha.min().date()} a {fecha.max().date()}",
    )


def hard_checks(df: pd.DataFrame) -> list[Check]:
    prob_cols = ["prob_home", "prob_draw", "prob_away", "prob_favorito", "prob_no_favorito"]
    columns_with_nulls = df.columns[df.isna().any()].tolist()
    undocumented_nulls = [c for c in columns_with_nulls if c not in NULLABLE_SILVER_COLUMNS]
    dtype_kinds = df.dtypes.astype(str).nunique()

    def underdog_defined():
        fav = df["equipo_favorito"]
        valid_label = fav.isin(["local", "visitante"])
        consistent = np.where(fav == "local", df["prob_favorito"] == df["prob_home"], df["prob_favorito"] == df["prob_away"])
        ordered = df["prob_favorito"] > df["prob_no_favorito"]
        ok = valid_label.all() and bool(consistent.all()) and ordered.all()
        return ok, f"filas sin underdog={int((~valid_label).sum())}, favorito inconsistente con probs={int((~consistent).sum())}, prob_favorito<=prob_no_favorito={int((~ordered).sum())}"

    def threshold_respected():
        gap = df["prob_favorito"] - df["prob_no_favorito"]
        violations = gap <= UNDERDOG_MIN_PROB_GAP - ROUNDING_TOLERANCE
        return not violations.any(), f"umbral={UNDERDOG_MIN_PROB_GAP}, gap mínimo en Silver={gap.min():.4f}, violaciones={int(violations.sum())}"

    def probabilities_sum_to_one():
        total = df["prob_home"] + df["prob_draw"] + df["prob_away"]
        worst = float((total - 1).abs().max())
        return worst <= PROB_SUM_TOLERANCE, f"máximo |prob_home+prob_draw+prob_away-1| = {worst:.6f} (tolerancia {PROB_SUM_TOLERANCE})"

    def no_leakage():
        leaked = sorted(set(df.columns) & set(LEAKAGE_COLUMNS))
        target_as_feature = TARGET_COLUMN in FEATURE_COLUMNS or TARGET_COLUMN in CANDIDATE_COLUMNS
        return not leaked and not target_as_feature, f"columnas post-partido presentes={leaked or 'ninguna'}"

    def no_perfect_predictor():
        # Todas las candidatas, entren o no al modelo: una con el resultado adentro es un bug en cualquier caso.
        numeric = [c for c in CANDIDATE_COLUMNS if c in df.columns and pd.api.types.is_numeric_dtype(df[c])]
        aucs = {c: single_feature_auc(df[c], df[TARGET_COLUMN]) for c in numeric}
        best = max(aucs, key=lambda c: aucs[c])
        return aucs[best] <= MAX_SINGLE_FEATURE_AUC, f"mejor AUC de una sola feature: {best} = {aucs[best]:.3f} (máximo permitido {MAX_SINGLE_FEATURE_AUC})"

    def target_is_binary():
        values = set(df[TARGET_COLUMN].dropna().unique().tolist())
        return values <= {True, False} and pd.api.types.is_bool_dtype(df[TARGET_COLUMN]), f"valores={sorted(values)}, dtype={df[TARGET_COLUMN].dtype}"

    return [
        # --- Entrega 1 ---
        _check("clave_sin_duplicados", 1, lambda: (df["match_id"].is_unique, f"duplicados={int(df['match_id'].duplicated().sum())}")),
        _check("volumen_suficiente", 1, lambda: (len(df) > MIN_ROWS, f"filas={len(df)} (mínimo {MIN_ROWS})")),
        _check("ancho_suficiente", 1, lambda: (df.shape[1] >= MIN_COLS, f"columnas={df.shape[1]} (mínimo {MIN_COLS})")),
        _check("mezcla_de_tipos", 1, lambda: (dtype_kinds >= 2, f"tipos distintos={dtype_kinds}")),
        _check("nulos_conocidos", 1, lambda: (not undocumented_nulls, f"columnas con nulos sin motivo documentado={undocumented_nulls or 'ninguna'}")),
        _check("sin_columnas_vacias", 1, lambda: (not df.isna().all().any(), f"100% nulas={df.columns[df.isna().all()].tolist() or 'ninguna'}")),
        _check("clave_primaria_es_match_id", 1, lambda: ("match_id" in df.columns, "match_id presente" if "match_id" in df.columns else "falta match_id")),
        # --- Entrega 2 ---
        _check("columnas_documentadas", 2, lambda: (list(df.columns) == SILVER_COLUMN_NAMES, f"no documentadas={[c for c in df.columns if c not in SILVER_COLUMN_NAMES] or 'ninguna'}, faltantes={[c for c in SILVER_COLUMN_NAMES if c not in df.columns] or 'ninguna'}")),
        _check("target_sin_nulos", 2, lambda: (df[TARGET_COLUMN].notna().all(), f"nulos en {TARGET_COLUMN}={int(df[TARGET_COLUMN].isna().sum())}")),
        _check("target_binario", 2, target_is_binary),
        _check("underdog_definido", 2, underdog_defined),
        _check("umbral_underdog_respetado", 2, threshold_respected),
        _check("probabilidades_en_rango", 2, lambda: (df[prob_cols].ge(0).all().all() and df[prob_cols].le(1).all().all(), "todas en [0, 1]" if df[prob_cols].ge(0).all().all() and df[prob_cols].le(1).all().all() else "hay probabilidades fuera de [0, 1]")),
        _check("probabilidades_suman_uno", 2, probabilities_sum_to_one),
        _check("sin_columnas_de_fuga", 2, no_leakage),
        _check("sin_predictor_perfecto", 2, no_perfect_predictor),
        _check("fechas_validas", 2, lambda: _season_window_ok(df)),
    ]


def informative_metrics(df: pd.DataFrame) -> dict:
    skew = numeric_skewness(df)
    return {
        "shape": list(df.shape),
        "distribucion_target": target_distribution(df),
        "columnas_constantes": constant_columns(df),
        "nulos_por_columna": {c: int(n) for c, n in df.isna().sum().items() if n > 0},
        "asimetria_top5": skew.head(5).to_dict(),
        "odds_source": df["odds_source"].value_counts().to_dict(),
        "partidos_por_temporada": df["temporada"].value_counts().sort_index().to_dict(),
        "partidos_por_liga": df["liga"].value_counts().to_dict(),
        "equipo_favorito": df["equipo_favorito"].value_counts().to_dict(),
    }


def run_quality_checks(df: pd.DataFrame) -> dict:
    checks = hard_checks(df)
    return {
        "passed": all(c.passed for c in checks),
        "hard_checks": [asdict(c) for c in checks],
        "informativas": informative_metrics(df),
    }


def log_report(report: dict) -> None:
    for check in report["hard_checks"]:
        level = logging.INFO if check["passed"] else logging.ERROR
        logger.log(level, "[%s] (E%d) %s: %s", "OK" if check["passed"] else "FALLA", check["entrega"], check["name"], check["detail"])
    info = report["informativas"]
    logger.info("Informativo - shape: %s", info["shape"])
    logger.info("Informativo - distribución del target: %s", info["distribucion_target"])
    logger.info("Informativo - columnas constantes: %s", info["columnas_constantes"] or "ninguna")
    logger.info("Informativo - nulos: %s", info["nulos_por_columna"] or "ninguno")
    logger.info("Informativo - mayor asimetría: %s", info["asimetria_top5"])


def assert_quality(report: dict) -> None:
    failed = [c["name"] for c in report["hard_checks"] if not c["passed"]]
    if failed:
        raise ValueError(f"Silver no pasa los hard checks: {failed}. Ver el log de esta tarea.")
