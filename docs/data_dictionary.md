# Diccionario de datos

> Generado con `python -m include.src.columns` desde `include/src/columns.py`, el mismo catálogo que usa el pipeline para construir Silver y los quality checks. No editar a mano.

**Momento de la predicción**: publicadas las alineaciones (~1 h antes del partido), antes del pitazo. *Pre-partido* = el valor existe en ese momento. **Calculada** = la construimos nosotros en el pipeline; **fuente** = viene tal cual de la European Soccer Database.

## Silver: `include/data/silver/underdog_dataset.parquet` (31 columnas)

| columna | rol | origen | tipo | disponible | entra al modelo | nulos |
|---|---|---|---|---|---|---|
| `match_id` | identificador | fuente | entero | pre-partido | no | 0 |
| `fecha` | metadata | fuente | fecha | pre-partido | no | 0 |
| `temporada` | metadata | fuente | texto | pre-partido | no | 0 |
| `jornada` | feature | fuente | entero | pre-partido | no | 0 |
| `liga` | feature | fuente | categórica | pre-partido | no | 0 |
| `odds_source` | metadata | calculada | texto | pre-partido | no | 0 |
| `prob_home` | auxiliar | calculada | decimal | pre-partido | no | 0 |
| `prob_draw` | feature | calculada | decimal | pre-partido | sí | 0 |
| `prob_away` | auxiliar | calculada | decimal | pre-partido | no | 0 |
| `equipo_favorito` | feature | calculada | categórica | pre-partido | no | 0 |
| `prob_favorito` | auxiliar | calculada | decimal | pre-partido | no | 0 |
| `prob_no_favorito` | feature | calculada | decimal | pre-partido | sí | 0 |
| `nofav_xi_overall_mean_gap` | feature | calculada | decimal | pre-partido | sí | 0 |
| `nofav_top3_overall_gap` | feature | calculada | decimal | pre-partido | sí | 0 |
| `nofav_best_overall_gap` | feature | calculada | decimal | pre-partido | sí | 0 |
| `nofav_worst_overall_gap` | feature | calculada | decimal | pre-partido | sí | 0 |
| `nofav_overall_std_gap` | feature | calculada | decimal | pre-partido | no | 0 |
| `nofav_gk_overall_gap` | feature | calculada | decimal | pre-partido | no | 4 |
| `nofav_def_overall_gap` | feature | calculada | decimal | pre-partido | sí | 2 |
| `nofav_mid_overall_gap` | feature | calculada | decimal | pre-partido | sí | 2 |
| `nofav_att_overall_gap` | feature | calculada | decimal | pre-partido | sí | 2 |
| `nofav_fastest_sprint_speed_gap` | feature | calculada | decimal | pre-partido | no | 0 |
| `nofav_best_finishing_gap` | feature | calculada | decimal | pre-partido | sí | 0 |
| `nofav_best_reactions_gap` | feature | calculada | decimal | pre-partido | sí | 0 |
| `nofav_best_marking_gap` | feature | calculada | decimal | pre-partido | sí | 0 |
| `nofav_strongest_strength_gap` | feature | calculada | decimal | pre-partido | no | 0 |
| `nofav_xi_age_mean_gap` | feature | calculada | decimal | pre-partido | no | 0 |
| `nofav_xi_height_mean_gap` | feature | calculada | decimal | pre-partido | no | 0 |
| `nofav_formacion` | feature | calculada | categórica | pre-partido | no | 2 |
| `fav_formacion` | feature | calculada | categórica | pre-partido | no | 2 |
| `gano_no_favorito` | target | calculada | booleano | post-partido | no | 0 |

### `match_id`

- **Descripción**: Identificador del partido (clave primaria: una fila = un partido).
- **Tipo**: entero
- **Rol**: identificador
- **Origen**: fuente original
- **De dónde sale**: `match.match_api_id`
- **Fórmula**: —
- **Disponible**: pre-partido
- **¿Entra al modelo?**: no (IDENTIFICADOR)
- **Motivo**: Clave, no feature: su valor no dice nada del partido.
- **¿Puede ser nula?**: no
- **Nulos en el Silver actual**: 0

### `fecha`

- **Descripción**: Fecha del partido.
- **Tipo**: fecha
- **Rol**: metadata
- **Origen**: fuente original
- **De dónde sale**: `match.date`
- **Fórmula**: —
- **Disponible**: pre-partido
- **¿Entra al modelo?**: no (AUXILIAR)
- **Motivo**: Se conserva para separar train/test en el tiempo; no es feature.
- **¿Puede ser nula?**: no
- **Nulos en el Silver actual**: 0

### `temporada`

- **Descripción**: Temporada (ej. 2012/2013).
- **Tipo**: texto
- **Rol**: metadata
- **Origen**: fuente original
- **De dónde sale**: `match.season`
- **Fórmula**: —
- **Disponible**: pre-partido
- **¿Entra al modelo?**: no (AUXILIAR)
- **Motivo**: Se conserva para cortes temporales; como feature solo identificaría la época.
- **¿Puede ser nula?**: no
- **Nulos en el Silver actual**: 0

### `jornada`

- **Descripción**: Número de fecha dentro de la temporada.
- **Tipo**: entero
- **Rol**: feature
- **Origen**: fuente original
- **De dónde sale**: `match.stage`
- **Fórmula**: —
- **Disponible**: pre-partido
- **¿Entra al modelo?**: candidata, no entra (SALE)
- **Motivo**: Se conoce antes del partido. Contra el target: separación estandarizada = 0,012 (rojo), no va al modelo; queda en Silver para análisis.
- **¿Puede ser nula?**: no
- **Nulos en el Silver actual**: 0

### `liga`

- **Descripción**: Liga del partido.
- **Tipo**: categórica
- **Rol**: feature
- **Origen**: fuente original
- **De dónde sale**: `league.name`
- **Fórmula**: —
- **Disponible**: pre-partido
- **¿Entra al modelo?**: candidata, no entra (SALE)
- **Motivo**: Se conoce antes del partido. Contra el target: η² = 0,0016 (rojo), no va al modelo; queda en Silver para análisis. Hipótesis 4 (refutada): la tasa de victoria del underdog casi no cambia entre ligas.
- **¿Puede ser nula?**: no
- **Nulos en el Silver actual**: 0

### `odds_source`

- **Descripción**: Casa de apuestas de la que salen las cuotas de la fila (PS = Pinnacle, B365 = Bet365, BW = bwin).
- **Tipo**: texto
- **Rol**: metadata
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `prepare_matches`
- **Fórmula**: primera casa de ODDS_BOOKMAKERS con las 3 cuotas completas
- **Disponible**: pre-partido
- **¿Entra al modelo?**: no (AUXILIAR)
- **Motivo**: Trazabilidad. No es feature: está confundida con la época (B365 hasta 2011/12, PS desde 2012/13).
- **¿Puede ser nula?**: no
- **Nulos en el Silver actual**: 0

### `prob_home`

- **Descripción**: Probabilidad implícita normalizada de victoria local.
- **Tipo**: decimal
- **Rol**: auxiliar
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `prepare_matches`
- **Fórmula**: (1 / odds_home) / overround
- **Disponible**: pre-partido
- **¿Entra al modelo?**: no (AUXILIAR)
- **Motivo**: Define al favorito y valida prob_home + prob_draw + prob_away = 1. Como feature es redundante con prob_favorito/prob_no_favorito + equipo_favorito.
- **¿Puede ser nula?**: no
- **Nulos en el Silver actual**: 0

### `prob_draw`

- **Descripción**: Probabilidad implícita normalizada de empate.
- **Tipo**: decimal
- **Rol**: feature
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `prepare_matches`
- **Fórmula**: (1 / odds_draw) / overround
- **Disponible**: pre-partido
- **¿Entra al modelo?**: sí (ENTRA)
- **Motivo**: Precio de mercado anterior al partido. Contra el target: separación estandarizada = 0,429 (amarillo), entra al modelo. Cola larga (asimetría -1,3), pero la relación con el target es recta (brecha Spearman - Pearson 0,013): entra sin transformar.
- **¿Puede ser nula?**: no
- **Nulos en el Silver actual**: 0

### `prob_away`

- **Descripción**: Probabilidad implícita normalizada de victoria visitante.
- **Tipo**: decimal
- **Rol**: auxiliar
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `prepare_matches`
- **Fórmula**: (1 / odds_away) / overround
- **Disponible**: pre-partido
- **¿Entra al modelo?**: no (AUXILIAR)
- **Motivo**: Idem prob_home.
- **¿Puede ser nula?**: no
- **Nulos en el Silver actual**: 0

### `equipo_favorito`

- **Descripción**: Qué equipo es el favorito: 'local' o 'visitante'.
- **Tipo**: categórica
- **Rol**: feature
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `define_underdog_and_target`
- **Fórmula**: 'local' si prob_home > prob_away, 'visitante' si prob_home < prob_away
- **Disponible**: pre-partido
- **¿Entra al modelo?**: candidata, no entra (SALE)
- **Motivo**: Sale de las cuotas pre-partido. Contra el target: η² = 0,0016 (rojo), no va al modelo; queda en Silver para análisis. La localía ya está en las probabilidades del mercado.
- **¿Puede ser nula?**: no
- **Nulos en el Silver actual**: 0

### `prob_favorito`

- **Descripción**: Probabilidad implícita de victoria del favorito.
- **Tipo**: decimal
- **Rol**: auxiliar
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `define_underdog_and_target`
- **Fórmula**: max(prob_home, prob_away)
- **Disponible**: pre-partido
- **¿Entra al modelo?**: no (AUXILIAR)
- **Motivo**: Define el umbral (prob_favorito - prob_no_favorito > 0.05). Como feature es derivable: 1 - prob_draw - prob_no_favorito.
- **¿Puede ser nula?**: no
- **Nulos en el Silver actual**: 0

### `prob_no_favorito`

- **Descripción**: Probabilidad implícita de victoria del underdog.
- **Tipo**: decimal
- **Rol**: feature
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `define_underdog_and_target`
- **Fórmula**: min(prob_home, prob_away)
- **Disponible**: pre-partido
- **¿Entra al modelo?**: sí (ENTRA)
- **Motivo**: Precio de mercado anterior al partido. Contra el target: separación estandarizada = 0,497 (amarillo), entra al modelo. Es la línea de base del modelo: el mercado solo.
- **¿Puede ser nula?**: no
- **Nulos en el Silver actual**: 0

### `nofav_xi_overall_mean_gap`

- **Descripción**: Ventaja del underdog en calidad media del once titular. Positivo = el underdog es superior.
- **Tipo**: decimal
- **Rol**: feature
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `build_lineup_features + build_silver_dataset`
- **Fórmula**: underdog - favorito, donde cada lado = promedio de overall_rating de los 11 titulares
- **Disponible**: pre-partido
- **¿Entra al modelo?**: sí (ENTRA)
- **Motivo**: Existe al publicarse las alineaciones: atributos con snapshot anterior al partido. Contra el target: separación estandarizada = 0,358 (amarillo), entra al modelo. Hipótesis 2 (refutada): al controlar por prob_no_favorito la separación cae a 0,08 (rojo). Entra, pero la Entrega 3 tiene que medir si agrega algo sobre el modelo solo-mercado.
- **¿Puede ser nula?**: sí: nula si en el underdog o en el favorito ningún titular tiene snapshot de atributos anterior al partido
- **Nulos en el Silver actual**: 0

### `nofav_top3_overall_gap`

- **Descripción**: Ventaja del underdog en calidad de las 3 figuras del once. Positivo = el underdog es superior.
- **Tipo**: decimal
- **Rol**: feature
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `build_lineup_features + build_silver_dataset`
- **Fórmula**: underdog - favorito, donde cada lado = promedio de los 3 mayores overall_rating del once
- **Disponible**: pre-partido
- **¿Entra al modelo?**: sí (ENTRA)
- **Motivo**: Existe al publicarse las alineaciones: atributos con snapshot anterior al partido. Contra el target: separación estandarizada = 0,329 (amarillo), entra al modelo. Correlación 0,96 con nofav_best_overall_gap y 0,93 con nofav_xi_overall_mean_gap: redundancia a resolver en la Entrega 3.
- **¿Puede ser nula?**: sí: nula si en el underdog o en el favorito ningún titular tiene snapshot de atributos anterior al partido
- **Nulos en el Silver actual**: 0

### `nofav_best_overall_gap`

- **Descripción**: Ventaja del underdog en calidad del mejor jugador en cancha. Positivo = el underdog es superior.
- **Tipo**: decimal
- **Rol**: feature
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `build_lineup_features + build_silver_dataset`
- **Fórmula**: underdog - favorito, donde cada lado = máximo overall_rating del once
- **Disponible**: pre-partido
- **¿Entra al modelo?**: sí (ENTRA)
- **Motivo**: Existe al publicarse las alineaciones: atributos con snapshot anterior al partido. Contra el target: separación estandarizada = 0,307 (amarillo), entra al modelo. Correlación 0,96 con nofav_top3_overall_gap: redundancia a resolver en la Entrega 3.
- **¿Puede ser nula?**: sí: nula si en el underdog o en el favorito ningún titular tiene snapshot de atributos anterior al partido
- **Nulos en el Silver actual**: 0

### `nofav_worst_overall_gap`

- **Descripción**: Ventaja del underdog en el eslabón más débil del once. Positivo = el underdog es superior.
- **Tipo**: decimal
- **Rol**: feature
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `build_lineup_features + build_silver_dataset`
- **Fórmula**: underdog - favorito, donde cada lado = mínimo overall_rating del once
- **Disponible**: pre-partido
- **¿Entra al modelo?**: sí (ENTRA)
- **Motivo**: Existe al publicarse las alineaciones: atributos con snapshot anterior al partido. Contra el target: separación estandarizada = 0,225 (amarillo), entra al modelo.
- **¿Puede ser nula?**: sí: nula si en el underdog o en el favorito ningún titular tiene snapshot de atributos anterior al partido
- **Nulos en el Silver actual**: 0

### `nofav_overall_std_gap`

- **Descripción**: Ventaja del underdog en dispersión del once (equipo parejo vs. dependiente de figuras). Positivo = el underdog es superior.
- **Tipo**: decimal
- **Rol**: feature
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `build_lineup_features + build_silver_dataset`
- **Fórmula**: underdog - favorito, donde cada lado = desvío estándar de overall_rating del once
- **Disponible**: pre-partido
- **¿Entra al modelo?**: candidata, no entra (SALE)
- **Motivo**: Existe al publicarse las alineaciones: atributos con snapshot anterior al partido. Contra el target: separación estandarizada = -0,005 (rojo), no va al modelo; queda en Silver para análisis.
- **¿Puede ser nula?**: sí: nula si en el underdog o en el favorito menos de 2 titulares con snapshot previo
- **Nulos en el Silver actual**: 0

### `nofav_gk_overall_gap`

- **Descripción**: Ventaja del underdog en calidad del arquero titular. Positivo = el underdog es superior.
- **Tipo**: decimal
- **Rol**: feature
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `build_lineup_features + build_silver_dataset`
- **Fórmula**: underdog - favorito, donde cada lado = overall_rating del titular con Y=1 (si hay dos, el de mayor gk_reflexes)
- **Disponible**: pre-partido
- **¿Entra al modelo?**: candidata, no entra (SALE)
- **Motivo**: Existe al publicarse las alineaciones: atributos con snapshot anterior al partido. Contra el target: separación estandarizada = 0,160 (rojo), no va al modelo; queda en Silver para análisis. Hipótesis 3: los subatributos del arquero salen por redundancia; el propio gk_overall tampoco separa.
- **¿Puede ser nula?**: sí: nula si en el underdog o en el favorito ningún titular tiene coordenada Y de arquero, o el arquero no tiene snapshot previo
- **Nulos en el Silver actual**: 4

### `nofav_def_overall_gap`

- **Descripción**: Ventaja del underdog en calidad de la línea defensiva que salió a jugar. Positivo = el underdog es superior.
- **Tipo**: decimal
- **Rol**: feature
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `build_lineup_features + build_silver_dataset`
- **Fórmula**: underdog - favorito, donde cada lado = promedio overall de titulares con 1 < Y <= 3
- **Disponible**: pre-partido
- **¿Entra al modelo?**: sí (ENTRA)
- **Motivo**: Existe al publicarse las alineaciones: atributos con snapshot anterior al partido. Contra el target: separación estandarizada = 0,337 (amarillo), entra al modelo.
- **¿Puede ser nula?**: sí: nula si en el underdog o en el favorito ningún titular de ese equipo quedó en esa línea según su coordenada Y (coordenadas mal cargadas en la fuente)
- **Nulos en el Silver actual**: 2

### `nofav_mid_overall_gap`

- **Descripción**: Ventaja del underdog en calidad del mediocampo que salió a jugar. Positivo = el underdog es superior.
- **Tipo**: decimal
- **Rol**: feature
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `build_lineup_features + build_silver_dataset`
- **Fórmula**: underdog - favorito, donde cada lado = promedio overall de titulares con 3 < Y <= 7
- **Disponible**: pre-partido
- **¿Entra al modelo?**: sí (ENTRA)
- **Motivo**: Existe al publicarse las alineaciones: atributos con snapshot anterior al partido. Contra el target: separación estandarizada = 0,303 (amarillo), entra al modelo.
- **¿Puede ser nula?**: sí: nula si en el underdog o en el favorito ningún titular de ese equipo quedó en esa línea según su coordenada Y (coordenadas mal cargadas en la fuente)
- **Nulos en el Silver actual**: 2

### `nofav_att_overall_gap`

- **Descripción**: Ventaja del underdog en calidad de la línea de ataque que salió a jugar. Positivo = el underdog es superior.
- **Tipo**: decimal
- **Rol**: feature
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `build_lineup_features + build_silver_dataset`
- **Fórmula**: underdog - favorito, donde cada lado = promedio overall de titulares con Y > 7
- **Disponible**: pre-partido
- **¿Entra al modelo?**: sí (ENTRA)
- **Motivo**: Existe al publicarse las alineaciones: atributos con snapshot anterior al partido. Contra el target: separación estandarizada = 0,287 (amarillo), entra al modelo.
- **¿Puede ser nula?**: sí: nula si en el underdog o en el favorito ningún titular de ese equipo quedó en esa línea según su coordenada Y (coordenadas mal cargadas en la fuente)
- **Nulos en el Silver actual**: 2

### `nofav_fastest_sprint_speed_gap`

- **Descripción**: Ventaja del underdog en velocidad del jugador más rápido. Positivo = el underdog es superior.
- **Tipo**: decimal
- **Rol**: feature
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `build_lineup_features + build_silver_dataset`
- **Fórmula**: underdog - favorito, donde cada lado = máximo sprint_speed del once
- **Disponible**: pre-partido
- **¿Entra al modelo?**: candidata, no entra (SALE)
- **Motivo**: Existe al publicarse las alineaciones: atributos con snapshot anterior al partido. Contra el target: separación estandarizada = 0,144 (rojo), no va al modelo; queda en Silver para análisis.
- **¿Puede ser nula?**: sí: nula si en el underdog o en el favorito ningún titular tiene snapshot de atributos anterior al partido
- **Nulos en el Silver actual**: 0

### `nofav_best_finishing_gap`

- **Descripción**: Ventaja del underdog en definición del mejor definidor. Positivo = el underdog es superior.
- **Tipo**: decimal
- **Rol**: feature
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `build_lineup_features + build_silver_dataset`
- **Fórmula**: underdog - favorito, donde cada lado = máximo finishing del once
- **Disponible**: pre-partido
- **¿Entra al modelo?**: sí (ENTRA)
- **Motivo**: Existe al publicarse las alineaciones: atributos con snapshot anterior al partido. Contra el target: separación estandarizada = 0,218 (amarillo), entra al modelo.
- **¿Puede ser nula?**: sí: nula si en el underdog o en el favorito ningún titular tiene snapshot de atributos anterior al partido
- **Nulos en el Silver actual**: 0

### `nofav_best_reactions_gap`

- **Descripción**: Ventaja del underdog en reacción (reactions) del jugador que mejor la tiene. Positivo = el underdog es superior.
- **Tipo**: decimal
- **Rol**: feature
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `build_lineup_features + build_silver_dataset`
- **Fórmula**: underdog - favorito, donde cada lado = máximo reactions del once
- **Disponible**: pre-partido
- **¿Entra al modelo?**: sí (ENTRA)
- **Motivo**: Existe al publicarse las alineaciones: atributos con snapshot anterior al partido. Contra el target: separación estandarizada = 0,276 (amarillo), entra al modelo.
- **¿Puede ser nula?**: sí: nula si en el underdog o en el favorito ningún titular tiene snapshot de atributos anterior al partido
- **Nulos en el Silver actual**: 0

### `nofav_best_marking_gap`

- **Descripción**: Ventaja del underdog en marca del mejor marcador. Positivo = el underdog es superior.
- **Tipo**: decimal
- **Rol**: feature
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `build_lineup_features + build_silver_dataset`
- **Fórmula**: underdog - favorito, donde cada lado = máximo marking del once
- **Disponible**: pre-partido
- **¿Entra al modelo?**: sí (ENTRA)
- **Motivo**: Existe al publicarse las alineaciones: atributos con snapshot anterior al partido. Contra el target: separación estandarizada = 0,251 (amarillo), entra al modelo.
- **¿Puede ser nula?**: sí: nula si en el underdog o en el favorito ningún titular tiene snapshot de atributos anterior al partido
- **Nulos en el Silver actual**: 0

### `nofav_strongest_strength_gap`

- **Descripción**: Ventaja del underdog en fuerza del jugador más fuerte. Positivo = el underdog es superior.
- **Tipo**: decimal
- **Rol**: feature
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `build_lineup_features + build_silver_dataset`
- **Fórmula**: underdog - favorito, donde cada lado = máximo strength del once
- **Disponible**: pre-partido
- **¿Entra al modelo?**: candidata, no entra (SALE)
- **Motivo**: Existe al publicarse las alineaciones: atributos con snapshot anterior al partido. Contra el target: separación estandarizada = 0,105 (rojo), no va al modelo; queda en Silver para análisis.
- **¿Puede ser nula?**: sí: nula si en el underdog o en el favorito ningún titular tiene snapshot de atributos anterior al partido
- **Nulos en el Silver actual**: 0

### `nofav_xi_age_mean_gap`

- **Descripción**: Ventaja del underdog en edad media del once (años). Positivo = el underdog es superior.
- **Tipo**: decimal
- **Rol**: feature
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `build_lineup_features + build_silver_dataset`
- **Fórmula**: underdog - favorito, donde cada lado = promedio de (fecha del partido - birthday) / 365,25
- **Disponible**: pre-partido
- **¿Entra al modelo?**: candidata, no entra (SALE)
- **Motivo**: Existe al publicarse las alineaciones: atributos con snapshot anterior al partido. Contra el target: separación estandarizada = -0,012 (rojo), no va al modelo; queda en Silver para análisis.
- **¿Puede ser nula?**: sí: nula si en el underdog o en el favorito titular sin fecha de nacimiento en la tabla player
- **Nulos en el Silver actual**: 0

### `nofav_xi_height_mean_gap`

- **Descripción**: Ventaja del underdog en altura media del once (cm). Positivo = el underdog es superior.
- **Tipo**: decimal
- **Rol**: feature
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `build_lineup_features + build_silver_dataset`
- **Fórmula**: underdog - favorito, donde cada lado = promedio de height de los 11 titulares
- **Disponible**: pre-partido
- **¿Entra al modelo?**: candidata, no entra (SALE)
- **Motivo**: Existe al publicarse las alineaciones: atributos con snapshot anterior al partido. Contra el target: separación estandarizada = 0,002 (rojo), no va al modelo; queda en Silver para análisis.
- **¿Puede ser nula?**: sí: nula si en el underdog o en el favorito titular sin altura en la tabla player
- **Nulos en el Silver actual**: 0

### `nofav_formacion`

- **Descripción**: Formación del underdog como defensores-medios-delanteros (ej. 4-4-2).
- **Tipo**: categórica
- **Rol**: feature
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `build_lineup_features`
- **Fórmula**: conteo de titulares por línea según su coordenada Y
- **Disponible**: pre-partido
- **¿Entra al modelo?**: candidata, no entra (SALE)
- **Motivo**: Existe al publicarse la alineación. Contra el target: η² = 0,0004 (rojo), no va al modelo; queda en Silver para análisis. 12 categorías. Los mediapuntas (Y=8) cuentan como ataque: un 4-2-3-1 aparece como 4-2-4.
- **¿Puede ser nula?**: sí: las coordenadas Y de los titulares de campo vienen vacías o en 0 en la fuente: no se puede reconstruir la formación (antes figuraba como un falso '0-0-0')
- **Nulos en el Silver actual**: 2

### `fav_formacion`

- **Descripción**: Formación del favorito (mismo formato).
- **Tipo**: categórica
- **Rol**: feature
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `build_lineup_features`
- **Fórmula**: idem nofav_formacion
- **Disponible**: pre-partido
- **¿Entra al modelo?**: candidata, no entra (SALE)
- **Motivo**: Existe al publicarse la alineación. Contra el target: η² = 0,0013 (rojo), no va al modelo; queda en Silver para análisis.
- **¿Puede ser nula?**: sí: las coordenadas Y de los titulares de campo vienen vacías o en 0 en la fuente: no se puede reconstruir la formación (antes figuraba como un falso '0-0-0')
- **Nulos en el Silver actual**: 2

### `gano_no_favorito`

- **Descripción**: True si el underdog ganó el partido. Empate o derrota = False.
- **Tipo**: booleano
- **Rol**: target
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `define_underdog_and_target`
- **Fórmula**: (favorito local y ganó el visitante) o (favorito visitante y ganó el local)
- **Disponible**: post-partido
- **¿Entra al modelo?**: no (TARGET)
- **Motivo**: Es lo que se quiere predecir: nunca puede ser feature.
- **¿Puede ser nula?**: no
- **Nulos en el Silver actual**: 0

## Auditoría: `include/data/audit/match_audit.parquet` (13 columnas)

Mismas filas que Silver, unidas por `match_id`. Tiene lo que **no puede** ser feature: goles y resultados (post-partido), nombres de equipos y cuotas crudas. Sirve para rastrear y leer resultados, nunca para entrenar.

### `equipo_local`

- **Descripción**: Nombre del equipo local.
- **Tipo**: texto
- **Rol**: auditoria
- **Origen**: fuente original
- **De dónde sale**: `team.team_long_name`
- **Fórmula**: —
- **Disponible**: pre-partido
- **¿Entra al modelo?**: no (SOLO AUDITORÍA)
- **Motivo**: Descriptiva: 299 equipos, no generaliza a partidos nuevos. Solo para leer resultados.
- **¿Puede ser nula?**: no

### `equipo_visitante`

- **Descripción**: Nombre del equipo visitante.
- **Tipo**: texto
- **Rol**: auditoria
- **Origen**: fuente original
- **De dónde sale**: `team.team_long_name`
- **Fórmula**: —
- **Disponible**: pre-partido
- **¿Entra al modelo?**: no (SOLO AUDITORÍA)
- **Motivo**: Idem equipo_local.
- **¿Puede ser nula?**: no

### `odds_home`

- **Descripción**: Cuota decimal de victoria local de odds_source.
- **Tipo**: decimal
- **Rol**: auditoria
- **Origen**: fuente original
- **De dónde sale**: `match.<casa>h`
- **Fórmula**: —
- **Disponible**: pre-partido
- **¿Entra al modelo?**: no (SOLO AUDITORÍA)
- **Motivo**: Derivable: prob_home = (1/odds_home)/overround. Se guarda para reconstruir las probabilidades.
- **¿Puede ser nula?**: no

### `odds_draw`

- **Descripción**: Cuota decimal de empate de odds_source.
- **Tipo**: decimal
- **Rol**: auditoria
- **Origen**: fuente original
- **De dónde sale**: `match.<casa>d`
- **Fórmula**: —
- **Disponible**: pre-partido
- **¿Entra al modelo?**: no (SOLO AUDITORÍA)
- **Motivo**: Idem odds_home.
- **¿Puede ser nula?**: no

### `odds_away`

- **Descripción**: Cuota decimal de victoria visitante de odds_source.
- **Tipo**: decimal
- **Rol**: auditoria
- **Origen**: fuente original
- **De dónde sale**: `match.<casa>a`
- **Fórmula**: —
- **Disponible**: pre-partido
- **¿Entra al modelo?**: no (SOLO AUDITORÍA)
- **Motivo**: Idem odds_home.
- **¿Puede ser nula?**: no

### `overround`

- **Descripción**: Margen de la casa: suma de las tres probabilidades sin normalizar.
- **Tipo**: decimal
- **Rol**: auditoria
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `prepare_matches`
- **Fórmula**: 1/odds_home + 1/odds_draw + 1/odds_away
- **Disponible**: pre-partido
- **¿Entra al modelo?**: no (SOLO AUDITORÍA)
- **Motivo**: Mide a la casa, no al partido: depende casi solo de odds_source (B365 ~1,064, PS ~1,024) y su correlación con el target es -0,02.
- **¿Puede ser nula?**: no

### `goles_local`

- **Descripción**: Goles del local al final del partido.
- **Tipo**: entero
- **Rol**: auditoria
- **Origen**: fuente original
- **De dónde sale**: `match.home_team_goal`
- **Fórmula**: —
- **Disponible**: post-partido
- **¿Entra al modelo?**: no (SOLO AUDITORÍA)
- **Motivo**: FUGA: solo existe después del partido. Se usa únicamente para construir el target.
- **¿Puede ser nula?**: no

### `goles_visitante`

- **Descripción**: Goles del visitante al final del partido.
- **Tipo**: entero
- **Rol**: auditoria
- **Origen**: fuente original
- **De dónde sale**: `match.away_team_goal`
- **Fórmula**: —
- **Disponible**: post-partido
- **¿Entra al modelo?**: no (SOLO AUDITORÍA)
- **Motivo**: FUGA: idem goles_local.
- **¿Puede ser nula?**: no

### `resultado_ft`

- **Descripción**: Resultado final: H (local), D (empate), A (visitante).
- **Tipo**: texto
- **Rol**: auditoria
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `define_underdog_and_target`
- **Fórmula**: comparación goles_local vs goles_visitante
- **Disponible**: post-partido
- **¿Entra al modelo?**: no (SOLO AUDITORÍA)
- **Motivo**: FUGA: es el resultado del partido.
- **¿Puede ser nula?**: no

### `resultado_no_favorito`

- **Descripción**: Resultado del underdog: gano / empato / perdio.
- **Tipo**: texto
- **Rol**: auditoria
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `define_underdog_and_target`
- **Fórmula**: resultado_ft visto desde el underdog
- **Disponible**: post-partido
- **¿Entra al modelo?**: no (SOLO AUDITORÍA)
- **Motivo**: FUGA: contiene el target (gano <=> gano_no_favorito).
- **¿Puede ser nula?**: no

### `home_xi_sin_atributos`

- **Descripción**: Titulares locales sin snapshot de atributos previo.
- **Tipo**: entero
- **Rol**: auditoria
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `build_lineup_features`
- **Fórmula**: cantidad de titulares sin snapshot anterior al partido
- **Disponible**: pre-partido
- **¿Entra al modelo?**: no (SOLO AUDITORÍA)
- **Motivo**: Control de calidad de la fila (0 en casi todas), no describe el partido.
- **¿Puede ser nula?**: no

### `away_xi_sin_atributos`

- **Descripción**: Titulares visitantes sin snapshot de atributos previo.
- **Tipo**: entero
- **Rol**: auditoria
- **Origen**: **calculada por nosotros**
- **De dónde sale**: `build_lineup_features`
- **Fórmula**: idem
- **Disponible**: pre-partido
- **¿Entra al modelo?**: no (SOLO AUDITORÍA)
- **Motivo**: Idem home_xi_sin_atributos.
- **¿Puede ser nula?**: no
