CREATE TYPE monitoramento.banco_origem_identificacao_enum AS ENUM ('e-SUS APS');

ALTER TABLE monitoramento.individuo_evento
  ADD COLUMN IF NOT EXISTS banco_origem_identificacao monitoramento.banco_origem_identificacao_enum,
  ADD COLUMN IF NOT EXISTS id_registro_identificacao text;

ALTER TABLE monitoramento.individuo_evento
ADD CONSTRAINT individuo_evento_identificacao_origem_chk
CHECK (
    (id_registro_identificacao IS NULL AND banco_origem_identificacao IS NULL)
    OR
    (id_registro_identificacao IS NOT NULL AND banco_origem_identificacao IS NOT NULL)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_individuo_evento_origem_metodo
  ON monitoramento.individuo_evento (
    individuo_id,
    tipo_evento,
    metodo_identificacao,
    banco_origem_identificacao,
    id_registro_identificacao
  )
  WHERE id_registro_identificacao IS NOT NULL
    AND banco_origem_identificacao IS NOT NULL;