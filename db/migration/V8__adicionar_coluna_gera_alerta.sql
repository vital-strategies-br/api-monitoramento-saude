ALTER TABLE monitoramento.individuo_evento ADD COLUMN gera_alerta boolean NOT NULL DEFAULT false;

DROP INDEX IF EXISTS monitoramento.idx_individuo_evento_lookup;

CREATE INDEX idx_individuo_evento_lookup_alerta
ON monitoramento.individuo_evento (individuo_id, tipo_evento, data_identificacao DESC) WHERE gera_alerta = true;
