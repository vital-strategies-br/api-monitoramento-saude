-- Alerts have a stable identity per source event. Creating one does not imply
-- that the client received it; each attempted positive response is recorded below.
CREATE TABLE monitoramento.alerta (
    id UUID PRIMARY KEY,
    individuo_evento_id BIGINT NOT NULL UNIQUE
        REFERENCES monitoramento.individuo_evento(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE monitoramento.alerta_resposta (
    id UUID PRIMARY KEY,
    alerta_id UUID NOT NULL REFERENCES monitoramento.alerta(id),
    endpoint TEXT NOT NULL,
    served_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    tipo_evento TEXT NOT NULL,
    metodo_identificacao TEXT NOT NULL,
    data_identificacao DATE NOT NULL,
    banco_origem_identificacao TEXT,
    id_registro_identificacao TEXT
);
CREATE INDEX idx_alerta_resposta_alerta_data
    ON monitoramento.alerta_resposta (alerta_id, served_at);

-- Store the normalized, distinct identifiers submitted for this response,
-- including identifiers that did not match the selected individual.
CREATE TABLE monitoramento.alerta_resposta_identificador (
    resposta_id UUID NOT NULL REFERENCES monitoramento.alerta_resposta(id),
    tipo_identificador TEXT NOT NULL,
    valor_identificador TEXT NOT NULL,
    PRIMARY KEY (resposta_id, tipo_identificador, valor_identificador)
);
CREATE INDEX idx_alerta_resposta_identificador_lookup
    ON monitoramento.alerta_resposta_identificador
    (tipo_identificador, valor_identificador);
