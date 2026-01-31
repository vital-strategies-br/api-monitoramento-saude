\copy (
WITH eventos_raw AS (
    SELECT
        rl.id_pessoa,
        'violencia'::text AS tipo_evento,
        'notificacao_sinan' AS metodo_identificacao,
        rl.dt_registro::date AS data_identificacao,
        'Sinan - Violências' AS banco_origem_identificacao,
        tsv.nu_not::int AS id_registro_identificacao
    FROM registro_linkage rl
    JOIN tratado_sinan_viol tsv USING (id_registro_linkage)
    WHERE rl.dt_registro >= DATE '2025-01-01'
      AND rl.idade_pessoa_registro >= 18

    UNION ALL

    SELECT
        rl.id_pessoa,
        'violencia'::text AS tipo_evento,
        'modelo_semantica_explicita' AS metodo_identificacao,
        rl.dt_registro::date AS data_identificacao,
        'e-SUS APS' AS banco_origem_identificacao,
        tea.cd_tba_co_seq_atend AS id_registro_identificacao
    FROM registro_linkage rl
    JOIN tratado_esus_aps tea USING (id_registro_linkage)
    JOIN registro_linkage_rotulo rlr USING (id_registro_linkage)
    JOIN rotulo r USING (id_rotulo)
    WHERE rl.dt_registro >= DATE '2025-01-01'
      AND r.tipo_metodo = 'Padrão semântico'
      AND r.tipo_violencia IS NOT NULL
      AND rl.idade_pessoa_registro >= 18

    UNION ALL

    SELECT
        rl.id_pessoa,
        'violencia'::text AS tipo_evento,
        'modelo_classificacao_provavel' AS metodo_identificacao,
        rl.dt_registro::date AS data_identificacao,
        NULL::text AS banco_origem_identificacao,
        NULL::int AS id_registro_identificacao
    FROM registro_linkage rl
    JOIN registro_linkage_rotulo rlr USING (id_registro_linkage)
    JOIN rotulo r USING (id_rotulo)
    WHERE rl.dt_registro >= DATE '2025-01-01'
      AND r.tipo_metodo = 'Classificação'
      AND r.tipo_violencia IS NOT NULL
      AND rl.idade_pessoa_registro >= 18
),
eventos AS (
    SELECT *
    FROM (
        SELECT
            e.*,
            row_number() OVER (
                PARTITION BY e.id_pessoa, e.metodo_identificacao
                ORDER BY
                    e.data_identificacao DESC,
                    e.id_registro_identificacao DESC NULLS LAST
            ) AS rn
        FROM eventos_raw e
    ) x
    WHERE rn = 1
),
identificadores AS (
    SELECT DISTINCT
        rl.id_pessoa,
        'cpf'::text AS tipo_identificador,
        NULLIF(btrim(tea.nu_doc::text), '') AS valor_identificador
    FROM registro_linkage rl
    LEFT JOIN tratado_esus_aps tea USING (id_registro_linkage)
    WHERE NULLIF(btrim(tea.nu_doc::text), '') IS NOT NULL

    UNION ALL

    SELECT DISTINCT
        rl.id_pessoa,
        'cns'::text AS tipo_identificador,
        NULLIF(btrim(COALESCE(
            tea.nu_cns::text,
            viol.nu_cns::text,
            iexo.nu_cns::text,
            sim.nu_cns::text,
            sih.nu_cns::text
        )), '') AS valor_identificador
    FROM registro_linkage rl
    LEFT JOIN tratado_esus_aps   tea  USING (id_registro_linkage)
    LEFT JOIN tratado_sinan_viol viol USING (id_registro_linkage)
    LEFT JOIN tratado_sinan_iexo iexo USING (id_registro_linkage)
    LEFT JOIN tratado_sim        sim  USING (id_registro_linkage)
    LEFT JOIN tratado_sih        sih  USING (id_registro_linkage)
    WHERE NULLIF(btrim(COALESCE(
        tea.nu_cns::text,
        viol.nu_cns::text,
        iexo.nu_cns::text,
        sim.nu_cns::text,
        sih.nu_cns::text
    )), '') IS NOT NULL
)
SELECT DISTINCT
    e.id_pessoa,
    e.tipo_evento,
    e.metodo_identificacao,
    e.data_identificacao,
    i.tipo_identificador,
    i.valor_identificador,
    e.banco_origem_identificacao,
    e.id_registro_identificacao
FROM eventos e
JOIN identificadores i USING (id_pessoa)
) TO 'export_violencia_identificacao.csv' WITH (FORMAT csv, HEADER true, DELIMITER ',');
