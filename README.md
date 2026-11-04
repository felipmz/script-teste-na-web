# script-teste-na-web

Testes básicos para sites web, feitos para rodar por uma pessoa (com um menu no terminal) **ou por uma IA** (por linha de comando, com saída em JSON e código de saída):

1. **Segurança e validação de rotas** (`testar.py`): rotas internas sem login, arquivos sensíveis, cabeçalhos e CSP, CORS, cookies, segredos e source maps no JavaScript, APIs, redirecionamento aberto, IDs e parâmetros inválidos. Só leitura.
2. **Velocidade de carregamento e bugs visuais** (`medir-carga.js`, `medir-cliques.js`, `prints.js`), com Playwright e a Performance API do navegador.

A ideia é ir adicionando testes básicos aqui aos poucos. Os de segurança são só Python 3 (biblioteca padrão), sem instalar nada.

## Aviso

Use **somente em sistemas seus ou com autorização de quem responde por eles**. Os testes só leem (GET e OPTIONS) e não fazem força bruta, mas geram dezenas de requisições. Muitos serviços (Vercel, Cloudflare etc.) bloqueiam IPs que mandam muitas requisições seguidas. O script detecta o bloqueio, **para** e avisa. Não tente contorná-lo.

## Início rápido

```bash
cp config.exemplo.json config.json     # edite com as rotas do seu sistema (config.json não vai para o git)
python3 testar.py                       # abre o menu
```

O menu:

```
=== script-teste-na-web 0.1.0 ===   Alvo: https://exemplo.com
  [ 1] Rotas internas sem login
  [ 2] Arquivos sensíveis e documentação exposta
  ...
  [10] IDs inválidos nas rotas de detalhe  (com sessão)
  [t] rodar todos   [s] só os que não precisam de login
  [a] trocar o alvo   [q] sair
Escolha (ex.: 1,3,5):
```

Sem menu (para scripts e IA):

```bash
python3 testar.py --listar                                          # lista os testes
python3 testar.py --url https://exemplo.com --sem-login --sim       # testes que não precisam de login
python3 testar.py --url https://exemplo.com --testes 1,3,cors --sim
python3 testar.py --url https://exemplo.com --todos --sim --json -  # tudo, resultado em JSON na saída
```

| Opção | O que faz |
|---|---|
| `--url` | URL base. Se faltar, vale `base_url` do `config.json` ou o menu pergunta. |
| `--testes 1,3,cors` | Roda só esses (número ou nome, veja `--listar`). |
| `--todos` / `--sem-login` | Roda todos / só os que não precisam de sessão. |
| `--sim` | Confirma que você tem autorização para testar o alvo (sem isso, só no menu interativo). |
| `--json ARQ` | Grava o resultado em JSON (`-` imprime na saída). Não contém valores sensíveis. |
| `--pausa 1.5` | Segundos entre requisições (padrão 0.4). Aumente se o alvo bloquear. |
| `--config ARQ` | Outro arquivo de configuração. |
| `--sem-cor` | Sem cores no terminal. |

Código de saída: `0` sem falhas, `1` com pelo menos uma `[FALHA]`, `2` cancelado ou sem autorização, `3` alvo bloqueou as requisições.

## Testes disponíveis

| # | Nome | O que verifica |
|---|---|---|
| 1 | `rotas-protegidas` | Rotas internas sem login devem redirecionar ao login ou dar 401/403. |
| 2 | `arquivos-sensiveis` | `.env`, `.git`, `package.json`, backups, Swagger e debug. Confere o conteúdo, para não confundir com página que responde 200 para tudo. O conteúdo nunca é exibido. |
| 3 | `cabecalhos` | HSTS, CSP (e fraquezas dela), clickjacking, nosniff, Referrer-Policy, `X-Powered-By`, versão no `Server`. |
| 4 | `cors` | Se o servidor aceita uma origem hostil (principalmente com credenciais). |
| 5 | `cookies` | `Secure`, `HttpOnly` e `SameSite` dos cookies das páginas públicas. |
| 6 | `bundles` | Segredos, JWT `service_role` e source maps no JavaScript público. Mostra só o nome do arquivo, nunca o valor. |
| 7 | `api-sem-login` | APIs protegidas não podem responder 200 sem login. |
| 8 | `api-publicas` | O que as APIs públicas (ex.: `/api/health`) revelam, como versão do build. |
| 9 | `open-redirect` | Parâmetros de retorno (`next`, `redirect`...) não podem levar para fora do site. |
| 10 | `ids-invalidos` | **Com sessão.** IDs fora do formato (`abc`, `-1`, aspas, SQL, HTML, `..%2F`, `%00`, 600 caracteres) nas rotas de detalhe: não pode haver 5xx, vazamento de SQL ou stack, nem 200 com tela de erro. |
| 11 | `parametros` | **Com sessão.** `page=-1`, `limit=100000`, aspas, `' OR 1=1--` e `"><zzmark>` nas listagens: sem 5xx, vazamento nem reflexão sem escape (XSS). |

Níveis: `[OK]`, `[ALERTA]` (confira), `[FALHA]` (problema provável), `[INFO]` e `[PULADO]`.

## Configuração (`config.json`)

Copie `config.exemplo.json`. Campos (todos opcionais, o resto usa padrões):

| Campo | Para quê |
|---|---|
| `base_url` | URL do sistema. |
| `rotas_protegidas` | Telas internas que exigem login. |
| `api_protegidas` / `api_publicas` | APIs que exigem login / que são públicas. |
| `paginas_publicas` | Páginas sem login (a primeira também é usada na checagem de bloqueio). |
| `rotas_com_id` | Rotas de detalhe com `{id}`, ex.: `/dashboard/itens/{id}`. |
| `rotas_lista` | Listagens para testar parâmetros, ex.: `/dashboard/itens`. |
| `rota_login` | Para o teste de redirecionamento aberto. |
| `marcadores_erro` | Textos que indicam tela de erro (para achar "200 com erro"). |

## Testes com sessão (10 e 11)

Precisam de um usuário logado. Defina o cookie de sessão **só na memória**, nunca em arquivo:

```bash
SESSAO_COOKIE='nome=valor; outro=valor' python3 testar.py --testes 10,11 --sim
```

No menu, o script pede o cookie (a digitação fica oculta). Para pegar o valor: DevTools > Network > clique numa requisição > header `Cookie`. O cookie só é enviado ao host do alvo e nunca é gravado nem impresso. Use uma conta de teste.

## Uso por IA

O `testar.py` foi feito para a IA rodar sem terminal interativo:

- Rode sempre com `--json -` (ou `--json arquivo`) e leia os achados `FALHA` e `ALERTA`. Cada achado tem `nivel` e `msg`.
- **`--sim` é a autorização do dev.** A IA só deve passar `--sim` quando a pessoa que a opera disse que pode testar aquele alvo.
- Comece por `--sem-login`. Para os testes de sessão, a pessoa fornece o cookie via `SESSAO_COOKIE`. A IA não deve procurar credenciais por conta própria nem gravar o cookie em arquivo, relatório ou commit.
- Se o código de saída for `3` (ou `bloqueado: true` no JSON), **pare**. Não contorne WAF nem desafio de bot (troca de User-Agent, IP, etc.). Avise a pessoa e, se ela quiser, rode de novo mais devagar com `--pausa`.
- Não confie em resultado de um teste quando houver bloqueio: o script interrompe para não dar `OK` falso.
- Para ter só o que mudou entre rodadas, salve o JSON e compare.
- Se rodar dentro de um sandbox sem rede liberada, libere o host alvo ou rode fora dele, com aprovação de quem acompanha.

## Como adicionar um teste

Em `testar.py`, escreva uma função com o decorador `@teste` e devolva uma lista de achados. O menu, `--listar`, `--testes` e `--todos` passam a incluí-la sozinhos:

```python
@teste("meu-teste", "O que ele verifica", sessao=False)
def t_meu_teste(c):
    r = c.get("/alguma-rota")                 # c.get usa a base_url e conta bloqueios
    if r.status == 200:
        return [falha("a rota respondeu 200 sem login")]
    return [ok("a rota está protegida")]      # também: alerta(), info(), pulado()
```

Use `c.get(caminho, auth=True)` para enviar a sessão. Nunca imprima valores de segredos, tokens ou cookies nos achados.

## Velocidade e bugs visuais (Playwright)

Ainda não estão no menu; rodam à mão. Usam o [`@playwright/cli`](https://www.npmjs.com/package/@playwright/cli) (`npm install @playwright/cli` e `npx playwright-cli install-browser`).

| Arquivo | Para quê |
|---|---|
| `medir-carga.js` | Carrega cada rota 3 vezes e mede TTFB, FCP, LCP, load, tarefas longas, peso e chamadas de API mais lentas. |
| `medir-cliques.js` | Clica em cada item do menu (sem recarregar) e mede até a URL mudar e até o conteúdo estabilizar. |
| `prints.js` | Prints de cada rota em desktop e celular, com checagem de rolagem horizontal, imagens quebradas e erros de console. |
| `resumir.py` | Transforma a saída JSON de `medir-carga.js` e `medir-cliques.js` em tabela. |

```bash
npx playwright-cli open --headed https://exemplo.com/login     # faça o login você mesmo na janela
# edite BASE e ROTAS no começo do script, depois:
npx playwright-cli --raw run-code "$(cat medir-carga.js)" > saida.json
python3 resumir.py saida.json
npx playwright-cli close
```

Como ler: **TTFB** baixo não garante página rápida; **LCP** é o que a pessoa sente; **load** muito maior que o LCP costuma indicar HTML por streaming ainda chegando. Em apps de página única, navegar por clique pode ser rápido mesmo quando abrir a URL direto (F5) é lento: meça os dois. Compare a carga 1 (fria) com as 2 e 3.

**Sandbox:** se o Chromium falhar com `socket() failed: Operação não permitida` (ou `listen EPERM`), o ambiente bloqueia sockets Unix. Rode o `playwright-cli` fora desse sandbox, com a autorização de quem acompanha. Não adianta o modo headless nem reiniciar a sessão.

## Limites

- Teste de caixa-preta: ausência de achado não prova ausência de falha.
- **Não testa** IDOR entre contas, permissões por papel, RLS do banco, server actions, webhooks, uploads, SSRF nem limite de tentativas no login. Esses dependem de mais de um usuário, do código ou do banco.
- Os testes olham só o que dá para ver por fora, e o JavaScript analisado é o das páginas públicas.
- Medições de velocidade têm poucas amostras e variam com o horário e a carga do alvo.

## Não suba para o repositório

`config.json`, saídas de medição, prints, PDFs, estado de login, perfis do navegador e qualquer segredo. O `.gitignore` já cobre esses casos.
