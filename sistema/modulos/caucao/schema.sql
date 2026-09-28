-- Módulo caução: registro da devolução da caução (garantia em dinheiro) quando o contrato acaba.
-- ON DELETE CASCADE: apagar o contrato apaga o registro, sem o núcleo precisar saber deste módulo.
CREATE TABLE IF NOT EXISTS caucoes (
  contrato_id INTEGER PRIMARY KEY REFERENCES contratos(id) ON DELETE CASCADE,
  devolvida_em TEXT NOT NULL,
  valor_devolvido_centavos INTEGER NOT NULL CHECK (valor_devolvido_centavos >= 0),
  descontos_centavos INTEGER NOT NULL DEFAULT 0 CHECK (descontos_centavos >= 0),
  motivo_descontos TEXT,
  observacao TEXT,
  registrado_por TEXT NOT NULL,
  registrado_em TEXT NOT NULL
);
