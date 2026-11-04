#!/usr/bin/env python3
"""Testes básicos de segurança e validação de rotas para sites web (somente leitura).

Uso interativo (menu):   python3 testar.py
Uso direto:              python3 testar.py --url https://exemplo.com --testes 1,3,5 --sim
Rodar tudo:              python3 testar.py --url https://exemplo.com --todos --sim
Listar os testes:        python3 testar.py --listar

Só usa a biblioteca padrão do Python 3. Veja o README para a configuração.
Use somente em sistemas seus ou com autorização de quem responde por eles.

Para adicionar um teste: escreva uma função com o decorador @teste(...) e devolva
uma lista de achados (nivel, mensagem) usando ok(), alerta(), falha(), info().
"""
import argparse
import base64
import getpass
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import namedtuple

VERSAO = "0.1.0"
UA = f"script-teste-na-web/{VERSAO} (verificacao-basica; somente-leitura)"
AQUI = os.path.dirname(os.path.abspath(__file__))
PAUSA = 0.4  # segundos entre requisições (padrão lento, para não disparar WAF nem sobrecarregar o alvo)
EVIL = "https://evil.example"

CORES = {"OK": "32", "ALERTA": "33", "FALHA": "31", "INFO": "36", "PULADO": "90"}
USAR_COR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

PADRAO = {
    "base_url": "",
    "rotas_protegidas": ["/dashboard", "/admin", "/painel", "/conta"],
    "api_protegidas": ["/api/me", "/api/users"],
    "api_publicas": ["/api/health"],
    "paginas_publicas": ["/", "/login"],
    "rotas_com_id": [],
    "rotas_lista": [],
    "rota_login": "/login",
    "marcadores_erro": ["Algo deu errado", "Application error", "Internal Server Error",
                        "Something went wrong", "Unhandled Runtime Error"],
}

# ---------------------------------------------------------------- achados
Achado = namedtuple("Achado", "nivel msg")


def ok(m): return Achado("OK", m)
def alerta(m): return Achado("ALERTA", m)
def falha(m): return Achado("FALHA", m)
def info(m): return Achado("INFO", m)
def pulado(m): return Achado("PULADO", m)


# ---------------------------------------------------------------- HTTP
R = namedtuple("R", "status headers cookies corpo url erro")


class _SemRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_ABRE_SEM = urllib.request.build_opener(_SemRedirect)
_ABRE_COM = urllib.request.build_opener()


def http(url, metodo="GET", headers=None, seguir=False, timeout=20, limite=2_000_000, cookie=None):
    """Faz uma requisição e devolve R. Nunca levanta exceção de rede."""
    time.sleep(PAUSA)
    h = {"User-Agent": UA, "Accept": "*/*"}
    h.update(headers or {})
    if cookie:
        h["Cookie"] = cookie
    rq = urllib.request.Request(url, method=metodo, headers=h)
    try:
        r = (_ABRE_COM if seguir else _ABRE_SEM).open(rq, timeout=timeout)
    except urllib.error.HTTPError as e:
        r = e
    except Exception as e:  # rede, DNS, TLS, timeout
        return R(0, {}, [], b"", url, str(e)[:80])
    try:
        corpo = r.read(limite) if metodo != "HEAD" else b""
    except Exception:
        corpo = b""
    hd = {k.lower(): v for k, v in r.headers.items()}
    cookies = r.headers.get_all("Set-Cookie") or []
    status = getattr(r, "status", None) or getattr(r, "code", 0)
    return R(status, hd, cookies, corpo, r.geturl(), None)


def texto(r):
    return r.corpo.decode("utf-8", "replace")


def eh_bloqueio(r):
    """True se a resposta é um bloqueio do alvo (WAF, desafio de bot, rate limit), não uma resposta real."""
    if r.status == 429 or "x-vercel-mitigated" in r.headers or "cf-mitigated" in r.headers:
        return True
    if r.status in (403, 503):
        t = texto(r)[:3000]
        return any(s in t for s in ("Security Checkpoint", "Just a moment", "Attention Required",
                                    "Access denied", "captcha", "challenge"))
    return False


class Bloqueado(Exception):
    """O alvo respondeu várias vezes com bloqueio (WAF, desafio, rate limit)."""


class Ctx:
    """Estado compartilhado entre os testes."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.base = cfg["base_url"].rstrip("/")
        self.host = urllib.parse.urlparse(self.base).netloc
        self.sessao = None  # None = ainda não perguntou; "" = sem sessão
        self.bloqueios = 0  # quantas respostas foram bloqueio do alvo

    def url(self, caminho):
        return self.base + (caminho if caminho.startswith("/") else "/" + caminho)

    def fetch(self, url, auth=False, **kw):
        cookie = self.sessao if (auth and self.sessao) else None
        r = http(url, cookie=cookie, **kw)
        if eh_bloqueio(r):
            self.bloqueios += 1
            if self.bloqueios >= 3:  # para de insistir num alvo que está bloqueando
                raise Bloqueado()
        return r

    def get(self, caminho, auth=False, **kw):
        return self.fetch(self.url(caminho), auth=auth, **kw)


# ---------------------------------------------------------------- registro
TESTES = []  # (id, slug, nome, precisa_sessao, funcao)


def teste(slug, nome, sessao=False):
    def deco(f):
        TESTES.append((len(TESTES) + 1, slug, nome, sessao, f))
        return f
    return deco


LOGIN_RE = re.compile(r"(login|signin|sign-in|entrar|auth|sso|session)", re.I)
VAZA_RE = re.compile(
    r"(stack ?trace|\bat [\w.<>$]+ \([^)]*:\d+:\d+\)|ECONNREFUSED|PGRST\d+|SQLSTATE|"
    r"invalid input syntax|syntax error at or near|duplicate key value|"
    r"relation \"[^\"]+\" does not exist|pg_catalog|Traceback \(most recent call last\)|"
    r"ORA-\d{5}|You have an error in your SQL syntax)", re.I)


# ---------------------------------------------------------------- 1. rotas protegidas
@teste("rotas-protegidas", "Rotas internas sem login")
def t_rotas_protegidas(c):
    out = []
    for p in c.cfg["rotas_protegidas"]:
        r = c.get(p)
        loc = r.headers.get("location", "")
        if r.erro:
            out.append(info(f"{p}: sem resposta ({r.erro})"))
        elif r.status in (301, 302, 303, 307, 308) and LOGIN_RE.search(loc):
            out.append(ok(f"{p}: redireciona para o login ({r.status})"))
        elif r.status in (401, 403):
            out.append(ok(f"{p}: {r.status}"))
        elif r.status in (301, 302, 303, 307, 308):
            out.append(alerta(f"{p}: redireciona ({r.status}) para {loc[:60]}, confirme se é o login"))
        elif r.status == 404:
            out.append(info(f"{p}: 404 (rota não existe)"))
        elif r.status >= 500:
            out.append(falha(f"{p}: erro {r.status} sem login (devia ser 401 ou redirecionar)"))
        elif r.status == 200:
            out.append(alerta(f"{p}: 200 sem login. Se não for só o 'casco' da página, está exposta"))
        else:
            out.append(info(f"{p}: {r.status}"))
    return out


# ---------------------------------------------------------------- 2. arquivos sensíveis
ARQUIVOS = [
    ".env", ".env.local", ".env.production", ".env.development", ".git/HEAD", ".git/config",
    "package.json", "package-lock.json", "next.config.js", "next.config.mjs", "vercel.json",
    "docker-compose.yml", "Dockerfile", "drizzle.config.ts", "supabase/config.toml",
    "config.json", "backup.sql", "dump.sql", "database.sql", "wp-config.php.bak", ".DS_Store",
    "phpinfo.php", "server-status", "actuator/env", "api/docs", "api/swagger",
    "api/openapi.json", "swagger", "swagger.json", "openapi.json", "docs", "api/debug", "api/env",
]
ASSINATURAS = {
    ".env": re.compile(rb"(?m)^[A-Z][A-Z0-9_]{2,}\s*="),
    ".git/HEAD": re.compile(rb"^ref:"),
    ".git/config": re.compile(rb"\[core\]"),
    "package.json": re.compile(rb'"(dependencies|scripts|name)"'),
}


@teste("arquivos-sensiveis", "Arquivos sensíveis e documentação exposta")
def t_arquivos(c):
    base = c.get("/" + secrets.token_hex(8))
    base_len = len(base.corpo)
    out, achou = [], False
    for a in ARQUIVOS:
        r = c.get("/" + a)
        if r.status != 200:
            continue
        tipo = r.headers.get("content-type", "")
        chave = ".env" if a.startswith(".env") else a
        sig = ASSINATURAS.get(chave)
        eh_html = "html" in tipo
        if sig and sig.search(r.corpo[:4000]):
            achou = True
            out.append(falha(f"/{a}: conteúdo real exposto (200). O conteúdo não foi exibido"))
        elif base.status == 200 and base_len and abs(len(r.corpo) - base_len) <= 0.05 * base_len:
            continue  # site devolve a mesma página para tudo (SPA)
        elif not eh_html:
            achou = True
            out.append(alerta(f"/{a}: 200 com tipo {tipo.split(';')[0] or '?'}, confira manualmente"))
        elif a.startswith(("api/", "swagger", "docs", "openapi", "actuator")):
            achou = True
            out.append(alerta(f"/{a}: 200 (documentação ou debug público?)"))
    if not achou:
        out.append(ok(f"{len(ARQUIVOS)} caminhos testados, nenhum exposto"))
    r = c.get("/.well-known/security.txt")
    out.append(info("security.txt presente") if r.status == 200 else info("sem /.well-known/security.txt"))
    return out


# ---------------------------------------------------------------- 3. cabeçalhos
@teste("cabecalhos", "Cabeçalhos de segurança e CSP")
def t_cabecalhos(c):
    r = c.get(c.cfg["paginas_publicas"][0], seguir=True)
    if r.erro:
        return [falha(f"sem resposta: {r.erro}")]
    h, out = r.headers, []
    csp = h.get("content-security-policy", "")
    if c.base.startswith("https"):
        if "strict-transport-security" in h:
            out.append(ok("HSTS presente"))
        else:
            out.append(alerta("sem Strict-Transport-Security (HSTS)"))
    if not csp:
        out.append(alerta("sem Content-Security-Policy"))
    else:
        out.append(ok("Content-Security-Policy presente"))
        script = re.search(r"script-src([^;]*)", csp) or re.search(r"default-src([^;]*)", csp)
        s = script.group(1) if script else ""
        if "'unsafe-eval'" in s:
            out.append(alerta("CSP permite 'unsafe-eval' em script"))
        if "'unsafe-inline'" in s and "nonce-" not in s:
            out.append(alerta("CSP permite 'unsafe-inline' em script sem nonce"))
        if re.search(r"(^|\s)(\*|https:|http:)(\s|$)", s):
            out.append(alerta("CSP com curinga em script-src/default-src"))
        if "'unsafe-inline'" in csp and "style-src" in csp and "'unsafe-inline'" not in s:
            out.append(info("CSP permite 'unsafe-inline' em estilos (comum)"))
    if "x-frame-options" in h or "frame-ancestors" in csp:
        out.append(ok("proteção contra clickjacking (X-Frame-Options ou frame-ancestors)"))
    else:
        out.append(alerta("sem proteção contra clickjacking"))
    if h.get("x-content-type-options", "").lower() == "nosniff":
        out.append(ok("X-Content-Type-Options: nosniff"))
    else:
        out.append(alerta("sem X-Content-Type-Options: nosniff"))
    out.append(ok("Referrer-Policy presente") if "referrer-policy" in h else alerta("sem Referrer-Policy"))
    if "permissions-policy" not in h:
        out.append(info("sem Permissions-Policy"))
    if "x-powered-by" in h:
        out.append(alerta(f"X-Powered-By revela a tecnologia: {h['x-powered-by']}"))
    srv = h.get("server", "")
    if re.search(r"\d+\.\d+", srv):
        out.append(alerta(f"Server revela versão: {srv}"))
    if h.get("access-control-allow-origin") == "*":
        out.append(alerta("Access-Control-Allow-Origin: * na página inicial"))
    return out


# ---------------------------------------------------------------- 4. CORS
@teste("cors", "CORS com origem hostil")
def t_cors(c):
    out, achou = [], False
    caminhos = ["/"] + c.cfg["api_publicas"] + c.cfg["api_protegidas"]
    for p in caminhos:
        for metodo in ("GET", "OPTIONS"):
            hd = {"Origin": EVIL}
            if metodo == "OPTIONS":
                hd["Access-Control-Request-Method"] = "POST"
            r = c.get(p, metodo=metodo, headers=hd)
            acao = r.headers.get("access-control-allow-origin", "")
            cred = r.headers.get("access-control-allow-credentials", "").lower() == "true"
            if acao == EVIL and cred:
                achou = True
                out.append(falha(f"{metodo} {p}: reflete a origem hostil COM credenciais"))
            elif acao == EVIL:
                achou = True
                out.append(alerta(f"{metodo} {p}: reflete a origem hostil"))
            elif acao == "*":
                achou = True
                out.append(alerta(f"{metodo} {p}: Access-Control-Allow-Origin: *"))
    if not achou:
        out.append(ok(f"{len(caminhos)} caminhos, nenhuma permissão CORS para origem hostil"))
    return out


# ---------------------------------------------------------------- 5. cookies
@teste("cookies", "Flags dos cookies das páginas públicas")
def t_cookies(c):
    out, vistos = [], set()
    for p in c.cfg["paginas_publicas"]:
        r = c.get(p, seguir=True)
        for raw in r.cookies:
            partes = [x.strip() for x in raw.split(";")]
            nome = partes[0].split("=")[0]
            if nome in vistos:
                continue
            vistos.add(nome)
            attrs = [x.lower() for x in partes[1:]]
            secure = "secure" in attrs
            httponly = "httponly" in attrs
            same = next((a.split("=")[1] for a in attrs if a.startswith("samesite=")), "")
            sessao = re.search(r"(sess|token|auth|sid|jwt|login)", nome, re.I)
            desc = f"{nome}: Secure={secure} HttpOnly={httponly} SameSite={same or '-'}"
            if sessao and c.base.startswith("https") and not secure:
                out.append(falha(desc + " (cookie de sessão sem Secure)"))
            elif sessao and not httponly:
                out.append(alerta(desc + " (cookie de sessão sem HttpOnly)"))
            elif not secure and c.base.startswith("https"):
                out.append(info(desc))
            else:
                out.append(ok(desc))
    if not out:
        out.append(info("nenhum cookie definido nas páginas públicas. Cookies de sessão só aparecem depois do "
                        "login: confira no navegador (DevTools > Application > Cookies)"))
    return out


# ---------------------------------------------------------------- 6. bundles
SEGREDOS = {
    "service_role": re.compile(r"service_role"),
    "chave Stripe (sk_/rk_)": re.compile(r"\b[sr]k_(live|test)_[0-9A-Za-z]{10,}"),
    "segredo de webhook (whsec_)": re.compile(r"whsec_[0-9A-Za-z]{10,}"),
    "chave AWS": re.compile(r"AKIA[0-9A-Z]{16}"),
    "chave privada": re.compile(r"BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY"),
    "token GitHub": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "token Slack": re.compile(r"xox[bpas]-[0-9A-Za-z-]{10,}"),
    "chave Google (AIza)": re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    "DATABASE_URL": re.compile(r"DATABASE_URL"),
    "URL de banco com senha": re.compile(r"(postgres(ql)?|mongodb(\+srv)?|mysql)://[^\s\"'@]+:[^\s\"'@]+@"),
}
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.(eyJ[A-Za-z0-9_-]{10,})\.[A-Za-z0-9_-]{10,}")
JS_RE = re.compile(r"""(?:src|href)=["']([^"']+\.js[^"']*)["']|(/_next/static/[^"' )\\]+\.js)""")


def _papel_jwt(parte):
    try:
        dado = base64.urlsafe_b64decode(parte + "=" * (-len(parte) % 4))
        return json.loads(dado).get("role", "")
    except Exception:
        return ""


@teste("bundles", "Segredos e source maps no JavaScript público")
def t_bundles(c):
    urls = []
    for p in c.cfg["paginas_publicas"]:
        r = c.get(p, seguir=True)
        for m in JS_RE.finditer(texto(r)):
            u = urllib.parse.urljoin(c.url(p), m.group(1) or m.group(2))
            if urllib.parse.urlparse(u).netloc == c.host and u not in urls:
                urls.append(u)
    urls = urls[:40]
    if not urls:
        return [info("nenhum arquivo JavaScript encontrado nas páginas públicas")]
    out, achados, jwts, mapas, refs = [], {}, {}, [], 0
    for u in urls:
        r = c.fetch(u, seguir=True)
        t = texto(r)
        nome = u.rsplit("/", 1)[-1].split("?")[0]
        if "sourceMappingURL" in t:
            refs += 1
        for rotulo, rx in SEGREDOS.items():
            if rx.search(t):
                achados.setdefault(rotulo, []).append(nome)
        for m in JWT_RE.finditer(t):
            jwts.setdefault(_papel_jwt(m.group(1)) or "?", set()).add(nome)
    for u in urls[:6]:
        m = c.fetch(u.split("?")[0] + ".map", limite=5000)
        if m.status == 200 and b'"version"' in m.corpo:
            mapas.append(u.rsplit("/", 1)[-1].split("?")[0])
    out.append(info(f"{len(urls)} arquivos JS analisados"))
    if mapas:
        out.append(alerta(f"source maps públicos: {', '.join(mapas[:3])}... (expõem o código-fonte)"))
    else:
        out.append(ok("source maps não estão publicados (amostra de 6 arquivos)"))
    if refs:
        out.append(info(f"{refs} arquivo(s) referenciam sourceMappingURL"))
    for rotulo, arqs in achados.items():
        nivel = falha if rotulo in ("service_role", "chave privada", "URL de banco com senha") else alerta
        out.append(nivel(f"possível {rotulo} em: {', '.join(sorted(set(arqs))[:3])} (valor não exibido)"))
    for papel, arqs in jwts.items():
        if papel == "service_role":
            out.append(falha(f"JWT com role service_role em: {', '.join(sorted(arqs)[:3])}"))
        else:
            out.append(info(f"JWT público (role={papel}) em {len(arqs)} arquivo(s): normal para chave 'anon', "
                            "confirme que o RLS protege as tabelas"))
    if not achados and "service_role" not in jwts:
        out.append(ok("nenhum padrão de segredo encontrado"))
    return out


# ---------------------------------------------------------------- 7. API sem login
@teste("api-sem-login", "APIs protegidas sem login")
def t_api_sem_login(c):
    out = []
    for p in c.cfg["api_protegidas"]:
        r = c.get(p)
        if r.erro:
            out.append(info(f"{p}: sem resposta ({r.erro})"))
        elif r.status in (401, 403) or (r.status in (301, 302, 303, 307, 308)):
            out.append(ok(f"{p}: {r.status}"))
        elif r.status == 404:
            out.append(info(f"{p}: 404 (não existe)"))
        elif r.status == 200:
            out.append(falha(f"{p}: 200 sem login"))
        elif r.status >= 500:
            out.append(alerta(f"{p}: erro {r.status} sem login (devia ser 401)"))
        else:
            out.append(info(f"{p}: {r.status}"))
        o = c.get(p, metodo="OPTIONS")
        if o.status and o.headers.get("allow"):
            out.append(info(f"{p}: métodos permitidos: {o.headers['allow']}"))
    return out or [info("nenhuma API protegida configurada (api_protegidas)")]


# ---------------------------------------------------------------- 8. APIs públicas
SENSIVEL_RE = re.compile(r"(sha|commit|version|build|env|host|region|database|db|secret|key|token|password)", re.I)


@teste("api-publicas", "O que as APIs públicas revelam")
def t_api_publicas(c):
    out = []
    for p in c.cfg["api_publicas"]:
        r = c.get(p)
        if r.status != 200:
            out.append(info(f"{p}: {r.status}"))
            continue
        try:
            chaves = list(json.loads(texto(r)).keys())
        except Exception:
            chaves = []
        sens = [k for k in chaves if SENSIVEL_RE.search(k)]
        if sens:
            out.append(alerta(f"{p}: público e expõe campos: {', '.join(sens)}"))
        else:
            out.append(ok(f"{p}: público, campos: {', '.join(chaves) or '(não é JSON)'}"))
    return out or [info("nenhuma API pública configurada (api_publicas)")]


# ---------------------------------------------------------------- 9. open redirect
@teste("open-redirect", "Redirecionamento aberto no login")
def t_open_redirect(c):
    out, achou = [], False
    base = c.cfg["rota_login"]
    if c.sessao is None and os.environ.get("SESSAO_COOKIE"):
        c.sessao = os.environ["SESSAO_COOKIE"]
    for param in ("next", "redirect", "return", "returnUrl", "redirect_uri", "url"):
        leva = []
        for val in (EVIL + "/x", "//evil.example/x", "/\\evil.example"):
            r = c.get(f"{base}?{param}={urllib.parse.quote(val, safe='')}", auth=True)
            loc = r.headers.get("location", "")
            if r.status in (301, 302, 303, 307, 308) and "evil.example" in loc:
                leva.append(val)
        if leva:
            achou = True
            out.append(falha(f"?{param}= redireciona para fora com: {', '.join(leva)}"))
    if not achou:
        out.append(ok("parâmetros de retorno comuns não redirecionam para fora"))
    if not c.sessao:
        out.append(info("sem sessão: o redirecionamento após o login só é visível com a sessão ou no navegador"))
    return out


# ---------------------------------------------------------------- 10. IDs inválidos (sessão)
PAYLOADS_ID = [
    ("texto", "abc"), ("numero", "0"), ("negativo", "-1"),
    ("uuid-nulo", "00000000-0000-0000-0000-000000000000"), ("uuid-aleatorio", str(uuid.uuid4())),
    ("aspas", "%27"), ("sql", "%27%20OR%201%3D1--"), ("html", "%3Cscript%3Ealert(1)%3C%2Fscript%3E"),
    ("traversal", "..%2F..%2Fetc%2Fpasswd"), ("nulo", "%00"), ("longo", "A" * 600),
]


@teste("ids-invalidos", "IDs inválidos nas rotas de detalhe", sessao=True)
def t_ids(c):
    if not c.cfg["rotas_com_id"]:
        return [pulado("configure rotas_com_id (ex.: /dashboard/itens/{id}) no config.json")]
    out, marc = [], c.cfg["marcadores_erro"]
    for modelo in c.cfg["rotas_com_id"]:
        s500, vaza, tela_erro, ok200 = [], [], [], []
        for nome, val in PAYLOADS_ID:
            r = c.get(modelo.replace("{id}", val), auth=True)
            t = texto(r)
            if r.status >= 500 or r.erro:
                s500.append(nome)
            elif VAZA_RE.search(t):
                vaza.append(nome)
            elif r.status == 200 and any(m in t for m in marc):
                tela_erro.append(nome)
            elif r.status == 200 and nome != "uuid-aleatorio":
                ok200.append(nome)
        if s500:
            out.append(falha(f"{modelo}: erro 5xx para: {', '.join(s500)}"))
        if vaza:
            out.append(falha(f"{modelo}: resposta com detalhe interno (SQL/stack) para: {', '.join(vaza)}"))
        if tela_erro:
            out.append(alerta(f"{modelo}: 200 com tela de erro (ID não validado, devia ser 400/404) "
                              f"para: {', '.join(tela_erro)}"))
        if ok200:
            out.append(alerta(f"{modelo}: 200 para ID inválido ou inexistente (devia ser 400/404) "
                              f"para: {', '.join(ok200)}"))
        if not (s500 or vaza or tela_erro or ok200):
            out.append(ok(f"{modelo}: {len(PAYLOADS_ID)} IDs inválidos tratados com 4xx"))
    return out


# ---------------------------------------------------------------- 11. parâmetros (sessão)
PARAMS = ["page=-1", "page=abc", "page=99999999", "limit=100000", "pageSize=100000", "q=%27",
          "q=%22%3E%3Czzmark%3E", "search=%27%20OR%201%3D1--", "sort=%27%3B--", "order=zzz",
          "status=zzz", "type=zzz", "from=zzz&to=zzz", "id=%27"]


@teste("parametros", "Parâmetros inválidos nas listagens", sessao=True)
def t_parametros(c):
    if not c.cfg["rotas_lista"]:
        return [pulado("configure rotas_lista (ex.: /dashboard/itens) no config.json")]
    out = []
    for rota in c.cfg["rotas_lista"]:
        s500, vaza, refl = [], [], []
        for q in PARAMS:
            r = c.get(f"{rota}?{q}", auth=True)
            t = texto(r)
            if r.status >= 500 or r.erro:
                s500.append(q)
            elif VAZA_RE.search(t):
                vaza.append(q)
            if '"><zzmark>' in t:
                refl.append(q)
        if s500:
            out.append(falha(f"{rota}: erro 5xx para: {', '.join(s500[:5])}"))
        if vaza:
            out.append(falha(f"{rota}: detalhe interno na resposta para: {', '.join(vaza[:5])}"))
        if refl:
            out.append(falha(f"{rota}: valor refletido SEM escape (XSS) em: {', '.join(refl)}"))
        if not (s500 or vaza or refl):
            out.append(ok(f"{rota}: {len(PARAMS)} variações sem erro, vazamento ou reflexão"))
    return out


# ---------------------------------------------------------------- execução e interface
def pintar(nivel):
    rot = f"[{nivel}]"
    return f"\033[{CORES[nivel]}m{rot}\033[0m" if USAR_COR else rot


def carregar_config(caminho):
    cfg = json.loads(json.dumps(PADRAO))
    if caminho and os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            cfg.update({k: v for k, v in json.load(f).items() if k in PADRAO})
    return cfg


def normalizar_url(u):
    u = u.strip()
    if u and "://" not in u:
        u = "https://" + u
    return u.rstrip("/")


def obter_sessao(c):
    if c.sessao is None:
        c.sessao = os.environ.get("SESSAO_COOKIE", "")
        if not c.sessao and sys.stdin.isatty():
            print("Este teste precisa de uma sessão (usuário logado). Cole o valor do header Cookie")
            print("(DevTools > Network > uma requisição > Cookie). Fica só na memória. Enter pula.")
            c.sessao = getpass.getpass("Cookie: ").strip()
    return c.sessao


MSG_BLOQUEIO = ("o alvo BLOQUEOU as requisições (WAF, desafio de bot ou rate limit). Os resultados não são "
                "confiáveis. Não contorne o bloqueio: espere alguns minutos, use --pausa maior (ex.: 1.5) e "
                "rode menos testes por vez, ou peça a quem cuida do alvo para liberar o seu IP.")


def rodar(c, ids):
    """Roda os testes. Devolve (resultado, falhas, bloqueado)."""
    resultado, falhas, bloqueado = [], 0, False
    por_id = {t[0]: t for t in TESTES}
    try:
        pre = c.get(c.cfg["paginas_publicas"][0])
    except Bloqueado:
        pre = R(429, {}, [], b"", c.base, None)
    if pre.erro:
        print(f"\n{pintar('FALHA')} não consegui acessar {c.base}: {pre.erro}")
        return resultado, 1, False
    if eh_bloqueio(pre):
        print(f"\n{pintar('FALHA')} {MSG_BLOQUEIO}")
        return resultado, 1, True
    for i in ids:
        _, slug, nome, sessao, func = por_id[i]
        print(f"\n== {i}. {nome} ==")
        antes = c.bloqueios
        if sessao and not obter_sessao(c):
            achados = [pulado("precisa de sessão: defina SESSAO_COOKIE ou cole o cookie quando pedir")]
        else:
            try:
                achados = func(c)
            except Bloqueado:
                achados = []
            except Exception as e:  # um teste com defeito não derruba os outros
                achados = [falha(f"erro interno no teste: {type(e).__name__}: {e}")]
        if c.bloqueios > antes:
            achados = [falha(f"{c.bloqueios - antes} requisição(ões) bloqueada(s): {MSG_BLOQUEIO}")]
            bloqueado = True
        for a in achados:
            print(f"  {pintar(a.nivel)} {a.msg}")
        falhas += sum(a.nivel == "FALHA" for a in achados)
        resultado.append({"id": i, "teste": slug, "achados": [a._asdict() for a in achados]})
        if bloqueado:
            print("\nExecução interrompida por causa do bloqueio.")
            break
    todos = [a for r in resultado for a in r["achados"]]
    cont = {n: sum(a["nivel"] == n for a in todos) for n in CORES}
    print("\nResumo: " + "  ".join(f"{pintar(n)} {cont[n]}" for n in CORES))
    return resultado, falhas, bloqueado


def listar():
    print("Testes disponíveis:")
    for i, slug, nome, sessao, _ in TESTES:
        print(f"  {i:>2}. {slug:<20} {nome}" + ("  (precisa de sessão)" if sessao else ""))


def interpretar(sel):
    sel = sel.strip().lower()
    if sel in ("t", "todos", "all"):
        return [t[0] for t in TESTES]
    if sel in ("s", "semlogin"):
        return [t[0] for t in TESTES if not t[3]]
    ids = []
    for parte in re.split(r"[,\s]+", sel):
        if not parte:
            continue
        achado = next((t[0] for t in TESTES if parte == str(t[0]) or parte == t[1]), None)
        if achado is None:
            raise ValueError(f"teste desconhecido: {parte}")
        ids.append(achado)
    return ids


def menu(c, args):
    while True:
        print(f"\n=== script-teste-na-web {VERSAO} ===   Alvo: {c.base}")
        for i, slug, nome, sessao, _ in TESTES:
            print(f"  [{i:>2}] {nome}" + ("  (com sessão)" if sessao else ""))
        print("  [t] rodar todos   [s] só os que não precisam de login")
        print("  [a] trocar o alvo   [q] sair")
        esc = input("Escolha (ex.: 1,3,5): ").strip().lower()
        if esc in ("q", "sair"):
            return 0
        if esc == "a":
            novo = normalizar_url(input("Nova URL base: "))
            if novo:
                c.base, c.host = novo, urllib.parse.urlparse(novo).netloc
                c.sessao = None
                if not confirmar(c):
                    return 2
            continue
        try:
            ids = interpretar(esc)
        except ValueError as e:
            print(f"  {e}")
            continue
        if ids:
            rodar(c, ids)


def confirmar(c):
    print(f"\nAlvo: {c.base}")
    print("Use somente em sistemas seus ou com autorização de quem responde por eles. Os testes só leem")
    print("(GET e OPTIONS) e não fazem força bruta, mas geram dezenas de requisições.")
    return input("Você é responsável por este sistema ou tem autorização? (s/N): ").strip().lower() in ("s", "sim")


def main():
    global USAR_COR, PAUSA
    ap = argparse.ArgumentParser(description="Testes básicos de segurança e validação de rotas (somente leitura).")
    ap.add_argument("--url", help="URL base do sistema (ex.: https://demo.exemplo.com)")
    ap.add_argument("--config", default=os.path.join(AQUI, "config.json"), help="arquivo de configuração")
    ap.add_argument("--testes", help="ids ou nomes separados por vírgula (veja --listar)")
    ap.add_argument("--todos", action="store_true", help="rodar todos os testes")
    ap.add_argument("--sem-login", action="store_true", help="rodar só os testes que não precisam de sessão")
    ap.add_argument("--listar", action="store_true", help="listar os testes e sair")
    ap.add_argument("--sim", action="store_true", help="confirma que você tem autorização para testar o alvo")
    ap.add_argument("--json", metavar="ARQUIVO", help="salvar o resultado em JSON, ou '-' para imprimir ao final "
                    "(sem valores sensíveis; bom para uso por IA)")
    ap.add_argument("--pausa", type=float, default=None,
                    help=f"segundos entre requisições (padrão {PAUSA}). Aumente se o alvo bloquear")
    ap.add_argument("--sem-cor", action="store_true")
    args = ap.parse_args()
    if args.sem_cor:
        USAR_COR = False
    if args.pausa is not None:
        PAUSA = max(0.0, args.pausa)
    if args.listar:
        listar()
        return 0
    cfg = carregar_config(args.config)
    if args.url:
        cfg["base_url"] = args.url
    cfg["base_url"] = normalizar_url(cfg["base_url"])
    interativo = sys.stdin.isatty()
    if not cfg["base_url"]:
        if not interativo:
            sys.exit("Informe --url ou base_url no config.json.")
        cfg["base_url"] = normalizar_url(input("URL base do sistema (ex.: https://demo.exemplo.com): "))
        if not cfg["base_url"]:
            return 2
    if cfg["base_url"].startswith("http://"):
        print("Aviso: o alvo usa HTTP sem TLS.")
    c = Ctx(cfg)
    if not args.sim:
        if not interativo:
            sys.exit("Sem terminal interativo: passe --sim para confirmar que você tem autorização.")
        if not confirmar(c):
            print("Cancelado.")
            return 2
    if args.todos or args.testes or args.sem_login:
        ids = ([t[0] for t in TESTES] if args.todos
               else [t[0] for t in TESTES if not t[3]] if args.sem_login
               else interpretar(args.testes))
        resultado, falhas, bloqueado = rodar(c, ids)
        if args.json:
            saida = {"alvo": c.base, "falhas": falhas, "bloqueado": bloqueado, "resultado": resultado}
            if args.json == "-":
                print(json.dumps(saida, ensure_ascii=False, indent=1))
            else:
                with open(args.json, "w", encoding="utf-8") as f:
                    json.dump(saida, f, ensure_ascii=False, indent=1)
        return 3 if bloqueado else (1 if falhas else 0)
    if not interativo:
        sys.exit("Sem terminal interativo: use --todos, --sem-login ou --testes.")
    return menu(c, args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrompido.")
        sys.exit(130)
