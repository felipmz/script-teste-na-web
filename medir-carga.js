// Mede a carga completa de cada rota (3 cargas por rota) pela Performance API.
// Uso: playwright-cli --raw run-code "$(cat medir-carga.js)" > saida.json
// Antes: abra o navegador, faça login e edite BASE e ROTAS abaixo.

async page => {
  const BASE = 'https://exemplo.com';
  const ROTAS = [['Início', '/'], ['Exemplo', '/exemplo']]; // [nome, caminho]
  const CARGAS = 3;        // quantas vezes carregar cada rota (a 1ª é a mais fria)
  const ESPERA_MS = 2500;  // espera depois do load para o LCP assentar

  const out = [];
  for (const [nome, rota] of ROTAS) {
    const runs = [];
    for (let i = 0; i < CARGAS; i++) {
      await page.addInitScript(() => {
        window.__lcp = 0; window.__lt = [];
        try {
          new PerformanceObserver(l => { for (const e of l.getEntries()) window.__lcp = e.startTime; })
            .observe({ type: 'largest-contentful-paint', buffered: true });
          new PerformanceObserver(l => { for (const e of l.getEntries()) window.__lt.push(e.duration); })
            .observe({ type: 'longtask', buffered: true });
        } catch (e) {}
      });
      const erros = [];
      const onConsole = m => { if (m.type() === 'error') erros.push(m.text().slice(0, 80)); };
      const ruins = [];
      const onResp = r => { if (r.status() >= 400) ruins.push(r.status() + ' ' + r.url().replace(BASE, '').slice(0, 60)); };
      page.on('console', onConsole);
      page.on('response', onResp);

      await page.goto(BASE + rota, { waitUntil: 'load', timeout: 60000 });
      await page.waitForTimeout(ESPERA_MS);

      const m = await page.evaluate(() => {
        const n = performance.getEntriesByType('navigation')[0];
        const fcp = (performance.getEntriesByType('paint').find(p => p.name === 'first-contentful-paint') || {}).startTime;
        const res = performance.getEntriesByType('resource');
        const api = res.filter(x => x.initiatorType === 'fetch' || x.initiatorType === 'xmlhttprequest')
          .sort((a, b) => b.duration - a.duration).slice(0, 3)
          .map(x => Math.round(x.duration) + 'ms ' + x.name.replace(location.origin, '').slice(0, 50));
        return {
          ttfb: Math.round(n.responseStart), dcl: Math.round(n.domContentLoadedEventEnd),
          load: Math.round(n.loadEventEnd), fcp: Math.round(fcp || 0), lcp: Math.round(window.__lcp),
          lt: window.__lt.length, ltMax: Math.round(Math.max(0, ...window.__lt)),
          req: res.length, kb: Math.round(res.reduce((s, x) => s + (x.transferSize || 0), 0) / 1024), api,
        };
      });
      page.off('console', onConsole);
      page.off('response', onResp);
      runs.push({ ...m, errs: [...new Set(erros)].slice(0, 3), bad: [...new Set(ruins)].slice(0, 3) });
    }
    out.push({ nome, rota, runs });
  }
  return JSON.stringify(out);
}
