# Guia para o Hermes: sistema de controle de aluguéis

> **Para o Hermes:** este guia é uma **orientação**, não uma ordem. Se você já faz alguma
> destas tarefas de outro jeito, ou se algo aqui não combina com o que o Paulo te pediu,
> **mostre a diferença ao Paulo e confirme com ele** antes de mudar sua rotina.

## O que é

O sistema guarda os imóveis, locatários, contratos, cobranças e pagamentos da família. Você
fala com ele pelas ferramentas do servidor MCP `controle-alugueis`.

**Princípio:** o sistema diz **o que é devido**. O banco diz **o que foi pago**. Você
**executa e registra**, não decide. Quando algo não estiver claro, use `criar_pendencia`
para uma pessoa olhar, em vez de adivinhar.

## Formatos

- Valores em reais, como texto no formato brasileiro: `"1.500,00"`.
- Datas: `AAAA-MM-DD` (ex.: `2026-10-10`).
- Vencimento em sábado, domingo ou feriado vale até o dia útil seguinte, sem multa nem juros (o
  sistema já considera isso: `vencimento_efetivo`). No boleto do banco, use o vencimento do contrato.
- Listas vêm como `{"quantidade": N, "itens": [...]}`. `quantidade: 0` quer dizer que não
  há nada (por exemplo, nenhuma pendência), não que houve erro.
- Competência (mês da cobrança): `AAAA-MM`. A cobrança de outubro é a que **vence** em
  outubro.
- Arquivos: caminho **relativo à pasta de documentos** (ex.:
  `imoveis/Anel Viario - Apto 101/contratos/2026-10 - Maria Souza/contrato-assinado.pdf`).

## Rotinas sugeridas

### Todo dia: boletos
1. `cobrancas_sem_boleto`: traz o que precisa de boleto, já com nome, CPF/CNPJ, e-mail,
   valor, vencimento, multa e juros do contrato. Pule as que têm `reajuste_pendente: true`
   (veja "Reajuste anual").
   Se `data_encerramento` vier preenchido (contrato encerrado, dívida antiga), **não emita** sem
   perguntar ao Paulo.
2. Emitir cada boleto no banco (hoje a Caixa), com a multa e os juros informados.
3. `registrar_boleto` com o nosso número (`identificador`), a linha digitável e o link.
4. Enviar o boleto por e-mail ao locatário.
5. `marcar_boleto_enviado`.

### Todo dia: pagamentos
1. `boletos_em_aberto`: lista os boletos ainda não pagos.
2. Conferir no banco quais foram pagos.
3. Para cada pago: `registrar_pagamento_boleto` com o identificador, a data e o valor que o
   banco informou. Pode repetir sem medo: o mesmo boleto nunca vira dois pagamentos.
4. Se a resposta trouxer `pendencias` ou `registrado: false`, avise o Paulo. `registrado: false`
   quer dizer que o dinheiro entrou mas o sistema não conseguiu ligá-lo a uma cobrança (boleto
   desconhecido, ou cobrança isentada ou cancelada): uma pendência foi criada, não faça mais nada.
5. Boleto de segunda via: o antigo continua pagável no banco e o sistema reconhece a baixa dele.

### Todo dia: avisos
`alertas` e `inadimplentes`. Sugestão: mandar ao Paulo um resumo curto só quando houver
novidade (atraso novo, contrato terminando, reajuste chegando, pendência nova).

### Quando chegar um comprovante (PIX, transferência)
1. `buscar_locatarios` pelo nome ou CPF/CNPJ de quem pagou.
2. `extrato_contrato` do contrato certo, para escolher a cobrança (a mais antiga em aberto,
   salvo indicação contrária).
3. `pasta_documento` com `entidade="contrato"`: salvar o comprovante nessa pasta, com o nome
   sugerido `comprovante-AAAA-MM.pdf` (competência da cobrança).
4. `registrar_pagamento` com `forma="pix"` (ou outra), o código da transação em
   `identificador_externo` (evita registrar duas vezes) e o caminho do comprovante.
5. Se o comprovante estiver ilegível ou não der para saber qual cobrança é:
   `criar_pendencia`.

### Cadastros
- Antes de cadastrar um locatário, `buscar_locatarios` para não duplicar.
- Ordem: `cadastrar_imovel` → `cadastrar_locatario` → `criar_contrato`. As cobranças são
  criadas sozinhas.
- **Contratos que já existem:** use a data de início verdadeira, o valor **atual** do aluguel e
  `valor_vigente_desde` = data do último reajuste (desde quando vale o valor atual). Isso é
  obrigatório se o contrato começou há mais de 1 ano. Se não souber a data, pergunte ao Paulo:
  é dela que o sistema calcula o próximo reajuste. O sistema não cria cobranças de meses
  anteriores ao início das cobranças, então não aparecem dívidas antigas.
- Documentos (contrato assinado, vistorias, RG): salvar na pasta de `pasta_documento` e
  chamar `registrar_documento`. A convenção de pastas está em `docs/estrutura-de-pastas.md`
  (também uma sugestão, a confirmar com o Paulo).

### Reajuste anual (IPCA e IGP-M)
Os `alertas` avisam quando um contrato faz aniversário. Sugestão:
1. `sugerir_reajuste` do contrato: o sistema busca na hora o acumulado das últimas 12
   variações publicadas (índice negativo = valor mantido).
2. Mostrar o `resumo` ao Paulo e perguntar se aprova, ou se o valor combinado é outro.
3. Só depois do "sim" dele: `registrar_reajuste` com o valor, `vigente_desde` e `motivo`.
4. Em `cobrancas_sem_boleto`, se uma cobrança vier com `reajuste_pendente: true`, **não emita
   o boleto** até o reajuste ser registrado. Assim o 13º boleto já sai reajustado.

### Renovação e encerramento
- `renovar_contrato`, `encerrar_contrato`. Confirme com o Paulo
  antes: são decisões dele. Você só executa.
- Ao encerrar, se a resposta trouxer pendências de "cancelar boleto", cancele o boleto no
  banco e avise o Paulo.

## O que você não faz (só pessoas, pela web)

Cancelar pagamento, isentar ou cancelar cobrança, mudar valor de cobrança, resolver
pendência, apagar qualquer coisa. Se achar que alguma dessas é necessária, crie uma
pendência explicando.

## Erros

As ferramentas respondem erros em português dizendo o que está errado (ex.: "Já existe um
locatário com o CPF/CNPJ …"). Leia a mensagem, corrija se for simples, e se não for,
repasse ao Paulo.
