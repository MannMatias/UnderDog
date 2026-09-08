"""Capa bronce: descarga la European Soccer Database de Kaggle tal como
viene (un archivo SQLite), sin transformarla.

Por qué esta fuente y no scrapear sofifa ni football-data.co.uk:

- sofifa.com bloquea explícitamente a bots en su robots.txt (`Disallow: /`
  para ClaudeBot, GPTBot, etc.) y está detrás de Cloudflare: un scraper
  tendría que evadir esa protección.
- football-data.co.uk (la fuente original de resultados+cuotas de este
  proyecto) lleva días devolviendo HTTP 503.
- Esta base ya trae en un solo archivo lo que antes requería cruzar dos
  fuentes por nombre de equipo: resultados, cuotas de 10 casas, la
  alineación titular real de cada partido y los atributos individuales de
  cada jugador fechados (linaje FIFA/sofifa). Al venir con `player_api_id`
  y `team_api_id`, el join es por id y no por nombre: desaparece toda la
  fragilidad del mapeo "Man United" vs "Manchester United".

Requiere credenciales de la API de Kaggle: generá un token en
https://www.kaggle.com/settings/api ("Generate New Token") y exportalo como
`KAGGLE_API_TOKEN` (en el `.env` del proyecto si corre bajo Astro).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from include.config import KAGGLE_DATASET_SLUG, SOCCER_DB_DIR, SOCCER_DB_PATH

logger = logging.getLogger(__name__)

# La base descomprimida pesa ~300 MB; si el archivo existente es mucho más
# chico está truncado o a medio bajar.
MIN_EXPECTED_BYTES = 250_000_000


def download_soccer_db(force: bool = False) -> Path:
    """Descarga y descomprime `database.sqlite` en `SOCCER_DB_DIR`."""
    if not force and SOCCER_DB_PATH.exists():
        size = SOCCER_DB_PATH.stat().st_size
        if size >= MIN_EXPECTED_BYTES:
            logger.info("Ya existe %s (%.0f MB), no descargo de nuevo.", SOCCER_DB_PATH, size / 1e6)
            return SOCCER_DB_PATH
        logger.warning(
            "%s existe pero pesa solo %.0f MB (esperado >%.0f MB): lo vuelvo a descargar.",
            SOCCER_DB_PATH, size / 1e6, MIN_EXPECTED_BYTES / 1e6,
        )

    if not os.environ.get("KAGGLE_API_TOKEN") and not (Path.home() / ".kaggle" / "access_token").exists():
        raise RuntimeError(
            "No se encontraron credenciales de Kaggle. Generá un token en "
            "https://www.kaggle.com/settings/api ('Generate New Token') y "
            "exportalo como variable de entorno KAGGLE_API_TOKEN (en el "
            "'.env' del proyecto si corre bajo Astro)."
        )

    import kaggle  # import perezoso: solo hace falta si hay que descargar

    SOCCER_DB_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Descargando dataset de Kaggle %s ...", KAGGLE_DATASET_SLUG)
    try:
        kaggle.api.authenticate()
        kaggle.api.dataset_download_files(
            KAGGLE_DATASET_SLUG, path=str(SOCCER_DB_DIR), unzip=True
        )
    except (Exception, SystemExit) as exc:
        raise RuntimeError(
            "Falló la autenticación o la descarga contra la API de Kaggle. "
            "Revisá que KAGGLE_API_TOKEN sea un token vigente generado en "
            "https://www.kaggle.com/settings/api."
        ) from exc

    if not SOCCER_DB_PATH.exists():
        raise RuntimeError(
            f"La descarga terminó pero no apareció {SOCCER_DB_PATH}. "
            f"Contenido de {SOCCER_DB_DIR}: {list(SOCCER_DB_DIR.iterdir())}"
        )

    logger.info("Descargado %s (%.0f MB)", SOCCER_DB_PATH, SOCCER_DB_PATH.stat().st_size / 1e6)
    return SOCCER_DB_PATH


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    download_soccer_db()


if __name__ == "__main__":
    main()
