-- Parameters :tipo_identificador and :valor_identificador must be supplied by
-- the SQL client. Values must use the API's normalization (digits for CPF/CNS).
-- Counts describe responses prepared by the API, not confirmed UI displays.
SELECT
    i.tipo_identificador,
    i.valor_identificador,
    r.alerta_id,
    r.metodo_identificacao,
    count(*) AS total_respostas,
    min(r.served_at) AS primeira_resposta,
    max(r.served_at) AS ultima_resposta
FROM monitoramento.alerta_resposta_identificador i
JOIN monitoramento.alerta_resposta r ON r.id = i.resposta_id
WHERE i.tipo_identificador = :tipo_identificador
  AND i.valor_identificador = :valor_identificador
GROUP BY i.tipo_identificador, i.valor_identificador,
         r.alerta_id, r.metodo_identificacao
ORDER BY ultima_resposta DESC;
