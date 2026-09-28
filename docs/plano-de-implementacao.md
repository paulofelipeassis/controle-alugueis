# Plano de implementação — sistema novo

Passo a passo para construir o sistema descrito em
[`regras-de-negocio.md`](regras-de-negocio.md). **Leia as regras de negócio inteiras antes de
começar qualquer etapa.**

## Situação atual (27/09/2026)

| Etapa | Situação |
|---|---|
| 1 e 2 — banco, regras, cobranças, relatórios | ✅ Feita, com testes |
| 3 — MCP do Hermes | ✅ Feita, com testes (inclusive de rede) e `docs/hermes.md` |
| 4 — Docker e backup | ✅ Arquivos prontos e testados num Docker local. **Falta instalar no servidor com o Paulo:** [`instalacao-servidor.md`](instalacao-servidor.md) |
| 5 — Páginas web | ✅ Feita, com testes e verificação visual em tela de celular |
| 6 — Virada | ⏳ Depende do Paulo (domínio, uso em paralelo, desligar o Streamlit) |
| Extra — reajuste | ✅ Sugestão de reajuste por IPCA/IGP-M calculada na hora (módulo `sistema/reajuste.py`), cobrança marcada até o reajuste ser registrado, e data do valor atual no cadastro de contratos antigos (regras §4) |

Estrutura modular (pedido do Paulo, 27/09/2026): o núcleo fica em `sistema/*.py`, e as funções
opcionais ficam em `sistema/modulos/<nome>/`: hoje `documentos` e `reajuste`. Apagar a pasta de
um módulo remove a função sem quebrar o resto (testado). Os caminhos de arquivo citados nas
etapas abaixo são do plano original; o `CLAUDE.md` descreve a estrutura atual.

Diferenças em relação ao plano abaixo, e por quê:
- Tudo foi feito numa branch só, e não uma por etapa, porque o Paulo pediu para seguir até o
  fim sem parar entre as etapas.
- Biblioteca `mcp` **1.x** (`FastMCP`), não a 2.x: a 1.x é a mais usada pelos clientes MCP
  atuais, e isso reduz o risco de incompatibilidade com o Hermes.
- MCP sem estado (`stateless_http`) e `host="0.0.0.0"`: a proteção automática da biblioteca
  só aceita conexões locais e bloquearia o Hermes dentro do Docker. A proteção é o token.
- O container roda como root, porque a pasta de documentos é compartilhada com o Hermes e o
  File Browser, e assim não há problema de permissão de arquivo.
- As cobranças não precisam de agendamento: são geradas (de forma idempotente) sempre que
  uma consulta depende delas.

Revisão antes de ir para o servidor (28/09/2026): dia útil no vencimento, pendências de boleto
(cobrança cancelada, segunda via, reajuste depois do boleto), reabrir contrato, migrações do banco,
aviso de backup no painel, bloqueio de tentativas de login, cookie seguro e arquivos enviados só
abrem no navegador se forem PDF, imagem ou texto. Detalhes nas regras de negócio.

## 0. Como trabalhar (leia antes de tudo)

### Sobre o Paulo
- Não é programador. Usa quase sempre o **celular**. Fale em **português**, simples, direto,
  sem jargão. Quando precisar de uma decisão dele, dê as opções e **recomende uma**.
- Ele gosta de respostas baseadas em evidência: quando afirmar algo técnico ou legal, diga de
  onde vem.
- Ele **não quer exagero** ("preciosismo"). Faça o que a etapa pede, nada além.
- **Nunca** peça para ele colar senha, chave ou arquivo de credenciais na conversa. Se for
  preciso configurar um segredo, explique onde ele mesmo deve colocar (painel da Hostinger,
  arquivo no servidor).

### Regras de trabalho
1. **Uma etapa por vez, na ordem.** Cada etapa é uma branch. Só comece a próxima depois que
   o Paulo testar e a anterior for mesclada no `main`.
2. Nome da branch: `etapa-N-nome` (ex.: `etapa-1-banco`). Se a sessão já definir um nome de
   branch obrigatório, use o da sessão.
3. **Não reabra decisões** das regras de negócio. Se algo não estiver coberto ou parecer
   errado, **pare e pergunte ao Paulo**.
4. **Não mexa no sistema antigo** (`app.py`, `auth_utils.py`, `data_access.py`, `pages/`,
   `requirements.txt` da raiz) até a Etapa 6. Ele continua em produção no Streamlit Cloud,
   que lê o `requirements.txt` da raiz.
5. Todo código novo fica na pasta **`sistema/`** (pacote Python). Não use `app/` como nome:
   conflita com o `app.py` do sistema antigo.
6. Nomes do domínio em **português** (tabelas, colunas, funções, telas), sem acento em
   identificadores de código (`locatario`, `cobranca`, `competencia`).
7. Antes de cada commit: `python -m pytest sistema/tests -q` tem que passar.
8. Commit com mensagem clara em português. Nunca commitar `.env`, banco de dados (`*.db`),
   arquivos de credenciais ou a pasta de documentos.
9. Ao terminar a etapa: push da branch e mande ao Paulo um resumo curto: o que foi feito,
   como ele testa, e o que fica para a próxima etapa. Abra PR só se ele pedir.

### Estrutura final de pastas do código

```
sistema/
  __init__.py
  config.py          # lê variáveis de ambiente
  db.py              # conexão SQLite, criação do schema, transação
  schema.sql         # todas as tabelas
  regras.py          # funções puras (datas, dinheiro, situação): sem banco
  servicos.py        # TODAS as operações que gravam no banco
  consultas.py       # TODAS as leituras/relatórios
  mcp_server.py      # ferramentas do Hermes (Etapa 3)
  web.py             # páginas web (Etapa 5)
  templates/         # HTML (Etapa 5)
  static/            # CSS (Etapa 5)
  requirements.txt
  tests/
scripts/             # já existe; scripts novos entram aqui
deploy/              # Dockerfile, docker-compose.yml, backup (Etapa 4)
```

Regra de ouro: **só `servicos.py` grava no banco.** `web.py` e `mcp_server.py` só chamam
`servicos` e `consultas`. Nenhuma regra de negócio dentro deles.

### Ordem das etapas

| Etapa | Branch | Resultado |
|---|---|---|
| 1 | `etapa-1-banco` | Banco SQLite, cadastros e contratos (com testes) |
| 2 | `etapa-2-cobrancas` | Cobranças, pagamentos, pendências, relatórios (com testes) |
| 3 | `etapa-3-mcp` | Servidor MCP com as ferramentas do Hermes |
| 4 | `etapa-4-docker` | Sistema rodando no servidor, Hermes conectado, backup diário |
| 5 | `etapa-5-web` | Páginas web com tudo que dá para fazer à mão |
| 6 | `etapa-6-virada` | Domínio, desligar Streamlit, remover código antigo |

Essa ordem foi escolhida pelo Paulo (banco → funções → MCP → Docker) e as páginas web vêm
depois porque o Hermes é a interface principal.

---

## Etapa 1 — Banco SQLite e cadastros

### 1.1 Dependências
Criar `sistema/requirements.txt` só com o necessário. Nesta etapa: `pytest`. As outras
entram nas etapas seguintes. Use versões fixas (`pacote==x.y.z`) com a versão que você
instalou.

Use **`sqlite3` da biblioteca padrão**, sem ORM. É suficiente para 20 imóveis e mais fácil
de ler.

### 1.2 `sistema/config.py`
Lê variáveis de ambiente com valores padrão para desenvolvimento:

| Variável | Padrão | Uso |
|---|---|---|
| `DB_PATH` | `dados/alugueis.db` | arquivo do banco |
| `DOCS_DIR` | `dados/documentos` | pasta de documentos |
| `INICIO_COBRANCAS` | `2026-10` | primeira competência gerada |
| `SESSION_SECRET` | (obrigatória na Etapa 5) | cookie de login |
| `MCP_TOKEN` | (obrigatória na Etapa 3) | senha do Hermes no MCP |
| `TZ` | `America/Sao_Paulo` | fuso |

Adicionar `dados/` e `*.db` ao `.gitignore`.

### 1.3 `sistema/schema.sql`
Use exatamente este schema (ajustes só se um teste mostrar necessidade real):

```sql
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

CREATE TABLE IF NOT EXISTS documentos (
  id INTEGER PRIMARY KEY,
  entidade TEXT NOT NULL CHECK (entidade IN ('imovel','locatario','contrato')),
  entidade_id INTEGER NOT NULL,
  tipo TEXT NOT NULL,
  caminho TEXT NOT NULL UNIQUE,           -- relativo a DOCS_DIR
  descricao TEXT,
  registrado_por TEXT NOT NULL,
  registrado_em TEXT NOT NULL
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
```

Convenções:
- **Dinheiro sempre em centavos (inteiro).** Nunca `float` para dinheiro (evita erro de
  arredondamento: `0.1 + 0.2 != 0.3` em ponto flutuante).
- **Datas como texto ISO** (`AAAA-MM-DD`), data e hora como `AAAA-MM-DD HH:MM:SS` no fuso
  de São Paulo. Texto ISO ordena e compara certo no SQLite.

### 1.4 `sistema/db.py`
- `conectar()` → abre `DB_PATH` (cria a pasta se preciso), `row_factory = sqlite3.Row`, e
  executa em toda conexão: `PRAGMA foreign_keys = ON`, `PRAGMA journal_mode = WAL`,
  `PRAGMA busy_timeout = 5000`. WAL permite a web e o MCP (dois processos) usarem o mesmo
  arquivo ao mesmo tempo.
- `inicializar()` → executa `schema.sql` (é idempotente por causa do `IF NOT EXISTS`).
- `transacao()` → context manager: `BEGIN IMMEDIATE`, commit no sucesso, rollback em erro.
- Tudo aceita um caminho de banco opcional para os testes usarem um arquivo temporário.

### 1.5 `sistema/regras.py` (funções puras, sem banco)
- `agora()`, `hoje()` no fuso de São Paulo.
- `reais_para_centavos(texto)`: aceita `"1.234,56"`, `"1234,56"`, `"1234.56"`, `"1234"`.
  (A versão antiga perdia valores com vírgula; teste esses quatro formatos.)
- `formatar_reais(centavos)` → `"R$ 1.234,56"`.
- `so_digitos(texto)`; `validar_cpf_cnpj(texto)` → dígitos, erro se não tiver 11 ou 14.
- `vencimento(competencia, dia)` → data; dia maior que o mês → último dia do mês.
- `proxima_competencia(competencia)`, `competencia_de(data)`.
- `primeira_competencia(data_inicio, dia_vencimento, inicio_cobrancas)` → competência do
  primeiro vencimento ≥ data de início, nunca antes de `inicio_cobrancas`.
- `encargos(valor, multa_pct, juros_mes_pct, vencimento, data)` → `(multa, juros)` em
  centavos; zero se `data <= vencimento`. Juros = valor × juros% × dias ÷ 30.
- `situacao_cobranca(situacao, valor, pago, vencimento, hoje)` → `'cancelada'`,
  `'isenta'`, `'paga'`, `'parcial'`, `'atrasada'` ou `'em_aberto'` (ver regras §5;
  `parcial` com vencimento passado é `atrasada`).
- `situacao_imovel(tem_contrato_ativo, em_manutencao)`.
- `nome_pasta(texto)` → remove acentos e caracteres inválidos em nome de pasta.
- `class ErroDeNegocio(Exception)`: erro com mensagem em português para mostrar ao usuário
  ou ao Hermes.

### 1.6 `sistema/servicos.py` (parte 1: cadastros e contratos)
Toda função:
- recebe `quem` (login ou `'hermes'`) como primeiro argumento;
- valida e levanta `ErroDeNegocio` com mensagem clara ("Já existe um locatário com o CPF
  123…");
- grava dentro de `transacao()` e chama `_auditar(con, quem, acao, entidade, id, detalhes)`
  **na mesma transação**;
- devolve o `id` criado ou um `dict` simples.

Funções:
- `cadastrar_imovel`, `atualizar_imovel`, `apagar_imovel` (só sem contratos).
- `cadastrar_locatario`, `atualizar_locatario`, `apagar_locatario` (só sem contratos).
  CPF/CNPJ normalizado para dígitos; e-mail obrigatório.
- `cadastrar_corretor`, `atualizar_corretor`, `apagar_corretor` (só sem contratos).
- `criar_contrato(quem, imovel_id, locatario_id, corretor_id, data_inicio,
  data_fim_prevista, dia_vencimento, valor_centavos, ...)` → cria o contrato **e** o primeiro
  registro em `valores_aluguel` (`vigente_desde = data_inicio`, motivo `'inicial'`). Erro
  claro se o imóvel já tem contrato ativo (a violação do índice único vira `ErroDeNegocio`).
  Erro se `data_fim_prevista <= data_inicio`.
- `atualizar_contrato(...)` → só campos que não mexem em dinheiro nem datas de cobrança
  (corretor, garantia, fiador, índice, observações, multa/juros).
- `registrar_reajuste(quem, contrato_id, novo_valor_centavos, vigente_desde, motivo)`.
  (Na Etapa 2 ela passa também a atualizar as cobranças futuras.)
- `renovar_contrato(quem, contrato_id, nova_data_fim, novo_valor_centavos=None,
  vigente_desde=None)` → nova data de fim > atual; se vier valor, chama o reajuste.
- `encerrar_contrato(quem, contrato_id, data_encerramento, motivo)`. (Na Etapa 2 passa a
  cancelar as cobranças futuras.)
- `apagar_contrato(quem, contrato_id)` → só se não tiver pagamento nem boleto; apaga as
  cobranças e valores dele.
- `criar_usuario(login, nome, senha)` com `bcrypt` (adicionar ao requirements).

### 1.7 `scripts/criar_usuario.py`
Pergunta login, nome e senha no terminal (`getpass`) e chama `servicos.criar_usuario`.

### 1.8 Testes (`sistema/tests/`)
- `conftest.py`: fixture que cria um banco novo em `tmp_path` para cada teste.
- `test_regras.py`: `reais_para_centavos` (4 formatos), `vencimento` (dia 31 em fevereiro,
  em abril; dia 29 em ano bissexto e não bissexto), `primeira_competencia` (início antes e
  depois do dia de vencimento; início antes de `INICIO_COBRANCAS`), `encargos` (em dia,
  10 dias de atraso), `situacao_cobranca` (todas as saídas), `validar_cpf_cnpj`.
- `test_cadastros.py`: CPF duplicado dá erro; grupo+unidade duplicado dá erro; segundo
  contrato ativo no mesmo imóvel dá erro; depois de encerrar, pode criar outro; apagar
  imóvel com contrato dá erro; reajuste mantém o valor antigo; renovação com data menor dá
  erro; toda operação gera linha na auditoria.

### Pronto quando
Testes passando, push feito, e o Paulo recebeu: "Etapa 1 pronta: banco e cadastros. Ainda
não tem tela; o teste foi automático. Próximo: cobranças." Não há o que ele testar à mão
nesta etapa; mescle quando ele aprovar.

---

## Etapa 2 — Cobranças, pagamentos, pendências e relatórios

### 2.1 `servicos.py` (parte 2)
- `gerar_cobrancas(quem, hoje=None)`: para **todo** contrato, da primeira competência
  (`regras.primeira_competencia`) em diante, cria as cobranças que faltam enquanto
  `vencimento <= hoje + 30 dias` e `vencimento <= data_encerramento` (se houver). Valor =
  valor vigente na data do vencimento (último `valores_aluguel` com `vigente_desde <=
  vencimento`). Usa `INSERT OR IGNORE` apoiado no `UNIQUE (contrato_id, competencia)`, então
  rodar duas vezes não duplica. Devolve quantas criou. Audita só se criou alguma.
- **Quando gerar:** não precisa de agendamento. Chame `gerar_cobrancas('sistema')` no
  começo de cada consulta que depende de cobranças (painel, alertas, cobranças sem boleto,
  inadimplentes, extrato) e depois de `criar_contrato`, `registrar_reajuste` e
  `renovar_contrato`. É barato com 20 imóveis e evita um "cron" a mais para configurar.
- `editar_valor_cobranca(quem, cobranca_id, valor_centavos, motivo)`: só sem boleto e sem
  pagamento válido.
- `isentar_cobranca` / `cancelar_cobranca(quem, cobranca_id, motivo)`: motivo obrigatório,
  só sem pagamento válido; se tinha boleto, cria pendência `cancelar_boleto`.
- `registrar_boleto(quem, cobranca_id, banco, identificador, linha_digitavel, link,
  substituir=False)`: cobrança tem que estar `normal` e com saldo. Se já tem boleto e
  `substituir` é falso → erro "Essa cobrança já tem boleto (…). Use substituir se for
  segunda via." Se é o mesmo identificador já registrado → devolve sem erro (idempotente).
  Na substituição, o identificador antigo vai para a auditoria.
- `marcar_boleto_enviado(quem, cobranca_id)`.
- `registrar_pagamento(quem, cobranca_id, data_pagamento, valor_centavos, forma,
  identificador_externo=None, comprovante_caminho=None, observacao=None)`:
  1. Se `identificador_externo` já existe num pagamento válido → devolve esse pagamento
     (`{"id": ..., "ja_existia": True}`), sem erro e sem duplicar.
  2. Cobrança cancelada/isenta → erro.
  3. Grava o pagamento.
  4. Cria pendência (mas mantém o pagamento) quando: valor difere do esperado em mais de
     R$ 1,00 (`pagamento_divergente`); cobrança já estava paga (`possivel_duplicidade`);
     contrato encerrado (`contrato_encerrado`). Esperado = saldo + encargos se pago depois
     do vencimento; senão, o saldo.
- `registrar_pagamento_boleto(quem, identificador, data_pagamento, valor_centavos,
  comprovante_caminho=None)`: acha a cobrança pelo `boleto_identificador`. Não achou →
  cria pendência `boleto_desconhecido` e devolve `{"registrado": False, "pendencia_id": …}`.
  Achou → `registrar_pagamento(..., forma='boleto', identificador_externo=identificador)`.
- `cancelar_pagamento(quem, pagamento_id, motivo)`: motivo obrigatório.
- `criar_pendencia(quem, tipo, descricao, entidade=None, entidade_id=None)` e
  `resolver_pendencia(quem, pendencia_id, resolucao)`.
- Completar da Etapa 1:
  - `registrar_reajuste` → atualiza o valor das cobranças `normal` sem boleto e sem pagamento
    com `vencimento >= vigente_desde`.
  - `encerrar_contrato` → cancela (motivo "contrato encerrado") as cobranças com
    `vencimento > data_encerramento` sem pagamento válido; para cada uma que tinha boleto,
    cria pendência `cancelar_boleto`.

### 2.2 Documentos (em `servicos.py`)
- `pasta_documento(entidade, entidade_id)` → caminho relativo seguindo
  [`estrutura-de-pastas.md`](estrutura-de-pastas.md):
  - imóvel: `imoveis/<Grupo - Unidade>/imovel/`
  - locatário: `locatarios/<cpf_cnpj> - <Nome>/`
  - contrato: `imoveis/<Grupo - Unidade>/contratos/<AAAA-MM do início> - <Nome do locatário>/`
  - sempre passando por `regras.nome_pasta` (sem acento).
- `registrar_documento(quem, entidade, entidade_id, tipo, caminho, descricao=None)`: o
  arquivo tem que existir dentro de `DOCS_DIR` (recusar caminho com `..` ou absoluto fora
  dela).
- `salvar_documento(quem, entidade, entidade_id, tipo, nome_arquivo, conteudo_bytes)`: usado
  pela web. Salva em `pasta_documento(...)`; nomes fixos para os tipos conhecidos
  (`contrato-assinado.pdf`, `vistoria-entrada.pdf`, `vistoria-saida.pdf`); se o arquivo já
  existir, acrescenta `-2`, `-3`…; depois chama `registrar_documento`.

### 2.3 `sistema/consultas.py`
Cada função devolve `dict`/`list` de `dict` com valores já prontos para mostrar (inclua os
centavos **e** o texto formatado `"R$ …"`), porque a web e o Hermes usam a mesma saída.

- `listar_imoveis(situacao=None)` com situação calculada e locatário atual.
- `ficha_imovel(imovel_id)`: dados, situação, contrato atual, histórico de contratos,
  documentos.
- `buscar_locatarios(texto)`: por parte do nome ou do CPF/CNPJ.
- `ficha_locatario(locatario_id)`: dados, contratos (todos), total em aberto, documentos.
- `listar_contratos(ativos=True)`.
- `extrato_contrato(contrato_id)`: dados do contrato, valor atual, histórico de valores e,
  para cada cobrança: competência, vencimento, valor, pago, saldo, situação, valor
  atualizado se atrasada, boleto, pagamentos (incluindo os cancelados, marcados).
- `listar_cobrancas(competencia=None, situacao=None, contrato_id=None)`.
- `cobrancas_sem_boleto(dias=10)`: situação `normal`, com saldo, sem boleto,
  `vencimento <= hoje + dias`. Inclui nome, e-mail e CPF/CNPJ do locatário, valor, vencimento,
  multa% e juros% (tudo que o Hermes precisa para emitir o boleto).
- `boletos_em_aberto()`: com boleto e saldo > 0.
- `inadimplentes(hoje=None)`: cobranças atrasadas de **qualquer** competência, agrupadas por
  contrato, com total do saldo e total atualizado.
- `resumo_do_mes(competencia=None)`: devido, recebido, falta receber.
- `painel(hoje=None)`: contagem de imóveis por situação e ocupação; `resumo_do_mes`;
  `inadimplentes`; `alertas`; número de pendências abertas.
- `alertas(hoje=None)`: os cinco tipos das regras §10.
- `listar_pendencias(abertas=True)`.
- `historico_pagamentos(data_de, data_ate, grupo=None, imovel_id=None, locatario_id=None)`:
  pagamentos válidos e total.
- `auditoria(entidade=None, entidade_id=None, limite=100)`.

### 2.4 Testes
Cenários obrigatórios (`test_cobrancas.py`, `test_pagamentos.py`, `test_consultas.py`):
- Contrato de 05/10/2026 com vencimento dia 10 → primeira cobrança 2026-10, vence 10/10.
- Vencimento dia 31 → cobrança de novembro vence 30/11.
- `gerar_cobrancas` duas vezes → mesma quantidade.
- Contrato começando antes de `INICIO_COBRANCAS` → nada antes de 2026-10.
- Reajuste atualiza só cobranças futuras sem boleto/pagamento.
- Encerramento cancela as futuras; a que tinha boleto gera pendência; saldo antigo continua
  em `inadimplentes`.
- Pagamento parcial → `parcial`; completando → `paga`; saldo não vai para o mês seguinte.
- Pagamento em atraso sem encargos → paga + pendência `pagamento_divergente`.
- `registrar_pagamento_boleto` duas vezes com o mesmo identificador → um pagamento só.
- Boleto desconhecido → pendência, nenhum pagamento.
- Cancelar pagamento → cobrança volta a ter saldo.
- Atraso de um mês antigo aparece em `inadimplentes` (erro da versão antiga: só olhava o mês
  atual).
- Mesmo locatário com dois contratos: pagamento cai na cobrança certa (erro da versão
  antiga).
- `pasta_documento` gera os caminhos do exemplo de `estrutura-de-pastas.md`; caminho com
  `..` é recusado.

### Pronto quando
Testes passando. Rode um script de demonstração (pode ficar em `scripts/demo.py`) que cria 3
imóveis, 2 locatários e 2 contratos, gera cobranças, registra um pagamento e imprime o
painel. Mande a saída para o Paulo conferir se as regras batem com o que ele espera.

---

## Etapa 3 — Servidor MCP (ferramentas do Hermes)

### 3.1 Base
- Biblioteca oficial `mcp` (Python SDK), usando `FastMCP`. Adicione ao requirements.
- `sistema/mcp_server.py` é um **processo separado** da web (mais simples que montar os dois
  no mesmo app). Os dois usam o mesmo arquivo SQLite (WAL, Etapa 1).
- Transporte **HTTP "streamable"**, porta `8001`, caminho `/mcp`. Rodar com
  `python -m sistema.mcp_server`.
- **Senha:** toda requisição precisa do cabeçalho `Authorization: Bearer <MCP_TOKEN>`.
  Implemente com um middleware simples em volta do app ASGI do FastMCP. Sem OAuth.
- Confira na documentação da versão instalada do `mcp` o nome exato do método que gera o app
  HTTP (ex.: `streamable_http_app()`); a API muda entre versões.
- Toda ferramenta chama `servicos`/`consultas` com `quem='hermes'`. Nenhuma regra aqui.
- `ErroDeNegocio` vira erro da ferramenta com a mesma mensagem.
- Cada ferramenta tem **docstring em português** explicando quando usar, parâmetros com
  formato (`AAAA-MM-DD`, valores em reais como texto `"1234,56"`) e o que devolve. O Hermes
  decide qual ferramenta usar lendo isso: capriche.
- Valores de entrada em reais → converter com `regras.reais_para_centavos`.

### 3.2 Ferramentas (exatamente estas)

Consulta:

| Ferramenta | Chama |
|---|---|
| `painel` | `consultas.painel` |
| `alertas` | `consultas.alertas` |
| `listar_imoveis(situacao?)` | `consultas.listar_imoveis` |
| `ficha_imovel(imovel_id)` | `consultas.ficha_imovel` |
| `buscar_locatarios(texto)` | `consultas.buscar_locatarios` |
| `ficha_locatario(locatario_id)` | `consultas.ficha_locatario` |
| `listar_contratos(ativos?)` | `consultas.listar_contratos` |
| `extrato_contrato(contrato_id)` | `consultas.extrato_contrato` |
| `listar_cobrancas(competencia?, situacao?)` | `consultas.listar_cobrancas` |
| `cobrancas_sem_boleto(dias?)` | `consultas.cobrancas_sem_boleto` |
| `boletos_em_aberto` | `consultas.boletos_em_aberto` |
| `inadimplentes` | `consultas.inadimplentes` |
| `resumo_do_mes(competencia?)` | `consultas.resumo_do_mes` |
| `historico_pagamentos(data_de, data_ate, ...)` | `consultas.historico_pagamentos` |
| `listar_pendencias` | `consultas.listar_pendencias` |
| `pasta_documento(entidade, entidade_id)` | `servicos.pasta_documento` |

Gravação:

| Ferramenta | Chama |
|---|---|
| `cadastrar_imovel` | `servicos.cadastrar_imovel` |
| `cadastrar_locatario` | `servicos.cadastrar_locatario` |
| `atualizar_contato_locatario(locatario_id, telefone?, email?)` | `servicos.atualizar_locatario` (só esses campos) |
| `cadastrar_corretor` | `servicos.cadastrar_corretor` |
| `criar_contrato` | `servicos.criar_contrato` |
| `registrar_reajuste` | `servicos.registrar_reajuste` |
| `renovar_contrato` | `servicos.renovar_contrato` |
| `encerrar_contrato` | `servicos.encerrar_contrato` |
| `registrar_boleto` | `servicos.registrar_boleto` |
| `marcar_boleto_enviado` | `servicos.marcar_boleto_enviado` |
| `registrar_pagamento_boleto` | `servicos.registrar_pagamento_boleto` |
| `registrar_pagamento` | `servicos.registrar_pagamento` |
| `registrar_documento` | `servicos.registrar_documento` |
| `criar_pendencia` | `servicos.criar_pendencia` |

**Não** criar ferramenta para: cancelar pagamento, isentar/cancelar cobrança, editar valor de
cobrança, resolver pendência, apagar qualquer coisa, usuários (regras §11).

### 3.3 `docs/hermes.md`
Guia curto **para o Hermes** (o Paulo vai colar ou apontar para ele):
- o que o sistema é e o princípio "o sistema diz o que é devido, o banco diz o que foi pago,
  você executa e registra";
- rotina diária sugerida: `cobrancas_sem_boleto` → emitir no banco → `registrar_boleto` →
  enviar e-mail → `marcar_boleto_enviado`; conferir pagos no banco →
  `registrar_pagamento_boleto`; olhar `alertas` e `inadimplentes` e avisar o Paulo;
- lançar comprovante: `buscar_locatarios` → `extrato_contrato` → escolher a cobrança →
  guardar o arquivo na `pasta_documento` → `registrar_pagamento` com o caminho;
- em caso de dúvida, `criar_pendencia` em vez de adivinhar;
- **escrito como orientação e sugestão**, pedindo que ele confirme com o Paulo o que for
  diferente do que já faz. Não dar ordens (pedido do Paulo).

### 3.4 Testes
- `test_mcp.py`: chame as funções das ferramentas diretamente (sem rede) e confira: cadastro
  completo de imóvel → locatário → contrato; `cobrancas_sem_boleto` → `registrar_boleto` →
  `registrar_pagamento_boleto` → `extrato_contrato` mostra paga; a auditoria registra
  `hermes`; valor `"1.234,56"` vira 123456 centavos; erro de negócio vira mensagem legível.
- Teste de fumaça com rede: suba o servidor e use o cliente do próprio SDK `mcp` para listar
  as ferramentas com o token certo (funciona) e sem token (recusado).

### Pronto quando
Testes passando e `docs/hermes.md` escrito. Diga ao Paulo que o teste real com o Hermes
acontece na Etapa 4, quando o sistema estiver no servidor.

---

## Etapa 4 — Docker, servidor, Hermes conectado e backup

Esta etapa é feita **junto com o Paulo** (ele tem o acesso ao painel da Hostinger). Mande
um passo de cada vez, com o texto exato do que ele clica ou cola.

### 4.1 Arquivos (em `deploy/`)
- `Dockerfile`: `python:3.12-slim`, instala `sistema/requirements.txt`, copia `sistema/` e
  `scripts/`, roda como usuário não-root. Uma imagem só para os serviços abaixo.
- `docker-compose.yml` com três serviços usando a mesma imagem:
  - `mcp`: `python -m sistema.mcp_server`. **Não** publicado na internet: só acessível pela
    rede Docker compartilhada com o Hermes.
  - `backup`: loop que roda `scripts/backup.py` uma vez por dia.
  - (`web` entra na Etapa 5.)
  - Volumes: `/dados` (banco) e `/documentos` (pasta de documentos). Ambos como pastas do
    servidor (bind mount), para o File Browser e o Hermes enxergarem.
  - Variáveis via arquivo `.env` **no servidor** (nunca no git). Commitar só um
    `deploy/.env.exemplo` sem valores reais.
- `scripts/backup.py`:
  1. cópia consistente do banco com a API de backup do SQLite
     (`sqlite3.Connection.backup`), que é segura com o sistema rodando;
  2. `tar.gz` com essa cópia e a pasta de documentos, nome com a data;
  3. envia para o Google Drive com **rclone** (instalado na imagem) e apaga do Drive as
     cópias além das 14 mais recentes.
  - Atenção: conta de serviço do Google **não tem cota de armazenamento** no Drive pessoal,
    então o upload com a conta de serviço usada na planilha falha. Use o rclone autorizado
    com a conta Google do Paulo (`rclone authorize "drive"` precisa de um navegador **uma
    vez**; combine com ele).

### 4.2 No servidor (com o Paulo)
1. Descobrir **antes de configurar**, sem adivinhar: onde o Traefik está e qual rede Docker
   ele usa (`docker ps`, `docker network ls`, `docker inspect` do container do Traefik); em
   qual rede está o Hermes; qual pasta o File Browser mostra (é `/home`).
2. Pasta de documentos no servidor: sugestão `/home/documentos` (o File Browser já mostra
   `/home`). Montar a mesma pasta no container do Hermes (hoje ele guarda arquivos em
   `/opt/data`, dentro dele). **Confirme com o Paulo** antes de mexer na configuração do
   Hermes.
3. Subir `mcp` e `backup`. Colocar o `mcp` na mesma rede do Hermes.
4. No painel do Hermes (aba MCP), adicionar o servidor: URL
   `http://<nome-do-serviço>:8001/mcp` e cabeçalho `Authorization: Bearer <token>`. O Paulo
   gera e cola o token direto no `.env` do servidor e no painel do Hermes: **o token não
   passa pela conversa.**
5. Passar o `docs/hermes.md` ao Hermes.
6. Criar os usuários com `scripts/criar_usuario.py` (cada pessoa digita a própria senha).
7. Rodar o backup uma vez à mão e conferir o arquivo no Drive.

### Pronto quando
O Paulo pede ao Hermes, por mensagem, "cadastre o imóvel de teste X" e depois "mostre o
painel", e funciona; o backup aparece no Drive. Depois do teste, apagar o banco de teste e
começar o cadastro real pelo Hermes.

---

## Etapa 5 — Páginas web

### 5.1 Base
- **FastAPI + Jinja2**, HTML gerado no servidor, **sem React, sem JavaScript de build**.
  Formulários HTML normais (`<form method="post">`). Dependências: `fastapi`,
  `uvicorn[standard]`, `jinja2`, `python-multipart`, `itsdangerous`.
- CSS: **Pico CSS** (arquivo copiado para `sistema/static/`, sem CDN). Funciona bem no
  celular sem escrever CSS. Menu **no topo**, não lateral (no Streamlit o menu lateral
  cobria os formulários no celular).
- Gráficos: **Plotly** (arquivo JS em `static/`), só no painel.
- Login: tabela `usuarios`, senha com `bcrypt`, sessão com o `SessionMiddleware` do
  Starlette (`SESSION_SECRET`). Toda página exige login, exceto `/login`.
- Padrão de formulário: POST → chama `servicos` → redireciona (evita gravar duas vezes ao
  atualizar a página) → mensagem de sucesso. Em `ErroDeNegocio`, mostra o mesmo formulário
  com os dados preenchidos e a mensagem.
- Valores em reais digitados como `1.234,56`; datas com `<input type="date">`.
- Seleção de contrato sempre por **imóvel + locatário**, nunca só pelo nome.
- `web.py` só chama `servicos` e `consultas`, com `quem = login do usuário`.
- Adicionar o serviço `web` no `docker-compose.yml`, publicado pelo Traefik (endereço do
  servidor até o domínio existir).

### 5.2 Páginas
| Página | Conteúdo |
|---|---|
| `/login`, `/sair` | entrar e sair |
| `/` Painel | ocupação, resumo do mês, atrasados, alertas, pendências abertas (destaque), 2 gráficos: recebido por mês (12 meses) e imóveis por situação |
| `/imoveis` | lista, novo, editar, apagar (se permitido), ficha com contratos e documentos, upload |
| `/locatarios` | lista com busca, novo, editar, apagar, ficha com contratos, total em aberto, documentos, upload |
| `/corretores` | lista, novo, editar, apagar |
| `/contratos` | lista (ativos/encerrados), novo, editar, ficha = extrato; ações: reajuste, renovar, encerrar, apagar (se permitido), upload |
| `/cobrancas` | filtro por competência e situação; ações: editar valor, isentar, cancelar, registrar boleto à mão, marcar enviado |
| `/pagamentos/novo` | imóvel/contrato → cobrança em aberto → dados → comprovante opcional |
| `/pagamentos` | histórico financeiro com filtros e total; cancelar pagamento (com motivo) |
| `/pendencias` | lista; resolver com texto |
| `/auditoria` | últimas ações, filtro por entidade |
| `/documentos/<id>` | baixa o arquivo (só dentro de `DOCS_DIR`) |

### 5.3 Testes
- `test_web.py` com o `TestClient` do FastAPI: sem login redireciona para `/login`; login
  errado recusa; fluxo completo (cadastrar imóvel, locatário, contrato, lançar pagamento) e
  conferir no extrato; erro de negócio aparece na página.
- Verificação visual com Playwright (Chromium já instalado no ambiente de nuvem) em largura
  de celular (390 px): todas as páginas abrem, menu não cobre formulário. Mande prints ao
  Paulo.

### Pronto quando
O Paulo consegue, pelo celular, fazer tudo que fazia no Streamlit, mais: fichas, extrato,
pendências e upload.

---

## Etapa 6 — Virada

1. Domínio: o Paulo registra na Hostinger; apontar o registro DNS `A` para o IP do servidor;
   trocar o endereço nas configurações do Traefik (HTTPS automático).
2. Definir com o Paulo o valor final de `INICIO_COBRANCAS` (regras §5) antes das cobranças
   reais.
3. Uma semana usando os dois sistemas; o Paulo confirma que o novo cobre tudo.
4. Só depois da confirmação dele: desligar o app no Streamlit Cloud; remover `app.py`,
   `auth_utils.py`, `data_access.py`, `pages/`, `scripts/generate_keys.py` e o
   `requirements.txt` da raiz; reescrever `README.md` e `CLAUDE.md` para o sistema novo.
5. Lembrar o Paulo de revogar a conta de serviço do Google usada pela planilha, se ela não for
   mais usada.
