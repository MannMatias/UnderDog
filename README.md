# ¿Gana el no favorito? — pipeline de dataset

## Pregunta del proyecto

¿Ganará el equipo no favorito (underdog) un partido, dadas las
probabilidades implícitas de las apuestas pre-partido y **las métricas
intrínsecas de cada uno de los jugadores que salen a la cancha**?

**Una fila es un partido**, con: (a) las cuotas pre-partido convertidas en
probabilidades implícitas normalizadas, (b) features construidos desde los
atributos individuales de los **22 titulares reales** de ese partido, tomados
de su último snapshot *anterior* a la fecha del encuentro, y (c) el resultado
real.

## Fuente

| Fuente | Qué aporta | Cómo se obtiene |
|---|---|---|
| [Kaggle: European Soccer Database](https://www.kaggle.com/datasets/hugomathien/soccer) (`hugomathien/soccer`) | 25.979 partidos de 11 ligas europeas (2008/09 a 2015/16) con cuotas 1X2 de 10 casas de apuestas, **la alineación titular real de cada partido** (22 jugadores con su posición en la cancha) y **183.978 snapshots fechados de atributos individuales** de 11.060 jugadores (linaje FIFA/sofifa) | Descarga vía API de Kaggle de un único archivo SQLite (~300 MB) |

### Por qué esta fuente y no las dos originales

- **sofifa.com** bloquea explícitamente a bots en su `robots.txt`
  (`Disallow: /` para ClaudeBot, GPTBot, etc., y `Content-Signal: ai-train=no`)
  y está detrás de Cloudflare: un scraper tendría que evadir esa protección.
- **football-data.co.uk** (la fuente original de resultados y cuotas) lleva
  días devolviendo `HTTP 503`.
- Esta base resuelve las dos cosas en un solo archivo y, sobre todo, **trae
  las alineaciones titulares**, que es lo que permite que la predicción salga
  de los valores intrínsecos de cada jugador y no de un promedio de plantel.
  Además, al venir con `player_api_id` y `team_api_id`, el join es por id:
  desaparece toda la fragilidad del mapeo de nombres ("Man United" vs
  "Manchester United").

## Qué produce

**19.694 filas × 82 columnas** (`include/data/processed/underdog_dataset.csv`),
9 ligas, 8 temporadas.

### Criterios de inclusión (explícitos, no descartes silenciosos)

El log del task `armar_dataset` informa cada filtro:

```
25.979 partidos en la base
→ 22.637 tras excluir 2 ligas sin ninguna cuota cargada (Polonia, Suiza)
→ 19.727 con alineación titular completa (22 jugadores)
→ 19.694 con las 3 cuotas 1X2 completas de al menos una casa
```

Un partido sin cuotas no puede definir favorito, y uno sin alineación no
tiene features de jugadores: en ambos casos la fila no puede responder la
pregunta, así que se excluye antes de entrar al dataset.

## Decisiones de diseño que hay que poder defender

1. **Nada de promedios de plantel.** Los features salen de la alineación
   titular real: el arquero titular concreto (`*_gk_overall`,
   `*_gk_reflexes`), el mejor jugador en cancha (`*_best_overall`), los tres
   mejores individuos (`*_top3_overall`), el eslabón más débil
   (`*_worst_overall`), la dispersión del once (`*_overall_std`, equipo
   estrella-dependiente vs. parejo), el más rápido
   (`*_fastest_sprint_speed`), el mejor definidor (`*_best_finishing`), y
   cada línea según la formación que salió a jugar (`*_def_overall`,
   `*_mid_overall`, `*_att_overall`).
2. **Sin fuga de información temporal.** Los atributos se cruzan con
   `merge_asof(direction="backward", allow_exact_matches=False)`: para cada
   jugador se toma su snapshot más reciente **estrictamente anterior** al
   partido. Nunca entra un rating publicado después del pitazo inicial.
3. **Probabilidades, no cuotas crudas.** `1/cuota` para las tres opciones,
   se suma el `overround` (margen de la casa, media 1,043 = 4,3%) y se
   normaliza para que `prob_home + prob_draw + prob_away = 1.0`.
4. **Una casa por fila, registrada.** Prioridad Pinnacle → Bet365 → resto
   (columna `odds_source`: 53% Pinnacle, 47% Bet365). Pinnacle es la
   referencia en estudios de eficiencia de mercado por tener el margen más
   bajo.
5. **El empate es un `False`.** La pregunta es "¿ganará el no favorito?": si
   empató, no ganó. Dejarlo nulo tiraría ~25% de las filas. La información
   del empate no se pierde: queda en `resultado_no_favorito`
   (`gano`/`empato`/`perdio`).
6. **La línea de cada titular sale de su coordenada Y en la cancha**, no de
   su posición nominal, así que respeta la formación real de ese partido
   (`*_formacion`, ej. `4-3-3`).
7. **Features orientados a la pregunta.** Las columnas `nofav_*_gap` miden
   la ventaja del **no favorito** sobre el favorito (positivo = el underdog
   es superior en esa dimensión), que es la forma directa de responderla.

## La concesión "tidy"

Igual que `player_positions` en el dataset canónico de la cátedra, acá la
concesión deliberada es que **una fila comprime a 22 jugadores**. Lo
estrictamente tidy sería una fila por (partido, jugador); pero entonces la
unidad de análisis dejaría de ser el partido, que es lo que la pregunta pide
predecir. La columna `*_xi_sin_atributos` deja a la vista cuántos titulares
de esa fila no tenían snapshot previo (0 en el 99,9% de los casos).

## Clave primaria

`match_id` (el `match_api_id` de la base). Es el test operativo de que una
fila es un partido: si se duplicara, el pipeline estaría devolviendo el mismo
partido dos veces.

## Nulos conocidos

El diccionario `NULL_REASONS` en [`include/src/transform.py`](include/src/transform.py)
documenta cada columna que puede tener nulos, y `quality_check.py` **falla la
corrida** si aparece un nulo en una columna no documentada. Los nulos reales
son mínimos:

| Columna | Nulos | Motivo |
|---|---|---|
| `nofav_gk_overall_gap` | 0,6% | Algún partido sin slot de arquero identificable por coordenada Y |
| `gano_no_favorito` y derivadas | 0,5% | Local y visitante con probabilidad implícita exactamente igual: no hay favorito definible |
| atributos de jugador | 0,03% | Titular sin ningún snapshot de atributos anterior a esa fecha |

## Validación del contenido (no solo del formato)

Los números dan lo que tienen que dar, lo cual es la mejor evidencia de que la
lógica del target no está invertida:

- El favorito es el local en el **72%** de los partidos (ventaja de localía).
- El no favorito **gana 21,4%**, empata 25,2% y pierde 53,4%.
- La tasa de victoria del underdog cae monotónicamente según cuán favorito
  sea el rival: **31,9%** en partidos parejos → **2,9%** cuando el favorito
  tiene más del 80% de probabilidad implícita.
- **Los features de jugadores aportan señal por encima de las cuotas**:
  cuando el once del underdog es mejor en papel
  (`nofav_xi_overall_mean_gap > 0`), su tasa de victoria sube de **19,3% a
  28,6%**.

## Estructura (proyecto Astro)

```
dags/underdog_pipeline_dag.py     # el DAG, solo orquesta
include/config.py                 # fuente, ligas excluidas, casas de apuestas
include/src/extract_soccer_db.py  # capa bronce: baja el SQLite de Kaggle
include/src/transform.py          # capa plata: features por jugador + target
include/src/quality_check.py      # los 7 criterios de la Entrega
include/data/raw/soccer_db/       # base cruda (no se versiona)
include/data/processed/           # CSV final (no se versiona)
```

`include/` se importa desde el DAG como `include.config`,
`include.src.transform`, etc. — Astro ya lo deja en el `PYTHONPATH` del
contenedor.

## Cómo correrlo (Astro CLI)

Requisitos: Docker Desktop corriendo y Astro CLI instalado (`astro version`).

1. Token de Kaggle: <https://www.kaggle.com/settings/api> → *Generate New Token*.
2. Completá `.env` en la raíz (ya está en `.gitignore`):
   ```
   KAGGLE_API_TOKEN=tu_token
   ```
   Si el entorno ya estaba corriendo, `astro dev restart` para que el
   scheduler tome la variable.
3. `astro dev start` → UI en <http://localhost:8080>.
4. Disparar el DAG `underdog_pipeline` desde la interfaz y seguir los 3
   tasks (`extraer_base`, `armar_dataset`, `chequear_calidad`).
5. `astro dev stop` al terminar.

### Correr los pasos sueltos para debug

```bash
astro dev bash
python -m include.src.extract_soccer_db
python -m include.src.transform
python -m include.src.quality_check
```

## Limitaciones conocidas

- **La base termina en la temporada 2015/2016.** Sirve para entrenar y
  validar el modelo, pero no para predecir un partido de la fecha que viene:
  para eso haría falta enchufar una fuente de alineaciones y cuotas actuales
  (que además solo se conocen ~1 hora antes del partido).
- **No hay estado de forma.** Los features son los atributos de los
  jugadores, no el rendimiento reciente del equipo. Se podría derivar
  (puntos en los últimos 5 partidos) desde los propios resultados de la base
  en la Entrega 2.
- Las lesiones y suspensiones no están como tal, pero se reflejan
  indirectamente: si un titular no jugó, no está en la alineación de esa
  fila.
- **Errores puntuales de la fuente, ya medidos:** 3 de 39.388 alineaciones
  traen las coordenadas en cero (se resuelve eligiendo al arquero por sus
  reflejos, ver `build_player_features`), 4 no permiten clasificar alguna
  línea (quedan como nulos documentados) y 1 repite un jugador dentro del
  mismo once. En total, menos del 0,02% de las alineaciones.
