-- check_source_db (SQLCheckOperator): la tarea falla si algún valor es falso.
-- Si falla con "relation ... does not exist", source-db está vacía: falta
-- correr el seed (python -m include.src.source_loader, ver README).
SELECT
    (SELECT COUNT(*) FROM match) > 0             AS hay_partidos,
    (SELECT COUNT(*) FROM league) > 0            AS hay_ligas,
    (SELECT COUNT(*) FROM team) > 0              AS hay_equipos,
    (SELECT COUNT(*) FROM player) > 0            AS hay_jugadores,
    (SELECT COUNT(*) FROM player_attributes) > 0 AS hay_atributos;
