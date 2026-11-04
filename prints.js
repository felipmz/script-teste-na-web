// Tira prints de cada rota em desktop e celular e checa problemas básicos:
// rolagem horizontal da página, imagens quebradas, erros de console e de página.
// Uso: playwright-cli --raw run-code "$(cat prints.js)" > saida-prints.json
// Antes: abra o navegador, faça login e edite PASTA, BASE e ROTAS abaixo.

async page => {
  const PASTA = '/caminho/absoluto/para/os/prints';
  const BASE = 'https://exemplo.com';
  const ROTAS = [['inicio', '/'], ['exemplo', '/exemplo']]; // [nome-do-arquivo, caminho]
  const TELAS = [['desktop', 1440, 900], ['celular', 390, 844]];
  const ESPERA_MS = 2500;

  const out = [];
  for (const [tag, w, h] of TELAS) {
    await page.setViewportSize({ width: w, height: h });
    let i = 0;
    for (const [nome, rota] of ROTAS) {
      i++;
      const erros = [];
      const onConsole = m => { if (m.type() === 'error') erros.push(m.text().slice(0, 90)); };
      const onPageError = e => erros.push('pageerror: ' + String(e).slice(0, 90));
      page.on('console', onConsole);
      page.on('pageerror', onPageError);
      await page.goto(BASE + rota, { waitUntil: 'load', timeout: 60000 }).catch(() => {});
      await page.waitForTimeout(ESPERA_MS);
      const chk = await page.evaluate(() => {
        const de = document.documentElement;
        return {
          rolagemHorizontal: de.scrollWidth > de.clientWidth + 2,
          imagensQuebradas: [...document.images].filter(im => im.complete && im.naturalWidth === 0).length,
          titulo: (document.querySelector('h1') || {}).textContent || '',
        };
      });
      await page.screenshot({ path: `${PASTA}/${tag}-${String(i).padStart(2, '0')}-${nome}.png` });
      page.off('console', onConsole);
      page.off('pageerror', onPageError);
      out.push({ tela: tag, nome, ...chk, erros: [...new Set(erros)].slice(0, 3) });
    }
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  return JSON.stringify(out);
}
