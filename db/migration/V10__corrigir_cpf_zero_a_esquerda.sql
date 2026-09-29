-- ============================================================
-- Recompoe o zero a esquerda dos CPFs ja carregados.
--
-- A origem (tratado_esus_aps.nu_doc) perdeu os zeros a esquerda a
-- montante: ~17% dos CPFs chegavam com 10 digitos e ~2,6% com 9.
-- Verificado contra os digitos verificadores: 100% dos valores curtos
-- passam a ser CPF valido quando completados com zero, o que descarta
-- a hipotese de serem documentos de outro tipo.
--
-- Efeito pratico do bug: a API recebe o CPF correto de 11 digitos, nao
-- acha o identificador truncado e responde negativo em silencio. Eram
-- alertas que existiam na base e nunca chegavam a quem consultava.
--
-- O export passou a aplicar lpad na origem (scripts/exportar_parquet.sql)
-- e o loader faz o mesmo por seguranca; esta migracao cuida do que ja
-- foi gravado torto.
-- ============================================================

-- 1. Quando o individuo ja tem a versao completa do mesmo CPF, a linha
--    truncada e redundante.
DELETE FROM monitoramento.individuo_identificador curto
USING monitoramento.individuo_identificador completo
WHERE curto.tipo_identificador = 'cpf'
  AND curto.valor_identificador ~ '^[0-9]{1,10}$'
  AND completo.tipo_identificador = 'cpf'
  AND completo.individuo_id      = curto.individuo_id
  AND completo.valor_identificador = lpad(curto.valor_identificador, 11, '0');

-- 2. Completa os truncados que nao colidem com nenhum CPF ja existente.
--    Dois valores truncados distintos nunca resultam no mesmo CPF
--    completado, entao nao ha colisao entre as proprias linhas atualizadas.
UPDATE monitoramento.individuo_identificador ii
SET valor_identificador = lpad(ii.valor_identificador, 11, '0')
WHERE ii.tipo_identificador = 'cpf'
  AND ii.valor_identificador ~ '^[0-9]{1,10}$'
  AND NOT EXISTS (
      SELECT 1
      FROM monitoramento.individuo_identificador outro
      WHERE outro.tipo_identificador  = 'cpf'
        AND outro.valor_identificador = lpad(ii.valor_identificador, 11, '0')
  );

-- 3. O que sobrar e CPF truncado cuja versao completa pertence a OUTRO
--    individuo — ou seja, duas pessoas do linkage que provavelmente sao
--    a mesma. Nao da para completar sem violar a unicidade e a fusao dos
--    individuos esta fora do escopo desta migracao, entao ficam como
--    estao (inertes: nunca casam com consulta) e sao apenas reportados.
DO $$
DECLARE
    restantes bigint;
BEGIN
    SELECT count(*) INTO restantes
    FROM monitoramento.individuo_identificador
    WHERE tipo_identificador = 'cpf'
      AND valor_identificador ~ '^[0-9]{1,10}$';

    IF restantes > 0 THEN
        RAISE NOTICE
          'V10: % CPF(s) truncado(s) mantidos: a versao completa ja pertence a outro individuo_id. Requer analise de duplicidade no linkage.',
          restantes;
    END IF;
END $$;
