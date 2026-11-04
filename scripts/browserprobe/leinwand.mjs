// Referenzbilder der Design-Leinwand (Plan P1, L10 Punkt 1).
//
//   node scripts/browserprobe/leinwand.mjs --quelle docs/design/2026-10-26-leinwand \
//        --ziel scripts/browserprobe/ergebnisse/leinwand [--nur Bausteine,Main]
//
// Kopiert jede Zeichenfläche aus canvas.json („order“) hell und dunkel in den Zielordner
// und ersetzt dabei nur die Platzhalter des Themas ({{theme}} → leer bzw. „dunkel“, in
// „Bausteine“ {{th.klasse}}/{{th.titel}} → hell bzw. dunkel). Das Original bleibt
// unverändert. Dann öffnet es jede Kopie in der Breite der Zeichenfläche und speichert
// ein ganzseitiges Bild. Ohne Netz (alle Anfragen außer file:// werden abgebrochen),
// ohne support.js; sc-if-Zweige stehen untereinander.
import { chromium } from 'playwright';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';

const { values: opt } = parseArgs({
  options: {
    quelle: { type: 'string', default: 'docs/design/2026-10-26-leinwand' },
    ziel: { type: 'string', default: 'scripts/browserprobe/ergebnisse/leinwand' },
    nur: { type: 'string' },
  },
});

const THEMEN = {
  hell: { theme: '', klasse: 'hell', titel: 'Hell' },
  dunkel: { theme: 'dunkel', klasse: 'dunkel', titel: 'Dunkel' },
};

export function ersetze(html, thema) {
  const t = THEMEN[thema];
  return html
    .replaceAll('{{theme}}', t.theme)
    .replaceAll('{{th.klasse}}', t.klasse)
    .replaceAll('{{th.titel}}', t.titel);
}

async function main() {
  const leinwand = JSON.parse(readFileSync(path.join(opt.quelle, 'canvas.json'), 'utf8'));
  const nur = opt.nur ? new Set(opt.nur.split(',')) : null;
  mkdirSync(opt.ziel, { recursive: true });
  const browser = await chromium.launch();
  const ergebnis = [];
  try {
    for (const datei of leinwand.order) {
      const name = datei.replace(/\.dc\.html$/, '');
      if (nur && !nur.has(name)) continue;
      const { w, h } = leinwand.boards[datei];
      const roh = readFileSync(path.join(opt.quelle, datei), 'utf8');
      for (const thema of Object.keys(THEMEN)) {
        const kopie = path.resolve(opt.ziel, `${name}-${thema}.html`);
        writeFileSync(kopie, ersetze(roh, thema));
        const kontext = await browser.newContext({ viewport: { width: w, height: h } });
        await kontext.route(/^(?!file:)/, (r) => r.abort());
        const seite = await kontext.newPage();
        await seite.goto(pathToFileURL(kopie).href);
        const breite = await seite.evaluate(() => document.documentElement.scrollWidth);
        const bild = path.resolve(opt.ziel, `${name}-${thema}.png`);
        await seite.screenshot({ path: bild, fullPage: true });
        ergebnis.push({ name, thema, breite: w, scrollWidth: breite, bild });
        await kontext.close();
      }
    }
  } finally {
    await browser.close();
  }
  writeFileSync(path.join(opt.ziel, 'leinwand.json'), JSON.stringify(ergebnis, null, 2));
  const breit = ergebnis.filter((e) => e.scrollWidth > e.breite);
  console.log(`${ergebnis.length} Bilder in ${opt.ziel}; waagrecht zu breit: ${breit.length}`);
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
