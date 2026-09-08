"""Configuracion central del proyecto: fuente, ligas y rutas.

Fuente única: European Soccer Database (Kaggle, `hugomathien/soccer`), un
SQLite con partidos de 11 ligas europeas (2008/2009 a 2015/2016) que incluye
cuotas pre-partido de 10 casas de apuestas, **la alineación titular real de
cada partido** (los 22 jugadores con su posición en la cancha) y atributos
individuales de jugador fechados (linaje FIFA/sofifa).
"""

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
RAW_DIR = ROOT_DIR / "data" / "raw"
SOCCER_DB_DIR = RAW_DIR / "soccer_db"
SOCCER_DB_PATH = SOCCER_DB_DIR / "database.sqlite"
PROCESSED_DIR = ROOT_DIR / "data" / "processed"
FINAL_DATASET_PATH = PROCESSED_DIR / "underdog_dataset.csv"

KAGGLE_DATASET_SLUG = "hugomathien/soccer"

# Ligas excluidas: Polonia y Suiza no traen cuotas en ninguna casa (0% de
# cobertura), así que ningún partido suyo puede definir favorito y quedarían
# como filas inútiles. Es una decisión de alcance explícita, no un descarte
# silencioso: el log del transform informa cuántas filas saca cada filtro.
EXCLUDED_LEAGUES = ("Poland Ekstraklasa", "Switzerland Super League")

# Cuotas 1X2 por casa, en orden de preferencia. Pinnacle (PS) es la
# referencia en estudios de eficiencia de mercado por tener el margen más
# bajo; Bet365 (B365) es la de mayor cobertura histórica; el resto son red
# de contención. Se usa UNA casa por fila y se registra cuál en `odds_source`.
ODDS_BOOKMAKERS = [
    ("PSH", "PSD", "PSA"),
    ("B365H", "B365D", "B365A"),
    ("BWH", "BWD", "BWA"),
    ("VCH", "VCD", "VCA"),
    ("WHH", "WHD", "WHA"),
    ("IWH", "IWD", "IWA"),
    ("LBH", "LBD", "LBA"),
    ("SJH", "SJD", "SJA"),
    ("GBH", "GBD", "GBA"),
    ("BSH", "BSD", "BSA"),
]

# Umbral para marcar partidos "parejos", donde la etiqueta de favorito es
# ruido: diferencia de probabilidad implícita entre local y visitante.
PARTIDO_PAREJO_MAX_GAP = 0.05
