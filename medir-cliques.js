// Cronometra a navegação por cliques no menu (sem recarregar a página), em 2 passadas.
// Mede: clique até a URL mudar, e clique até o DOM parar de mudar.
// Uso: playwright-cli --raw run-code "$(cat medir-cliques.js)" > saida-cliques.json
// Antes: abra o navegador, faça login e edite BASE, INICIO, ITENS e SELETOR abaixo.

async page => {
  const BASE = 'https://exemplo.com';
  const INICIO = '/';
  const ITENS = [['Exemplo', '/exemplo'], ['Outro', '/outro']]; // [nome, href do link no menu]
  const SELETOR = 'nav a, aside a';  // onde ficam os links do menu
  const SILENCIO_MS = 700;           // tempo sem mudança no DOM para considerar estável
  const PASSADAS = 2;

  const out = [];
  await page.goto(BASE + INICIO, { waitUntil: 'load' });
  await page.waitForTimeout(2000);
  for (let passada = 1; passada <= PASSADAS; passada++) {
    for (const [nome, href] of ITENS) {
      await page.evaluate(() => {
        window.__t0 = performance.now(); window.__last = window.__t0;
        if (window.__mo) window.__mo.disconnect();
        window.__mo = new MutationObserver(() => { window.__last = performance.now(); });
        window.__mo.observe(document.body, { childList: true, subtree: true, characterData: true });
        window.__lt = [];
        try { new PerformanceObserver(l => { for (const e of l.getEntries()) window.__lt.push(e.duration); }).observe({ type: 'longtask' }); } catch (e) {}
      });
      const t0 = Date.now();
      await page.locator(`${SELETOR.split(',').map(s => s.trim() + `[href="${href}"]`).join(', ')}`).first().click();
      await page.waitForURL('**' + href, { timeout: 20000 }).catch(() => {});
      const url = Date.now() - t0;
      while (Date.now() - t0 < 20000) {
        await page.waitForTimeout(150);
        if (await page.evaluate(() => performance.now() - window.__last) > SILENCIO_MS) break;
      }
      const m = await page.evaluate(() => ({ estavel: Math.round(window.__last - window.__t0), lt: Math.round(Math.max(0, ...window.__lt)) }));
      out.push({ passada, nome, url, estavel: m.estavel, lt: m.lt });
    }
  }
  return JSON.stringify(out);
}
