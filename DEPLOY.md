# Guia de Deploy (VPS Hostinger + domínio próprio)

Guia passo a passo para colocar o app no ar num servidor próprio. Escrito
para quem nunca fez isso antes — cada bloco de comando vem com uma frase
explicando o que ele faz. Você só precisa copiar e colar, na ordem.

Assume uma VPS com **Ubuntu** (22.04 ou 24.04), que é o padrão mais comum
oferecido pela Hostinger. Se você escolher outro sistema operacional na
Hostinger, os comandos de instalação de pacotes mudam (avise que eu adapto).

Onde `SEU-DOMINIO-AQUI` aparecer abaixo, troque pelo domínio real que a
Hostinger te der (ex: `alugueis-familia.com`).

## 0. O que você precisa ter em mãos antes de começar

- O **IP da VPS** e a forma de acessá-la por SSH (usuário + senha, ou chave
  SSH) — isso a Hostinger te dá no painel dela.
- O **domínio** que veio com o plano da VPS.

## 1. Apontar o domínio para a VPS

No painel da Hostinger, na área de gerenciamento de DNS do domínio, crie um
registro:

- Tipo: `A`
- Nome/Host: `@` (ou deixe em branco, representa o domínio raiz)
- Aponta para: o IP da sua VPS

Isso pode levar de alguns minutos a algumas horas para propagar. Pode seguir
os próximos passos enquanto espera.

## 2. Conectar na VPS

No terminal do seu computador (ou um app de SSH no celular, tipo Termius):

```bash
ssh root@IP-DA-VPS
```

Todos os comandos abaixo são executados **dentro da VPS**, depois de
conectado.

## 3. Instalar as ferramentas básicas

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv git curl
```

Isso atualiza a lista de pacotes do sistema e instala Python, a ferramenta
de ambiente virtual do Python, o Git (para baixar o código) e o `curl`
(usado no próximo passo).

## 4. Criar um usuário próprio para rodar o app

```bash
sudo adduser --system --group --home /opt/controle-alugueis controle-alugueis
```

Por segurança, o app não deve rodar como `root` (o usuário "dono de tudo"
do servidor). Esse comando cria um usuário limitado, só para isso.

## 5. Baixar o código

```bash
sudo git clone https://github.com/paulofelipeassis/controle-alugueis.git /opt/controle-alugueis
sudo chown -R controle-alugueis:controle-alugueis /opt/controle-alugueis
```

Baixa o repositório para `/opt/controle-alugueis` e entrega a pasta para o
usuário criado no passo anterior.

## 6. Criar o ambiente virtual e instalar as dependências

```bash
sudo -u controle-alugueis python3 -m venv /opt/controle-alugueis/.venv
sudo -u controle-alugueis /opt/controle-alugueis/.venv/bin/pip install -r /opt/controle-alugueis/requirements.txt
```

Um "ambiente virtual" é uma pasta isolada com sua própria cópia do Python e
das bibliotecas do projeto, para não interferir com o resto do sistema.

## 7. Criar o arquivo de segredos (`secrets.toml`)

Esse arquivo tem as senhas e credenciais do Google — **nunca fica no Git**,
precisa ser criado manualmente aqui na VPS:

```bash
sudo -u controle-alugueis mkdir -p /opt/controle-alugueis/.streamlit
sudo -u controle-alugueis nano /opt/controle-alugueis/.streamlit/secrets.toml
```

O `nano` é um editor de texto simples dentro do terminal. Cole o conteúdo
abaixo (ajustando os valores reais), salve com `Ctrl+O`, `Enter`, e saia com
`Ctrl+X`:

```toml
[credentials.usernames.fulano]
email = "fulano@example.com"
name = "Fulano da Silva"
password = "$2b$12$..."  # hash bcrypt

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

Veja o `README.md` do projeto para detalhes de como gerar o hash da senha e
de onde tirar as credenciais do Google.

## 8. Testar o app manualmente (antes de automatizar)

```bash
sudo -u controle-alugueis /opt/controle-alugueis/.venv/bin/streamlit run /opt/controle-alugueis/app.py --server.port 8501 --server.address 127.0.0.1
```

Isso roda o app "na mão", só para confirmar que sobe sem erro. Pare com
`Ctrl+C` depois de ver que não deu erro — o passo 10 vai deixá-lo rodando
de verdade, sozinho, em segundo plano.

## 9. Instalar o Caddy (o "porteiro" HTTPS)

O Caddy é um servidor que fica ouvindo a internet nas portas 80/443 (as
portas padrão da web) e emite/renova o certificado HTTPS sozinho. Comandos
oficiais do site do Caddy para Ubuntu/Debian:

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy
```

## 10. Configurar o Caddy para o seu domínio

Copie o arquivo `deploy/Caddyfile` deste repositório para o lugar que o
Caddy espera, e edite trocando `SEU-DOMINIO-AQUI` pelo domínio real:

```bash
sudo cp /opt/controle-alugueis/deploy/Caddyfile /etc/caddy/Caddyfile
sudo nano /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

## 11. Configurar o app para ligar sozinho (systemd)

Copie o arquivo `deploy/controle-alugueis.service` deste repositório para
o lugar que o systemd espera:

```bash
sudo cp /opt/controle-alugueis/deploy/controle-alugueis.service /etc/systemd/system/controle-alugueis.service
sudo systemctl daemon-reload
sudo systemctl enable --now controle-alugueis
```

`enable` faz o app subir sozinho sempre que a VPS reiniciar. `--now` já
inicia agora, sem precisar reiniciar o servidor.

## 12. Testar

Abra `https://SEU-DOMINIO-AQUI` no navegador. Deve aparecer a tela de
login, já com o cadeado de HTTPS.

## Comandos úteis para o dia a dia

Ver se o app está rodando e os últimos logs (útil se algo der errado):

```bash
sudo systemctl status controle-alugueis
sudo journalctl -u controle-alugueis -f
```

Reiniciar o app manualmente (ex: depois de trocar o `secrets.toml`):

```bash
sudo systemctl restart controle-alugueis
```

Atualizar o app quando houver mudanças no código (depois de um `git pull`):

```bash
cd /opt/controle-alugueis
sudo -u controle-alugueis git pull
sudo -u controle-alugueis /opt/controle-alugueis/.venv/bin/pip install -r requirements.txt
sudo systemctl restart controle-alugueis
```

## Por que isso é seguro o suficiente para este projeto

- O Streamlit só escuta em `127.0.0.1` (a própria máquina) — quem acessa de
  fora só fala com o Caddy, nunca diretamente com o app.
- O app roda com um usuário sem privilégios (`controle-alugueis`), não como
  `root`.
- O HTTPS é automático e renovado sozinho pelo Caddy.

Isso é proporcional a um sistema pequeno, de 3-4 usuários conhecidos — não
tenta ser uma infraestrutura de produção de larga escala.
