CREATE TYPE monitoramento.metodo_identificacao_enum AS ENUM (
    'n_a',
    'modelo_semantica_explicita',
    'modelo_classificacao_provavel'
);

ALTER TABLE monitoramento.individuo_evento
ADD COLUMN metodo_identificacao monitoramento.metodo_identificacao_enum NOT NULL DEFAULT 'n_a';
