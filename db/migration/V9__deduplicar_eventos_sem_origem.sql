-- ============================================================
-- Torna a carga de eventos idempotente para registros sem origem.
--
-- O indice unico criado em V4 (ux_individuo_evento_origem_metodo) e
-- parcial: so cobre linhas com id_registro_identificacao NOT NULL.
-- Eventos de 'modelo_classificacao_provavel' chegam com origem NULL e
-- portanto nao conflitam com nada, duplicando a cada execucao do
-- loader. Aqui consolidamos o que ja foi duplicado e criamos o indice
-- que faltava, para o loader poder fazer upsert.
-- ============================================================

-- 1. Consolida cada grupo na linha mais antiga (min(id)): o alerta e
--    preservado se qualquer duplicata o tinha, e a data passa a ser a
--    identificacao mais recente do grupo.
UPDATE monitoramento.individuo_evento ie
SET gera_alerta        = g.gera_alerta,
    data_identificacao = g.data_identificacao
FROM (
    SELECT
        min(id)                 AS id_mantido,
        bool_or(gera_alerta)    AS gera_alerta,
        max(data_identificacao) AS data_identificacao
    FROM monitoramento.individuo_evento
    WHERE id_registro_identificacao IS NULL
      AND banco_origem_identificacao IS NULL
    GROUP BY individuo_id, tipo_evento, metodo_identificacao
) g
WHERE ie.id = g.id_mantido
  AND (ie.gera_alerta        IS DISTINCT FROM g.gera_alerta
    OR ie.data_identificacao IS DISTINCT FROM g.data_identificacao);

-- 2. Remove as duplicatas restantes. min(id) nao e afetado pelo UPDATE
--    acima, entao a linha mantida aqui e a mesma consolidada ali.
DELETE FROM monitoramento.individuo_evento ie
USING (
    SELECT
        min(id) AS id_mantido,
        individuo_id,
        tipo_evento,
        metodo_identificacao
    FROM monitoramento.individuo_evento
    WHERE id_registro_identificacao IS NULL
      AND banco_origem_identificacao IS NULL
    GROUP BY individuo_id, tipo_evento, metodo_identificacao
) g
WHERE ie.individuo_id         = g.individuo_id
  AND ie.tipo_evento          = g.tipo_evento
  AND ie.metodo_identificacao = g.metodo_identificacao
  AND ie.id_registro_identificacao IS NULL
  AND ie.banco_origem_identificacao IS NULL
  AND ie.id <> g.id_mantido;

-- 3. Indice complementar ao ux_individuo_evento_origem_metodo (V4):
--    juntos, cobrem todas as linhas da tabela.
CREATE UNIQUE INDEX IF NOT EXISTS ux_individuo_evento_sem_origem
  ON monitoramento.individuo_evento (
    individuo_id,
    tipo_evento,
    metodo_identificacao
  )
  WHERE id_registro_identificacao IS NULL
    AND banco_origem_identificacao IS NULL;
