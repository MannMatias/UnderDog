# ¿Gana el underdog? — pipeline de datos (Entrega 2)

## 1. Pregunta

¿Ganará el equipo no favorito (*underdog*) un partido, dadas las **probabilidades implícitas pre-partido** y métricas
construidas a partir de **sus jugadores titulares**?

## 2. Unidad de análisis

**Una fila = un partido**, con clave `match_id`. Silver final: **17.959 partidos × 31 columnas**, 9 ligas europeas,
temporadas 2008/09 a 2015/16.

## 3. Target

`gano_no_favorito`: `True` si ganó el underdog; empate o derrota = `False`. Sin nulos.
**20,35% True** (3.654) / 79,65% False (14.305).

## 4. Fuente

[European Soccer Database](https://www.kaggle.com/datasets/hugomathien/soccer) (Kaggle, `hugomathien/soccer`):
25.979 partidos con cuotas 1X2 de 10 casas, **la alineación titular real de cada partido** (22 jugadores con su
coordenada en la cancha) y 183.978 snapshots fechados de atributos de 11.060 jugadores (linaje FIFA/sofifa).
Se publica como SQLite y **se importa una vez a PostgreSQL** (`source-db`). A partir de ahí es la base fuente que
consulta Airflow.

## 5. Arquitectura

```
database.sqlite --seed único--> source-db (PostgreSQL, servicio propio)
                                    |  Airflow Connection "soccer_source_db"
                                    v
                    SQLCheckOperator / PostgresHook + include/sql/*.sql
                                    v
                    BRONZE  (resultado crudo de cada consulta, Parquet)
                                    v
                    transformaciones (include/src/transform.py)
                                    v
                    SILVER  (sin columnas post-partido)  +  AUDIT (goles, resultados)
                                    v
                    quality checks  ->  perfil  ->  EDA (notebook)
```

El DAG `underdog_pipeline` tiene 15 tareas con responsabilidades separadas. Diagrama y tabla de entradas y salidas por tarea
en **[docs/architecture.md](docs/architecture.md)**. `source-db` es un PostgreSQL **distinto** del PostgreSQL de
metadata de Airflow.

## 6. Capas

| Capa | Dónde | Qué es |
|---|---|---|
| Fuente | `source-db` (PostgreSQL) | las 7 tablas originales |
| **Bronze** | `include/data/bronze/{matches,teams,players,player_attributes}.parquet` | lo que devolvió cada consulta SQL, **sin transformar** (mismos valores, nulos y tipos; test `tests/test_bronze.py`) |
| Intermedia | `include/data/intermediate/` | cada etapa entre Bronze y Silver, persistida (nada grande viaja por XCom) |
| **Silver** | `include/data/silver/underdog_dataset.parquet` (+ `.csv`) | el dataset para EDA/modelado |
| Auditoría | `include/data/audit/` | goles, resultados, cuotas crudas y partidos excluidos **con su motivo** |
| Reportes | `include/data/reports/` | quality report, perfil, auditoría de fuga, sensibilidad del umbral |

## 7. Definición de underdog

- **Favorito** = el equipo con **mayor** probabilidad implícita de ganar; **underdog** = el de **menor**.
- Se comparan solo `prob_home` y `prob_away`. **El empate no es un equipo.**
- Probabilidad implícita = `(1/cuota) / overround`, con overround = suma de las tres `1/cuota` (el margen de la casa).
  Así las tres suman 1. Se usa **una** casa por partido (Pinnacle, si no Bet365, si no las siguientes), registrada en `odds_source`.

## 8. Criterio del umbral

Un partido entra solo si **|prob_home − prob_away| > 0,05** (`UNDERDOG_MIN_PROB_GAP` en `include/config.py`).
No es un valor elegido "porque parece razonable". Por debajo de ese gap, **quién es el underdog depende de la casa de apuestas**:
Pinnacle y Bet365 eligen distinto favorito en el 54% de los partidos con gap ≤ 0,005, y en el 0% desde 0,045. 0,05 es el menor
umbral evaluado (0; 0,02; 0,03; 0,05; 0,075; 0,10) sin etiquetas que dependan de la casa, y cuesta 1.703 filas (8,66%).
Tabla completa en [docs/decisions.md](docs/decisions.md#4-partidos-sin-underdog-identificable-umbral-underdog_min_prob_gap--005).

## 9. Features

23 **candidatas**, todas pre-partido. El momento de predicción es con las alineaciones ya publicadas y antes del pitazo. A
cada una se le aplicó el semáforo de la cátedra contra el objetivo: separación estandarizada si es numérica, η² si es
categórica. **Entran al modelo las 12 que dan amarillo o verde:**

- **Mercado**: `prob_no_favorito`, `prob_draw`.
- **Jugadores titulares**: 10 diferencias `nofav_<métrica>_gap` (underdog − favorito; positivo = el underdog es mejor): promedio
  del XI, top 3, mejor, peor, defensa, mediocampo, ataque, definición, reacción y marca.

**Salen las 11 en rojo**, que quedan en Silver para análisis: arquero, velocidad, fuerza, dispersión, edad, altura, las dos
formaciones, `equipo_favorito`, `jornada` y `liga`.

Los atributos de cada titular son los de su **último snapshot estrictamente anterior** al partido
(`merge_asof(direction="backward", allow_exact_matches=False)`). Diccionario columna por columna, con fórmula y origen
(**fuente** o **calculada por nosotros**): [docs/data_dictionary.md](docs/data_dictionary.md). Tabla de candidatas con la zona
y la decisión de cada columna, más el destino de las 82 columnas de la Entrega 1: [docs/column_candidates.md](docs/column_candidates.md).

## 10. Data leakage

Regla: **si una columna solo existe después de jugarse el partido, no puede ser feature.**

- Goles (`goles_local`, `goles_visitante`), `resultado_ft` y `resultado_no_favorito` se usan **solo** para construir el
  target y quedan en `include/data/audit/`, **no en Silver**.
- Las consultas SQL ni siquiera traen las columnas de eventos del partido (`goal`, `card`, `possession`, …).
- El DAG **falla** si Silver tiene una columna post-partido, una columna no documentada, o una feature que predice sola el
  target con AUC > 0,90. La mejor feature sola, `prob_no_favorito`, da 0,64.
- `split_features_target()` en `include/src/columns.py` arma X/y a partir del catálogo y se niega si X tendría información del resultado.

## 11. Cómo levantar el entorno (Docker + Astro CLI)

Requisitos: Docker Desktop corriendo y [Astro CLI](https://www.astronomer.io/docs/astro/cli/install-cli).

```bash
cp .env.example .env
```

```bash
cp source_db.env.example source_db.env
```

Completá la misma contraseña en los dos archivos (sin caracteres especiales). Después:

```bash
astro dev start
```

Levanta Airflow (UI en <http://localhost:8080>) **y** `source-db` (definido en `docker-compose.override.yml`, que Astro combina
con su compose). Desde la PC, `source-db` queda en `localhost:5433`.

## 12. La Airflow Connection

La conexión `soccer_source_db` se define por variable de entorno en `.env` (no se versiona):

```
AIRFLOW_CONN_SOCCER_SOURCE_DB=postgres://soccer:<password>@source-db:5432/soccer
```

Ningún archivo de Python tiene host, usuario, contraseña ni puerto. El DAG y el seed piden
`PostgresHook(postgres_conn_id="soccer_source_db")` y Airflow resuelve el resto. Las credenciales del contenedor de la base
están en `source_db.env`, aparte, para que ese contenedor no reciba las variables de Airflow.

La tarea `check_source_db` la verifica en cada corrida. `airflow connections test` viene deshabilitado en Airflow 3, así que para
probarla a mano, dentro de `astro dev bash`:

```bash
python -c "from include.src.database import get_source_hook; print(get_source_hook().get_first('select current_user, current_database()'))"
```

## 13. Seed de source-db (una sola vez)

Poné `database.sqlite` en `include/data/raw/soccer_db/`. Si no lo tenés, el seed lo puede bajar de Kaggle con `--download`
y `KAGGLE_API_TOKEN` en `.env`. Después:

```bash
astro dev bash
```

Y dentro del contenedor:

```bash
python -m include.src.source_loader
```

Crea las 7 tablas en PostgreSQL (≈3 minutos; `match` es la más pesada por las columnas XML de eventos). Es idempotente:
si las tablas ya tienen las filas del SQLite, no hace nada. `--force` las recrea. Los datos viven en el volumen
`source_db_data` y sobreviven a `astro dev stop/restart`.

## 14. Cómo ejecutar el DAG

- **Programado**: todos los días a las 06:00 UTC (`catchup=False`). Si la fuente y el código no cambiaron desde la última
  corrida exitosa, `detect_source_changes` saltea el resto. La huella combina filas, fecha máxima y md5 del contenido de cada tabla.
- **Manual**: en la UI, *Trigger* sobre `underdog_pipeline`. Con el parámetro `force_rebuild = true` se reconstruye todo aunque
  no haya cambios. Por línea de comandos:

```bash
astro dev run dags trigger underdog_pipeline --conf '{"force_rebuild": true}'
```

Por qué diario y cómo funciona el ShortCircuit: [docs/architecture.md](docs/architecture.md#schedule-y-detección-de-cambios).

## 15. Qué produce

```
25.979 partidos en la fuente
→ 22.637 sin las 2 ligas sin cuotas (Polonia, Suiza)
→ 19.727 con alineación titular completa (22 jugadores)
→ 19.694 con cuotas 1X2 completas de al menos una casa
→ 19.662 con cuotas coherentes (empate implícito ≤ 40%)
→ 19.559 con underdog identificable (probabilidades distintas)
→ 17.959 con underdog estable (|prob_home − prob_away| > 0,05)   ← Silver
```

- `silver/underdog_dataset.parquet`: 17.959 × 31. De esas 31 columnas, 23 son candidatas a feature (12 entran al modelo), 1 es el target, 1 la clave y 6 son metadata o auxiliares.
- `reports/quality_report.json`: 17 hard checks (los 7 de la Entrega 1 + 10 nuevos), todos OK.
- `reports/dataset_profile.{json,md}`, `reports/leakage_audit.csv`, `reports/threshold_sensitivity.csv`.
- `audit/match_audit.parquet` (mismo `match_id` que Silver) y `audit/excluded_matches.parquet` (8.020 partidos con su motivo).

## 16. Dónde están Bronze y Silver

`include/data/bronze/` y `include/data/silver/`. Tabla completa en el punto 6. Los datos no se versionan: se regeneran con
seed + DAG.

## 17. Tests

85 tests. En el contenedor de Airflow corren todos, incluidos los del DAG:

```bash
astro dev pytest
```

En local, sin Airflow, corren los de lógica, Bronze, checks y Silver real; los del DAG se saltean:

```bash
python -m venv .venv
```

```bash
.venv/Scripts/pip install -r requirements-dev.txt
```

```bash
.venv/Scripts/python -m pytest tests
```

Cubren: `match_id` único, target sin nulos y binario, underdog en todas las filas, sin goles ni columnas de fuga,
probabilidades que suman 1, snapshots estrictamente anteriores al partido (sintético y sobre los datos reales), filtro de umbral
según `config.py`, DAG importable, schedule, tareas y dependencias, cada quality check, detección de cambios, y que Bronze no
modifica lo que devuelve SQL.

## 18. Notebook

`notebooks/entrega_2_eda.ipynb` se guarda **con sus outputs**. Lee Silver y las capas intermedias (hay que haber corrido el DAG).
Para re-ejecutarlo de arriba a abajo:

```bash
.venv/Scripts/jupyter nbconvert --to notebook --execute --inplace notebooks/entrega_2_eda.ipynb
```

Sigue la consigna de la Entrega 2. Tiene el perfil con los comandos de verificación, cuatro fichas con los seis campos
del TP2 y el semáforo de la cátedra, la tabla de columnas candidatas y el control final de fuga. El campo "Qué espero ver"
de cada ficha está marcado como borrador: lo tiene que reescribir el grupo. Checklist de la entrega: [docs/entrega_2_checklist.md](docs/entrega_2_checklist.md).

## 19. Limitaciones

- **La base termina en 2015/16.** Sirve para entrenar y validar, no para predecir la fecha que viene: haría falta una fuente
  de alineaciones y cuotas actuales, que se conocen ~1 h antes del partido.
- **Las cuotas se publican días antes que las alineaciones.** Una cuota "de cierre" (más cercana al pitazo) sería un rival más
  difícil para los features de jugadores. En esta fuente no hay cuotas de cierre.
- **La señal de los jugadores por encima del mercado es chica.** En la hipótesis 2, al controlar por `prob_no_favorito`, la
  separación del gap del XI cae de 0,36 a 0,03–0,16 (rojo). La línea de base a superar es el mercado solo.
- **`odds_source` cambia con la época** (Bet365 hasta 2011/12, Pinnacle desde 2012/13): una partición temporal compara
  márgenes distintos.
- **La formación comprime a 3 líneas por coordenada Y**: un 4-2-3-1 aparece como 4-2-4.
- No hay estado de forma reciente, lesiones ni suspensiones como columnas. Un titular ausente se refleja solo porque no está en la alineación.
- Errores puntuales de la fuente, medidos: en 4 partidos de Silver las coordenadas Y vienen vacías o en 0 (nulos documentados),
  y 835 snapshots duplicados vacíos (descartados).

## Estructura

```
dags/underdog_pipeline_dag.py        el DAG: solo orquesta
include/config.py                    configuración técnica + reglas de negocio
include/sql/                         consultas: check, huella y las 4 extracciones de Bronze
include/src/database.py              acceso a source-db por la Airflow Connection
include/src/extract.py               Bronze: consulta -> Parquet sin transformar
include/src/change_detection.py      huella fuente+código y manifest
include/src/transform.py             reglas de negocio y features (funciones puras)
include/src/columns.py               catálogo de columnas (diccionario, features, fuga) + generador de docs
include/src/quality_check.py         hard checks + métricas informativas
include/src/profiling.py             perfil, sensibilidad del umbral, auditoría de fuga
include/src/storage.py               escrituras atómicas de Parquet/CSV/JSON
include/src/source_loader.py         seed SQLite -> PostgreSQL (fuera del DAG)
docker-compose.override.yml          servicio source-db
notebooks/entrega_2_eda.ipynb        EDA de la Entrega 2
docs/                                arquitectura, decisiones, diccionario, candidatas, checklist
tests/                               tests de lógica, Bronze, checks, Silver real y DAG
```
