# Regras de negócio — sistema novo

Este documento registra **o que foi decidido** com o Paulo para o sistema novo, e por quê.
O **como construir** está em [`plano-de-implementacao.md`](plano-de-implementacao.md).

> **Para quem for implementar:** estas decisões já foram discutidas e aprovadas. Não
> reabra nenhuma delas por conta própria. Se algo aqui parecer errado ou faltar, pare e
> pergunte ao Paulo antes de mudar.

## 1. Contexto

- Negócio familiar de aluguel (da mãe do Paulo): **até 20 imóveis**, **até 3 usuários**,
  todos com acesso total. Raramente mais de um usuário ao mesmo tempo.
- Hoje: app Streamlit + Google Sheets, hospedado no Streamlit Cloud. Ele **continua
  funcionando** até o sistema novo estar pronto e testado.
- Novo: servidor próprio (VPS Hostinger KVM 2, Ubuntu 24.04, Docker, Traefik já instalado),
  domínio próprio (ainda vai ser registrado na Hostinger) e o **Hermes Agent** (agente de IA
  da Nous Research) rodando no mesmo servidor.
- O banco começa **do zero**. O Hermes recadastra imóveis, locatários e contratos. Não há
  migração da planilha.

## 2. Princípios (valem para tudo)

1. **O sistema é a fonte da verdade do que é devido. O banco é a fonte da verdade do que foi
   pago. O Hermes é o mensageiro: não decide, executa e registra.**
2. **Simples antes de tudo.** Sem exagero em prevenção de erros ou segurança. É um negócio
   pequeno com 3 usuários de confiança. Na dúvida, a solução com menos código.
3. **Uma função para cada operação, usada por todos.** As páginas web e o Hermes chamam as
   **mesmas** funções de serviço. Nenhuma regra de negócio fica duplicada em página ou em
   ferramenta do Hermes.
4. **O Hermes é a interface principal, mas tudo pode ser feito à mão.** Toda operação que o
   Hermes faz também tem formulário na web (redundância para quando o Hermes estiver fora do
   ar ou errar).
5. **Nada é apagado depois que tem história.** Contratos são encerrados, cobranças são
   canceladas ou isentadas, pagamentos são cancelados, sempre com motivo. Só se apaga
   cadastro que não está ligado a nada.
6. **Status são calculados, não digitados.** "Alugado/Vago", "Ativo/Encerrado",
   "Paga/Em aberto/Atrasada" saem dos dados. Assim nunca ficam dessincronizados (problema
   real da versão com planilha).
7. **Tudo que alguém ou o Hermes grava fica na auditoria:** quem, quando e o quê.

## 3. Cadastros

### Imóvel
Grupo (ex.: "Anel Viário"), unidade (ex.: "Apto 101"), endereço, IPTU anual, nº do medidor
Saneago, nº do medidor Enel, observações, e uma marcação **"em manutenção"**.

- Grupo + unidade não se repetem, **nem com outra grafia** ("Anel Viário" e "Anel Viario", maiúsculas
  e espaços a mais contam como o mesmo imóvel): as pastas de documentos usam o nome sem acento e se
  misturariam.
- Situação calculada: **Alugado** se tem contrato ativo; senão **Em manutenção** se marcado;
  senão **Vago**.

### Locatário (novo — antes os dados ficavam dentro do contrato)
Nome, **CPF ou CNPJ** (só números, 11 ou 14 dígitos, não se repete), telefone, **e-mail
(obrigatório, porque os boletos são enviados por e-mail)**, observações.

- Um locatário pode ter vários contratos (ex.: uma construtora que aluga 3 apartamentos).
- Não se valida dígito verificador do CPF/CNPJ (decisão de simplicidade).

### Corretor (substitui o antigo "Gestor")
Nome, telefone, e-mail, observações. É quem intermediou o contrato, faz a cobrança e responde
por falhas do contrato. Contrato pode ter corretor ou não.

- **Pendente:** comissão do corretor. O Paulo está confirmando como funciona. **Não
  implementar nada de comissão** até ele definir.

### Usuário
Login próprio para cada pessoa (nome, login, senha). Todos com acesso total. Sem níveis de
permissão. Depois de 5 senhas erradas seguidas no mesmo login, o login fica bloqueado por 15
minutos. Senha esquecida: quem cuida do servidor troca pelo terminal (`docs/instalacao-servidor.md`).

## 4. Contrato

Liga **um imóvel** a **um locatário** (e opcionalmente um corretor). Campos:

- data de início, **data de fim prevista**, data de encerramento (vazia enquanto ativo);
- **dia de vencimento** (1 a 31);
- **multa por atraso** (padrão 2%) e **juros ao mês** (padrão 1%);
- garantia: tipo (caução, fiador, seguro-fiança, nenhuma) e valor; dados do fiador em texto;
- índice de reajuste (IGP-M, IPCA, outro);
- observações;
- **valor do aluguel com histórico**: cada reajuste é um novo valor com "vigente desde".
  O valor antigo nunca é sobrescrito (na versão com planilha o reajuste apagava o valor
  anterior).

Regras:

- **Um imóvel só pode ter um contrato ativo** por vez.
- **Ativo** = sem data de encerramento. **Encerrado** = com data de encerramento.
- Passou a data de fim prevista e ninguém encerrou: o contrato **continua ativo e gerando
  cobranças**, e aparece um alerta "prazo vencido: renovar ou encerrar". Isso segue a lei:
  locação residencial que passa do prazo sem oposição fica prorrogada por prazo
  indeterminado (Lei 8.245/1991, arts. 46 §1º, 47 e 56, parágrafo único).
- **Renovar** = mudar a data de fim prevista do **mesmo** contrato (e, se houver, registrar
  novo valor). Não se cria contrato novo para renovação.
- **Reajuste anual: o sistema sugere, uma pessoa registra** (decisão do Paulo, 27/09/2026):
  - O próximo reajuste é **12 meses depois do último valor** (a lei proíbe periodicidade menor
    que 1 ano: Lei 10.192/2001, art. 2º §1º). Até 30 dias antes, aparece o alerta.
  - Para **IPCA** e **IGP-M**, ao abrir "Calcular reajuste" no contrato (ou pelo Hermes), o
    sistema busca **naquele momento** as **últimas 12 variações publicadas** no Banco Central
    e sugere o novo valor. Não precisa bater exatamente com o mês do aniversário. Não há busca
    diária nem cópia dos índices no banco.
  - **Índice acumulado negativo ou zero: o valor se mantém.**
  - **Nada muda sem uma pessoa registrar.** Dá para trocar o valor por um combinado, ou
    registrar o mesmo valor para não reajustar naquele ano.
  - **O 13º boleto tem que sair reajustado:** as cobranças que vencem a partir do aniversário
    ficam marcadas "reajuste pendente" até o reajuste do ano ser registrado, e o Hermes não
    emite boleto delas antes disso.
  - Outro índice (ex.: INPC) ou Banco Central fora do ar: registrar o valor à mão.
  - O cálculo pelo índice é um **módulo opcional** (`sistema/modulos/reajuste/`). O alerta, a
    marcação do 13º boleto e o registro do reajuste são do núcleo.
- **Contrato que já existia antes do sistema:** é cadastrado com a **data de início
  verdadeira** e o **valor atual**, mais a **data desde quando vale o valor atual** (data do
  último reajuste). Esta última é obrigatória se o contrato começou há mais de 1 ano, porque é
  dela que sai o próximo reajuste. Não são geradas cobranças de meses anteriores a
  `INICIO_COBRANCAS`, então não aparecem dívidas antigas.
- **Encerrar** = informar data e motivo. As cobranças com vencimento depois do encerramento
  e sem pagamento são canceladas. Se alguma já tinha boleto emitido, o sistema cria uma
  **pendência** "cancelar boleto no banco". Dívidas anteriores continuam em aberto.
- **Reabrir** um contrato encerrado por engano (ou com a data errada): só pessoas, pela web, com
  motivo. O contrato volta a ficar ativo e as cobranças que o encerramento cancelou voltam a valer;
  as que tinham boleto viram pendência ("o boleto pode ter sido cancelado no banco"). Não reabre se
  o imóvel já tem outro contrato ativo.
- A **data de fim prevista** pode ser corrigida a qualquer momento (para mais ou para menos). Início,
  dia de vencimento e valor não se corrigem: se foram cadastrados errados e ainda não há pagamento
  nem boleto, apaga-se o contrato e cadastra-se de novo.
- Contrato cadastrado por engano pode ser apagado **só se** não tiver nenhum pagamento nem
  boleto.

## 5. Cobranças

Cobrança = o aluguel devido de um contrato em um mês. **Todo pagamento pertence a uma
cobrança.** Essa é a peça central do sistema novo (na planilha, o pagamento era solto e o
"mês de referência" era texto livre).

- **Competência** = mês do vencimento. "A cobrança de outubro é a que vence em outubro."
- **Vencimento** = dia de vencimento do contrato naquele mês. Se o mês não tem esse dia
  (29, 30, 31), vence no **último dia do mês**.
- **Vencimento em dia sem expediente bancário** (sábado, domingo, feriado nacional, Carnaval,
  Sexta-feira Santa, Corpus Christi, e os dias de `FERIADOS_EXTRAS`): o locatário pode pagar até o
  **primeiro dia útil seguinte** sem multa nem juros. A cobrança só fica atrasada, e a multa e os
  juros só contam, a partir daí. Base: regra dos boletos bancários e Código Civil, art. 132, §1º
  ("se o dia do vencimento cair em feriado, considerar-se-á prorrogado o prazo até o seguinte dia
  útil"). Sem isso, o boleto pago na segunda-feira de um vencimento de sábado apareceria como
  atrasado e geraria pendência falsa. Feriados municipais (ex.: 24/10 em Goiânia) entram em
  `FERIADOS_EXTRAS`.
- **Primeira cobrança** = o primeiro vencimento **a partir da data de início** do contrato.
- **Início das cobranças no sistema:** parâmetro `INICIO_COBRANCAS` (combinado: outubro de
  2026, `2026-10`). Nenhuma cobrança é gerada antes disso. Se o sistema entrar no ar mais
  tarde, o Paulo define o novo valor na hora (para não gerar como "atrasadas" cobranças que
  já foram pagas pelo sistema antigo).
- **Geração automática e idempotente:** o sistema gera as cobranças que faltam para todo
  contrato, até 30 dias à frente. Rodar a geração duas vezes não duplica nada (um contrato
  só tem uma cobrança por competência).
- **Valor** = valor do aluguel vigente na data do vencimento. Pode ser editado à mão
  (ex.: primeiro mês proporcional, desconto combinado) enquanto não tiver boleto nem
  pagamento. O sistema **não** calcula proporcional sozinho.
- Reajuste registrado atualiza o valor das cobranças futuras que ainda não têm boleto nem
  pagamento.
- **Isentar** ou **cancelar** uma cobrança: só por uma pessoa (web), com motivo, e só se não
  tiver pagamento. Se tiver boleto, gera pendência "cancelar boleto no banco".
- Situação calculada (para cobranças não canceladas/isentas):
  - **Paga**: soma dos pagamentos válidos ≥ valor da cobrança;
  - **Parcial**: pagou alguma coisa, mas menos que o valor;
  - **Em aberto**: nada pago e vencimento hoje ou no futuro;
  - **Atrasada**: saldo > 0 e vencimento já passou.
- **Pagamento parcial** mantém o saldo na mesma cobrança. O saldo **não** é somado
  automaticamente ao boleto do mês seguinte.
- **Valor atualizado de cobrança atrasada** (para mostrar e para conferir pagamento):
  multa = valor × multa%; juros = valor × juros% × dias de atraso ÷ 30.

## 6. Boletos (via Hermes e API do banco)

- Banco atual: **Caixa**. Pode mudar. Por isso os campos do boleto são genéricos: banco,
  identificador (nosso número), linha digitável, link do PDF, emitido em, enviado em.
- Fluxo: o Hermes pergunta ao sistema quais cobranças estão sem boleto → emite o boleto na
  API do banco (com multa e juros do contrato) → registra o boleto na cobrança → envia por
  e-mail ao locatário → marca como enviado.
- Um boleto por cobrança. Segunda via / reemissão: registrar de novo com "substituir"; o
  identificador antigo fica na auditoria. **O boleto antigo continua pagável no banco**: se o banco
  informar o pagamento dele, o sistema reconhece a cobrança pela auditoria e dá a baixa normalmente.
- **Baixa:** o Hermes confere o banco **todo dia** (ou recebe aviso do banco, se a API
  oferecer) e registra o pagamento **pelo identificador do boleto**.
- **Idempotente:** registrar o mesmo pagamento duas vezes não duplica (o identificador
  externo de um pagamento válido não se repete). Isso protege contra o Hermes repetir uma
  ação.

## 7. Pagamentos

Data do pagamento, valor pago, forma (boleto, PIX, transferência, dinheiro, outro),
identificador externo (nosso número do boleto ou código da transação PIX, opcional),
caminho do comprovante (opcional), observação, quem registrou e quando.

- Pagamento manual (web ou Hermes lendo um comprovante): escolhe-se **o contrato e depois a
  cobrança** em aberto. Isso corrige o erro da versão atual, que escolhia o contrato pelo
  nome do locatário e errava quando a pessoa tinha dois contratos.
- **Cancelar pagamento:** só uma pessoa (web), com motivo. O pagamento continua guardado,
  marcado como cancelado.
- O pagamento **sempre é registrado** (o dinheiro entrou), mas vira **pendência** para uma
  pessoa conferir quando:
  - o valor não bate com o esperado (diferença maior que R$ 1,00 do valor, ou do valor
    atualizado se atrasado);
  - a cobrança já estava paga (possível duplicidade);
  - o pagamento é **depois** da data de encerramento do contrato (dívida paga por quem já saiu). Pagar
    antes ou na própria data de encerramento, inclusive com o encerramento registrado com antecedência,
    não gera pendência.
- Boleto pago que o sistema não conhece (identificador não encontrado): **não** registra
  pagamento, cria pendência "boleto desconhecido".
- Boleto pago de uma cobrança já **isentada ou cancelada** (o banco não cancelou o boleto e o locatário
  pagou): o pagamento não entra na cobrança, mas o dinheiro **não se perde**: vira pendência
  "pagamento sem cobrança", para uma pessoa decidir entre devolver ou reativar. Repetir a baixa não
  cria outra pendência.
- Reajuste registrado depois de o boleto já ter sido emitido com o valor antigo: pendência
  "boleto com valor antigo" (segunda via com o valor novo, ou cobrar a diferença depois).

## 8. Pendências

Lista de coisas que **uma pessoa precisa olhar**. Criadas automaticamente pelas regras acima
ou pelo Hermes (ex.: "comprovante ilegível"). Resolvidas por uma pessoa na web, com um texto
dizendo o que foi feito. Aparecem em destaque no painel.

## 9. Documentos

- O sistema **não guarda arquivos dentro do banco**. Os arquivos (contratos assinados,
  vistorias, RG etc.) ficam numa **pasta de documentos** do servidor, compartilhada entre o
  sistema, o Hermes e o File Browser. O banco guarda só o **caminho** de cada arquivo, ligado
  a um imóvel, locatário ou contrato.
- Convenção de pastas: [`estrutura-de-pastas.md`](estrutura-de-pastas.md). O **sistema** é
  dono da convenção: ele calcula a pasta certa de cada documento e o Hermes pergunta ao
  sistema onde salvar.
- Upload também pela web (redundância).
- É um **módulo opcional** (`sistema/modulos/documentos/`): pode ser removido sem afetar o
  resto. Os comprovantes de pagamento não dependem dele (ficam no próprio pagamento).
- A convenção foi enviada ao Hermes **como sugestão**: ele deve comparar com a estrutura
  que já usa e confirmar diferenças com o Paulo. Não dar ordens ao Hermes sobre isso.

## 10. Relatórios e consultas

Os mesmos para a web e para o Hermes:

- **Painel:** imóveis alugados/vagos/em manutenção e ocupação; resumo do mês (devido,
  recebido, falta receber); cobranças atrasadas (**de qualquer mês**, não só do atual, outro
  erro da versão atual); alertas; pendências abertas.
- **Alertas:** contratos com fim previsto nos próximos 60 dias; contratos com prazo vencido
  (renovar ou encerrar); reajustes devidos nos próximos 30 dias ou já vencidos; cobranças
  que vencem em até 10 dias sem boleto; boletos emitidos e não enviados.
- **Inadimplentes:** por locatário/contrato, total em atraso e valor atualizado.
- **Extrato do contrato:** todas as cobranças com valor, pagamentos, saldo, situação e boleto.
- **Ficha do locatário:** dados, todos os contratos (atuais e antigos), total em aberto,
  documentos. Serve para consultar o histórico de um locatário anterior.
- **Ficha do imóvel:** dados, situação, contrato atual, histórico de contratos, documentos.
- **Histórico financeiro:** pagamentos válidos filtrados por período, grupo, imóvel ou
  locatário, com total.

## 11. Integração com o Hermes (a maior preocupação do projeto)

- O Hermes **nunca** acessa o banco diretamente. Ele usa um **servidor MCP** do sistema, com
  ferramentas **estreitas** (cada uma faz uma coisa só, com regras aplicadas pelo sistema).
- O que o Hermes **pode**: consultar tudo; cadastrar imóvel, locatário, corretor e contrato;
  registrar reajuste, renovação e encerramento; calcular a sugestão de reajuste; registrar boleto e envio; registrar
  pagamento; anexar documento; criar pendência.
- O que o Hermes **não pode** (só pessoas, pela web): cancelar pagamento, isentar ou
  cancelar cobrança, editar valor de cobrança, resolver pendência, apagar qualquer coisa,
  gerenciar usuários.
- Toda ação do Hermes fica na auditoria com autor `hermes`.
- Mensagens de erro das ferramentas em português claro, dizendo o que fazer (o Hermes lê e
  repassa).

## 12. Backup

Diário, para o **Google Drive**, com o banco e a pasta de documentos. Roda no servidor,
**independente do Hermes**. Mantém pelo menos as últimas 14 cópias. Faz um backup também ao ligar
seu servidor, se o último completo tem mais de 20 horas.

O **painel avisa** (módulo opcional `backup`): faixa vermelha se o backup falhou ou está parado há
mais de 36 horas (ninguém lê o log do servidor), faixa amarela se o Drive não está configurado, e uma
linha discreta com a data do último backup quando está tudo certo. Backup que nunca foi restaurado
não vale: o procedimento de restauração está em `docs/instalacao-servidor.md` e foi testado.

## 12b. Mudanças futuras no banco

O sistema guarda a versão do schema. Toda mudança depois de haver dados reais entra como uma
**migração** numerada (`sistema/db.py`, lista `MIGRACOES`), aplicada uma única vez, com cópia do
banco antes. Nunca se edita uma migração já publicada.

## 13. Fora do escopo (não fazer)

Recibo, despesas do imóvel, portal do locatário, contabilidade/imposto, comissão do corretor
(até o Paulo definir), níveis de permissão, app de celular, migração dos dados da planilha.

## 14. Glossário

| Termo | Significado |
|---|---|
| Competência | Mês da cobrança, no formato `AAAA-MM`. É o mês do vencimento. |
| Cobrança | O aluguel devido de um contrato em uma competência. |
| Saldo | Valor da cobrança menos a soma dos pagamentos válidos. |
| Pendência | Algo que uma pessoa precisa conferir ou resolver. |
| Identificador externo | Nosso número do boleto ou código da transação PIX. |
