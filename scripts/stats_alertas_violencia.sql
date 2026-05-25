-- ============================================================
-- Estatísticas básicas: alertas de violência (metricas_diarias_endpoint)
-- ============================================================

-- 1. Taxa de positividade geral
\echo '=== 1. Taxa de Positividade Geral ==='
SELECT
    SUM(total_chamadas)                                                              AS total_consultas,
    SUM(respostas_positivas)                                                         AS total_positivas,
    ROUND(100.0 * SUM(respostas_positivas) / NULLIF(SUM(total_chamadas), 0), 2)     AS taxa_positividade_pct,
    MIN(data)                                                                        AS primeiro_dia,
    MAX(data)                                                                        AS ultimo_dia,
    COUNT(DISTINCT data)                                                             AS dias_com_atividade
FROM monitoramento.metricas_diarias_endpoint
WHERE tipo_evento = 'violencia';

-- 2. Positivas por método
\echo ''
\echo '=== 2. Positivas por Método ==='
SELECT
    metodo_identificacao,
    SUM(total_chamadas)       AS chamadas,
    SUM(respostas_positivas)  AS positivas,
    ROUND(100.0 * SUM(respostas_positivas) / NULLIF(SUM(total_chamadas), 0), 2)
                              AS taxa_positividade_pct
FROM monitoramento.metricas_diarias_endpoint
WHERE tipo_evento = 'violencia'
  AND metodo_identificacao <> 'n_a'
GROUP BY metodo_identificacao
ORDER BY positivas DESC;

-- 3. Tendência mensal
\echo ''
\echo '=== 3. Tendência Mensal ==='
SELECT
    TO_CHAR(DATE_TRUNC('month', data), 'YYYY-MM')  AS mes,
    SUM(total_chamadas)                            AS total_consultas,
    SUM(respostas_positivas)                       AS positivas,
    ROUND(100.0 * SUM(respostas_positivas) / NULLIF(SUM(total_chamadas), 0), 2)
                                                   AS taxa_positividade_pct
FROM monitoramento.metricas_diarias_endpoint
WHERE tipo_evento = 'violencia'
GROUP BY DATE_TRUNC('month', data)
ORDER BY DATE_TRUNC('month', data);
