# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Streamlit app for managing rental properties ("Controle de Aluguéis") for a small
family business (3-4 users, rarely simultaneous). There is no backend database: a
Google Sheet named **"Controle de Aluguéis"** is the sole data store, accessed via
`gspread` with a service account. All Portuguese identifiers (sheet names, column
names, UI text) are the domain language of this project — keep new code consistent
with it rather than translating to English.

## Rewrite in progress — read this first

The app is being rebuilt as a new system in `sistema/` (SQLite + FastAPI web pages + MCP
server for the Hermes Agent, Docker on a Hostinger VPS). Stages 1–5 of the plan are
implemented; stage 4's server install and stage 6 (switch-over) need Paulo on the server.
Before any work on the new system, read, in order:

1. `docs/regras-de-negocio.md` — agreed business rules (do not reopen decisions).
2. `docs/plano-de-implementacao.md` — step-by-step plan and its current status.
3. `docs/estrutura-de-pastas.md` — document folder convention; `docs/hermes.md` — guide for
   Hermes; `docs/instalacao-servidor.md` — server install.

New system commands (from the repo root):

```bash
pip install -r sistema/requirements.txt
python -m pytest sistema -q                    # all tests, core + modules (uses temp DBs)
uvicorn sistema.web:app --reload               # web pages on :8000
MCP_TOKEN=x python -m sistema.mcp_server       # MCP on :8001/mcp
python -m scripts.demo                         # prints a sample dashboard
python -m scripts.simular                      # 15 simulated months, 20 properties, checks every month
python -m scripts.criar_usuario                # creates a login
```

New system architecture: `servicos.py` is the **only** core writer (every write audited via
`servicos.auditar`, raises `ErroDeNegocio` with a Portuguese message); `consultas.py` has all
core reads/reports; `regras.py` holds pure date/money/status rules; `arquivos.py` owns the
shared documents folder and its path convention; `web.py` (+ helpers/templates in
`web_comum.py`) and `mcp_server.py` only translate parameters and call those.

Optional features live in `sistema/modulos/<nome>/` (today: `documentos`, `reajuste`, `backup`) and are
discovered automatically by `sistema/modulos/__init__.py`: optional `schema.sql`, `web.py`
(`router`), `mcp.py` (`registrar(mcp)`), `templates/<nome>/`, and their own `test_*.py`.
Deleting a module folder removes the feature and the rest keeps working (verified by running
the suite with each module deleted). Core code never imports a module by name; core templates
use `{% if modulo_ativo("nome") %}`; module tables use `ON DELETE CASCADE` so core deletes
don't need to know about them. Money is integer centavos, dates ISO text, statuses are
computed, never stored. `config.py` values are read as `config.X` at call time so tests can
monkeypatch them.

Keep the core small and optional features removable (Paulo's rule: "modularize sempre que
possível", "não criar um Frankenstein"). The core is cadastros → contratos → cobranças
(with boletos) → pagamentos (+ pendências, auditoria, usuários). Any new feature that the
core doesn't strictly need goes in a new `sistema/modulos/<nome>/` folder.
Schema changes once real data exists go in `db.MIGRACOES` (numbered, applied once, DB copied first;
see the comment there) and also in `schema.sql`. A due date on a weekend/holiday is payable
without late fees until the next business day (`regras.vencimento_efetivo`): use it, never the raw
due date, whenever judging lateness or computing fees.
Don't add tables or scheduled jobs for things that can be computed on demand, and don't
build features "just in case" — the schema is what's hard to change once real data exists.

The Streamlit app described below stays in production, untouched, until stage 6.

## Running the app

```bash
pip install -r requirements.txt
streamlit run app.py
```

The Streamlit app has no lint, test, or build scripts (the new system in `sistema/` has pytest tests, see above).

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
