UPDATE monitoramento.metricas_diarias_endpoint SET metodo_identificacao = 'n_a' WHERE metodo_identificacao IS NULL;

ALTER TABLE monitoramento.metricas_diarias_endpoint ALTER COLUMN metodo_identificacao SET DEFAULT 'n_a';
ALTER TABLE monitoramento.metricas_diarias_endpoint ALTER COLUMN metodo_identificacao SET NOT NULL;

ALTER TABLE monitoramento.metricas_diarias_endpoint DROP CONSTRAINT metricas_diarias_endpoint_pkey;
ALTER TABLE monitoramento.metricas_diarias_endpoint ADD CONSTRAINT metricas_diarias_endpoint_pkey PRIMARY KEY (endpoint, tipo_evento, metodo_identificacao, data);