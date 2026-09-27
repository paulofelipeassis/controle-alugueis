# Sugestão de estrutura de pastas para os documentos da imobiliária

> **Para o Hermes:** este documento é uma **sugestão**, não uma ordem. Você já tem uma estrutura de pastas própria, provavelmente parecida com esta. Antes de mover, renomear ou criar qualquer coisa:
>
> 1. Compare esta sugestão com a estrutura que você já usa.
> 2. Onde as duas forem equivalentes, **mantenha a sua**.
> 3. Liste para o Paulo as diferenças que encontrar e **peça a confirmação dele** antes de mudar qualquer coisa.

## Contexto

O sistema de controle de aluguéis está sendo refeito. Ele vai guardar os **dados** (imóveis, locatários, contratos, cobranças, pagamentos), mas **não os arquivos**. Os arquivos (contratos assinados, vistorias, documentos pessoais) ficam nas pastas do servidor, e o sistema guarda apenas o **caminho** de cada arquivo, para poder abri-lo quando alguém pedir.

Por isso a organização das pastas precisa ser **estável e previsível**: tanto o Hermes quanto uma pessoa usando o formulário do sistema (quando o Hermes estiver indisponível) devem salvar o mesmo tipo de arquivo no mesmo lugar, com o mesmo padrão de nome.

## Princípio

- **O que é do imóvel** fica na pasta do imóvel: escritura, IPTU, fotos.
- **O que é da pessoa ou empresa** fica na pasta do locatário: RG, CPF/CNPJ, comprovante de renda.
- **O contrato**, que liga os dois, fica **na pasta do imóvel**.

Assim, uma empresa que aluga três apartamentos tem os documentos dela **em um lugar só**, sem duplicação, e cada apartamento guarda o **histórico dos seus contratos em ordem**.

As outras perguntas ("tudo do locatário X", "contratos de 2026") são respondidas pelo sistema, que liga cada contrato ao seu imóvel e ao seu locatário. A pasta não precisa responder tudo.

## Estrutura sugerida

```
documentos/
  _a-classificar/
  imoveis/
    Anel Viario - Apto 101/
      imovel/
      contratos/
        2025-03 - Maria Souza/
          contrato-assinado.pdf
          vistoria-entrada.pdf
          vistoria-saida.pdf
        2026-10 - Construtora XYZ/
          contrato-assinado.pdf
          vistoria-entrada.pdf
          aditivo-2027-10.pdf
  locatarios/
    12345678900 - Maria Souza/
    12345678000199 - Construtora XYZ/
```

## Regras sugeridas e por quê

| Regra | Por quê |
|---|---|
| Pasta do imóvel: `Grupo - Unidade` (ex.: `Anel Viario - Apto 101`) | É como a família se refere ao imóvel no dia a dia. |
| Pasta do locatário começa pelo **CPF ou CNPJ, só números**, seguido do nome | O documento nunca muda e nunca se repete. O nome pode ser escrito de formas diferentes ("Construtora XYZ", "XYZ Construções"), o que criaria pastas duplicadas. |
| Pasta do contrato começa pelo **mês de início** (`AAAA-MM`) | O histórico do imóvel fica em ordem cronológica automaticamente. |
| Nomes fixos dentro da pasta do contrato: `contrato-assinado.pdf`, `vistoria-entrada.pdf`, `vistoria-saida.pdf`, `aditivo-AAAA-MM.pdf` | Qualquer pessoa (ou o sistema) sabe onde procurar sem abrir arquivo por arquivo. |
| Nomes de pasta **sem acento** | Evita "Anel Viário" e "Anel Viario" virarem duas pastas diferentes para o mesmo imóvel. |
| Documentos do **fiador** ficam na pasta do contrato | O fiador vale apenas para aquele contrato. |
| Arquivo sem destino claro vai para `_a-classificar/` | É melhor uma pessoa decidir depois do que o arquivo ficar no lugar errado. |

## O que cabe em cada pasta

- `imoveis/<imovel>/imovel/`: escritura, matrícula, IPTU, plantas, fotos do imóvel.
- `imoveis/<imovel>/contratos/<contrato>/`: contrato assinado, vistorias de entrada e saída, aditivos, documentos do fiador.
- `locatarios/<CPF ou CNPJ - nome>/`: RG, CPF/CNPJ, comprovante de renda, comprovante de endereço; para empresas, contrato social e documentos do responsável.
- `_a-classificar/`: qualquer arquivo recebido que ainda não foi organizado.

## Observação técnica

Hoje o Hermes guarda arquivos no espaço dele no servidor, e o File Browser pode estar olhando outra pasta física. Quando o sistema novo for instalado, os três (Hermes, File Browser e o sistema) serão configurados para enxergar **a mesma pasta de documentos**. Até lá, a organização pode ser feita normalmente onde o Hermes já trabalha: mudar a pasta de lugar depois não quebra nada.
