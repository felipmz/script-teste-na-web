# script-teste-na-web

Scripts e guia para medir a velocidade de carregamento de um site, tela a tela, e procurar bugs visuais, usando um navegador real e a Performance API (a mesma base do DevTools e do Lighthouse). Feito para ser rodado por uma pessoa ou por uma IA com acesso a terminal.

Usa o [`@playwright/cli`](https://www.npmjs.com/package/@playwright/cli) (comando `playwright-cli`) com Chromium. Os scripts `.js` rodam dentro do navegador com `run-code`. O `resumir.py` usa só a biblioteca padrão do Python 3.

## O que tem aqui

| Arquivo | Para quê |
|---|---|
| `medir-carga.js` | Carrega cada rota 3 vezes e mede TTFB, FCP, LCP, load, tarefas longas, peso, chamadas de API mais lentas, erros de console e respostas 4xx/5xx. |
| `medir-cliques.js` | Clica em cada item do menu (sem recarregar) e mede o tempo até a URL mudar e até o conteúdo parar de mudar. |
| `prints.js` | Tira prints de cada rota em desktop e celular e checa rolagem horizontal, imagens quebradas e erros de console/página. |
| `resumir.py` | Transforma a saída JSON de `medir-carga.js` e `medir-cliques.js` em tabela de texto. |

## Pré-requisitos

- Node.js e o `@playwright/cli` instalados, com o Chromium baixado (`npm install @playwright/cli` e `npx playwright-cli install-browser`).
- Python 3 (só para o `resumir.py`).
- Um site de teste (demo ou local). **Não rode contra produção** sem autorização de quem responde pelo sistema.

## Como usar

1. Abra o navegador com janela visível (aba em foco, para não distorcer a primeira pintura):

   ```bash
   npx playwright-cli open --headed https://exemplo.com/login
   ```

2. Faça o login você mesmo na janela. Não coloque senha em arquivo, em script nem em commit.

3. Edite o bloco de configuração no começo de cada script: `BASE`, `ROTAS` (ou `ITENS`) e, no `prints.js`, `PASTA`.

4. Rode e salve a saída:

   ```bash
   npx playwright-cli --raw run-code "$(cat medir-carga.js)" > saida.json
   npx playwright-cli --raw run-code "$(cat medir-cliques.js)" > saida-cliques.json
   npx playwright-cli --raw run-code "$(cat prints.js)" > saida-prints.json
   ```

5. Veja o resumo:

   ```bash
   python3 resumir.py saida.json
   python3 resumir.py saida-cliques.json
   ```

6. Feche o navegador: `npx playwright-cli close`.

Ajuda de qualquer comando: `npx playwright-cli --help <comando>`. Se sobrar processo de navegador: `npx playwright-cli kill-all`.

## Como ler os números

- **TTFB**: primeiro byte do HTML. Bom se baixo, mas não diz nada sobre quando a página termina de chegar.
- **FCP / LCP**: primeira pintura e maior elemento visível. É o que a pessoa sente.
- **load**: fim do carregamento. Muito maior que o LCP costuma indicar HTML por streaming que ainda não terminou, ou scripts esperando.
- **Cliques no menu**: em apps de página única a navegação por clique pode ser rápida mesmo quando abrir a URL direto (F5, link externo) é lento. Meça os dois.
- **Carga 1 vs 2 e 3**: a primeira é a mais fria. Diferença grande sugere cache no servidor ou no CDN.
- Para separar rede e servidor, busque a URL isolada com `fetch` dentro de `eval`/`run-code` e compare o primeiro byte com o fim do corpo.

## Limites

- Poucas cargas por tela: telas com pico variam muito de uma rodada para outra. Repita em horários diferentes.
- Ambiente de demo compartilhado muda de carga. Compare sempre sob as mesmas condições.
- Sem throttling de rede/CPU e sem o painel gráfico Performance do DevTools.
- Não testa fluxos de escrita nem telas internas.

## Rodando em sandbox

Se o navegador falhar ao abrir com `socket() failed: Operação não permitida` (ou `listen EPERM`), o ambiente (por exemplo, o sandbox de um agente de IA) está bloqueando a criação de sockets Unix pelo Chromium. Rode o `playwright-cli` fora desse sandbox, com a autorização de quem acompanha. Não adianta o modo headless nem reiniciar a sessão.

## Não suba para o repositório

Saídas das medições, prints, PDFs, estado de login (`state-save`), perfis do navegador e qualquer segredo. O `.gitignore` já cobre esses casos.
