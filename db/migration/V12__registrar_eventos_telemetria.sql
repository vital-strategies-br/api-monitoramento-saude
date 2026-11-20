-- Dashboard events sent by the alert plugin backend (POST /api/v1/telemetria/eventos).
-- The full event is kept in `payload`; the extracted columns enforce the contract.
CREATE TABLE monitoramento.telemetria_evento (
    internal_id UUID PRIMARY KEY,
    -- Client-generated; a repeated evento_id is ignored (the first one wins).
    evento_id UUID NOT NULL UNIQUE,
    evento TEXT NOT NULL,
    -- No foreign key: an unknown alerta_id is not a reason to reject an event.
    alerta_id UUID NOT NULL,
    payload JSONB NOT NULL,
    created_by TEXT NOT NULL,
    created_on TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by TEXT,
    updated_on TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_telemetria_evento_alerta
    ON monitoramento.telemetria_evento (alerta_id);

-- An alert is closed at most once (spec CE-7).
CREATE UNIQUE INDEX uq_telemetria_evento_alerta_encerrado
    ON monitoramento.telemetria_evento (alerta_id)
    WHERE evento = 'alerta_encerrado';
