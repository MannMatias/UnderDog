-- Bronze: snapshots fechados de atributos de jugador (linaje FIFA/sofifa).
-- Un jugador tiene varios snapshots en el tiempo; build_lineup_features toma,
-- para cada titular, el último ESTRICTAMENTE anterior a la fecha del partido.
--
-- Solo los atributos que alimentan algún feature (de los ~40 que tiene la
-- tabla). El ORDER BY incluye el id para que la extracción sea determinística:
-- hay 835 pares (jugador, fecha) repetidos en la fuente, todos con el mismo
-- overall_rating.
SELECT
    pa.player_api_id,
    pa.date,
    pa.overall_rating,
    pa.reactions,
    pa.sprint_speed,
    pa.strength,
    pa.finishing,
    pa.marking,
    pa.gk_reflexes,
    pa.gk_diving,
    pa.gk_handling
FROM player_attributes AS pa
ORDER BY pa.player_api_id, pa.date, pa.id;
