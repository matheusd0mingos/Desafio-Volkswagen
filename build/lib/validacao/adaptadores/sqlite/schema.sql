-- Base única de validação · SQL padrão (testado em SQLite; porta para SQL Server/Azure SQL)
-- Cada CONSTRAINT nomeada corresponde a um problema encontrado no diagnóstico (1.1).
PRAGMA foreign_keys = ON;

CREATE TABLE parametro (
  nome  TEXT PRIMARY KEY,
  valor TEXT NOT NULL
);

CREATE TABLE programa (
  programa_id  TEXT PRIMARY KEY,
  tipo_veiculo TEXT NOT NULL
);

CREATE TABLE veiculo (
  chassi      TEXT PRIMARY KEY,                                   -- chave do veículo: física, não muda
  codigo      TEXT NOT NULL UNIQUE
              CONSTRAINT codigo_pt_nn CHECK (codigo GLOB 'PT-[0-9][0-9]'),
  programa_id TEXT NOT NULL REFERENCES programa(programa_id)
);

CREATE TABLE status_frota (
  chassi    TEXT NOT NULL REFERENCES veiculo(chassi),
  data      TEXT NOT NULL CONSTRAINT data_iso CHECK (date(data) IS NOT NULL AND data = date(data)),
  status    TEXT NOT NULL CONSTRAINT status_frota_lista CHECK (status IN ('Disponível', 'Em manutenção', 'Indisponível')),
  motivo    TEXT,
  previsao_retorno TEXT CONSTRAINT previsao_iso CHECK (previsao_retorno IS NULL OR previsao_retorno = date(previsao_retorno)),
  CONSTRAINT indisponivel_exige_motivo CHECK (status = 'Disponível' OR motivo IS NOT NULL),
  PRIMARY KEY (chassi, data)
);

CREATE TABLE leitura_km (
  chassi       TEXT NOT NULL REFERENCES veiculo(chassi),        -- fim do veículo órfão
  data         TEXT NOT NULL CONSTRAINT data_iso CHECK (date(data) IS NOT NULL AND data = date(data)),
  semana       TEXT GENERATED ALWAYS AS (strftime('%Y-W%W', data)) STORED,
  km           REAL NOT NULL CONSTRAINT km_numerico_positivo CHECK (typeof(km) IN ('integer', 'real') AND km >= 0),
  responsavel  TEXT NOT NULL,
  linha_origem INTEGER,
  origem       TEXT NOT NULL DEFAULT 'carga inicial' CHECK (origem IN ('carga inicial', 'plataforma')),
  lancado_em   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  PRIMARY KEY (chassi, data),
  CONSTRAINT uma_leitura_por_semana UNIQUE (chassi, semana)
);
-- Km >= leitura anterior e salto por semana comparam LINHAS diferentes: não cabem em CHECK.
-- Ficam na validação de entrada (domínio Python / Power Apps).

CREATE TABLE teste (
  teste_id   TEXT PRIMARY KEY CONSTRAINT teste_t_nnn CHECK (teste_id GLOB 'T-[0-9][0-9][0-9]'),
  chassi     TEXT NOT NULL REFERENCES veiculo(chassi),
  tipo       TEXT NOT NULL,
  prevista   TEXT NOT NULL CONSTRAINT prevista_iso CHECK (date(prevista) IS NOT NULL AND prevista = date(prevista)),
  realizada  TEXT CONSTRAINT realizada_iso CHECK (realizada IS NULL OR realizada = date(realizada)),
  iniciado   INTEGER NOT NULL DEFAULT 0 CHECK (iniciado IN (0, 1)),
  engenheiro TEXT NOT NULL
);

CREATE TABLE ocorrencia (
  ocorrencia_id   TEXT PRIMARY KEY CONSTRAINT ocorrencia_oc CHECK (ocorrencia_id GLOB 'OC-*'),
  chassi          TEXT NOT NULL REFERENCES veiculo(chassi),
  teste_id        TEXT REFERENCES teste(teste_id),
  descricao       TEXT NOT NULL,
  status          TEXT NOT NULL CONSTRAINT status_ocorrencia_lista CHECK (status IN ('Aberto', 'Em análise', 'Fechado')),
  abertura        TEXT NOT NULL CONSTRAINT abertura_iso CHECK (date(abertura) IS NOT NULL AND abertura = date(abertura)),
  fechamento      TEXT CONSTRAINT fechamento_iso CHECK (fechamento IS NULL OR fechamento = date(fechamento)),
  responsavel     TEXT NOT NULL,
  grupo_duplicata TEXT NOT NULL,
  linha_origem    INTEGER,
  origem          TEXT NOT NULL DEFAULT 'carga inicial' CHECK (origem IN ('carga inicial', 'plataforma')),
  lancado_em      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  CONSTRAINT fechamento_apos_abertura CHECK (fechamento IS NULL OR fechamento >= abertura),
  CONSTRAINT fechado_tem_data CHECK ((status = 'Fechado') = (fechamento IS NOT NULL))
);

CREATE TABLE log_qualidade (
  aba TEXT, linha_origem TEXT, campo TEXT, valor_original TEXT,
  regra TEXT, severidade TEXT, acao TEXT
);

-- O que não entrou na base: fica aqui até o dono resolver (nada se perde).
CREATE TABLE pendencia (
  id             INTEGER PRIMARY KEY,
  tabela         TEXT NOT NULL,
  linha_origem   INTEGER,
  chave          TEXT,
  motivo         TEXT NOT NULL,
  barrado_por    TEXT NOT NULL CHECK (barrado_por IN ('Domínio', 'Banco')),
  responsavel    TEXT,
  dados          TEXT,                 -- JSON da linha recusada, para corrigir e reenviar
  valor_sugerido REAL,
  resolvida      INTEGER NOT NULL DEFAULT 0 CHECK (resolvida IN (0, 1))
);

-- Status do teste não é digitado: é calculado.
CREATE VIEW vw_teste AS
SELECT t.*,
       CASE WHEN realizada IS NOT NULL THEN 'Concluído'
            WHEN prevista < (SELECT valor FROM parametro WHERE nome = 'data_corte') THEN 'Atrasado'
            WHEN iniciado = 1 THEN 'Em andamento'
            ELSE 'Planejado' END AS status
FROM teste t;

-- O Gate Review em uma consulta.
CREATE VIEW vw_gate_programa AS
WITH grupos_fechados AS (
       SELECT DISTINCT grupo_duplicata FROM ocorrencia WHERE status = 'Fechado'),
     abertas AS (
       SELECT v.programa_id, COUNT(DISTINCT o.grupo_duplicata) AS n
       FROM ocorrencia o JOIN veiculo v USING (chassi)
       WHERE o.status <> 'Fechado'
         AND o.grupo_duplicata NOT IN (SELECT grupo_duplicata FROM grupos_fechados)
       GROUP BY v.programa_id),
     km AS (
       SELECT v.programa_id, SUM(km_max - km_min) AS km
       FROM (SELECT chassi, MAX(km) AS km_max, MIN(km) AS km_min FROM leitura_km GROUP BY chassi)
       JOIN veiculo v USING (chassi)
       GROUP BY v.programa_id),
     testes AS (
       SELECT v.programa_id, SUM(t.status = 'Concluído') AS concluidos, SUM(t.status = 'Atrasado') AS atrasados
       FROM vw_teste t JOIN veiculo v USING (chassi)
       GROUP BY v.programa_id)
SELECT p.programa_id                                                  AS programa,
       (SELECT COUNT(*) FROM veiculo v WHERE v.programa_id = p.programa_id) AS veiculos,
       COALESCE(km.km, 0)                                             AS km_rodado,
       COALESCE(abertas.n, 0)                                         AS falhas_abertas,
       COALESCE(testes.concluidos, 0)                                 AS testes_concluidos,
       COALESCE(testes.atrasados, 0)                                  AS testes_atrasados
FROM programa p
LEFT JOIN km      USING (programa_id)
LEFT JOIN abertas USING (programa_id)
LEFT JOIN testes  USING (programa_id)
ORDER BY p.programa_id;
