"""Resume em tabela a saída de medir-carga.js e de medir-cliques.js.

Uso:
    python3 resumir.py saida.json            # saída de medir-carga.js
    python3 resumir.py saida-cliques.json    # saída de medir-cliques.js

Só usa a biblioteca padrão do Python 3. A saída do `playwright-cli --raw run-code`
é um JSON dentro de uma string, por isso o arquivo é lido em duas etapas.
"""
import json
import sys

if len(sys.argv) != 2:
    sys.exit("Uso: python3 resumir.py <saida.json>")

with open(sys.argv[1], encoding="utf-8") as f:
    dados = json.load(f)
if isinstance(dados, str):
    dados = json.loads(dados)


def mediana(valores):
    v = sorted(valores)
    return v[len(v) // 2]


if dados and "runs" in dados[0]:
    print("tela | TTFB | FCP | LCP | load (carga 1) | LCP mediana | load mediana | req/KB | erros")
    for t in dados:
        r = t["runs"]
        a = r[0]
        erros = len([e for x in r for e in x["errs"] + x["bad"]])
        print(f'{t["nome"]} | {a["ttfb"]} | {a["fcp"]} | {a["lcp"]} | {a["load"]} | '
              f'{mediana([x["lcp"] for x in r])} | {mediana([x["load"] for x in r])} | '
              f'{a["req"]}/{a["kb"]} | {erros}')
elif dados and "estavel" in dados[0]:
    print("tela | passada | url (ms) | estável (ms) | tarefa longa (ms)")
    for x in dados:
        print(f'{x["nome"]} | {x["passada"]} | {x["url"]} | {x["estavel"]} | {x["lt"]}')
else:
    sys.exit("Formato não reconhecido.")
