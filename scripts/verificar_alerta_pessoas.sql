-- ============================================================
-- Checks whether a list of people (id_pessoa) is in the alert database
-- Read-only (SELECT) — safe to run in production.
--
-- id_pessoa here is the same id_pessoa as in the linkage system
-- (registro_linkage/pessoa), which maps directly to
-- monitoramento.individuo.id.
-- ============================================================

-- 1. CSV exported from the original spreadsheet, with all columns:
--    row_id,nome,mae,nascimento,id_pessoa,nome_encontrado,nome_mae_encontrado,
--    dt_nascimento_encontrada,sexo,raca_cor,orientacao_sexual,identidade_genero,
--    id_bairro_ultimo,sim_nome,sim_nome_mae,sim_data,score_final,
--    match_percentual,is_match_exato

-- 2. Create the temporary table and load the CSV
-- Everything as TEXT so rows with empty id_pessoa/fields do not break
-- (people the linkage could not identify).
CREATE TEMP TABLE pessoas_planilha (
    row_id                   TEXT,
    nome                     TEXT,
    mae                      TEXT,
    nascimento               TEXT,
    id_pessoa                TEXT,
    nome_encontrado          TEXT,
    nome_mae_encontrado      TEXT,
    dt_nascimento_encontrada TEXT,
    sexo                     TEXT,
    raca_cor                 TEXT,
    orientacao_sexual        TEXT,
    identidade_genero        TEXT,
    id_bairro_ultimo         TEXT,
    sim_nome                 TEXT,
    sim_nome_mae             TEXT,
    sim_data                 TEXT,
    score_final              TEXT,
    match_percentual         TEXT,
    is_match_exato           TEXT
);

\copy pessoas_planilha FROM '/home/ec2-user/resultados_claria.csv' WITH (FORMAT csv, HEADER true)

-- 3. Check alert status by id_pessoa
SELECT
    pp.row_id,
    pp.nome,
    pp.nome_encontrado,
    pp.id_pessoa,
    bool_or(ie.gera_alerta) AS esta_no_alerta,
    array_agg(DISTINCT ie.metodo_identificacao) FILTER (WHERE ie.gera_alerta) AS metodo_com_alerta,
    -- method that exists but currently has gera_alerta=false (what
    -- would show up if that flag were flipped to true)
    array_agg(DISTINCT ie.metodo_identificacao) FILTER (WHERE NOT ie.gera_alerta) AS metodo_avaliado_sem_alerta,
    CASE
        WHEN NULLIF(pp.id_pessoa, '') IS NULL THEN 'id_pessoa vazio na planilha (linkage não identificou)'
        WHEN i.id IS NULL THEN 'id_pessoa não encontrado na base'
        WHEN COUNT(ie.id) = 0 THEN 'encontrado, sem evento registrado'
        WHEN bool_or(ie.gera_alerta) THEN 'NO BANCO DE ALERTA'
        ELSE 'avaliado, sem alerta'
    END AS status
FROM pessoas_planilha pp
LEFT JOIN monitoramento.individuo i
    ON i.id = NULLIF(pp.id_pessoa, '')::bigint
LEFT JOIN monitoramento.individuo_evento ie
    ON ie.individuo_id = NULLIF(pp.id_pessoa, '')::bigint
GROUP BY pp.row_id, pp.nome, pp.nome_encontrado, pp.id_pessoa, i.id
ORDER BY NULLIF(pp.row_id, '')::int;
