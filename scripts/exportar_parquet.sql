-- Run from a machine with access to the linkage database (currently via an
-- SSH tunnel on local port 5454). The dev and prod instances do NOT have
-- that access: they only receive the finished .parquet.
--
--   ssh -N -L 5454:localhost:5432 <user>@<linkage-host>
--
-- The password comes from ~/.pgpass (permissions 0600), not from here.
INSTALL postgres;
LOAD postgres;

ATTACH 'postgresql://alorenzi@localhost:5454/linkage_recife3?sslmode=require' AS pg (TYPE postgres, READ_ONLY);

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
    -- 61 CNES codes for the 60 pilot units in unidades_piloto.txt.
    -- Derived by scripts/conferir_unidades_piloto.sql; re-run that
    -- script and update this list whenever the spreadsheet changes.
    -- 'Coelhos' contributes 2 codes because of the Coelhos I + II merger.
    WHERE es.codigo_cnes IN (
        817, 825, 876, 1163, 1252, 1503, 1511, 1759,
        2011, 2127, 2135, 20567, 20648, 22187, 22195, 22209,
        22217, 22225, 22233, 22268, 22306, 22314, 22322, 22330,
        22349, 22357, 22365, 22373, 22381, 24503, 24511, 24538,
        26212, 26220, 26328, 28053, 28088, 28096, 28649, 28665,
        28975, 29122, 29130, 3006468, 3153487, 3301974, 3302032, 3382001,
        3445275, 3567826, 3703223, 3862836, 5139155, 5320380, 5356881, 6008984,
        6916325, 7524501, 7946651, 7992955, 9384324
    )
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
    -- nu_doc lost its leading zeros upstream: 17% of CPFs arrive
    -- with 10 digits, 2.6% with 9. Left-padding with zeros recovers the value --
    -- 100% of the short ones then pass both check-digit validations.
    -- Without this the API cannot find anyone whose CPF starts with zero.
    SELECT DISTINCT
        rb.id_pessoa,
        'cpf'::text AS tipo_identificador,
        CASE
            WHEN btrim(tea.nu_doc::text) ~ '^[0-9]{1,11}$'
                THEN lpad(btrim(tea.nu_doc::text), 11, '0')
            ELSE NULLIF(btrim(tea.nu_doc::text), '')
        END AS valor_identificador
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
    JOIN passou_cnes pc USING (id_pessoa)
)
SELECT *
FROM base_result;
$$)

  -- Two fictitious people for smoke-testing the endpoint. They are excluded
  -- by default; they are only included if the variable is set before running:
  --   duckdb -c "SET VARIABLE incluir_linhas_teste = true;" \
  --          -c ".read scripts/exportar_parquet.sql"
  UNION ALL
  SELECT * FROM (VALUES
    (15000000::BIGINT, 'violencia', 'modelo_classificacao_provavel', CURRENT_DATE,
     'cpf', '04335193041', NULL::VARCHAR, NULL::BIGINT, TRUE),
    (15000001::BIGINT, 'violencia', 'modelo_semantica_explicita', CURRENT_DATE,
     'cpf', '10132960443', 'e-SUS APS', 654321::BIGINT, TRUE)
  ) AS t(id_pessoa, tipo_evento, metodo_identificacao, data_identificacao,
         tipo_identificador, valor_identificador, banco_origem_identificacao,
         id_registro_identificacao, gera_alerta)
  WHERE coalesce(getvariable('incluir_linhas_teste'), false)
)
TO 'dados_api.parquet'
(FORMAT PARQUET);
