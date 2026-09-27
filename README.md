# Controle de Aluguéis

Aplicação em Streamlit para administrar os imóveis alugados, contratos de
locação e recebimentos. Não há banco de dados próprio: uma planilha do Google
Sheets chamada **"Controle de Aluguéis"** é a única fonte de dados, acessada
via `gspread` com uma conta de serviço do Google Cloud.

## Páginas

| Ordem | Página | Função |
|---|---|---|
| — | `app.py` | Login (`streamlit_authenticator`) |
| 1 | Visão Geral | Dashboard: ocupação, meta de recebimento, atrasos, vencimentos, reajustes |
| 2 | Lançar Pagamento | Registra um novo pagamento na aba `Lancamentos_Financeiros` |
| 3 | Imóveis | Consulta/filtra a aba `Imoveis` |
| 4 | Contratos | Consulta/filtra a aba `Contratos` |
| 5 | Histórico Financeiro | Lista e permite cancelar lançamentos |
| 6 | Cadastrar Imóvel | Cria um novo imóvel |
| 7 | Cadastrar Contrato | Cria um novo contrato (e marca o imóvel como "Alugado") |
| 8 | Editar Contrato | Edita um contrato existente |
| 9 | Editar Imóvel | Edita um imóvel existente |

## Rodando localmente

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py --server.enableCORS false --server.enableXsrfProtection false
```

A aplicação abre em `http://localhost:8501`.

## Configuração necessária (`.streamlit/secrets.toml`)

Esse arquivo **não é versionado** (veja `.gitignore`) e precisa ser criado
manualmente, seja em `.streamlit/secrets.toml` local ou nas configurações de
"Secrets" da plataforma de hospedagem. Estrutura mínima:

```toml
[credentials.usernames.fulano]
email = "fulano@example.com"
name = "Fulano da Silva"
password = "$2b$12$..."  # hash bcrypt — gere com scripts/generate_keys.py

[cookie]
name = "controle_alugueis_auth"
key = "uma-chave-secreta-qualquer"
expiry_days = 30

[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "..."
client_email = "..."
client_id = "..."
# demais campos do JSON de credenciais da conta de serviço do Google Cloud
```

A conta de serviço do Google precisa ter acesso de edição à planilha
"Controle de Aluguéis" (compartilhar a planilha com o e-mail
`client_email` da conta de serviço).

### Gerando hash de senha para um novo usuário

```bash
streamlit run scripts/generate_keys.py
```

Cole a(s) senha(s) em texto puro, copie o(s) hash(es) gerado(s) e cole em
`password` no `secrets.toml`. É uma ferramenta de uso pontual, não faz parte
do fluxo normal da aplicação.

## Planilha do Google Sheets

A planilha precisa conter as seguintes abas (nomes e cabeçalhos exatos):

- `Imoveis` — `ID_Imovel`, `Grupo`, `Unidade`, `Endereco_Completo`, `Status`,
  `Valor_IPTU_Anual`, `Num_Medidor_Saneago`, `Num_Medidor_Enel`
- `Contratos` — `ID_Contrato`, `ID_Imovel`, `Gestor_Responsavel`,
  `Nome_Locatario`, `CPF_Locatario`, `Telefone_Locatario`, `Email_Locatario`,
  `Data_Inicio`, `Data_Fim`, `Valor_Aluguel_Base`, `Dia_Vencimento`,
  `Tipo_Garantia`, `Valor_da_Garantia`, `Indice_Reajuste`, `Status_Contrato`,
  `Observacoes_do_Contrato`
- `Lancamentos_Financeiros` — 10 colunas na ordem em que
  `pages/2_Lançar_Pagamento.py` grava (`append_row`): `ID_Lancamento`,
  `ID_Contrato`, `Mes_Referencia`, `Data_Pagamento`, valor do aluguel pago,
  multa/juros, `Valor_Total_Pago`, forma de pagamento, status do pagamento,
  `Status_Lancamento`. Só os nomes em `código` são lidos de volta por nome
  em algum lugar do app — os demais (valor do aluguel, multa/juros, forma e
  status do pagamento) são escritos apenas por posição; confira os
  cabeçalhos reais da sua planilha antes de renomeá-los.
- `Gestores` — `Nome_Gestor`

## Desenvolvimento

Não há scripts de lint, teste ou build neste repositório. Detalhes de
arquitetura (padrão de acesso a dados, guarda de autenticação por página,
relacionamento entre as abas) estão em `CLAUDE.md`.
