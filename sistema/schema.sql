-- Schema do sistema novo. Idempotente (IF NOT EXISTS): roda a cada inicialização.
CREATE TABLE IF NOT EXISTS usuarios (
  id INTEGER PRIMARY KEY,
  login TEXT NOT NULL UNIQUE,
  nome TEXT NOT NULL,
  senha_hash TEXT NOT NULL,
  ativo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS corretores (
  id INTEGER PRIMARY KEY,
  nome TEXT NOT NULL,
  telefone TEXT,
  email TEXT,
  observacoes TEXT
);

CREATE TABLE IF NOT EXISTS locatarios (
  id INTEGER PRIMARY KEY,
  nome TEXT NOT NULL,
  cpf_cnpj TEXT NOT NULL UNIQUE,          -- só dígitos, 11 ou 14
  telefone TEXT,
  email TEXT NOT NULL,
  observacoes TEXT
);

CREATE TABLE IF NOT EXISTS imoveis (
  id INTEGER PRIMARY KEY,
  grupo TEXT NOT NULL,
  unidade TEXT NOT NULL,
  endereco TEXT NOT NULL,
  em_manutencao INTEGER NOT NULL DEFAULT 0,
  iptu_anual_centavos INTEGER,
  medidor_saneago TEXT,
  medidor_enel TEXT,
  observacoes TEXT,
  UNIQUE (grupo, unidade)
);

CREATE TABLE IF NOT EXISTS contratos (
  id INTEGER PRIMARY KEY,
  imovel_id INTEGER NOT NULL REFERENCES imoveis(id),
  locatario_id INTEGER NOT NULL REFERENCES locatarios(id),
  corretor_id INTEGER REFERENCES corretores(id),
  data_inicio TEXT NOT NULL,              -- 'AAAA-MM-DD'
  data_fim_prevista TEXT NOT NULL,
  data_encerramento TEXT,                 -- NULL = ativo
  motivo_encerramento TEXT,
  dia_vencimento INTEGER NOT NULL CHECK (dia_vencimento BETWEEN 1 AND 31),
  multa_pct REAL NOT NULL DEFAULT 2,
  juros_mes_pct REAL NOT NULL DEFAULT 1,
  garantia_tipo TEXT NOT NULL DEFAULT 'nenhuma'
    CHECK (garantia_tipo IN ('caucao','fiador','seguro_fianca','nenhuma')),
  garantia_valor_centavos INTEGER,
  fiador TEXT,
  indice_reajuste TEXT,
  observacoes TEXT
);
-- Um imóvel só pode ter um contrato ativo (garantido pelo próprio banco).
CREATE UNIQUE INDEX IF NOT EXISTS um_contrato_ativo_por_imovel
  ON contratos(imovel_id) WHERE data_encerramento IS NULL;

CREATE TABLE IF NOT EXISTS valores_aluguel (
  id INTEGER PRIMARY KEY,
  contrato_id INTEGER NOT NULL REFERENCES contratos(id),
  valor_centavos INTEGER NOT NULL CHECK (valor_centavos > 0),
  vigente_desde TEXT NOT NULL,
  motivo TEXT,
  UNIQUE (contrato_id, vigente_desde)
);

CREATE TABLE IF NOT EXISTS cobrancas (
  id INTEGER PRIMARY KEY,
  contrato_id INTEGER NOT NULL REFERENCES contratos(id),
  competencia TEXT NOT NULL,              -- 'AAAA-MM'
  vencimento TEXT NOT NULL,               -- 'AAAA-MM-DD'
  valor_centavos INTEGER NOT NULL,
  situacao TEXT NOT NULL DEFAULT 'normal'
    CHECK (situacao IN ('normal','isenta','cancelada')),
  motivo_situacao TEXT,
  boleto_banco TEXT,
  boleto_identificador TEXT UNIQUE,
  boleto_linha_digitavel TEXT,
  boleto_link TEXT,
  boleto_emitido_em TEXT,
  boleto_enviado_em TEXT,
  UNIQUE (contrato_id, competencia)
);

CREATE TABLE IF NOT EXISTS pagamentos (
  id INTEGER PRIMARY KEY,
  cobranca_id INTEGER NOT NULL REFERENCES cobrancas(id),
  data_pagamento TEXT NOT NULL,
  valor_centavos INTEGER NOT NULL CHECK (valor_centavos > 0),
  forma TEXT NOT NULL
    CHECK (forma IN ('boleto','pix','transferencia','dinheiro','outro')),
  identificador_externo TEXT,
  comprovante_caminho TEXT,
  observacao TEXT,
  registrado_por TEXT NOT NULL,
  registrado_em TEXT NOT NULL,
  cancelado_em TEXT,
  motivo_cancelamento TEXT
);
-- O mesmo boleto/PIX não gera dois pagamentos válidos.
CREATE UNIQUE INDEX IF NOT EXISTS um_pagamento_por_identificador
  ON pagamentos(identificador_externo)
  WHERE identificador_externo IS NOT NULL AND cancelado_em IS NULL;

CREATE TABLE IF NOT EXISTS pendencias (
  id INTEGER PRIMARY KEY,
  tipo TEXT NOT NULL,
  descricao TEXT NOT NULL,
  entidade TEXT,
  entidade_id INTEGER,
  criada_em TEXT NOT NULL,
  criada_por TEXT NOT NULL,
  resolvida_em TEXT,
  resolvida_por TEXT,
  resolucao TEXT
);

CREATE TABLE IF NOT EXISTS auditoria (
  id INTEGER PRIMARY KEY,
  quando TEXT NOT NULL,
  quem TEXT NOT NULL,                     -- login do usuário ou 'hermes'
  acao TEXT NOT NULL,
  entidade TEXT,
  entidade_id INTEGER,
  detalhes TEXT                           -- JSON
);

