"""Semáforo de la cátedra (consigna del TP2) y sus medidas.

Cada medida cae en una de tres zonas según su valor absoluto. En verde y en
rojo se termina (el efecto es claro, o no está); en amarillo hay que indagar
con un movimiento. El semáforo no pregunta si el efecto existe (con 18 mil
filas casi cualquier diferencia da significativa) sino si es lo bastante
grande como para cambiar una decisión.

| medida                      | cuándo se usa                        | rojo    | amarillo    | verde   |
|-----------------------------|--------------------------------------|---------|-------------|---------|
| separación estandarizada    | una numérica entre dos grupos        | < 0,2   | 0,2 a 0,8   | > 0,8   |
| η² (razón de correlación)   | una numérica entre muchos grupos     | < 0,05  | 0,05 a 0,25 | > 0,25  |
| correlación                 | dos numéricas                        | < 0,2   | 0,2 a 0,6   | > 0,6   |
| brecha Spearman − Pearson   | detectar que la relación no es recta | < 0,05  | 0,05 a 0,15 | > 0,15  |
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from include.config import TARGET_COLUMN

SEMAFORO = {
    "separacion_estandarizada": (0.2, 0.8),
    "eta2": (0.05, 0.25),
    "correlacion": (0.2, 0.6),
    "brecha_spearman_pearson": (0.05, 0.15),
}
NOMBRE = {
    "separacion_estandarizada": "separación estandarizada",
    "eta2": "η²",
    "correlacion": "correlación",
    "brecha_spearman_pearson": "brecha Spearman − Pearson",
}


def zona(medida: str, valor: float) -> str:
    rojo_hasta, verde_desde = SEMAFORO[medida]
    v = abs(valor)
    if v < rojo_hasta:
        return "rojo"
    return "verde" if v > verde_desde else "amarillo"


def separacion_estandarizada(valores: pd.Series, grupo: pd.Series) -> float:
    """(media del grupo True − media del grupo False) / desvío combinado.
    Positivo = la columna es más alta en el grupo True."""
    grupo = grupo.astype(bool)
    a, b = valores[grupo].dropna(), valores[~grupo].dropna()
    desvio = np.sqrt(((len(a) - 1) * a.var() + (len(b) - 1) * b.var()) / (len(a) + len(b) - 2))
    return float((a.mean() - b.mean()) / desvio)


def eta_cuadrado(valores: pd.Series, grupos: pd.Series) -> float:
    """Qué parte de la variación de `valores` explican los grupos
    (suma de cuadrados entre grupos / suma de cuadrados total)."""
    v = valores.astype(float)
    media_grupo = v.groupby(grupos).transform("mean")
    return float(((media_grupo - v.mean()) ** 2).sum() / ((v - v.mean()) ** 2).sum())


def correlacion(x: pd.Series, y: pd.Series) -> float:
    return float(x.corr(y))


def brecha_spearman_pearson(x: pd.Series, y: pd.Series) -> float:
    return float(abs(x.corr(y, method="spearman") - x.corr(y)))


def medida_contra_target(df: pd.DataFrame, columna: str) -> tuple[str, float]:
    """Medida del semáforo de una columna candidata contra el target
    (binario): separación estandarizada si es numérica, η² si es categórica."""
    if pd.api.types.is_numeric_dtype(df[columna]):
        return "separacion_estandarizada", separacion_estandarizada(df[columna], df[TARGET_COLUMN])
    return "eta2", eta_cuadrado(df[TARGET_COLUMN], df[columna])


def zonas_de_candidatas(df: pd.DataFrame, columnas: list[str]) -> pd.DataFrame:
    rows = []
    for col in columnas:
        medida, valor = medida_contra_target(df, col)
        rows.append({"columna": col, "medida": NOMBRE[medida], "valor": round(valor, 4), "zona": zona(medida, valor)})
    return pd.DataFrame(rows)
