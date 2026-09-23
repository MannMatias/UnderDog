"""Configuración central del proyecto.

Está partida en dos bloques a propósito:

1. CONFIGURACIÓN TÉCNICA: rutas, conexión, formatos. Cambiarla no cambia el
   contenido del dataset.
2. REGLAS DE NEGOCIO: qué partidos entran y cómo se define el underdog.
   Cambiarlas SÍ cambia el dataset. Como este archivo forma parte de la huella
   del pipeline (ver `include/src/change_detection.py`), cualquier cambio acá
   hace que la próxima corrida programada reconstruya Silver.

Fuente: European Soccer Database (Kaggle, `hugomathien/soccer`), un SQLite con
partidos de 11 ligas europeas (2008/09 a 2015/16) que incluye cuotas 1X2 de 10
casas de apuestas, la alineación titular real de cada partido y atributos de
jugador fechados (linaje FIFA/sofifa). Ese SQLite se importa una sola vez a
PostgreSQL (`source-db`) y Airflow consulta esa base, nunca el archivo.
"""

from pathlib import Path

# =============================================================================
# 1. CONFIGURACIÓN TÉCNICA
# =============================================================================

INCLUDE_DIR = Path(__file__).resolve().parent
SQL_DIR = INCLUDE_DIR / "sql"
DATA_DIR = INCLUDE_DIR / "data"

# raw/: el SQLite original. Solo lo lee el seed de source-db, nunca el DAG.
RAW_DIR = DATA_DIR / "raw"
SOCCER_DB_PATH = RAW_DIR / "soccer_db" / "database.sqlite"
KAGGLE_DATASET_SLUG = "hugomathien/soccer"

# bronze/: resultado crudo de cada consulta SQL a source-db, sin transformar.
BRONZE_DIR = DATA_DIR / "bronze"
# intermediate/: pasos entre Bronze y Silver (persisten para no pasar
# DataFrames por XCom y para poder auditar cada etapa).
INTERMEDIATE_DIR = DATA_DIR / "intermediate"
# silver/: el dataset para EDA/modelado. Sin columnas post-partido.
SILVER_DIR = DATA_DIR / "silver"
# audit/: columnas que no pueden ser features (goles, resultado) y filas
# excluidas, para poder rastrear cada decisión.
AUDIT_DIR = DATA_DIR / "audit"
# reports/: quality checks, perfil del dataset y tablas de evidencia.
REPORTS_DIR = DATA_DIR / "reports"

SILVER_DATASET_PATH = SILVER_DIR / "underdog_dataset.parquet"
# Copia legible del mismo Silver para abrir en una planilla.
SILVER_CSV_PATH = SILVER_DIR / "underdog_dataset.csv"
SILVER_MANIFEST_PATH = SILVER_DIR / "_manifest.json"

# Airflow Connection a la base fuente. Host, usuario y contraseña NO están en
# el código: viven en la variable de entorno AIRFLOW_CONN_SOCCER_SOURCE_DB.
SOURCE_DB_CONN_ID = "soccer_source_db"

# Tablas de Bronze: nombre lógico -> consulta que la produce (include/sql/).
BRONZE_QUERIES = {
    "matches": "extract_matches.sql",
    "teams": "extract_teams.sql",
    "players": "extract_players.sql",
    "player_attributes": "extract_player_attributes.sql",
}

# Las cuotas vienen con 2 decimales: más allá del cuarto decimal, cualquier
# dígito de una probabilidad es ruido de la división.
FLOAT_DECIMALS = 4

# =============================================================================
# 2. REGLAS DE NEGOCIO
# =============================================================================

# Polonia y Suiza no traen cuotas en ninguna casa (0% de cobertura): ningún
# partido suyo puede definir favorito. Decisión de alcance explícita; el log de
# prepare_matches informa cuántas filas saca cada filtro.
EXCLUDED_LEAGUES = ("Poland Ekstraklasa", "Switzerland Super League")

# Cuotas 1X2 por casa, en orden de preferencia. Pinnacle (PS) es la referencia
# de eficiencia de mercado por su margen bajo; Bet365 (B365) tiene la mayor
# cobertura histórica; el resto es red de contención. Se usa UNA casa por
# partido y queda registrada en `odds_source`. Nombres en minúscula porque así
# quedan las columnas en PostgreSQL.
ODDS_BOOKMAKERS = [
    ("psh", "psd", "psa"),
    ("b365h", "b365d", "b365a"),
    ("bwh", "bwd", "bwa"),
    ("vch", "vcd", "vca"),
    ("whh", "whd", "wha"),
    ("iwh", "iwd", "iwa"),
    ("lbh", "lbd", "lba"),
    ("sjh", "sjd", "sja"),
    ("gbh", "gbd", "gba"),
    ("bsh", "bsd", "bsa"),
]

# Tope de probabilidad implícita de empate (1/cuota, sin normalizar) para
# aceptar la tripleta 1X2 como un mercado pre-partido coherente. Hasta 0.40 la
# cuota de empate está calibrada (la tasa real de empate sube de 13% a 28-30% y
# el margen queda entre 1.04 y 1.07); por encima se rompe (44% y 56% de empates
# reales, margen 1.08-1.09). Son 32 partidos de 2008/09 a 2012/13, 29 de Serie
# A: cuotas corruptas en la fuente (tabla en docs/decisions.md).
MAX_PROB_EMPATE_IMPLICITA = 0.40

# Diferencia mínima |prob_home - prob_away| para que el underdog esté
# identificado. Un partido entra a Silver solo si la diferencia es
# ESTRICTAMENTE mayor. Con 0 se sacarían únicamente los empates exactos de
# probabilidad (sin underdog posible).
#
# Evidencia (tabla completa en docs/decisions.md y reports/threshold_sensitivity.csv):
# por debajo de 0.045 la etiqueta de favorito depende de la casa elegida
# (Pinnacle y Bet365 eligen distinto favorito en el 54% de los partidos con
# gap <= 0.005 y en el 13% con gap entre 0.015 y 0.02); desde 0.045 no
# discrepan nunca. 0.05 es el menor umbral evaluado a partir del cual el
# underdog no depende de la casa de apuestas; cuesta 8.7% de las filas.
UNDERDOG_MIN_PROB_GAP = 0.05

# Umbrales evaluados en el análisis de sensibilidad (profiling y notebook).
UNDERDOG_GAP_CANDIDATES = (0.0, 0.02, 0.03, 0.05, 0.075, 0.10)

# Línea de cada titular según su coordenada Y en la cancha (1 = arco propio,
# 11 = área rival), no según su posición nominal: respeta la formación real de
# ese partido. Tramos (a, b]: arquero Y=1, defensa 2-3, medio 4-7, ataque 8+.
LINEUP_Y_BINS = (-1, 1, 3, 7, 99)
LINEUP_Y_LABELS = ("gk", "def", "mid", "att")

# Columna objetivo.
TARGET_COLUMN = "gano_no_favorito"
