# Revisão de UX (outubro/2026)

Método: o sistema foi aberto com os dados fictícios (20 imóveis, 15 meses), em celular (390 px) e computador
(1280 px), página por página. Cada achado foi comparado com princípios publicados. O que foi mudado só mexe em
`templates/` e `static/estilo.css` (mais dois filtros de texto em `web_comum.py`): nenhuma regra de negócio.

## O que estava difícil, e o que mudou

| # | Problema encontrado | Princípio | Mudança |
|---|---|---|---|
| 1 | Menu escondido atrás de um botão "Menu" com 12 itens, sem indicar a página atual | NN/g: navegação escondida reduz a descoberta (≈ metade) e piora tempo e sucesso nas tarefas, no celular e mais ainda no computador. Heurísticas de Nielsen nº 1 (visibilidade do estado) e nº 6 (reconhecer em vez de lembrar) | Celular: barra fixa embaixo com Painel, Cobranças, **Lançar**, Contratos e Mais. Computador: links no topo. A página atual fica destacada |
| 2 | Tabelas largas no celular: colunas cortadas, só com rolagem lateral (Valor e Saldo ficavam fora da tela) | WCAG 1.4.10 (reflow) isenta tabelas de dados, mas o uso real no celular pede leitura sem rolagem lateral | No celular cada linha vira um cartão (imóvel como título, rótulo e valor lado a lado). Nenhuma página rola de lado em 320 px (conferido) |
| 3 | Painel: 5 números do mesmo peso, atraso sem destaque, 11 alertas em lista corrida | Heurística nº 8 (minimalista) e hierarquia visual | Faixa vermelha com o total atrasado no topo; cartão do mês com barra de progresso (recebido de devido); ocupação com barra; só 5 alertas, o resto em "ver mais"; telefone do locatário atrasado vira link de ligar |
| 4 | Contraste e cor como único sinal | WCAG 1.4.3 (mínimo 4,5:1) e 1.4.1 (não depender só da cor) | Paleta nova com contraste entre 5,8:1 e 8,8:1 nos selos, 6,7:1 nos botões e links. Selos ganharam um ponto e o texto continua escrito. "⚠️" virou "⚠ prazo vencido" |
| 5 | Formulários longos sem agrupamento; lista de cobranças do lançamento com texto enorme | Rótulos acima do campo: Penzo (2006, rastreamento ocular) e Baymard (testes em celular). Agrupar campos relacionados | Campos agrupados (Quem e onde / Prazo e valor / Condições), "* obrigatório" explicado, campo de busca por imóvel ou locatário no lançamento, resumo do saldo ao escolher a cobrança, itens opcionais recolhidos |
| 6 | Botão "Apagar contrato" solto no fim da ficha, no mesmo estilo dos outros | Heurística nº 5 (prevenção de erros) | Ação destrutiva recolhida em "Cadastrei este contrato por engano", em vermelho, com a explicação do que o sistema permite |
| 7 | Filtros sem estado (qual está ativo?) | Heurística nº 1 | Filtros viraram botões com o ativo marcado; mês e situação filtram ao mudar |
| 8 | Todas as páginas com o mesmo título de aba | WCAG 2.4.2 (página com título) | Título por página ("Contratos · Controle de Aluguéis") |
| 9 | Alvos de toque pequenos, sem foco visível | WCAG 2.5.8 (mínimo 24 px) e 2.4.7 (foco visível); Apple HIG recomenda 44 pt | Botões e itens de menu com 44 px ou mais, anel de foco visível, link "ir para o conteúdo" |

## Segunda rodada: visual moderno e modo escuro

A primeira rodada arrumou navegação e legibilidade, mas manteve o visual padrão do Pico CSS (botões, cores e
tipografia com cara de 2010). Esta rodada troca a camada visual, sem mudar nenhuma página nem regra:

- Tipografia Inter (hospedada no próprio site, sem depender de serviço externo; licença OFL em `static/inter-LICENSE.txt`).
- Paleta índigo com tokens de cor no começo de `estilo.css`: cartões com raio e sombra suaves, botões com peso e estados
  (principal, secundário, contorno, perigo), seletores segmentados nos filtros, tabelas como cartões com cabeçalho discreto.
- Cartão do mês em destaque no painel, barra de navegação flutuante no celular com a ação "Lançar" em evidência.
- Modo escuro: segue o aparelho (`prefers-color-scheme`) e tem botão sol/lua no topo; a escolha fica salva no navegador.
  Os gráficos leem as cores do tema e se redesenham ao alternar. Todos os pares de cor de texto foram conferidos
  com razão de contraste ≥ 4,5:1 nos dois temas (WCAG 1.4.3).

## Fica para decidir (muda comportamento, não só aparência)

- A lista de Cobranças abre com todos os meses (264 no exemplo). Abrir no mês atual seria mais útil.
- A faixa de backup do painel fala em "serviço 'backup'": linguagem técnica para quem usa o painel.
- Data nos formulários usa o formato do navegador do celular (dd/mm/aaaa no Brasil); não há como forçar.
- Pendências poderiam aparecer como número no menu.

## Referências

- NN/g, [Hamburger Menus and Hidden Navigation Hurt UX Metrics](https://www.nngroup.com/articles/hamburger-menus/) (estudo com 179 participantes).
- W3C, [Understanding SC 1.4.10 Reflow](https://www.w3.org/WAI/WCAG21/Understanding/reflow.html) e [SC 2.5.8 Target Size (Minimum)](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html).
- Baymard, [Field Label UX: Place Labels Above the Field](https://baymard.com/blog/mobile-form-usability-label-position).
- Penzo, M. (2006), [Label Placement in Forms](https://www.uxmatters.com/mt/archives/2006/07/label-placement-in-forms.php), UXmatters.
- Nielsen, J., [10 Usability Heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/).
