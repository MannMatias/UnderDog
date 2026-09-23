-- Bronze: equipos. Solo el id (clave de join con match) y el nombre largo,
-- que se usa únicamente en el dataset de auditoría para que sea legible.
SELECT
    t.team_api_id,
    t.team_long_name
FROM team AS t
ORDER BY t.team_api_id;
