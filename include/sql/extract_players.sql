-- Bronze: jugadores. Datos biográficos fijos de cada jugador:
--   * birthday -> edad del titular a la fecha del partido;
--   * height   -> altura media del once.
-- No se traen nombre ni peso: no los usa ningún feature.
SELECT
    p.player_api_id,
    p.birthday,
    p.height
FROM player AS p
ORDER BY p.player_api_id;
