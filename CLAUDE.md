# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Streamlit app for managing rental properties ("Controle de Aluguéis") for a small
family business (3-4 users, rarely simultaneous). There is no backend database: a
Google Sheet named **"Controle de Aluguéis"** is the sole data store, accessed via
`gspread` with a service account. All Portuguese identifiers (sheet names, column
names, UI text) are the domain language of this project — keep new code consistent
with it rather than translating to English.

## Running the app

```bash
pip install -r requirements.txt
streamlit run app.py
```

There are no lint, test, or build scripts in this repo.

### Required secrets (`.streamlit/secrets.toml`, never committed)

- `[credentials.usernames.<user>]` — `email`, `name`, `password` (bcrypt hash; generate
  with `streamlit run scripts/generate_keys.py`) and `[cookie]` — `name`, `key`,
  `expiry_days`, consumed by `streamlit_authenticator`.
- `[gcp_service_account]` — service-account credentials dict for
  `gspread.service_account_from_dict`. The spreadsheet must be shared with its
  `client_email`.

## Architecture

**Entry point / auth**: `app.py` is the login page; on success it `st.switch_page`s to
`pages/1_Visão_Geral.py`. Every page under `pages/` must call
`auth_utils.page_guard()` as its first statement — it is the only access control.

**Data access — `data_access.py` is the single point of contact with the sheet.**
Pages never import `gspread` directly. Use:
- Reads: `load_data(name)` (10-min cache), `load_data_fresh(name)` (30s, for edit
  pages about to overwrite a row), `load_data_uncached(name)` (for duplicate checks).
  All three coerce types: `ID_*` columns to `str`, known numeric columns to float,
  date columns to datetime. A sheet with only a header row returns a zero-row
  DataFrame that still has its columns.
- Writes: `append_row`, `update_row` (whole row, located by ID in column A),
  `update_cell`. Each clears `st.cache_data` and logs + re-raises on failure; pages wrap
  calls in `try/except` and show `st.error`.
- Domain operations that keep `Imoveis.Status` and `Contratos.Status_Contrato` in sync:
  `criar_contrato` (marks the property `Alugado`), `atualizar_contrato` (releases the
  property to `Vago` when the contract leaves `Ativo` and no other active contract
  points at it), `cancelar_lancamento`, `proximo_id_lancamento`.

Two Sheets-API gotchas already handled in `data_access.py` — don't undo them:
- `get_all_values()` returns *display* strings; on this pt-BR sheet decimals come back
  as `"1234,56"`. `_parse_locale_number` normalizes before `pd.to_numeric`, otherwise
  the value silently becomes 0.
- The real `gspread` JSON-serializes writes; numpy scalars (anything read back from a
  coerced DataFrame) fail with `int64 is not JSON serializable`. `_to_native` converts
  them in every write helper.

Logging goes through `data_access.logger` (stderr), also used by `app.py` and
`auth_utils.py`.

**Report logic lives inside the page scripts** (`1_Visão_Geral.py`: occupancy, monthly
target, overdue rents, contracts expiring in 60 days, readjustments due in 30 days;
`5_Histórico_Financeiro.py`: filtered totals). It is interleaved with `st.*` calls, so
it can't be reused outside Streamlit without extracting it first.

## Google Sheet schema

- `Imoveis` (8 cols, A–H): `ID_Imovel` (= `{first 4 letters of Grupo}-{Unidade without
  spaces}`, e.g. `PRDI-APTO101`), `Grupo`, `Unidade`, `Endereco_Completo`, `Status`
  (`Alugado`/`Vago`/`Em Manutenção`/…, column E), `Valor_IPTU_Anual`,
  `Num_Medidor_Saneago`, `Num_Medidor_Enel`.
- `Contratos` (16 cols, A–P): `ID_Contrato` (= `{ID_Imovel}-{YYYYMMDD start}`),
  `ID_Imovel`, `Gestor_Responsavel`, `Nome_Locatario`, `CPF_Locatario`,
  `Telefone_Locatario`, `Email_Locatario`, `Data_Inicio`, `Data_Fim`,
  `Valor_Aluguel_Base`, `Dia_Vencimento`, `Tipo_Garantia`, `Valor_da_Garantia`,
  `Indice_Reajuste`, `Status_Contrato` (`Ativo`/`Encerrado`/`Renovado`),
  `Observacoes_do_Contrato`.
- `Lancamentos_Financeiros` (10 cols): `ID_Lancamento`, `ID_Contrato`,
  `Mes_Referencia` (`MM/AAAA` string), `Data_Pagamento`, `Valor_Aluguel_Pago`,
  `Multa_Juros_por_Atraso`, `Valor_Total_Pago`, `Forma_Pagamento`, `Status_Pagamento`,
  `Status_Lancamento` (`Válido`/`Cancelado`, column J). Rows are never deleted —
  cancelling flips `Status_Lancamento`, so totals must filter on `Válido`.
- `Gestores`: `Nome_Gestor`, `Email_Gestor`, `Telefone_Gestor` (only `Nome_Gestor` is read).

Writes locate rows with `worksheet.find()` by value, so IDs must be unique and live in
column A. Nothing prevents two payments for the same contract and month.
