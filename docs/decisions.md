# Registro de decisiones

Cada decisión tiene cuatro partes: **DECISIÓN / EVIDENCIA / JUSTIFICACIÓN / IMPACTO**. Todos los números salen del
pipeline final (corrida `manual__2026-09-22T23:33:47`) o del notebook `notebooks/entrega_2_eda.ipynb`, que los recalcula.

---

## 1. Unidad de análisis: una fila = un partido

- **DECISIÓN**: cada fila de Silver es un partido; la clave es `match_id` (`match.match_api_id` de la fuente).
- **EVIDENCIA**: 17.959 filas y 17.959 `match_id` distintos. Hard check `clave_sin_duplicados` y test `test_match_id_is_unique`.
- **JUSTIFICACIÓN**: la pregunta es sobre partidos ("¿ganará el underdog este partido?"). Una fila por jugador (lo
  estrictamente *tidy*) cambiaría la unidad de análisis. La concesión es que una fila resume a 22 jugadores, y cada
  feature se puede rastrear a jugadores concretos.
- **IMPACTO**: los features de jugadores se agregan por lado y se orientan underdog − favorito.

## 2. Target: `gano_no_favorito`

- **DECISIÓN**: `True` si ganó el underdog; empate o derrota = `False`. Booleano, sin nulos.
- **EVIDENCIA**: 3.654 True (20,35%) / 14.305 False (79,65%), 0 nulos. El test `test_target_matches_the_audited_result`
  verifica fila por fila que el target coincide con los goles guardados en auditoría.
- **JUSTIFICACIÓN**: si empató, el underdog no ganó. Dejar el empate como nulo tiraría ~25% de las filas (el underdog empata el 24,95%).
- **IMPACTO**: el problema es binario y desbalanceado (20/80). Se evalúa con AUC y log-loss, no con accuracy.

## 3. Favorito y underdog

- **DECISIÓN**:
  - **favorito** = el equipo con **mayor probabilidad implícita de ganar**;
  - **underdog** = el de **menor** probabilidad implícita de ganar.
  - Se comparan solo `prob_home` y `prob_away`. **El empate no es un equipo**: `prob_draw` no participa de la definición.
- **EVIDENCIA**: el favorito es el local en el 73,2% de los partidos (ventaja de localía). La tasa de victoria del underdog
  cae de forma monótona a medida que el favorito es más claro: 30,4% con `prob_favorito` ≤ 0,40, 26,2% entre 0,40 y 0,50,
  19,2% entre 0,50 y 0,60, 13,8% entre 0,60 y 0,70, 7,2% entre 0,70 y 0,80, y 2,9% por encima de 0,80. La lógica del target
  no está invertida.
- **JUSTIFICACIÓN**: la pregunta es "¿gana el que el mercado considera peor?". Comparar contra el empate mezclaría un
  resultado con un equipo.
- **IMPACTO**: `equipo_favorito`, `prob_favorito` y `prob_no_favorito` se calculan en `define_underdog_and_target`.

## 4. Partidos sin underdog identificable: umbral `UNDERDOG_MIN_PROB_GAP = 0.05`

- **DECISIÓN**: entra a Silver solo un partido con **|prob_home − prob_away| > 0,05**. Los demás se **filtran**
  (antes solo se marcaban con `es_partido_parejo`). Esto también saca los 103 partidos con probabilidades idénticas,
  que no tienen underdog.
- **EVIDENCIA** (`reports/threshold_sensitivity.csv`, hipótesis 1 del EDA):

| umbral | filas quedan | eliminadas | % eliminado | underdog gana | favorito gana | dif. media prob | etiqueta cambia Pinnacle↔Bet365 | mercado contradice |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0,00 | 19.559 | 103 | 0,52% | 21,43% | 53,39% | 0,307 | 1,14% | 1,32% |
| 0,02 | 18.983 | 679 | 3,45% | 21,10% | 53,82% | 0,316 | 0,11% | 0,33% |
| 0,03 | 18.694 | 968 | 4,92% | 20,88% | 54,11% | 0,320 | 0,04% | 0,14% |
| **0,05** | **17.959** | **1.703** | **8,66%** | **20,35%** | **54,70%** | **0,332** | **0,00%** | **0,01%** |
| 0,075 | 16.967 | 2.695 | 13,71% | 19,83% | 55,61% | 0,348 | 0,00% | 0,01% |
| 0,10 | 15.977 | 3.685 | 18,74% | 19,04% | 56,51% | 0,364 | 0,00% | 0,01% |

  Por tramo fino de gap, Pinnacle y Bet365 eligen distinto favorito en el **54,0%** de los partidos con gap ≤ 0,005,
  el 45,0% entre 0,005 y 0,01, el 13,2% entre 0,015 y 0,02, el 1,0% entre 0,04 y 0,045, y en el **0%** de todos los tramos
  desde 0,045. "Mercado contradice" = la mitad o más de las casas que cotizan el partido eligen otro favorito.
- **JUSTIFICACIÓN**: el pipeline usa **una** casa por partido. Si cambiar de casa cambia quién es el underdog, el target
  de esa fila es arbitrario. 0,05 es el **menor umbral evaluado** en el que ningún partido restante depende de la casa.
  Con 0,03 todavía quedan etiquetas inestables. Con 0,075 o 0,10 se pierden 5 a 10 puntos más de filas sin ganar
  estabilidad, y se sesga el dataset hacia partidos desparejos (la tasa del underdog cae a 19,04%).
- **IMPACTO**: −1.703 filas (8,66%): 103 sin underdog y 1.600 parejos, cada una registrada en `audit/excluded_matches.parquet`.
  `es_partido_parejo` desaparece (quedaría constante). El valor vive en `include/config.py`; si se cambia, la próxima
  corrida programada reconstruye Silver sola.

## 5. Ligas excluidas

- **DECISIÓN**: se excluyen *Poland Ekstraklasa* y *Switzerland Super League* (`EXCLUDED_LEAGUES`).
- **EVIDENCIA**: 0% de cobertura de cuotas en las 10 casas; 3.342 partidos.
- **JUSTIFICACIÓN**: sin cuotas no hay favorito ni underdog. Es una decisión de alcance explícita.
- **IMPACTO**: quedan 9 ligas, 8 temporadas (2008/09 a 2015/16).

## 6. Cobertura de cuotas y casa de apuestas utilizada

- **DECISIÓN**: una casa por partido, en orden de preferencia Pinnacle → Bet365 → las otras 8 (`ODDS_BOOKMAKERS`), registrada en `odds_source`.
- **EVIDENCIA**: en Silver, PS 9.513 (53,0%), B365 8.445 (47,0%), BW 1. Pinnacle no cotiza en la fuente hasta 2011/12 y
  cubre el 98,7% al 99,8% desde 2012/13. 33 partidos no tienen ninguna tripleta 1X2 completa y se excluyen.
- **JUSTIFICACIÓN**: Pinnacle es la referencia de eficiencia (margen más bajo: overround medio 1,024 vs. 1,064 de Bet365).
  Mezclar casas en una fila no tendría sentido.
- **IMPACTO**: `odds_source` queda como **metadata, no feature**: está confundida con la época. `overround` también
  sale de las features (ver 13).

## 7. Tope de probabilidad implícita de empate: `MAX_PROB_EMPATE_IMPLICITA = 0.40`

- **DECISIÓN**: se excluyen los partidos con 1/cuota de empate > 0,40.
- **EVIDENCIA** (recalculada sobre Bronze):

| 1/cuota empate | partidos | empates reales | overround medio |
|---|---:|---:|---:|
| ≤ 0,20 | 2.382 | 13,2% | 1,040 |
| 0,20–0,25 | 3.082 | 22,6% | 1,040 |
| 0,25–0,30 | 8.702 | 26,4% | 1,039 |
| 0,30–0,35 | 5.471 | 30,0% | 1,052 |
| 0,35–0,40 | 25 | 28,0% | 1,065 |
| 0,40–0,45 | 9 | 44,4% | 1,079 |
| > 0,45 | 23 | 56,5% | 1,090 |

- **JUSTIFICACIÓN**: por encima de 0,40 la cuota deja de predecir el empate y el margen salta. No es un precio pre-partido
  coherente, y sin precio no hay favorito. Son 32 partidos (29 de Serie A, 2008/09 a 2012/13).
- **IMPACTO**: −32 filas.

## 8. Por qué los goles no entran

- **DECISIÓN**: `goles_local` y `goles_visitante` existen solo en `define_underdog_and_target` para construir el target, y
  después van a `audit/match_audit.parquet`. **No están en Silver.**
- **EVIDENCIA**: hard check `sin_columnas_de_fuga`, tests `test_no_goals_and_no_leakage_columns` y
  `test_goal_columns_in_silver_fail_as_leakage`.
- **JUSTIFICACIÓN**: regla del proyecto: *si una columna solo existe después de jugarse el partido, no puede ser feature*.
  Los goles **son** el resultado.
- **IMPACTO**: cualquier intento de agregarlas a Silver hace fallar el DAG.

## 9. Por qué los resultados no entran

- **DECISIÓN**: `resultado_ft` (H/D/A) y `resultado_no_favorito` (gano/empato/perdio) van a auditoría. Tampoco se extraen
  de la fuente las columnas de eventos del partido (`goal`, `shoton`, `shotoff`, `foulcommit`, `card`, `cross`, `corner`,
  `possession`).
- **EVIDENCIA**: `resultado_no_favorito == "gano"` ⇔ `gano_no_favorito`: sería el target copiado. El test
  `test_extraction_queries_select_explicit_columns_only` verifica que las consultas no las traen.
- **JUSTIFICACIÓN**: son post-partido.
- **IMPACTO**: la lista `LEAKAGE_COLUMNS` (generada desde el catálogo) contiene las 14 columnas post-partido conocidas.

## 10. Nulos

- **DECISIÓN**: no se imputa en Silver. Cada columna que puede tener nulos tiene su motivo documentado en el catálogo, y
  el DAG falla si aparece un nulo sin motivo (`nulos_conocidos`) o una columna 100% nula.
- **EVIDENCIA**: 6 columnas con nulos, máximo 4 filas (0,02%). Todos vienen de coordenadas Y vacías o en 0 en la fuente,
  que impiden identificar al arquero (`nofav_gk_overall_gap`, 4), una línea (`nofav_def/mid/att_overall_gap`, 2 cada una)
  o la formación (2 cada una). El target no tiene nulos.
- **JUSTIFICACIÓN**: imputar en Silver sería inventar datos. En el modelado se imputa con la mediana del *train* o se descartan
  esas filas; son tan pocas que ninguna opción cambia el resultado.
- **IMPACTO**: la formación de esos partidos ahora es nula. Antes figuraba como un falso "0-0-0".

## 11. Snapshots temporales de atributos

- **DECISIÓN**: se conserva `merge_asof(direction="backward", allow_exact_matches=False)`: cada titular recibe su último
  snapshot de atributos **estrictamente anterior** a la fecha del partido. Se agregan (a) una verificación que falla si algún
  snapshot no es anterior, y (b) el descarte de snapshots vacíos.
- **EVIDENCIA**: el snapshot usado más cercano es de **1 día antes** del partido; el 100% de los 432.564 titulares tiene snapshot.
  Test `test_real_lineup_snapshots_are_strictly_before_each_match` sobre los datos reales.
  **Corrección**: la fuente repite 835 pares (jugador, fecha) y siempre es una fila completa + una fila con todos los
  atributos vacíos. El pipeline anterior elegía entre las dos según un ordenamiento inestable, así que en 111 alineaciones
  (58 locales y 53 visitantes, sobre los 19.662 partidos con cuotas coherentes) un titular quedaba "sin atributos" al azar
  y los features de ese once se calculaban con 10 jugadores. Ahora se descartan los snapshots vacíos y el orden es estable.
- **JUSTIFICACIÓN**: un rating publicado el día del partido podría ser posterior al pitazo.
- **IMPACTO**: 0,000% de titulares sin snapshot (antes 0,04%). `xi_sin_atributos` queda en 0 y pasa a auditoría.

## 12. Columnas calculadas por nosotros

- **DECISIÓN**: cada columna del catálogo indica `origen` (**fuente** o **calculada**), de qué tabla o etapa sale y su fórmula.
- **EVIDENCIA**: de las 31 columnas de Silver, 5 vienen tal cual de la fuente (`match_id`, `fecha`, `temporada`, `jornada`,
  `liga`) y **26 las calculamos nosotros**: probabilidades, favorito, target, 16 gaps y 2 formaciones. Ver `docs/data_dictionary.md`.
- **JUSTIFICACIÓN**: la devolución pidió dejar claro qué columnas son nuestras.
- **IMPACTO**: el diccionario se genera desde el catálogo (`python -m include.src.columns`) y no puede quedar desactualizado.

## 13. Features eliminadas y transformadas (de 82 a 31 columnas)

- **DECISIÓN**: 23 features, 8 columnas no-feature en Silver (clave, metadata, auxiliares y target) y el resto en
  auditoría, intermedias o eliminadas. Detalle columna por columna en `docs/column_candidates.md`.
- **EVIDENCIA** (EDA):
  - `*_gap` local − visitante (10): **exactamente derivables** de `nofav_*_gap` + `equipo_favorito` (diferencia máxima 0,0000) → SALEN.
  - Niveles `home_*/away_*` de 16 métricas (32): no agregan información a los gaps (LR p = 0,42, peor AUC fuera de
    muestra: 0,651 → 0,648) → TRANSFORMAR en `nofav_*_gap`.
  - Subatributos del arquero (6): LR p = 0,25, peor fuera de muestra → SALEN.
  - `odds_home/draw/away`: derivables de las probabilidades → auditoría. `overround`: mide a la casa (B365 1,064 ± 0,008,
    PS 1,024 ± 0,004), correlación −0,02 con el target → auditoría.
  - `pais`: 1:1 con `liga` → SALE. `prob_gap`: `prob_home − prob_away` → SALE. `es_partido_parejo`: constante tras el filtro → SALE.
  - `equipo_local/visitante`: 299 equipos, descriptivas → auditoría. `xi_sin_atributos`: control de calidad → auditoría.
- **JUSTIFICACIÓN**: no se saca información útil sin evidencia. Cada métrica de la Entrega 1 (arquero, mejor, top 3, peor,
  promedio, dispersión, velocidad, definición, reacción, marca, fuerza, líneas, edad, altura, formación) sigue en Silver
  orientada a la pregunta. La diferencia local − visitante se recupera cambiando el signo.
- **IMPACTO**: 82 → 31 columnas.

## 14. Decisiones de las hipótesis del EDA

| # | Hipótesis | Zona | Evidencia | Decisión |
|---|---|---|---|---|
| H1 | En partidos muy parejos el underdog no está bien definido | 🟢 confirmada | Etiqueta cambia Pinnacle↔Bet365 en 54% (gap ≤ 0,005), 0% desde 0,045 | Umbral 0,05, se filtra |
| H2 | Con mejor XI, el underdog gana más de lo que dice el mercado | 🟡 inconclusa | Tasa real − esperada por quintil entre −1,3 y +0,1 pp; AUC 0,647 → 0,650 fuera de muestra; LR p < 0,001 | El gap del XI entra; la base a superar es el mercado |
| H3 | Los subatributos del arquero agregan información a su overall | 🔴 refutada | Correlación 0,81–0,87; LR p = 0,25; peor fuera de muestra | Salen 6 columnas |
| H4 | `home_*/away_*` son redundantes frente a `nofav_*_gap` | 🟢 confirmada | Derivación exacta; LR p = 0,42; AUC 0,651 → 0,648 | Se transforman a gaps; salen 10 `*_gap` |

## 15. La fuente es una base de datos (arquitectura)

- **DECISIÓN**: PostgreSQL propio (`source-db`), cargado una vez con un seed. Airflow lo consulta con la Connection
  `soccer_source_db` (`SQLCheckOperator` + `PostgresHook`). Bronze es el resultado de las consultas.
- **EVIDENCIA**: el Silver producido por el DAG desde PostgreSQL es **idéntico** al calculado corriendo las mismas consultas
  contra el SQLite original (`assert_frame_equal`). Los agregados de control coinciden entre ambas bases.
- **JUSTIFICACIÓN**: devolución del profesor: Airflow no debe ser un lanzador de scripts, tiene que comunicarse con la base.
- **IMPACTO**: ningún módulo abre `sqlite3` salvo el seed; ninguna credencial está en el código. Ver `docs/architecture.md`.

## 16. Schedule

- **DECISIÓN**: `0 6 * * *` (diario 06:00 UTC), `catchup=False`, `max_active_runs=1`, con detección de cambios por huella
  y `ShortCircuit`. Disparo manual con `force_rebuild`.
- **EVIDENCIA**: una corrida sin cambios termina con 3 tareas en *success* y 12 en *skipped*.
- **JUSTIFICACIÓN**: ver `docs/architecture.md` ("Schedule y detección de cambios").
- **IMPACTO**: el DAG se puede dejar encendido sin reconstruir de más.
