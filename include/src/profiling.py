"""Perfil del dataset (Entrega 2) y tablas de evidencia.

- `dataset_profile`: shape, tipos, nulos, constantes, duplicados, distribución
  del target y asimetría de las numéricas.
- `threshold_sensitivity`: qué pasa con el dataset para cada umbral candidato
  del underdog. Es la evidencia detrás de UNDERDOG_MIN_PROB_GAP.
- `leakage_audit`: control final de fuga columna por columna.

Todo se calcula sobre los datos: nada de números escritos a mano.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from include.config import ODDS_BOOKMAKERS, TARGET_COLUMN, UNDERDOG_GAP_CANDIDATES
from include.src.columns import NULLABLE_SILVER_COLUMNS, leakage_audit_frame
from include.src.transform import underdog_gap

KEY_COLUMN = "match_id"
ROW_MEANING = "un partido"
# |asimetría| por encima de este valor se considera marcadamente asimétrica.
STRONG_SKEW = 1.0

# -----------------------------------------------------------------------------
# Perfil del dataset
# -----------------------------------------------------------------------------


def null_table(df: pd.DataFrame) -> pd.DataFrame:
    nulls = df.isna().sum()
    table = pd.DataFrame({"nulos": nulls, "pct_nulos": (nulls / len(df) * 100).round(3)})
    table["motivo"] = [NULLABLE_SILVER_COLUMNS.get(col, "") for col in table.index]
    return table.sort_values("nulos", ascending=False)


def constant_columns(df: pd.DataFrame) -> list[str]:
    return [col for col in df.columns if df[col].nunique(dropna=False) <= 1]


def numeric_skewness(df: pd.DataFrame) -> pd.Series:
    """Asimetría (Fisher-Pearson ajustada, la de pandas) de las columnas
    numéricas que miden algo: se excluyen la clave y los booleanos."""
    numeric = df.select_dtypes(include="number").drop(columns=[KEY_COLUMN], errors="ignore")
    return numeric.skew().round(3).sort_values(key=lambda s: s.abs(), ascending=False)


def target_distribution(df: pd.DataFrame) -> dict:
    counts = df[TARGET_COLUMN].value_counts(dropna=False)
    n = len(df)
    positives = int(counts.get(True, 0))
    return {
        "true": positives,
        "false": int(counts.get(False, 0)),
        "nulos": int(df[TARGET_COLUMN].isna().sum()),
        "pct_true": round(positives / n * 100, 2) if n else None,
        "pct_false": round((n - positives) / n * 100, 2) if n else None,
    }


def dataset_profile(df: pd.DataFrame) -> dict:
    nulls = null_table(df)
    skew = numeric_skewness(df)
    return {
        "filas": int(df.shape[0]),
        "columnas": int(df.shape[1]),
        "una_fila_es": ROW_MEANING,
        "clave": KEY_COLUMN,
        "tipos": df.dtypes.astype(str).to_dict(),
        "conteo_por_tipo": df.dtypes.astype(str).value_counts().to_dict(),
        "nulos": nulls[nulls["nulos"] > 0].to_dict(orient="index"),
        "columnas_con_nulos": int((nulls["nulos"] > 0).sum()),
        "columnas_constantes": constant_columns(df),
        "match_id_duplicados": int(df[KEY_COLUMN].duplicated().sum()),
        "target": target_distribution(df),
        "asimetria": skew.to_dict(),
        "columnas_muy_asimetricas": skew[skew.abs() > STRONG_SKEW].index.tolist(),
    }


def profile_markdown(profile: dict) -> str:
    """Versión legible del perfil (reports/dataset_profile.md)."""
    t = profile["target"]
    lines = [
        "# Perfil del dataset Silver",
        "",
        f"- **Shape**: {profile['filas']:,} filas x {profile['columnas']} columnas".replace(",", "."),
        f"- **Una fila es**: {profile['una_fila_es']} (clave `{profile['clave']}`, duplicados: {profile['match_id_duplicados']})",
        f"- **Tipos**: {profile['conteo_por_tipo']}",
        f"- **Columnas constantes**: {profile['columnas_constantes'] or 'ninguna'}",
        f"- **Target `{TARGET_COLUMN}`**: {t['true']} True ({t['pct_true']}%) / {t['false']} False ({t['pct_false']}%), nulos: {t['nulos']}",
        "",
        "## Nulos",
        "",
        "| columna | nulos | % | motivo |",
        "|---|---:|---:|---|",
        *[f"| `{c}` | {v['nulos']} | {v['pct_nulos']} | {v['motivo']} |" for c, v in profile["nulos"].items()],
        "",
        f"## Asimetría (|skew| > {STRONG_SKEW} en negrita)",
        "",
        "| columna | skew |",
        "|---|---:|",
        *[
            f"| `{c}` | {'**' + str(s) + '**' if abs(s) > STRONG_SKEW else s} |"
            for c, s in profile["asimetria"].items()
        ],
    ]
    return "\n".join(lines) + "\n"


# -----------------------------------------------------------------------------
# Sensibilidad del umbral del underdog
# -----------------------------------------------------------------------------


def favourite_by_bookmaker(df: pd.DataFrame) -> pd.DataFrame:
    """Para cada casa con las tres cuotas: 'H' si su favorito es el local, 'A'
    si es el visitante, 'T' si cotiza igual a los dos; nulo si no cotiza."""
    out = {}
    for home_col, draw_col, away_col in ODDS_BOOKMAKERS:
        if not {home_col, draw_col, away_col}.issubset(df.columns):
            continue
        quoted = df[[home_col, draw_col, away_col]].notna().all(axis=1)
        pick = np.select([df[home_col] < df[away_col], df[home_col] > df[away_col]], ["H", "A"], default="T")
        out[home_col[:-1].upper()] = pd.Series(pick, index=df.index).where(quoted)
    return pd.DataFrame(out, index=df.index)


def label_stability(df: pd.DataFrame) -> pd.DataFrame:
    """Qué tan estable es la etiqueta de favorito de cada partido:

    - `favorito_cambia_ps_b365`: Pinnacle y Bet365 (las dos casas que usa el
      pipeline) eligen distinto favorito. Solo donde cotizan las dos.
    - `mercado_contradice`: la mitad o más de las casas que cotizan eligen un
      favorito distinto del que usa el pipeline.
    """
    picks = favourite_by_bookmaker(df)
    chosen = pd.Series(np.select([df["prob_home"] > df["prob_away"], df["prob_home"] < df["prob_away"]], ["H", "A"], default="T"), index=df.index)
    disagrees = picks.ne(chosen, axis=0).where(picks.notna())
    both = picks["PS"].notna() & picks["B365"].notna()
    return pd.DataFrame(
        {
            "favorito_cambia_ps_b365": (picks["PS"] != picks["B365"]).where(both),
            "mercado_contradice": (disagrees.sum(axis=1) / picks.notna().sum(axis=1)) >= 0.5,
        },
        index=df.index,
    )


def _pct(series: pd.Series) -> float:
    series = series.dropna()
    return round(float(series.astype(float).mean() * 100), 2) if len(series) else float("nan")


def threshold_sensitivity(candidates: pd.DataFrame, thresholds=UNDERDOG_GAP_CANDIDATES) -> pd.DataFrame:
    """Una fila por umbral candidato. `candidates` son los partidos ANTES de
    filtrar (salida de define_underdog_and_target), con las cuotas de todas
    las casas."""
    gap = underdog_gap(candidates)
    has_underdog = candidates["equipo_favorito"].notna()
    stability = label_stability(candidates)
    target = candidates[TARGET_COLUMN].astype("float")
    favourite_won = (
        ((candidates["equipo_favorito"] == "local") & (candidates["resultado_ft"] == "H"))
        | ((candidates["equipo_favorito"] == "visitante") & (candidates["resultado_ft"] == "A"))
    ).where(has_underdog)
    total = len(candidates)

    rows = []
    for threshold in thresholds:
        kept = has_underdog & (gap > threshold)
        removed = ~kept
        rows.append({
            "umbral": threshold,
            "filas_quedan": int(kept.sum()),
            "filas_eliminadas": int(removed.sum()),
            "pct_eliminado": round(removed.sum() / total * 100, 2),
            "target_true": int(target[kept].sum()),
            "target_false": int((1 - target[kept]).sum()),
            "tasa_victoria_underdog_pct": _pct(target[kept]),
            "tasa_victoria_favorito_pct": _pct(favourite_won[kept]),
            "dif_media_prob": round(float(gap[kept].mean()), 4),
            "pct_favorito_cambia_ps_b365": _pct(stability.loc[kept, "favorito_cambia_ps_b365"]),
            "pct_mercado_contradice": _pct(stability.loc[kept, "mercado_contradice"]),
            "eliminadas_pct_favorito_cambia_ps_b365": _pct(stability.loc[removed, "favorito_cambia_ps_b365"]),
        })
    return pd.DataFrame(rows)


def stability_by_gap_band(candidates: pd.DataFrame, width: float = 0.005, upper: float = 0.15) -> pd.DataFrame:
    """Estabilidad de la etiqueta por tramo fino de |prob_home - prob_away|
    (para el gráfico de la hipótesis 1 del EDA)."""
    df = candidates[candidates["equipo_favorito"].notna()]
    gap = underdog_gap(df)
    stability = label_stability(df)
    edges = np.round(np.arange(0, upper + width / 2, width), 4)
    band = pd.cut(gap, bins=[*edges, 1.0], include_lowest=False)
    grouped = pd.DataFrame({"banda": band, "gap": gap, **stability}).groupby("banda", observed=True)
    return grouped.agg(
        partidos=("gap", "size"),
        gap_medio=("gap", "mean"),
        pct_favorito_cambia_ps_b365=("favorito_cambia_ps_b365", _pct),
        pct_mercado_contradice=("mercado_contradice", _pct),
    ).reset_index()


# -----------------------------------------------------------------------------
# Auditoría de fuga
# -----------------------------------------------------------------------------


def leakage_audit(silver: pd.DataFrame) -> pd.DataFrame:
    return leakage_audit_frame(list(silver.columns))
