# Checklist Entrega 2

Cada ítem apunta a dónde está la evidencia. Verificado sobre la corrida final del DAG y el notebook ejecutado.

## Notebook (`notebooks/entrega_2_eda.ipynb`)

- [x] **Notebook corre completo**: `jupyter nbconvert --to notebook --execute --inplace notebooks/entrega_2_eda.ipynb`, sin errores.
- [x] **Outputs guardados** en el `.ipynb` (tablas y 7 gráficos, todos con título y ejes con nombre).
- [x] **Shape**: 17.959 filas × 31 columnas (Parte 1).
- [x] **Tipos**: `df.dtypes.value_counts()` y por qué las 6 columnas de texto son categóricas (Parte 1).
- [x] **Nulos**: 6 columnas, máx. 4 filas (0,02%), todas con motivo (Parte 1).
- [x] **Constantes**: ninguna (Parte 1).
- [x] **Duplicados**: 0 `match_id` duplicados (Parte 1).
- [x] **Target distribution**: 3.654 True (20,35%) / 14.305 False (79,65%), gráfico + decisión (Parte 1).
- [x] **Skewness**: asimetría de todas las numéricas; solo `prob_draw` con |skew| > 1 (−1,3), con decisión (Parte 1).
- [x] **4 fichas con los seis campos del TP2**: afirmación, qué espero ver, cómo la mido, qué encontré, qué movimiento hice,
  qué hago con eso. Cada una con su número, la zona del semáforo de la cátedra y su gráfico (Parte 2).
  - una que responde algo del dominio: H1 y H2;
  - una que decide sobre columnas del modelo: H3 y H4.
  - el único movimiento (H2, controlar por `prob_no_favorito`) está justificado por lo que muestra el gráfico.
- [x] **Al menos una refutada/inconclusa**: H2 (🟡 → movimiento → 🔴) y H4 (🔴).
- [ ] **"Qué espero ver" reescrito por el grupo**: está marcado como BORRADOR en las 4 fichas.
- [x] **Tabla de columnas candidatas**: Parte 3 del notebook (columna, qué mide, medida, zona, decisión, ¿existiría al predecir?).
  Las 23 candidatas y las 4 descartadas por fuga; entran 12. La versión completa con las 82 columnas de la Entrega 1 está en
  `docs/column_candidates.md` / `.csv`.
- [x] **Chequeo de leakage**: Parte 4 del notebook + `reports/leakage_audit.csv` + hard checks `sin_columnas_de_fuga` y
  `sin_predictor_perfecto`.

## Correcciones de la Entrega 1 (devolución)

- [x] **Airflow se comunica con la base** (no lanza scripts): Connection `soccer_source_db` + `SQLCheckOperator` + `PostgresHook`, consultas en `include/sql/`.
- [x] **Bronze = resultado de las consultas**, no el SQLite descargado (`include/data/bronze/`, test `tests/test_bronze.py`).
- [x] **Sacar columnas no necesarias**: consultas con columnas explícitas (sin `SELECT *`); 82 → 31 columnas con decisión por columna.
- [x] **Umbral definido y filtrando de verdad**: `UNDERDOG_MIN_PROB_GAP = 0.05`, elegido con la tabla de sensibilidad (`docs/decisions.md` §4).
- [x] **Sacar los goles**: `goles_local`/`goles_visitante` solo en `audit/`.
- [x] **Dejar claro qué columnas calculamos**: `docs/data_dictionary.md` (26 de 31 columnas de Silver son calculadas por nosotros).

## Pipeline

- [x] **DAG en verde**: 15/15 tareas en *success* (`manual__2026-09-22T23:33:47`, también con `force_rebuild=true` en
  `manual__2026-09-22T23:51:42`). Una corrida sin cambios en la fuente deja 3 tareas en success y 12 en *skipped*
  (`manual__2026-09-22T23:35:06`). Un cambio real en una fila de `source-db` se detecta ("cambió el contenido de la fuente")
  y reconstruye.
- [x] **source-db levantada**: servicio `source-db` (PostgreSQL 16) en `docker-compose.override.yml`, *healthy*, separado de
  la metadata de Airflow. Seed de 7 tablas verificado contra el SQLite (mismos conteos y agregados).
- [x] **Airflow Connection funcionando**: `AIRFLOW_CONN_SOCCER_SOURCE_DB` resuelve con `PostgresHook` (usuario `soccer`,
  base `soccer`, PostgreSQL 16.14). `check_source_db` pasa.
- [x] **Bronze generado desde SQL**: 4 Parquet (matches 25.979 × 83, teams 299 × 2, players 11.060 × 3,
  player_attributes 183.978 × 11).
- [x] **Silver generado**: `silver/underdog_dataset.parquet`. Es idéntico al que resulta de correr las mismas consultas contra
  el SQLite original, y determinístico entre corridas (mismo sha256).
- [x] **Target no nulo**: 0 nulos (hard check `target_sin_nulos`, test `test_target_has_no_nulls_and_is_binary`).
- [x] **Underdog definido**: en todas las filas, con gap > 0,05 (hard checks `underdog_definido`, `umbral_underdog_respetado`).
- [x] **Goles fuera del dataset de modelado**: hard check `sin_columnas_de_fuga`, test `test_no_goals_and_no_leakage_columns`.

## Tests

- [x] 85 tests en el contenedor de Airflow (`pytest tests`, Airflow 3.3.1 + pandas 2.3); 64 en local sin Airflow (los del DAG se saltean).
