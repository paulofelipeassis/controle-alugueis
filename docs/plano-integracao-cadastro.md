# Plano — sistema de aluguéis usando o cadastro único do Hermes

> **Situação:** proposta para o Paulo revisar (21/10/2026). Nada foi implementado.
> Decisão de origem: o Paulo escolheu **uma lista de imóveis só, a do Hermes** (21/10/2026),
> para acabar com a cópia e a conciliação mensal entre dois cadastros.

## 1. A ideia em uma frase

O **imóvel** (ID, apelido, tipo, finalidade, vendido ou não, UCs, IPTU, pasta) passa a existir
**só no cadastro do Hermes**. O sistema de aluguéis **lê** esse cadastro e guarda apenas o que é
do **aluguel**: locatário, contrato, valores, cobranças, boletos, pagamentos, caução, e a marcação
"em manutenção".

| Hoje (proposta antiga) | Com este plano |
|---|---|
| Duas tabelas de imóveis, cópia do Hermes para o sistema | Uma tabela, a do Hermes |
| Campo `id_hermes`, bloqueio de campos, conciliação todo mês | Nada disso: o sistema já usa o ID do Hermes (`RIF-101`) |
| Imóvel que vira aluguel precisa ser copiado | Aparece no sistema na hora |
| Imóvel vendido precisa ser tirado do sistema | Sai da lista de alugáveis na hora |

### O que fica onde

**Os contratos continuam inteiros no sistema de aluguéis.** Só a lista de imóveis deixa de
existir nele.

| Cadastro do Hermes | Sistema de aluguéis (como já estava preparado) |
|---|---|
| O imóvel em si: ID, apelido, tipo, finalidade, vendido ou não, UCs, IPTU, pasta | **Locatário:** nome, CPF/CNPJ, telefone, e-mail |
| | **Contrato:** início, fim, vencimento, multa, juros, garantia, caução, fiador, índice |
| | **Valor do aluguel** com o histórico de reajustes |
| | **Cobranças, boletos, pagamentos, pendências** e todas as regras |

O contrato só passa a apontar para o imóvel pelo ID do Hermes (`RIF-101`). O Hermes **não guarda
contratos**: quando um operador pede um contrato, o Hermes o cadastra **no sistema**, pelo MCP, e
o sistema confere as regras (princípio 1 de `regras-de-negocio.md`: o Hermes é o mensageiro).

**Arquivos:** as únicas pastas são as do Hermes (decisão do Paulo, 21/10/2026). Ver seção 3b.

## 2. Como o sistema lê o cadastro

- O Hermes já grava, a cada mudança, uma cópia legível do cadastro:
  `imobiliaria/_cadastro/imoveis-exportado.csv`. Ela é escrita de forma **atômica** (o arquivo
  troca de uma vez; nunca há meio arquivo).
- A pasta `_cadastro` entra nos containers do sistema **só para leitura** (`/cadastro:ro`). O
  sistema não tem como alterar o cadastro, nem por engano.
- **Por que o CSV e não o banco do Hermes:** ler um SQLite de outro programa por uma pasta só de
  leitura dá erro quando o Hermes está gravando no mesmo instante. O CSV não tem esse problema, e
  o banco do Hermes continua com um único dono (o `cadastro.py`).
- Cada vez que o sistema abre o banco dele, carrega o CSV numa tabela temporária `imoveis` (são
  ~30 linhas: instantâneo). Assim as consultas de hoje continuam funcionando quase sem mudança.
- **Se o CSV sumir ou vier com defeito:** o sistema usa a **última cópia boa**, que ele guarda em
  `dados/cadastro-ultima-copia.csv`, e mostra uma faixa no painel ("cadastro do Hermes
  indisponível desde …"). Boletos e pagamentos não param por causa disso.

## 3. O que muda no sistema de aluguéis

| Parte | Mudança |
|---|---|
| Tabela `imoveis` | Sai do banco do sistema. Fica uma tabela pequena `imoveis_operacao` (ID do Hermes + "em manutenção"). |
| `contratos.imovel_id` | Passa a ser o **ID do Hermes** (texto, `RIF-101`). O banco de produção está vazio, então a troca não tem dado para migrar. |
| Documentos (`imovel_id`) | Idem. |
| Cadastrar / editar / apagar imóvel (web e Hermes/MCP) | **Sai.** A ficha do imóvel na web mostra os dados do cadastro, só leitura, com "para alterar, peça ao Hermes". |
| Campos IPTU anual, medidor Saneago, medidor Enel | **Saem** (decisões do cadastro: só UC; IPTU proporcional fica para depois de novembro). |
| Nome do imóvel nas telas | **Apelido**, com o ID: "101 da Rifânia (RIF-101)". |
| Filtro "grupo" | Vira **prédio** (o prédio da unidade) ou o tipo, para casas e terrenos. |
| Quais imóveis aparecem para contrato | Só os **alugáveis**: finalidade `aluguel`, situação `ativo`, e que não são prédio. |

**Situação (Alugado / Reservado / Em manutenção / Vago)** continua calculada como hoje. A única
diferença é de onde vem a lista.

## 3b. Pastas de documentos: só as do Hermes

Hoje o sistema aponta para `/home/documentos`, que está **vazia**. Os documentos de verdade
estão em `imobiliaria/` do Hermes. O sistema passa a usar essa pasta, e deixa de ter convenção
própria:

| Arquivo | Onde fica |
|---|---|
| Documento do imóvel | `imobiliaria/imoveis/<pasta do cadastro>/...` (subpastas do Hermes) |
| Contrato, vistoria, aditivo | `imobiliaria/imoveis/<pasta do cadastro>/contratos/` |
| Comprovante de pagamento | Junto do imóvel (subpasta a confirmar com a convenção do Hermes) |
| Documentos do locatário | `imobiliaria/clientes/` — **o padrão dessa pasta ainda não foi definido no Hermes**; definir junto, antes do primeiro contrato |

- O **nome da pasta do imóvel vem do cadastro** (campo `pasta`), nunca é calculado pelo sistema.
- Os nomes de arquivo seguem a nomenclatura do Hermes (`estrutura-e-nomenclatura.md`).
- O upload pela web continua existindo (redundância, princípio 4).
- Os containers do sistema passam a gravar como o **mesmo usuário do Hermes** (uid 10000). Sem
  isso, um arquivo enviado pela web ficaria com outro dono e o Hermes não conseguiria mexer nele.
- `docs/estrutura-de-pastas.md` deixa de valer: passa a apontar para a convenção do Hermes.

### Avisos novos no painel (no lugar da conciliação mensal)

- Contrato ativo em imóvel que **deixou de ser de aluguel** ou foi **vendido** → "encerrar o contrato
  ou corrigir o cadastro". O sistema **não encerra sozinho** (encerrar tem regras de cobrança final).
- Cópia do cadastro **velha ou ilegível** (ver seção 2).

O Hermes faz a mesma conferência pelo MCP antes de emitir boletos (ferramenta `alertas`, que já
existe).

## 4. Ordem de trabalho e prazo

As cobranças começam em **novembro/2026**, e os contratos precisam estar cadastrados antes dos
boletos. A ordem é:

1. **Virada do cadastro no Hermes** (já pronta e ensaiada). É ela que cria o CSV. **Pode ser feita
   assim que o Paulo aprovar os textos**, e convém fazer logo, porque o resto depende dela.
2. **Sistema de aluguéis lendo o cadastro** (este plano), testado em cópia e com os dados reais
   do cadastro. Entra no ar por PR aprovado pelo Paulo.
3. **Cadastro dos contratos** (pelo Hermes ou pela web).
4. **Boletos de novembro.** Pela API da Caixa se ela estiver pronta; senão, do jeito atual (gerado
   no banco, link registrado no sistema).

Se a etapa 2 atrasar, o plano B é cadastrar os contratos assim mesmo **depois** dela. Não há
plano B que cadastre contratos antes, porque seria cadastrar imóvel em dobro de novo.

## 5. Testes

- Os 183 testes atuais continuam passando, ajustados para o imóvel vindo de um CSV de teste.
- Testes novos: CSV ausente, CSV com defeito, imóvel vendido com contrato ativo, imóvel que vira
  aluguel aparece na hora, prédio não aceita contrato, ID desconhecido recusado.
- Teste **com os dois sistemas juntos** na VPS, numa cópia: Hermes muda um imóvel → o sistema
  enxerga na próxima página aberta.

## 6. O que contraria `regras-de-negocio.md` (precisa do OK do Paulo)

O documento de regras pede para não mudar decisões sem perguntar. Estas mudam:

1. **§1** — "O Hermes recadastra imóveis" no sistema: deixa de existir; o imóvel já está no cadastro.
2. **§3, Imóvel** — campos grupo, unidade, IPTU anual e medidores: substituídos pelo cadastro do Hermes.
3. **§11** — o Hermes **não** cadastra imóvel pelo MCP (cadastra pelo `cadastro.py`, do lado dele).
4. **§9, Documentos** — "o **sistema** é dono da convenção de pastas" deixa de valer. **Decidido pelo
   Paulo (21/10/2026): as únicas pastas são as do Hermes** (seção 3b).

## 7. Depois deste plano (não entra agora)

- API de boletos da Caixa.
- IPTU proporcional repassado ao locatário (depois de novembro).
