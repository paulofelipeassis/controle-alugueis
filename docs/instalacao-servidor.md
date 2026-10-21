# Instalação no servidor (VPS Hostinger)

Passo a passo para colocar o sistema novo no ar. Os comandos são colados no **terminal do
navegador da Hostinger** (hPanel → VPS → botão "Terminal" / "Browser terminal").

> **Segurança:** senhas, tokens e chaves só são digitados **no terminal do servidor** ou
> no **painel do Hermes**, nunca em conversa com IA.

O sistema tem três partes, todas na mesma imagem Docker:

| Serviço | O que faz | Aparece na internet? |
|---|---|---|
| `web` | as páginas (login, painel, formulários) | sim, pelo Traefik, com HTTPS |
| `mcp` | as ferramentas do Hermes | **não**, só na rede do Hermes |
| `backup` | backup diário (3h) do banco e dos documentos para o Google Drive | não |

## 1. Baixar o código

```bash
mkdir -p /opt/controle-alugueis && cd /opt/controle-alugueis
git clone https://github.com/paulofelipeassis/controle-alugueis.git codigo
cd codigo/deploy
```

Se o repositório for privado, o `git clone` pede usuário e senha: use seu usuário do GitHub e,
como senha, um *token* criado em GitHub → Settings → Developer settings → Fine-grained tokens,
com acesso **só de leitura** a este repositório.

## 2. Descobrir como o Traefik e o Hermes estão configurados

Não adivinhe esses valores: eles dependem de como a Hostinger instalou cada coisa.

```bash
docker ps --format 'table {{.Names}}\t{{.Image}}'
```

Anote o nome do container do **Traefik** e o do **Hermes**. O Traefik da Hostinger roda em modo
`host` e acha o site pelo IP da rede `alugueis-web`, que o próprio compose cria: não há rede do
Traefik para informar. Depois (troque os nomes):

```bash
# Nome do certresolver e do entrypoint HTTPS (procure por certificatesresolvers.XXX e entrypoints.YYY.address=:443)
docker inspect NOME_DO_TRAEFIK --format '{{join .Config.Cmd "\n"}}' | grep -E 'certificatesresolvers|entrypoints'
# Rede do Hermes
docker inspect NOME_DO_HERMES --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}'
```

Se o Traefik for configurado por arquivo, e não por linha de comando, o `grep` não mostra
nada. Nesse caso, procure no arquivo `traefik.yml` do container.

## 3. Pastas e configuração

```bash
mkdir -p /opt/controle-alugueis/dados /home/documentos
cp .env.exemplo .env
sed -i "s/^SESSION_SECRET=.*/SESSION_SECRET=$(openssl rand -hex 32)/" .env
sed -i "s/^MCP_TOKEN=.*/MCP_TOKEN=$(openssl rand -hex 32)/" .env
nano .env
```

No `nano`, preencha `TRAEFIK_ENTRYPOINT`, `TRAEFIK_CERTRESOLVER` e
`HERMES_REDE` com o que você descobriu no passo 2. Confira também o `DOMINIO`, o
`INICIO_COBRANCAS` (já vem `2026-11`) e `FERIADOS_EXTRAS` (já vem com os de Formosa). `COOKIE_SEGURO=1` já vem
ligado: o login só funciona entrando por `https://`. Para salvar e sair: Ctrl+O, Enter, Ctrl+X.

`/home/documentos` é a pasta de documentos. Ela aparece no File Browser, que mostra `/home`.

## 4. Subir

```bash
docker compose up -d --build
docker compose ps
```

Os três serviços devem aparecer como `Up`. Abra `https://DOMINIO` no celular: deve aparecer a
tela de login.

## 5. Criar os usuários

Um por pessoa:

```bash
docker compose exec web python -m scripts.criar_usuario
```

Se você criar o usuário de outra pessoa, use uma senha provisória e peça que ela troque em
Menu → Trocar senha.

**Alguém esqueceu a senha?** Rode o mesmo comando, digite o login que já existe e responda `s`
quando ele perguntar se quer trocar a senha.

## 6. Conectar o Hermes

1. Veja o token (aparece só no terminal):
   ```bash
   grep MCP_TOKEN .env
   ```
2. No painel do Hermes, aba **MCP**, adicione um servidor:
   - URL: `http://alugueis-mcp:8001/mcp`
   - Cabeçalho: `Authorization` = `Bearer ` seguido do token (com o espaço depois de "Bearer").
3. Passe ao Hermes o guia [`docs/hermes.md`](hermes.md) e a sugestão de pastas
   [`docs/estrutura-de-pastas.md`](estrutura-de-pastas.md).
4. **Pasta de documentos do Hermes:** hoje ele guarda arquivos em `/opt/data`, dentro do
   container dele. Para ele enxergar `/home/documentos`, é preciso acrescentar na configuração
   do Hermes (no Docker Manager da Hostinger, editar o projeto dele) o volume
   `/home/documentos:/opt/data/documentos`. **Isso mexe na configuração do Hermes: confirme
   antes.** Depois, avise o Hermes de que os caminhos passados ao sistema são **relativos**
   a essa pasta (ex.: `imoveis/Anel Viario - Apto 101/imovel/iptu-2026.pdf`).

Teste: peça ao Hermes "cadastre o imóvel de teste Teste / Apto 1, endereço Rua Teste" e
depois "mostre o painel". O imóvel deve aparecer no site. Apague-o pelo site (Imóveis → Teste
→ Apagar imóvel).

Se o Hermes não conseguir conectar, confira `HERMES_REDE` e rode `docker compose up -d` de
novo.

## 7. Backup no Google Drive

A conta de serviço do Google (a da planilha) **não serve** para isso: contas de serviço não
têm espaço próprio no Drive. O backup usa a **sua** conta Google, autorizada uma vez com o
rclone.

1. No servidor:
   ```bash
   docker compose run --rm backup rclone config
   ```
   Responda: `n` (novo) → nome `drive` → tipo `drive` → deixe `client_id` e `client_secret` em
   branco → escopo `1` (acesso total) → deixe o resto no padrão → na pergunta **"Use web
   browser to automatically authenticate?"** (ou **"Use auto config?"**) responda `n`.
2. Ele mostra um comando `rclone authorize "drive" ...`. Esse passo precisa de um
   **computador com navegador**: instale o rclone nele (https://rclone.org/downloads/), rode o
   comando, faça login no Google e copie o código que aparece.
3. Cole o código **no terminal do servidor**. Confirme até o fim (`q` para sair).
4. No `.env`, preencha `RCLONE_DESTINO=drive:Backup Alugueis` e rode:
   ```bash
   docker compose up -d
   docker compose exec backup python -m scripts.backup
   ```
5. Confira no Google Drive a pasta "Backup Alugueis" com o arquivo `backup-alugueis-....tar.gz`.

O backup roda todo dia às 3h e mantém as 14 cópias mais recentes. Uma cópia local também
fica em `/opt/controle-alugueis/dados/backups`.

**Restaurar** (se um dia precisar): parar o sistema (`docker compose down`), abrir o
`.tar.gz`, colocar `alugueis.db` em `/opt/controle-alugueis/dados/` e a pasta `documentos` em
`/home/documentos`, e subir de novo (`docker compose up -d`).

## Restaurar um backup (se o servidor quebrar ou o banco estragar)

1. Instale tudo de novo pelos passos 1 a 4 (um servidor novo serve).
2. Pare o sistema: `docker compose down`.
3. Baixe o `.tar.gz` mais recente do Google Drive (pasta "Backup Alugueis") e abra:
   ```bash
   mkdir /tmp/restaurar && tar -xzf backup-alugueis-AAAA-MM-DD-HHMM.tar.gz -C /tmp/restaurar
   rm -f /opt/controle-alugueis/dados/alugueis.db-wal /opt/controle-alugueis/dados/alugueis.db-shm
   cp /tmp/restaurar/alugueis.db /opt/controle-alugueis/dados/alugueis.db
   cp -r /tmp/restaurar/documentos/. /home/documentos/
   ```
4. Suba de novo: `docker compose up -d`. Os usuários e a senha voltam junto com o banco. O que
   não está no backup é o `.env` (segredos): gere de novo, e o Hermes precisa do token novo.

## Atualizar para uma versão nova

```bash
cd /opt/controle-alugueis/codigo && git pull && cd deploy && docker compose up -d --build
```

## Ver o que está acontecendo

```bash
docker compose logs --tail 50 web      # ou mcp, ou backup
```

## Domínio (quando tiver)

1. No painel da Hostinger, em DNS do domínio, crie um registro `A` apontando para o IP do
   servidor.
2. No `.env`, troque `DOMINIO=` pelo domínio novo e rode `docker compose up -d`. O Traefik
   gera o HTTPS sozinho.
