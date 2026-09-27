-- Módulo documentos: cada arquivo da pasta de documentos ligado a UM imóvel, locatário ou
-- contrato. ON DELETE CASCADE: apagar o cadastro apaga a ligação (o arquivo fica na pasta),
-- sem o núcleo precisar saber que este módulo existe.
CREATE TABLE IF NOT EXISTS documentos (
  id INTEGER PRIMARY KEY,
  imovel_id INTEGER REFERENCES imoveis(id) ON DELETE CASCADE,
  locatario_id INTEGER REFERENCES locatarios(id) ON DELETE CASCADE,
  contrato_id INTEGER REFERENCES contratos(id) ON DELETE CASCADE,
  tipo TEXT NOT NULL,
  caminho TEXT NOT NULL UNIQUE,           -- relativo à pasta de documentos
  descricao TEXT,
  registrado_por TEXT NOT NULL,
  registrado_em TEXT NOT NULL,
  CHECK ((imovel_id IS NOT NULL) + (locatario_id IS NOT NULL) + (contrato_id IS NOT NULL) = 1)
);
