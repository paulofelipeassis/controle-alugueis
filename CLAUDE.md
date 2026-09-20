# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Streamlit app for managing rental properties ("Controle de Aluguéis"). There is no
backend database: a Google Sheet named **"Controle de Aluguéis"** is the sole data
store, accessed via `gspread` with a service account. All Portuguese identifiers
(sheet names, column names, UI text) are the domain language of this project — keep
new code consistent with it rather than translating to English.

## Running the app

```bash
pip install -r requirements.txt
streamlit run app.py --server.enableCORS false --server.enableXsrfProtection false
```

The devcontainer (`.devcontainer/devcontainer.json`) runs the same command on
attach and forwards port 8501. There are no lint, test, or build scripts in this
repo — nothing to run beyond starting the app.

### Required secrets

The app reads everything from `st.secrets` (Streamlit secrets.toml, not committed).
It will fail at startup without:

- `st.secrets["credentials"]["usernames"][<user>]` — `email`, `name`, `password`
  (bcrypt hash) per login user, and `st.secrets["cookie"]` — `name`, `key`,
  `expiry_days`, consumed by `streamlit_authenticator`.
- `st.secrets["gcp_service_account"]` — full service-account credentials dict for
  `gspread.service_account_from_dict`, used to open the "Controle de Aluguéis"
  Google Sheet.

`generate_keys.py` is a one-off standalone utility (not part of the app flow) for
bcrypt-hashing passwords to paste into the credentials secrets.

## Architecture

**Entry point / auth**: `app.py` is the login page. On successful auth it
redirects (`st.switch_page`) into `pages/1_Visão_Geral.py`. Every other page in
`pages/` is a Streamlit multipage-app page, numbered to control sidebar order.

**Page guard pattern**: every page under `pages/` calls `auth_utils.page_guard()`
as its first real statement. This is the *only* access control mechanism — it
checks `st.session_state["authentication_status"]`, stops the page if not
authenticated, and renders the sidebar logout button. New pages must call it
before rendering any content.

**Data access pattern**: there is no shared data layer/module — each page
independently:
1. Opens the sheet via `gspread.service_account_from_dict(st.secrets["gcp_service_account"]).open("Controle de Aluguéis")`,
   usually memoized with `@st.cache_resource` as `get_connection()`.
2. Loads a worksheet with `worksheet.get_all_values()` into a pandas DataFrame
   (first row = headers), memoized with `@st.cache_data(ttl=...)` — TTLs vary
   per page (600s for read-heavy dashboards, 30s on edit pages that need fresher
   data after a save).
3. Writes go directly to the worksheet (`append_row`, `update_cell`, `update`
   with an `A1:P1`-style range) followed by `st.cache_data.clear()` and
   `st.rerun()`/`st.success()` to reflect the change.

Because each page re-implements this loading logic (slightly differently —
some coerce numeric/date columns, some wrap in try/except), when fixing a bug
in one page's `load_data`, check whether the same bug exists in the other
pages' copies.

**Worksheets (tabs) in the Google Sheet** and their consumers:
- `Imoveis` — properties. Key columns: `ID_Imovel`, `Grupo`, `Unidade`, `Status`
  (`Alugado`/`Vago`/…), `Endereco_Completo`, `Valor_IPTU_Anual`,
  `Num_Medidor_Saneago`, `Num_Medidor_Enel`. `ID_Imovel` is derived as
  `{GRUPO_PREFIXO}-{UNIDADE_LIMPA}` (see `gerar_id_imovel` in
  `pages/6_Cadastrar_Imóvel.py`).
- `Contratos` — lease contracts. Key columns: `ID_Contrato` (derived as
  `{ID_Imovel}-{YYYYMMDD do início}`), `ID_Imovel`, `Gestor_Responsavel`,
  `Nome_Locatario`, `Data_Inicio`, `Data_Fim`, `Valor_Aluguel_Base`,
  `Dia_Vencimento`, `Status_Contrato` (`Ativo`/`Encerrado`/`Renovado`).
  Creating a contract also flips the linked property's `Status` to `Alugado`
  (`pages/7_Cadastrar_Contrato.py`).
- `Lancamentos_Financeiros` — payment ledger. Key columns: `ID_Lancamento`,
  `ID_Contrato`, `Mes_Referencia` (`MM/AAAA` string, not a date), `Data_Pagamento`,
  `Valor_Total_Pago`, `Status_Lancamento` (`Válido`/`Cancelado`). Entries are
  never deleted — cancelling (`5_Histórico_Financeiro.py`) sets
  `Status_Lancamento` to `Cancelado` in place, so financial totals must always
  filter on `Status_Lancamento == 'Válido'`.
- `Gestores` — list of property managers (`Nome_Gestor`), used to populate the
  manager dropdown in `7_Cadastrar_Contrato.py`.

Since sheet rows are matched by value (`worksheet.find(...)`) rather than a
stable row index, edits assume `ID_Imovel`/`ID_Contrato` values are unique and
present in column A.

**Cross-sheet consistency**: property `Status` and contract `Status_Contrato`
are two independent fields that must be kept in sync manually by page logic
(e.g. `1_Visão_Geral.py` explicitly warns when their counts diverge). When
touching contract or property status transitions, check both sheets are
updated together.
