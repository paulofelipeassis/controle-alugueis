-- Módulo proporcional: guarda a decisão sobre o primeiro período de cada contrato (uma linha por contrato).
-- ON DELETE CASCADE: apagar o contrato apaga a decisão, sem o núcleo precisar saber deste módulo.
CREATE TABLE IF NOT EXISTS primeiro_periodo (
  contrato_id INTEGER PRIMARY KEY REFERENCES contratos(id) ON DELETE CASCADE,
  decisao TEXT NOT NULL CHECK (decisao IN ('proporcional', 'cheio')),
  decidido_por TEXT NOT NULL,
  decidido_em TEXT NOT NULL
);
