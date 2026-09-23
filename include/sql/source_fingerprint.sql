-- Huella (fingerprint) de las tablas que lee el pipeline.
--
-- Por tabla: cantidad de filas, fecha máxima (si tiene) y un hash del
-- contenido completo (md5 de cada fila, concatenados en orden de id). El
-- conteo y la fecha máxima detectan partidos nuevos; el hash detecta además
-- correcciones sobre filas existentes (un gol o una cuota corregida).
SELECT 'match' AS tabla, COUNT(*) AS filas, MAX(m.date)::text AS max_fecha,
       md5(string_agg(md5(m::text), '' ORDER BY m.id)) AS hash_contenido
FROM match AS m
UNION ALL
SELECT 'league', COUNT(*), NULL,
       md5(string_agg(md5(l::text), '' ORDER BY l.id))
FROM league AS l
UNION ALL
SELECT 'team', COUNT(*), NULL,
       md5(string_agg(md5(t::text), '' ORDER BY t.id))
FROM team AS t
UNION ALL
SELECT 'player', COUNT(*), NULL,
       md5(string_agg(md5(p::text), '' ORDER BY p.id))
FROM player AS p
UNION ALL
SELECT 'player_attributes', COUNT(*), MAX(pa.date)::text,
       md5(string_agg(md5(pa::text), '' ORDER BY pa.id))
FROM player_attributes AS pa
ORDER BY tabla;
