INSTALL postgres;
LOAD postgres;

ATTACH 'postgresql://postgres@localhost:5454/linkage_recife3' AS pg (TYPE postgres, READ_ONLY);

COPY (
  SELECT *
  FROM postgres_query('pg', $$
WITH rl_base AS (
    SELECT
        rl.id_registro_linkage,
        rl.id_pessoa,
        rl.dt_registro::date AS data_identificacao
    FROM registro_linkage rl
    JOIN pessoa p ON p.id_pessoa = rl.id_pessoa
    WHERE rl.dt_registro >= DATE '2025-01-01'
      AND rl.idade_pessoa_registro >= 18
      AND p.sexo = 'F'
),
passou_cnes AS (
    SELECT DISTINCT rb.id_pessoa
    FROM rl_base rb
    JOIN registro_linkage rl USING (id_registro_linkage)
    JOIN estabelecimento_saude es
      ON es.id_estabelecimento_saude = rl.id_estabelecimento_saude
    WHERE es.codigo_cnes IN (22187, 28665, 9384324)
),
eventos_raw AS (
    SELECT
        rb.id_pessoa,
        'violencia'::text AS tipo_evento,
        'notificacao_sinan' AS metodo_identificacao,
        rb.data_identificacao,
        'Sinan - Violências' AS banco_origem_identificacao,
        tsv.nu_not::int AS id_registro_identificacao
    FROM rl_base rb
    JOIN tratado_sinan_viol tsv USING (id_registro_linkage)

    UNION ALL

    SELECT
        rb.id_pessoa,
        'violencia'::text AS tipo_evento,
        'modelo_semantica_explicita' AS metodo_identificacao,
        rb.data_identificacao,
        'e-SUS APS' AS banco_origem_identificacao,
        tea.cd_tba_co_seq_atend AS id_registro_identificacao
    FROM rl_base rb
    JOIN tratado_esus_aps tea USING (id_registro_linkage)
    JOIN registro_linkage_rotulo rlr USING (id_registro_linkage)
    JOIN rotulo r USING (id_rotulo)
    WHERE r.tipo_metodo = 'Padrão semântico'
      AND r.tipo_violencia IS NOT NULL

    UNION ALL

    SELECT
        rb.id_pessoa,
        'violencia'::text AS tipo_evento,
        'modelo_classificacao_provavel' AS metodo_identificacao,
        rb.data_identificacao,
        NULL::text AS banco_origem_identificacao,
        NULL::int AS id_registro_identificacao
    FROM rl_base rb
    JOIN registro_linkage_rotulo rlr USING (id_registro_linkage)
    JOIN rotulo r USING (id_rotulo)
    WHERE r.tipo_metodo = 'Classificação'
      AND r.tipo_violencia IS NOT NULL
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
        rb.id_pessoa,
        'cpf'::text AS tipo_identificador,
        NULLIF(btrim(tea.nu_doc::text), '') AS valor_identificador
    FROM rl_base rb
    LEFT JOIN tratado_esus_aps tea USING (id_registro_linkage)
    WHERE NULLIF(btrim(tea.nu_doc::text), '') IS NOT NULL

    UNION ALL

    SELECT DISTINCT
        rb.id_pessoa,
        'cns'::text AS tipo_identificador,
        NULLIF(btrim(COALESCE(
            tea.nu_cns::text,
            viol.nu_cns::text,
            iexo.nu_cns::text,
            sim.nu_cns::text,
            sih.nu_cns::text
        )), '') AS valor_identificador
    FROM rl_base rb
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
),
base_result AS (
    SELECT DISTINCT
        e.id_pessoa,
        e.tipo_evento,
        e.metodo_identificacao,
        e.data_identificacao,
        i.tipo_identificador,
        i.valor_identificador,
        e.banco_origem_identificacao,
        e.id_registro_identificacao,
        (pc.id_pessoa IS NOT NULL) AS gera_alerta
    FROM eventos e
    JOIN identificadores i USING (id_pessoa)
    LEFT JOIN passou_cnes pc USING (id_pessoa)
)
SELECT *
FROM base_result
UNION ALL
SELECT
    15000000::bigint AS id_pessoa,
    'violencia'::text AS tipo_evento,
    'modelo_classificacao_provavel'::text AS metodo_identificacao,
    CURRENT_DATE AS data_identificacao,
    'cpf'::text AS tipo_identificador,
    '04335193041'::text AS valor_identificador,
    NULL::text AS banco_origem_identificacao,
    NULL::int AS id_registro_identificacao,
    TRUE AS gera_alerta
UNION ALL
SELECT
    15000001::bigint AS id_pessoa,
    'violencia'::text AS tipo_evento,
    'modelo_semantica_explicita'::text AS metodo_identificacao,
    CURRENT_DATE AS data_identificacao,
    'cpf'::text AS tipo_identificador,
    '10132960443'::text AS valor_identificador,
    'e-SUS APS'::text AS banco_origem_identificacao,
    654321::int AS id_registro_identificacao,
    TRUE AS gera_alerta;
$$)
)
TO 'dados_api.parquet'
(FORMAT PARQUET);
