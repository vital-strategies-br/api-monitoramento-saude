-- =========================
-- Individuos sem dados pessoas
-- =========================
CREATE TABLE monitoramento.individuo (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =========================
-- Identificadores associados ao individuo
-- =========================
CREATE TABLE monitoramento.individuo_identificador (
    id BIGSERIAL PRIMARY KEY,
    individuo_id BIGINT NOT NULL
        REFERENCES monitoramento.individuo(id)
        ON DELETE CASCADE,
    tipo_identificador TEXT NOT NULL,
    valor_identificador TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_individuo_identificador_lookup
    ON monitoramento.individuo_identificador
    (tipo_identificador, valor_identificador);

-- =========================
-- Eventos associados ao individuo
-- =========================
CREATE TABLE monitoramento.individuo_evento (
    id BIGSERIAL PRIMARY KEY,
    individuo_id BIGINT NOT NULL
        REFERENCES monitoramento.individuo(id)
        ON DELETE CASCADE,
    tipo_evento TEXT NOT NULL,
    data_identificacao TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_individuo_evento_lookup
    ON monitoramento.individuo_evento
    (individuo_id, tipo_evento);

-- =========================
-- Métricas diárias por endpoint
-- =========================
CREATE TABLE monitoramento.metricas_diarias_endpoint (
    endpoint TEXT NOT NULL,
    tipo_evento TEXT NOT NULL,
    data DATE NOT NULL,
    total_chamadas BIGINT NOT NULL DEFAULT 0,
    respostas_positivas BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (endpoint, tipo_evento, data)
);
