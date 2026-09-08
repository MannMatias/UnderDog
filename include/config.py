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

# Tope de probabilidad implicita de empate para aceptar la tripleta 1X2 como
# un mercado pre-partido coherente. Ninguna casa real paga un empate por
# encima del 40%, y el dato lo confirma: hasta 1/cuota = 0.40 la cuota de
# empate esta bien calibrada (la tasa real de empate sube monotonicamente de
# 13% a 30% y el margen de la casa se queda en ~1.04), pero por encima de
# 0.40 la calibracion se rompe (44% y 56% de empates reales) y el margen
# salta a ~1.09. Son 32 de 19.694 partidos, todos de 2008/09 a 2012/13 y casi
# todos de Serie A: cuotas corruptas en la fuente. Una fila asi no puede
# definir favorito, que es la base de la pregunta, asi que se excluye.
MAX_PROB_EMPATE_IMPLICITA = 0.40

# Umbral para marcar partidos "parejos", donde la etiqueta de favorito es
# ruido: diferencia de probabilidad implícita entre local y visitante.
PARTIDO_PAREJO_MAX_GAP = 0.05
