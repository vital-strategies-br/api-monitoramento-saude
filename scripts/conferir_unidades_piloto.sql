-- ============================================================
-- Resolve os nomes de unidades_piloto.txt em codigos CNES.
-- Somente leitura — seguro para rodar em producao.
--
--   psql "postgresql://USUARIO@HOST:PORTA/linkage_recife3?sslmode=require" \
--        -X -f scripts/conferir_unidades_piloto.sql
--
-- Rode a partir da raiz do repo (o \copy usa caminho relativo).
--
-- A lista de CNES do bloco 4 e o que alimenta scripts/exportar_parquet.sql.
-- Reexecute isto quando unidades_piloto.txt mudar e reflita o resultado la.
-- ============================================================

\set ON_ERROR_STOP on

CREATE TEMP TABLE piloto (nome_planilha text);
\copy piloto (nome_planilha) FROM 'unidades_piloto.txt'

-- Normaliza para comparacao: sem acento, minuscula, sem o que vem entre
-- parenteses, sem o prefixo 'US <numero>' e sem o token de tipo de
-- unidade. 'US 404 USF MAIS SANTO AMARO III' -> 'santo amaro iii'.
CREATE OR REPLACE FUNCTION pg_temp.norm(txt text) RETURNS text AS $$
  SELECT btrim(regexp_replace(
    regexp_replace(
      regexp_replace(
        regexp_replace(
          regexp_replace(lower(unaccent(coalesce($1,''))), '\([^)]*\)', ' ', 'g'),
          '[^a-z0-9]+', ' ', 'g'),
        '^\s*us\s+[0-9]+\s+', ' '),
      '^\s*(usf mais|usf|psf|ubs|upinha|cs|policlinica|upa)\s+', ' '),
    '\s+', ' ', 'g'));
$$ LANGUAGE sql IMMUTABLE;

-- Casos que a normalizacao nao resolve. Cada um foi conferido contra o
-- volume real em registro_linkage no periodo do export.
CREATE TEMP TABLE override (nome_planilha text, codigo_cnes bigint, motivo text);
INSERT INTO override VALUES
 ('Alto dos Coqueiros',                     3006468, 'nome_fantasia tem sufixo CORREGO DA JAQUEIRA'),
 ('Chié',                                   7992955, 'tres unidades TASSO BEZERRA CHIE; so esta tem registros no periodo'),
 ('Coelhos (Integrou Coelhos I e II)',        22195, 'unidade fundida: COELHOS I registra ate 2025-07-11, complementa o 22209'),
 ('Coque Berilo',                              1252, 'nome_fantasia e COQUE DR BERILO PERNAMBUCANO'),
 ('Dr. Luiz Wilson',                            876, 'nome_fantasia grafa WILSOM'),
 ('Eduardo Campos',                         7946651, 'a USF; a UPC DE APS homonima (184772) tem 5 registros'),
 ('Fernanda Wanderley',                     7524501, 'a USF; a UPC DE APS homonima (184764) tem 0 registros'),
 ('Francisco de Areias',                      22268, 'nome_fantasia e PROF ANTONIO FRANCISCO AREIAS'),
 ('Ilha Santa Terezinha',                     22187, 'nome_fantasia tem DE a mais: ILHA DE SANTA TEREZINHA'),
 ('José Severiano',                           26328, 'nome_fantasia tem sufixo DA SILVA'),
 ('Mario Ramos',                                1759, 'nome_fantasia tem prefixo PROF'),
 ('Padre josé edwaldo (Poço)',                20567, 'nome_fantasia tem sufixo GOMES'),
 ('Santo Amaro I',                            22217, 'nome_fantasia tem sufixo SITIO DO CEU; similaridade rankeava SANTO AMARO II na frente'),
 ('Síto Wanderley',                          5320380, 'planilha grafa Sito, base grafa SITIO'),
 ('Skylab',                                   22306, 'unica SKYLAB na base, nomeada SKYLAB II'),
 ('UBT Olinto de Oliveira',                     817, 'nome_fantasia e OLINTO OLIVEIRA, sem UBT nem DE'),
 ('Upinha Nossa Sra. Pilar',                  28665, 'nome_fantasia tem sufixo BAIRRO DO RECIFE');

CREATE TEMP VIEW p AS
  SELECT nome_planilha, pg_temp.norm(nome_planilha) AS chave FROM piloto;
CREATE TEMP VIEW e AS
  SELECT codigo_cnes, nome_fantasia, pg_temp.norm(nome_fantasia) AS chave
  FROM estabelecimento_saude;

CREATE TEMP VIEW mapa AS
  SELECT p.nome_planilha, e.codigo_cnes, e.nome_fantasia, 'exato' AS origem
  FROM p JOIN e ON e.chave = p.chave
  UNION
  SELECT o.nome_planilha, e.codigo_cnes, e.nome_fantasia, 'override'
  FROM override o JOIN e ON e.codigo_cnes = o.codigo_cnes;

\echo ''
\echo '=== 1. Mapeamento final ==='
SELECT nome_planilha, codigo_cnes, nome_fantasia, origem
FROM mapa ORDER BY nome_planilha, codigo_cnes;

\echo ''
\echo '=== 2. Nomes SEM CNES (tem de vir vazio) ==='
SELECT p.nome_planilha
FROM p WHERE NOT EXISTS (SELECT 1 FROM mapa m WHERE m.nome_planilha = p.nome_planilha)
ORDER BY 1;

\echo ''
\echo '=== 3. Overrides que nao casaram com nenhum CNES (tem de vir vazio) ==='
SELECT o.* FROM override o
WHERE NOT EXISTS (SELECT 1 FROM estabelecimento_saude es WHERE es.codigo_cnes = o.codigo_cnes)
   OR NOT EXISTS (SELECT 1 FROM piloto pl WHERE pl.nome_planilha = o.nome_planilha);

\echo ''
\echo '=== 4. Lista de CNES para exportar_parquet.sql ==='
SELECT string_agg(codigo_cnes::text, ', ' ORDER BY codigo_cnes) AS cnes_piloto
FROM (SELECT DISTINCT codigo_cnes FROM mapa) t;

\echo ''
\echo '=== 5. Resumo ==='
SELECT
  (SELECT count(*) FROM piloto)                          AS nomes_na_planilha,
  (SELECT count(DISTINCT nome_planilha) FROM mapa)       AS nomes_resolvidos,
  (SELECT count(DISTINCT codigo_cnes) FROM mapa)         AS cnes_distintos;
