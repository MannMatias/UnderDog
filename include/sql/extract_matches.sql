-- Bronze: partidos. Una fila por partido, tal como están en source-db.
--
-- Solo se traen las columnas que usa el pipeline:
--   * identificación y calendario del partido (+ nombre de la liga);
--   * goles: SOLO para construir el target, nunca llegan a Silver;
--   * los 22 titulares (player_api_id) y su coordenada Y en la cancha, que
--     define la línea (arquero / defensa / medio / ataque) de cada uno;
--   * cuotas 1X2 de las 10 casas: prepare_matches elige una por partido.
--
-- Quedan afuera a propósito: las coordenadas X (no se usan), y las columnas
-- de eventos del partido (goal, shoton, shotoff, foulcommit, card, cross,
-- corner, possession), que además solo existen después de jugarse.
SELECT
    m.match_api_id,
    l.name AS league_name,
    m.season,
    m.stage,
    m.date,
    m.home_team_api_id,
    m.away_team_api_id,
    m.home_team_goal,
    m.away_team_goal,
    m.home_player_1,
    m.home_player_2,
    m.home_player_3,
    m.home_player_4,
    m.home_player_5,
    m.home_player_6,
    m.home_player_7,
    m.home_player_8,
    m.home_player_9,
    m.home_player_10,
    m.home_player_11,
    m.away_player_1,
    m.away_player_2,
    m.away_player_3,
    m.away_player_4,
    m.away_player_5,
    m.away_player_6,
    m.away_player_7,
    m.away_player_8,
    m.away_player_9,
    m.away_player_10,
    m.away_player_11,
    m.home_player_y1,
    m.home_player_y2,
    m.home_player_y3,
    m.home_player_y4,
    m.home_player_y5,
    m.home_player_y6,
    m.home_player_y7,
    m.home_player_y8,
    m.home_player_y9,
    m.home_player_y10,
    m.home_player_y11,
    m.away_player_y1,
    m.away_player_y2,
    m.away_player_y3,
    m.away_player_y4,
    m.away_player_y5,
    m.away_player_y6,
    m.away_player_y7,
    m.away_player_y8,
    m.away_player_y9,
    m.away_player_y10,
    m.away_player_y11,
    m.psh, m.psd, m.psa,
    m.b365h, m.b365d, m.b365a,
    m.bwh, m.bwd, m.bwa,
    m.vch, m.vcd, m.vca,
    m.whh, m.whd, m.wha,
    m.iwh, m.iwd, m.iwa,
    m.lbh, m.lbd, m.lba,
    m.sjh, m.sjd, m.sja,
    m.gbh, m.gbd, m.gba,
    m.bsh, m.bsd, m.bsa
FROM match AS m
JOIN league AS l ON l.id = m.league_id
ORDER BY m.match_api_id;
