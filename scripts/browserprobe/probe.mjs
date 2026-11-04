// Browserprobe der Oberfläche (Spec 10c A112, AK1/AK2/AK5 …; Plan P1, Schritte 5 und 14).
//
//   node scripts/browserprobe/probe.mjs --welt DIR/probe.json [--browser chromium]
//        [--benutzer jan,fritz] [--seiten /muster,/pruefen] [--breiten 1440,390,320]
//        [--themen hell,dunkel] [--auslassen geruest] [--bilder]
//        [--vergleich scripts/browserprobe/ergebnisse/leinwand] [--fehlerseite] [--ablaeufe]
//
// Meldet sich je Benutzer an (TOTP aus probe.json mit node:crypto), öffnet jede
// erlaubte HTML-Seite der Welt je Breite und Thema und misst: kein waagrechtes Scrollen
// (AK1, 320/390 px), axe-core 4.14.0 mit WCAG 2.0–2.2 A/AA (AK2, 1440/390 px, in einem
// Kontext mit bypassCSP), keine CSP-Meldung in der Konsole (AK5, Kontext ohne
// Umgehung). Auf /muster dazu der Fokus nach dem Austausch (A104) und die Maßprobe
// (L10 Punkt 4) in beiden Themenrahmen und mit ?theme=. Schritt 14 misst je Seite
// AK4 (Dunkelmodus: Bedienelemente, kbd), AK6/AK44 (Leisten, Kopf, Ziele, Inhaltsbreite,
// Kurztitel bei 320 px), AK49 (Angaben überlappen nicht, Codefeld-Label), AK50
// (tabular-nums, Symbole, Gewichte, reduzierte Bewegung), AK52 (Rollen, ARIA-Schnappschuss),
// AK55 (Zielgrößen 24/44, Tastatur auf /pruefen, Arbeitsfläche, /konto), AK56 (640 × 400
// mit Textabständen); Runde 2 je Breite (z. B. --breiten 1920,1440,1280,1024,390,320) ohne
// und mit Textabständen „abschnitt“ (nichts abgeschnitten, scrollende Rahmen bedienbar,
// jedes Bedienelement anklickbar, Seitentitel im Kopf ganz); --ablaeufe dazu AK7, AK8,
// AK45, AK53 und AK54. --vergleich legt Bilder der
// Anwendung neben die Referenzbilder aus leinwand.mjs (ergebnisse/<datum>-vergleich.html).
// Ergebnis: ergebnisse/<datum>-<browser>.json; Rückgabewert 1 bei einem Befund.
import { chromium, firefox } from 'playwright';
import { createHash, createHmac } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';

const HIER = path.dirname(fileURLToPath(import.meta.url));
const AXE_DATEI = path.join(HIER, 'node_modules', 'axe-core', 'axe.min.js');
const AXE_SHA256 = '20c09fe157a8a34a30e241aaa1fcdade657734f08ab379ecfbeb7d45cc46e878';
const AXE_REGELN = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];
const HOEHEN = { 1920: 1080, 1440: 900, 1280: 800, 1024: 768, 390: 844, 320: 568 };

// Token nach Plan P1, L1 (hell, dunkel) — die Maßprobe vergleicht die berechneten Werte
const TOKEN = {
  hell: {
    '--grund': '#f5f4f1', '--flaeche': '#ffffff', '--flaeche-2': '#efede8',
    '--text': '#1b1f24', '--text-2': '#555d66', '--linie': '#d6d3cc',
    '--linie-stark': '#7a8088', '--akzent': '#1a5a73', '--akzent-text': '#ffffff',
    '--akzent-flaeche': '#e3eef2', '--fokus': '#b35c00', '--ok': '#1d6b3a',
    '--ok-flaeche': '#e5f2e9', '--warn': '#8a5a00', '--warn-flaeche': '#fbf0d9',
    '--fehler': '#a8241f', '--fehler-flaeche': '#fbe7e5', '--fehler-text': '#ffffff',
    '--info': '#1f5fa8', '--info-flaeche': '#e6eef9',
    '--schatten': '0 1px 2px rgba(27,31,36,.05),0 4px 12px rgba(27,31,36,.04)',
    '--schleier': 'rgb(0 0 0 / .08)', '--marke-1': '#7b3fa0', '--marke-2': '#1f6fa8',
    '--marke-3': '#2f7d5b', '--marke-4': '#a8551f', '--marke-5': '#a8244f',
    '--marke-6': '#5f6b1f', '--beleg-hintergrund': '#ffffff',
  },
  dunkel: {
    '--grund': '#121417', '--flaeche': '#1a1d21', '--flaeche-2': '#22262b',
    '--text': '#e8eaed', '--text-2': '#a7aeb6', '--linie': '#33383f',
    '--linie-stark': '#6f7781', '--akzent': '#7dc3db', '--akzent-text': '#0e1a1f',
    '--akzent-flaeche': '#183039', '--fokus': '#ffb366', '--ok': '#7fd19b',
    '--ok-flaeche': '#16291d', '--warn': '#f0c46a', '--warn-flaeche': '#2e2614',
    '--fehler': '#ff9a92', '--fehler-flaeche': '#341a19', '--fehler-text': '#2a0d0b',
    '--info': '#8db8f0', '--info-flaeche': '#172436', '--schatten': 'none',
    '--schleier': 'rgb(255 255 255 / .08)', '--marke-1': '#c79ae6',
    '--marke-2': '#8db8f0', '--marke-3': '#7fd1ad', '--marke-4': '#f0a46a',
    '--marke-5': '#f08fb0', '--marke-6': '#b5c25a', '--beleg-hintergrund': '#ffffff',
  },
};

const { values: opt } = parseArgs({
  options: {
    welt: { type: 'string' },
    browser: { type: 'string', default: 'chromium' },
    benutzer: { type: 'string' },
    seiten: { type: 'string' },
    breiten: { type: 'string', default: '1440,390,320' },
    themen: { type: 'string', default: 'hell,dunkel' },
    auslassen: { type: 'string', default: '' },
    bilder: { type: 'boolean', default: false },
    vergleich: { type: 'string' },
    fehlerseite: { type: 'boolean', default: false },
    ablaeufe: { type: 'boolean', default: false },
    ziel: { type: 'string', default: path.join(HIER, 'ergebnisse') },
  },
});

// --- TOTP (RFC 6238, SHA-1, 30 s, 6 Stellen) wie accounti.auth.totp -----------------
function base32(text) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  let bits = '';
  for (const z of text.replace(/=+$/, '').toUpperCase()) {
    const i = alphabet.indexOf(z);
    if (i < 0) throw new Error(`kein Base32: ${z}`);
    bits += i.toString(2).padStart(5, '0');
  }
  const bytes = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) bytes.push(parseInt(bits.slice(i, i + 8), 2));
  return Buffer.from(bytes);
}

export function totp(geheimnis, zeitMs = Date.now()) {
  const zaehler = Buffer.alloc(8);
  zaehler.writeBigUInt64BE(BigInt(Math.floor(zeitMs / 1000 / 30)));
  const mac = createHmac('sha1', base32(geheimnis)).update(zaehler).digest();
  const versatz = mac[mac.length - 1] & 0x0f;
  const zahl = (mac.readUInt32BE(versatz) & 0x7fffffff) % 1_000_000;
  return String(zahl).padStart(6, '0');
}

function hexZuRgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return `rgb(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255})`;
}

function axeQuelle() {
  const inhalt = readFileSync(AXE_DATEI);
  const summe = createHash('sha256').update(inhalt).digest('hex');
  if (summe !== AXE_SHA256) throw new Error(`axe.min.js: Prüfsumme ${summe} ≠ ${AXE_SHA256}`);
  return inhalt.toString('utf8');
}

// --- Anmeldung --------------------------------------------------------------------------
async function anmelden(browser, basis, name, daten) {
  const kontext = await browser.newContext();
  const seite = await kontext.newPage();
  for (let versuch = 0; versuch < 2; versuch += 1) {
    await seite.goto(`${basis}/anmelden`);
    await seite.fill('[name=benutzer]', name);
    await seite.fill('[name=passwort]', daten.passwort);
    await seite.fill('[name=einmalcode]', totp(daten.geheimnis));
    const antwort = seite.waitForResponse((r) => r.request().method() === 'POST' && new URL(r.url()).pathname === '/anmelden');
    await seite.locator('form[action="/anmelden"] button[type=submit]').click();
    if ((await antwort).status() === 303) {
      const stand = await kontext.storageState();
      await kontext.close();
      return stand;
    }
    // derselbe Code war schon benutzt (zweiter Lauf binnen 30 s): auf den nächsten warten
    await new Promise((r) => setTimeout(r, 30_000 - (Date.now() % 30_000) + 500));
  }
  await kontext.close();
  throw new Error(`Anmeldung als ${name} gescheitert`);
}

// --- Messungen (je Kriterium eine Funktion) -----------------------------------------------
const MESSUNGEN = {
  // AK1: kein waagrechtes Scrollen
  async ak1(seite) {
    const w = await seite.evaluate(() => ({ scroll: document.documentElement.scrollWidth, fenster: window.innerWidth }));
    return { ok: w.scroll <= w.fenster, ...w };
  },
  // AK2: axe-core 0 Verstöße (A/AA) — nur im Kontext mit bypassCSP
  async ak2(seite, { axe }) {
    await seite.addScriptTag({ content: axe });
    const verstoesse = await seite.evaluate(async (regeln) => {
      // eslint-disable-next-line no-undef
      const r = await axe.run(document, { runOnly: { type: 'tag', values: regeln }, resultTypes: ['violations'] });
      return r.violations.map((v) => ({ id: v.id, impact: v.impact, anzahl: v.nodes.length, ziele: v.nodes.slice(0, 3).map((n) => n.target.join(' ')) }));
    }, AXE_REGELN);
    return { ok: verstoesse.length === 0, verstoesse };
  },
  // A104: nach dem Austausch über /muster/beispiel liegt der Fokus auf data-fokus
  async fokus(seite) {
    const knopf = seite.locator('[hx-get="/muster/beispiel"]').first();
    if ((await knopf.count()) === 0) return { ok: false, grund: 'kein Austausch-Knopf' };
    await knopf.click();
    await seite.waitForSelector('#austausch-ziel [data-fokus]', { timeout: 5000 });
    await seite.waitForTimeout(300);
    const aktiv = await seite.evaluate(() => ({
      fokus: document.activeElement?.hasAttribute('data-fokus') ?? false,
      element: document.activeElement?.outerHTML.slice(0, 80) ?? null,
      busy: document.querySelector('#austausch-ziel')?.getAttribute('aria-busy') ?? null,
    }));
    return { ok: aktiv.fokus, ...aktiv };
  },
};

// L10 Punkt 4 — läuft in der Seite; rahmen = Selektor des Themenrahmens oder null (Seite)
function massprobeInSeite({ rahmen, token, farben, geruest, breite }) {
  const wurzel = rahmen ? document.querySelector(rahmen) : document.documentElement;
  const befunde = [];
  const pruefe = (name, ok, wert) => befunde.push({ name, ok: Boolean(ok), wert });
  if (!wurzel) return [{ name: `Rahmen ${rahmen}`, ok: false, wert: 'fehlt' }];
  const cs = getComputedStyle(wurzel);
  const norm = (w) => w.replace(/\s+/g, '').toLowerCase();
  for (const [t, w] of Object.entries(token)) {
    const ist = cs.getPropertyValue(t).trim();
    pruefe(`Token ${t}`, norm(ist) === norm(w), ist);
  }
  const suche = (sel) => (rahmen ? wurzel.querySelector(sel) : document.querySelector(`main ${sel}`));
  const stil = (sel) => {
    const e = suche(sel);
    return e ? getComputedStyle(e) : null;
  };
  const hoehe = (sel) => suche(sel)?.getBoundingClientRect().height ?? null;
  const k = stil('.karte');
  if (breite >= 1024 && k) {
    pruefe('Karte Radius 10', k.borderTopLeftRadius === '10px', k.borderTopLeftRadius);
    pruefe('Karte Rahmen 1', k.borderTopWidth === '1px', k.borderTopWidth);
    pruefe('Karte Innenabstand 20/24', k.paddingTop === '20px' && k.paddingLeft === '24px', `${k.paddingTop} ${k.paddingLeft}`);
  }
  const knopf = stil('.knopf:not(.knopf-klein):not(.knopf-gross)');
  if (knopf) {
    pruefe('Knopf ≥ 44', hoehe('.knopf:not(.knopf-klein):not(.knopf-gross)') >= 44, hoehe('.knopf:not(.knopf-klein):not(.knopf-gross)'));
    pruefe('Knopf Radius 6', knopf.borderTopLeftRadius === '6px', knopf.borderTopLeftRadius);
  }
  const reiter = stil('.reiter > a[aria-current="page"]');
  if (reiter) {
    pruefe('Reiter-Strich 3', reiter.borderBottomWidth === '3px', reiter.borderBottomWidth);
    pruefe('Reiter-Strich Akzent', reiter.borderBottomColor === farben.akzent, reiter.borderBottomColor);
  }
  const option = stil('.optionskarte:has(input:checked)');
  if (option) pruefe('Optionskarte gewählt 2', option.borderTopWidth === '2px', option.borderTopWidth);
  const feld = stil('.feld:not(.feld-fehler):not(.feld-warnung) > .eingabe');
  if (feld) pruefe('Feldrand 1', feld.borderTopWidth === '1px', feld.borderTopWidth);
  const fehler = stil('.feld-fehler > .eingabe');
  if (fehler) {
    pruefe('Feldrand Fehler 2', fehler.borderTopWidth === '2px', fehler.borderTopWidth);
    pruefe('Feldrand Fehler Farbe', fehler.borderTopColor === farben.fehler, fehler.borderTopColor);
  }
  const fokus = stil('.zeige-fokus');
  if (fokus) pruefe('Fokusring 3/2', fokus.outlineWidth === '3px' && fokus.outlineOffset === '2px' && fokus.outlineStyle === 'solid', `${fokus.outlineWidth} ${fokus.outlineOffset}`);
  const pille = stil('.status');
  if (pille) pruefe('Pille ohne Umbruch, 13 px, 600', pille.whiteSpace === 'nowrap' && pille.fontSize === '13px' && pille.fontWeight === '600', `${pille.whiteSpace} ${pille.fontSize} ${pille.fontWeight}`);
  const etikett = stil('.etikett');
  if (etikett) pruefe('Etikett Versalien', etikett.textTransform === 'uppercase', etikett.textTransform);
  const betrag = stil('.betrag-wert');
  if (betrag) pruefe('Betrag ohne Umbruch', betrag.whiteSpace === 'nowrap', betrag.whiteSpace);
  if (geruest && !rahmen) {
    const sichtbar = (sel) => {
      const e = document.querySelector(sel);
      return e ? getComputedStyle(e).display !== 'none' : false;
    };
    const kopf = document.querySelector('body > header.kopfleiste, header.kopfleiste');
    pruefe('Kopfleiste 56', kopf && Math.round(kopf.getBoundingClientRect().height) === 56, kopf?.getBoundingClientRect().height);
    const seitenleiste = document.querySelector('nav.seitenleiste:not(.muster-rahmen *)');
    const leiste = document.querySelector('nav.untere-leiste:not(.muster-rahmen *)');
    if (breite >= 1024) {
      pruefe('Seitenleiste sichtbar', sichtbar('nav.seitenleiste:not(.muster-rahmen *)'), null);
      const w = seitenleiste?.getBoundingClientRect().width ?? 0;
      pruefe('Seitenleiste 232 ± 1', Math.abs(w - 232) <= 1, w);
      pruefe('Untere Leiste aus', leiste && getComputedStyle(leiste).display === 'none', leiste ? getComputedStyle(leiste).display : 'fehlt');
    } else {
      pruefe('Seitenleiste aus', seitenleiste && getComputedStyle(seitenleiste).display === 'none', seitenleiste ? getComputedStyle(seitenleiste).display : 'fehlt');
      const h = leiste?.getBoundingClientRect().height ?? 0;
      pruefe('Untere Leiste 64', Math.round(h) === 64, h);
    }
  }
  return befunde;
}

async function massprobe(seite, rahmen, thema, breite, geruest) {
  const token = TOKEN[thema];
  const farben = { akzent: hexZuRgb(token['--akzent']), fehler: hexZuRgb(token['--fehler']) };
  const befunde = await seite.evaluate(massprobeInSeite, { rahmen, token, farben, geruest, breite });
  return { ok: befunde.every((b) => b.ok), fehler: befunde.filter((b) => !b.ok), anzahl: befunde.length };
}

// --- Schritt 14: Messungen je Seite (AK4, AK6/AK44, AK49, AK50, AK52) — laufen in der Seite
function seitenmessungInSeite({ breite, thema }) {
  const befunde = [];
  const pruefe = (ak, name, ok, wert) => befunde.push({ ak, name, ok: Boolean(ok), wert });
  const sichtbar = (e) => {
    if (!e) return false;
    const cs = getComputedStyle(e);
    const r = e.getBoundingClientRect();
    return cs.display !== 'none' && cs.visibility !== 'hidden' && r.width > 0 && r.height > 0 && !e.closest('.unsichtbar, [hidden], .muster-rahmen');
  };
  const rgb = (text) => (text.match(/[\d.]+/g) || []).map(Number);
  const leucht = ([r, g, b]) => {
    const lin = (k) => { k /= 255; return k <= 0.04045 ? k / 12.92 : ((k + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
  };
  const kontrast = (a, b) => { const [h, d] = [leucht(a), leucht(b)].sort((x, y) => y - x); return (h + 0.05) / (d + 0.05); };
  const hintergrund = (e) => {
    for (let x = e; x; x = x.parentElement) {
      const f = rgb(getComputedStyle(x).backgroundColor);
      if (f.length >= 3 && (f.length < 4 || f[3] === 1)) return f;
    }
    return rgb(getComputedStyle(document.body).backgroundColor);
  };
  // AK4: im Dunkelmodus keine weißen Bedienelemente; kbd ≥ 4,5 : 1, Deckkraft 1
  if (thema === 'dunkel') {
    for (const e of document.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio]), select, textarea, button')) {
      if (!sichtbar(e) || e.closest('.thema-hell')) continue; // der helle Rahmen auf /muster
      const f = getComputedStyle(e).backgroundColor;
      if (f === 'rgb(255, 255, 255)') pruefe('AK4', `weiß: ${e.tagName} ${e.id || e.className}`, false, f);
    }
    for (const k of document.querySelectorAll('kbd')) {
      if (!sichtbar(k)) continue;
      const cs = getComputedStyle(k);
      const wert = kontrast(rgb(cs.color), hintergrund(k));
      pruefe('AK4', 'kbd', wert >= 4.5 && cs.opacity === '1', `${wert.toFixed(2)} / ${cs.opacity}`);
    }
  }
  // AK6/AK44: Seitenleiste ab 64rem, sonst untere Leiste; Kopf ≤ 56; ≤ 5 Ziele; Inhalt ≤ 90rem
  const seitenleiste = document.querySelector('.geruest-rumpf > .seitenleiste');
  const leiste = document.querySelector('body > .untere-leiste');
  const kopf = document.querySelector('body > header.kopfleiste');
  if (leiste || seitenleiste) {
    const breit = breite >= 1024;
    pruefe('AK6', 'Seitenleiste', breit ? sichtbar(seitenleiste) : !sichtbar(seitenleiste), seitenleiste ? getComputedStyle(seitenleiste).display : 'fehlt');
    pruefe('AK6', 'untere Leiste', breit ? !sichtbar(leiste) : sichtbar(leiste), leiste ? getComputedStyle(leiste).display : 'fehlt');
    if (leiste) pruefe('AK6', '≤ 5 Ziele', leiste.querySelectorAll('a').length <= 5, leiste.querySelectorAll('a').length);
    if (!breit && kopf) pruefe('AK6', 'Kopf ≤ 56', kopf.getBoundingClientRect().height <= 56.5, kopf.getBoundingClientRect().height);
    if (breite <= 320 && leiste) {
      for (const t of leiste.querySelectorAll('.leisten-titel')) {
        const ziel = t.closest('a').getBoundingClientRect();
        const r = t.getBoundingClientRect();
        // nicht abgeschnitten: ganz im Ziel (ein Umbruch in zwei Zeilen ist erlaubt)
        pruefe('AK6', `Titel ganz: ${t.textContent.trim()}`, t.scrollWidth <= t.clientWidth + 1 && r.left >= ziel.left - 1 && r.right <= ziel.right + 1 && r.top >= ziel.top - 1 && r.bottom <= ziel.bottom + 1, `${Math.round(r.width)}×${Math.round(r.height)} in ${Math.round(ziel.width)}×${Math.round(ziel.height)}`);
      }
    }
  }
  const inhalt = document.querySelector('#inhalt');
  if (inhalt) pruefe('AK44', 'Inhalt ≤ 90rem', inhalt.getBoundingClientRect().width <= 1440, inhalt.getBoundingClientRect().width);
  // AK49: Label und Wert jeder Angabenliste überlappen nicht; Codefeld mit sichtbarem Label
  for (const dl of document.querySelectorAll('dl.angaben')) {
    if (!sichtbar(dl)) continue;
    for (const dt of dl.querySelectorAll('dt')) {
      const dd = dt.nextElementSibling;
      if (!dd) continue;
      const a = dt.getBoundingClientRect();
      const b = dd.getBoundingClientRect();
      const ueber = a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1;
      if (ueber) pruefe('AK49', `überlappt: ${dt.textContent.trim()}`, false, null);
    }
  }
  for (const c of document.querySelectorAll('input[name=einmalcode]')) {
    const l = document.querySelector(`label[for="${c.id}"]`);
    pruefe('AK49', `Codefeld-Label ${c.id}`, sichtbar(l), l?.textContent.trim());
  }
  // AK50: Beträge mit gleich breiten Ziffern; Symbole beschriftet oder versteckt; 400/600
  for (const b of document.querySelectorAll('.betrag-wert, td.zahl')) {
    if (!/tabular-nums/.test(getComputedStyle(b).fontVariantNumeric)) pruefe('AK50', 'tabular-nums', false, b.textContent.trim());
  }
  for (const s of document.querySelectorAll('svg.symbol')) {
    const ok = s.getAttribute('aria-hidden') === 'true' || (s.getAttribute('role') === 'img' && s.getAttribute('aria-label'));
    if (!ok) pruefe('AK50', 'Symbol ohne Beschriftung', false, s.outerHTML.slice(0, 60));
  }
  const gewichte = new Set();
  for (const e of document.body.querySelectorAll('*')) {
    if (![...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) continue;
    gewichte.add(getComputedStyle(e).fontWeight);
  }
  pruefe('AK50', 'Gewichte 400/600', [...gewichte].every((g) => g === '400' || g === '600'), [...gewichte].join(','));
  // AK52: Tabellen tragen die Rollen auch in der Kartenform
  for (const t of document.querySelectorAll('main table')) {
    const ok = t.getAttribute('role') === 'table' && [...t.querySelectorAll('tr')].every((r) => r.getAttribute('role') === 'row') && [...t.querySelectorAll('td')].every((d) => d.getAttribute('role') === 'cell');
    pruefe('AK52', 'Rollen', ok, t.querySelector('caption')?.textContent.trim());
  }
  return befunde;
}

async function seitenmessung(seite, breite, thema) {
  const befunde = await seite.evaluate(seitenmessungInSeite, { breite, thema });
  return { ok: befunde.every((b) => b.ok), fehler: befunde.filter((b) => !b.ok), anzahl: befunde.length };
}

// AK50: mit prefers-reduced-motion jede transition-duration 0 s
async function bewegung(seite) {
  await seite.emulateMedia({ reducedMotion: 'reduce' });
  const lang = await seite.evaluate(() => [...document.querySelectorAll('*')]
    .map((e) => getComputedStyle(e).transitionDuration)
    .filter((d) => d.split(',').some((x) => parseFloat(x) > 0)).length);
  await seite.emulateMedia({ reducedMotion: 'no-preference' });
  return { ok: lang === 0, mit_dauer: lang };
}

// AK52: ARIA-Schnappschuss der ersten Tabelle bei 390 px (Kartenform) zeigt Zeilen und Zellen
async function ariaTabelle(seite) {
  const t = seite.locator('main table').first();
  if ((await t.count()) === 0) return { ok: true, tabelle: false };
  const schnapp = await t.ariaSnapshot();
  return { ok: /- row/.test(schnapp) && /- cell/.test(schnapp), auszug: schnapp.slice(0, 160) };
}

// AK55: Tab durch die Seite — Sprunglink zuerst, Fokus nie ganz verdeckt, Ring ≥ 2 px,
// nach endlich vielen Tabs wieder oben; Ziele ≥ 24 × 24 (grob: ≥ 44 × 44)
async function tastatur(seite) {
  const befunde = [];
  await seite.keyboard.press('Tab');
  const erstes = await seite.evaluate(() => document.activeElement?.className ?? '');
  befunde.push({ name: 'erster Tab-Stopp Sprunglink', ok: /sprunglink/.test(erstes), wert: erstes });
  let zurueck = false;
  for (let i = 0; i < 250; i += 1) {
    const info = await seite.evaluate(() => {
      const e = document.activeElement;
      if (!e || e === document.body) return { body: true };
      const r = e.getBoundingClientRect();
      const verdeckt = (sel) => {
        const x = document.querySelector(sel);
        if (!x || getComputedStyle(x).position !== 'fixed' && getComputedStyle(x).position !== 'sticky') return false;
        const b = x.getBoundingClientRect();
        if (x.contains(e)) return false;
        return r.top >= b.top && r.bottom <= b.bottom && r.left >= b.left && r.right <= b.right;
      };
      const cs = getComputedStyle(e);
      return {
        klasse: e.className?.baseVal ?? e.className,
        text: (e.textContent || e.getAttribute('aria-label') || e.name || '').trim().slice(0, 40),
        verdeckt: verdeckt('body > header.kopfleiste') || verdeckt('body > .untere-leiste'),
        ring: parseFloat(cs.outlineWidth) || 0,
        stil: cs.outlineStyle,
        sprung: /sprunglink/.test(e.className),
        iframe: e.tagName === 'IFRAME',
      };
    });
    if (info.body || (i > 0 && info.sprung)) { zurueck = true; break; }
    if (info.verdeckt) befunde.push({ name: `verdeckt: ${info.text}`, ok: false, wert: info.klasse });
    // ein iframe (PDF-Vorschau) zeigt den Fokus in seinem eigenen Dokument
    if (!info.iframe && (info.ring < 2 || info.stil === 'none')) befunde.push({ name: `Ring: ${info.text}`, ok: false, wert: `${info.ring} ${info.stil}` });
    await seite.keyboard.press('Tab');
  }
  befunde.push({ name: 'keine Falle (wieder am Anfang)', ok: zurueck, wert: null });
  return { ok: befunde.every((b) => b.ok), fehler: befunde.filter((b) => !b.ok), anzahl: befunde.length };
}

function zieleInSeite(mindest) {
  const fehler = [];
  const ziele = document.querySelectorAll('a[href], button, select, textarea, summary, input:not([type=hidden])');
  for (const e of ziele) {
    if (e.closest('.unsichtbar, [hidden], details:not([open]) > :not(summary), .muster-rahmen, .druckkopf')) continue;
    const cs = getComputedStyle(e);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    if (e.classList.contains('sprunglink') && document.activeElement !== e) continue;
    // Kontrollkästchen und Optionsfelder: Ziel ist das umschließende label (L7 Nr. 20)
    let ziel = e;
    if (e.matches('input[type=checkbox], input[type=radio]')) ziel = e.closest('label') ?? e;
    // Links im Fließtext sind ausgenommen (WCAG 2.5.8)
    if (e.tagName === 'A' && !e.matches('.knopf, .nav-eintrag, .leisten-ziel') && e.closest('p, li, dd, td, .hinweis-text, .neben, h1, h2, h3, .brotkrumen li')) {
      const block = getComputedStyle(e).display;
      if (block === 'inline') continue;
    }
    const r = ziel.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    if (r.width + 0.5 < mindest || r.height + 0.5 < mindest) fehler.push(`${e.tagName.toLowerCase()} ${(e.textContent || e.name || '').trim().slice(0, 30)} ${Math.round(r.width)}×${Math.round(r.height)}`);
  }
  return fehler;
}

async function zielgroessen(seite, mindest) {
  const fehler = await seite.evaluate(zieleInSeite, mindest);
  return { ok: fehler.length === 0, mindest, fehler: fehler.slice(0, 12), anzahl: fehler.length };
}

// AK56: 640 × 400 (1280 px bei 200 %) mit dem Textabstands-Stylesheet aus WCAG 1.4.12
const TEXTABSTAND = '* { line-height: 1.5 !important; letter-spacing: 0.12em !important; word-spacing: 0.16em !important; } p { margin-bottom: 2em !important; }';
async function zoom(seite) {
  await seite.addStyleTag({ content: TEXTABSTAND });
  await seite.waitForTimeout(100);
  return seite.evaluate(() => {
    const abgeschnitten = [];
    for (const e of document.querySelectorAll('main *, header *')) {
      if (e.closest('.unsichtbar, svg, [hidden], .sprunglink') || e.matches('input, select, textarea')) continue;
      const cs = getComputedStyle(e);
      // visuell versteckt (Screenreader-Text, etwa der Name der Gesellschaft im schmalen Kopf)
      if (cs.clipPath === 'inset(50%)' || (e.getBoundingClientRect().width <= 1 && e.getBoundingClientRect().height <= 1)) continue;
      if (!['hidden', 'clip'].includes(cs.overflowY) && !['hidden', 'clip'].includes(cs.overflowX)) continue;
      if (e.scrollHeight > e.clientHeight + 1 || e.scrollWidth > e.clientWidth + 1) abgeschnitten.push(`${e.tagName.toLowerCase()}.${e.className} ${e.scrollWidth}/${e.clientWidth} ${e.scrollHeight}/${e.clientHeight}`);
    }
    const scroll = document.documentElement.scrollWidth;
    return { ok: scroll <= window.innerWidth && abgeschnitten.length === 0, scroll, fenster: window.innerWidth, abgeschnitten: abgeschnitten.slice(0, 8) };
  });
}

// A107/AK56 bei jeder Breite (Runde 2, D-H1/D-M1): nichts abgeschnitten — kein Inhalt
// breiter oder höher als ein Rahmen mit overflow hidden/clip; ein Rahmen, der scrollt, ist
// fokussierbar und benannt (role=region, aria-label; axe scrollable-region-focusable);
// jedes Bedienelement in Kopf und Inhalt trifft elementFromPoint in seiner Mitte (nach
// scrollIntoView); der Seitentitel im schmalen Kopf liegt ganz in der Kopfleiste; die
// Seite scrollt nicht waagrecht. Läuft in der Seite.
function abschnittInSeite() {
  const befunde = [];
  const name = (e) => `${e.tagName.toLowerCase()}.${String(e.className?.baseVal ?? e.className).trim().replace(/\s+/g, '.')} "${(e.textContent || e.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim().slice(0, 30)}"`;
  const versteckt = (e) => e.closest('.unsichtbar, [hidden], .sprunglink, .druckkopf, details:not([open]) > :not(summary)');
  const klemmt = (w) => w === 'hidden' || w === 'clip';
  const scrollt = (w) => w === 'auto' || w === 'scroll';
  for (const e of document.querySelectorAll('main *, header *')) {
    if (versteckt(e) || e.closest('svg') || e.matches('input, select, textarea, iframe')) continue;
    const cs = getComputedStyle(e);
    const r = e.getBoundingClientRect();
    if (cs.display === 'none' || cs.clipPath === 'inset(50%)' || (r.width <= 1 && r.height <= 1)) continue;
    const breiter = e.scrollWidth > e.clientWidth + 1;
    const hoeher = e.scrollHeight > e.clientHeight + 1;
    if ((breiter && klemmt(cs.overflowX)) || (hoeher && klemmt(cs.overflowY))) {
      befunde.push(`abgeschnitten: ${name(e)} ${e.scrollWidth}/${e.clientWidth} ${e.scrollHeight}/${e.clientHeight}`);
    } else if ((breiter && scrollt(cs.overflowX)) || (hoeher && scrollt(cs.overflowY))) {
      const fokus = e.tabIndex >= 0;
      const benannt = e.getAttribute('role') === 'region' && (e.getAttribute('aria-label') || e.getAttribute('aria-labelledby'));
      if (!fokus || !benannt) befunde.push(`scrollt ohne Fokus/Namen: ${name(e)}`);
    }
  }
  const kopf = document.querySelector('body > header.kopfleiste');
  const titel = document.querySelector('.kopf-titel');
  if (kopf && titel && getComputedStyle(titel).display !== 'none') {
    const k = kopf.getBoundingClientRect();
    const t = titel.getBoundingClientRect();
    const passt = titel.scrollWidth <= titel.clientWidth + 1 && titel.scrollHeight <= titel.clientHeight + 1 && t.top >= k.top - 1 && t.bottom <= k.bottom + 1;
    if (!passt) befunde.push(`Kopftitel passt nicht: "${titel.textContent.trim()}" ${titel.scrollWidth}/${titel.clientWidth} ${Math.round(t.top)}–${Math.round(t.bottom)} in ${Math.round(k.top)}–${Math.round(k.bottom)}`);
  }
  const ziele = document.querySelectorAll('main a[href], main button, main input:not([type=hidden]), main select, main textarea, main summary, header a[href], header button, header summary');
  for (const e of ziele) {
    if (versteckt(e)) continue;
    const cs = getComputedStyle(e);
    if (cs.display === 'none' || cs.visibility === 'hidden' || cs.clipPath === 'inset(50%)') continue;
    const vorab = e.getBoundingClientRect();
    if (vorab.width <= 1 || vorab.height <= 1) continue;
    e.scrollIntoView({ block: 'center', inline: 'center' });
    // ein Link über zwei Zeilen: die Mitte seines ersten Stücks (die Mitte des Rechtecks
    // läge zwischen den Zeilen)
    const r = cs.display === 'inline' ? e.getClientRects()[0] : e.getBoundingClientRect();
    const x = r.left + r.width / 2;
    const y = r.top + r.height / 2;
    const treffer = x >= 0 && y >= 0 && x < innerWidth && y < innerHeight ? document.elementFromPoint(x, y) : null;
    const label = treffer?.closest('label');
    const ok = treffer && (treffer === e || e.contains(treffer) || (label && (label.control === e || label.contains(e))));
    if (!ok) befunde.push(`nicht anklickbar: ${name(e)} trifft ${treffer ? name(treffer) : 'nichts'}`);
  }
  window.scrollTo(0, 0);
  for (const e of document.querySelectorAll('main *')) if (e.scrollLeft) e.scrollLeft = 0;
  const seite = document.documentElement.scrollWidth;
  if (seite > innerWidth) befunde.push(`Seite scrollt waagrecht: ${seite}/${innerWidth}`);
  return befunde;
}

async function abschnitt(seite, abstand = false) {
  if (abstand) {
    await seite.addStyleTag({ content: TEXTABSTAND });
    await seite.waitForTimeout(100);
  }
  const befunde = await seite.evaluate(abschnittInSeite);
  return { ok: befunde.length === 0, abstand, fehler: befunde.slice(0, 12), anzahl: befunde.length };
}

// --- Schritt 14: Abläufe über mehrere Seiten (AK7, AK8, AK45, AK53, AK54) --------------
async function neueSeite(kontext, breite = 1440) {
  const seite = await kontext.newPage();
  await seite.setViewportSize({ width: breite, height: HOEHEN[breite] ?? 900 });
  return seite;
}

// AK7: Wechsel über /gesellschaft ändert Titel und Kennfarbe
async function ak7(browser, welt, name) {
  const kontext = await browser.newContext({ storageState: await anmelden(browser, welt.basis, name, welt.benutzer[name]) });
  const seite = await neueSeite(kontext);
  const lies = async () => seite.evaluate(() => ({ titel: document.title, marke: document.querySelector('.kopf-gesellschaft .marke')?.className, kuerzel: document.querySelector('.kopf-gesellschaft')?.dataset.gesellschaft }));
  await seite.goto(`${welt.basis}/`);
  const vorher = await lies();
  await seite.goto(`${welt.basis}/gesellschaft`);
  const knopf = seite.locator('form[action="/gesellschaft"] button').first();
  await knopf.click();
  await seite.waitForLoadState('load');
  const nachher = await lies();
  // zurück in die erste Gesellschaft (für die übrigen Messungen)
  await seite.goto(`${welt.basis}/gesellschaft`);
  await seite.locator('form[action="/gesellschaft"] button').first().click();
  await seite.waitForLoadState('load');
  await kontext.close();
  const ok = vorher.kuerzel !== nachher.kuerzel && vorher.titel !== nachher.titel && / · accounti$/.test(nachher.titel) && vorher.marke !== nachher.marke;
  return { ok, vorher, nachher };
}

// AK8: Druckansicht einer Liste ohne Navigation und Knöpfe, mit Druckkopf; Runde 2 (A97)
// auch im Hochformat (794 px, sonst Kartenform) und im Dunkelmodus: keine nav (Reiter),
// das h1 sichtbar, Tabellenkopf als table-header-group, Text schwarz auf weißen Flächen
async function ak8(browser, welt, stand, pfad, breite = 1440, schema = 'light') {
  const kontext = await browser.newContext({ storageState: stand, colorScheme: schema });
  const seite = await neueSeite(kontext, breite);
  await seite.goto(welt.basis + pfad);
  await seite.emulateMedia({ media: 'print', colorScheme: schema });
  await seite.waitForTimeout(300); // Farbübergänge (120 ms) abwarten
  const w = await seite.evaluate(() => {
    const zu = (sel) => [...document.querySelectorAll(sel)].filter((e) => getComputedStyle(e).display !== 'none' && e.getBoundingClientRect().height > 0).length;
    const h1 = document.querySelector('main h1:not(.unsichtbar)');
    const kopf = [...document.querySelectorAll('main table thead')].map((t) => `${getComputedStyle(t).display} ${Math.round(t.getBoundingClientRect().height)}`);
    const farben = [...document.querySelectorAll('main .karte, main .tabelle-rahmen, main td, main a, main h1, main p')].map((e) => getComputedStyle(e)).flatMap((c) => [c.color, c.backgroundColor]);
    const fremd = [...new Set(farben)].filter((f) => !['rgb(0, 0, 0)', 'rgb(255, 255, 255)', 'rgba(0, 0, 0, 0)'].includes(f));
    // Runde 3 (gp1-2-design N-2): auf dem Papier scrollt kein Rahmen — keine Tabelle
    // breiter als ihr Rahmen, Zellen mit waagrechtem Abstand, Beträge rechtsbündig
    const tabellen = [...document.querySelectorAll('main .tabelle-rahmen')].filter((r) => r.getBoundingClientRect().height > 0).map((r) => {
      const td = r.querySelector('tbody td');
      const zahl = r.querySelector('tbody td.zahl');
      const c = td ? getComputedStyle(td) : null;
      return { breiter: r.scrollWidth > r.clientWidth + 1, abstand: c ? parseFloat(c.paddingLeft) + parseFloat(c.paddingRight) : 99, zahl: zahl ? getComputedStyle(zahl).textAlign : 'right' };
    });
    return { navigation: zu('.kopfleiste, .seitenleiste, .untere-leiste, main nav'), knoepfe: zu('button, .knopf'), druckkopf: getComputedStyle(document.querySelector('.druckkopf')).display, h1: h1 ? Math.round(h1.getBoundingClientRect().height) : 0, kopf, fremd, tabellen };
  });
  await kontext.close();
  const papier = w.tabellen.every((t) => !t.breiter && t.abstand >= 4 && ['right', 'end'].includes(t.zahl));
  const ok = w.navigation === 0 && w.knoepfe === 0 && w.druckkopf !== 'none' && w.h1 > 1 && w.kopf.every((k) => /^table-header-group [1-9]/.test(k)) && w.fremd.length === 0 && papier;
  return { ok, pfad, breite, schema, ...w };
}

async function vorliebe(seite, basis, felder) {
  await seite.goto(`${basis}/konto`);
  for (const [name, wert] of Object.entries(felder)) await seite.check(`form.layout-formular input[name="${name}"][value="${wert}"]`);
  await seite.locator('form[action="/konto/vorlieben"].layout-formular button[type=submit]').click();
  await seite.waitForLoadState('load');
}

// AK45: Darstellung am Benutzer gilt im neuen Kontext; „auto“ folgt der Emulation;
// „Tastenkürzel aus“: f löst auf der Arbeitsfläche keine Anfrage aus
async function ak45(browser, welt, name, arbeitsflaeche) {
  const befunde = [];
  const stand = await anmelden(browser, welt.basis, name, welt.benutzer[name]);
  let kontext = await browser.newContext({ storageState: stand });
  let seite = await neueSeite(kontext);
  await vorliebe(seite, welt.basis, { darstellung: 'dunkel', tastenkuerzel: 'aus' });
  await kontext.close();
  kontext = await browser.newContext({ storageState: await anmelden(browser, welt.basis, name, welt.benutzer[name]), colorScheme: 'light' });
  seite = await neueSeite(kontext);
  await seite.goto(`${welt.basis}/`);
  const dunkel = await seite.evaluate(() => ({ theme: document.documentElement.dataset.theme, schema: getComputedStyle(document.documentElement).colorScheme, grund: getComputedStyle(document.body).backgroundColor }));
  befunde.push({ name: 'dunkel im neuen Kontext', ok: dunkel.theme === 'dunkel' && dunkel.schema === 'dark' && dunkel.grund === 'rgb(18, 20, 23)', wert: dunkel });
  const anfragen = [];
  seite.on('request', (r) => { if (r.method() === 'POST') anfragen.push(r.url()); });
  await seite.goto(welt.basis + arbeitsflaeche);
  await seite.locator('main h1').focus().catch(() => {});
  await seite.keyboard.press('f');
  await seite.waitForTimeout(500);
  befunde.push({ name: 'Taste f ohne Anfrage', ok: anfragen.length === 0, wert: [...anfragen] });
  // Runde 2: auch „?“ ist ein Einzeichen-Kürzel (WCAG 2.1.4) — die Tastenhilfe bleibt zu
  await seite.keyboard.press('?');
  await seite.waitForTimeout(200);
  const offen = await seite.evaluate(() => document.querySelector('#tastenhilfe')?.open ?? null);
  befunde.push({ name: 'Taste ? ohne Wirkung', ok: offen === false, wert: offen });
  await vorliebe(seite, welt.basis, { darstellung: 'auto', tastenkuerzel: 'an' });
  for (const [schema, grund] of [['dark', 'rgb(18, 20, 23)'], ['light', 'rgb(245, 244, 241)']]) {
    await seite.emulateMedia({ colorScheme: schema });
    await seite.goto(`${welt.basis}/`);
    const w = await seite.evaluate(() => ({ theme: document.documentElement.dataset.theme, grund: getComputedStyle(document.body).backgroundColor }));
    befunde.push({ name: `auto folgt ${schema}`, ok: w.theme === 'auto' && w.grund === grund, wert: w });
  }
  await kontext.close();
  return { ok: befunde.every((b) => b.ok), befunde };
}

// AK53: Einfügen in jedes Codefeld; „Wiederherstellungscode verwenden“ ohne JS, weiter bleibt
async function ak53(browser, welt, name) {
  const befunde = [];
  const stand = await anmelden(browser, welt.basis, name, welt.benutzer[name]);
  const kontext = await browser.newContext({ storageState: stand, permissions: ['clipboard-read', 'clipboard-write'] });
  for (const pfad of ['/freigaben', `/buchungen/${welt.seiten.find((s) => s.vorlage === '/buchungen/{buchung_id:uuid}').pfad.split('/').pop()}`]) {
    const seite = await neueSeite(kontext);
    await seite.goto(welt.basis + pfad);
    for (const id of await seite.locator('input[name=einmalcode]').evaluateAll((l) => l.map((e) => e.id))) {
      await seite.evaluate(() => navigator.clipboard.writeText('123 456'));
      await seite.locator(`#${id}`).focus();
      await seite.keyboard.press('Control+V');
      const wert = await seite.locator(`#${id}`).inputValue();
      befunde.push({ name: `Einfügen ${pfad} #${id}`, ok: wert === '123 456', wert });
    }
    await seite.close();
  }
  await kontext.close();
  const ohneJs = await browser.newContext({ javaScriptEnabled: false });
  const seite = await neueSeite(ohneJs, 390);
  await seite.goto(`${welt.basis}/anmelden?weiter=/pruefen`);
  await seite.evaluate(() => navigator.clipboard?.writeText).catch(() => {});
  await seite.getByText('Wiederherstellungscode verwenden').click();
  await seite.waitForLoadState('load');
  const w = { url: seite.url(), modus: await seite.locator('#einmalcode').getAttribute('inputmode'), weiter: await seite.locator('input[name=weiter]').inputValue() };
  befunde.push({ name: 'Wiederherstellungscode ohne JS', ok: /code=wiederherstellung/.test(w.url) && w.modus === 'text' && w.weiter === '/pruefen', wert: w });
  await ohneJs.close();
  return { ok: befunde.every((b) => b.ok), befunde };
}

// Runde 2 (A104, gp1-bestand N1/N3): nach „Freigeben“ per htmx liegt der Fokus auf der
// Überschrift des neuen Inhalts, nicht auf body; „Übernehmen“ im Benutzermenü und
// „Tastenkürzel ausschalten“ führen auf die Buchung zurück, die der Browser jetzt zeigt
// (mit ?ansicht=). Läuft nach AK54 und gibt den ersten offenen Vorschlag frei (es muss
// danach noch einer offen sein); stellt die Kürzel wieder an.
async function rueckweg(browser, welt, name) {
  const befunde = [];
  const kontext = await browser.newContext({ storageState: await anmelden(browser, welt.basis, name, welt.benutzer[name]) });
  const seite = await neueSeite(kontext);
  await seite.goto(`${welt.basis}/pruefen?ansicht=offen`);
  const erster = await seite.locator('main a[href^="/pruefen/"][href*="ansicht=offen"]').first().getAttribute('href');
  const ziel = welt.basis + erster;
  await seite.goto(ziel);
  const knopf = seite.locator('form.freigeben button[type=submit]');
  await knopf.focus();
  await knopf.press('Enter');
  await seite.waitForURL((u) => u.href !== ziel, { timeout: 8000 }).catch(() => {});
  await seite.waitForTimeout(400);
  const nachher = seite.url();
  const fokus = await seite.evaluate(() => ({ data: document.activeElement?.hasAttribute('data-fokus') ?? false, el: document.activeElement?.outerHTML.slice(0, 60) }));
  befunde.push({ name: 'Fokus nach dem Austausch', ok: nachher !== ziel && fokus.data, wert: { url: nachher, ...fokus } });
  await seite.locator('summary.benutzermenue-ausloeser').click();
  await seite.locator('form.benutzermenue-wahl button[type=submit]').click();
  await seite.waitForLoadState('load');
  befunde.push({ name: 'Übernehmen bleibt auf der Buchung', ok: seite.url() === nachher, wert: { erwartet: nachher, ist: seite.url() } });
  await seite.locator('#tastenhilfe > summary').click();
  await seite.locator('form.tasten-schalter button[type=submit]').click();
  await seite.waitForLoadState('load');
  befunde.push({ name: 'Tastenkürzel-Schalter bleibt auf der Buchung', ok: seite.url() === nachher, wert: { erwartet: nachher, ist: seite.url() } });
  // Runde 3 (gp1-2 N-1, gw-web N4): eine Seite als Antwort auf ein POST steht unter dem
  // Pfad des POST — „Übernehmen“ führt auf die Seite darüber, nicht auf ein GET mit 405
  await seite.goto(`${welt.basis}/pruefen/regeln`);
  const regel = seite.locator('form[action$="/deaktivieren"]').first();
  if (await regel.count()) {
    await regel.evaluate((f) => { f.noValidate = true; });
    const [fehler] = await Promise.all([seite.waitForNavigation(), regel.locator('button[type=submit]').click()]);
    const unter = new URL(seite.url()).pathname;
    await seite.locator('summary.benutzermenue-ausloeser').click();
    const [antwort] = await Promise.all([seite.waitForNavigation(), seite.locator('form.benutzermenue-wahl button[type=submit]').click()]);
    const ist = new URL(seite.url()).pathname;
    const vorbedingung = fehler?.status() === 422 && unter.endsWith('/deaktivieren');
    befunde.push({ name: 'Übernehmen nach einer Seite unter POST-Pfad', ok: vorbedingung && ist === '/pruefen/regeln' && antwort?.status() === 200, wert: { unter, fehlerstatus: fehler?.status(), ist, status: antwort?.status() } });
  } else {
    // ohne aktive Regel misst der Schritt nichts — das ist ein Befund, kein Grün (gp1-3 B6)
    befunde.push({ name: 'Übernehmen nach einer Seite unter POST-Pfad', ok: false, wert: 'keine aktive Regel in der Welt' });
  }
  await vorliebe(seite, welt.basis, { tastenkuerzel: 'an' });
  await kontext.close();
  return { ok: befunde.every((b) => b.ok), befunde };
}

// AK54: nach einer Freigabe per htmx steht das Ergebnis in #status; während der Anfrage
// trägt das Ziel aria-busy="true" (Antwort verzögert über page.route)
async function ak54(browser, welt, name, arbeitsflaeche) {
  const kontext = await browser.newContext({ storageState: await anmelden(browser, welt.basis, name, welt.benutzer[name]) });
  const seite = await neueSeite(kontext);
  await seite.goto(welt.basis + arbeitsflaeche);
  await seite.route('**/freigeben', async (route) => { await new Promise((r) => setTimeout(r, 800)); await route.continue(); });
  await seite.locator('form.freigeben button[type=submit]').click();
  await seite.waitForTimeout(300);
  const busy = await seite.locator('#arbeitsflaeche').getAttribute('aria-busy');
  await seite.waitForFunction(() => document.querySelector('#status')?.textContent.trim().length > 0, null, { timeout: 8000 }).catch(() => {});
  const status = await seite.evaluate(() => ({ text: document.querySelector('#status')?.textContent.trim(), rolle: document.querySelector('#status')?.getAttribute('role'), busy: document.querySelector('#arbeitsflaeche')?.getAttribute('aria-busy') }));
  await kontext.close();
  return { ok: busy === 'true' && status.rolle === 'status' && /freigegeben|approved/i.test(status.text ?? '') && status.busy !== 'true', waehrend: busy, ...status };
}

const TASTATUR = new Set(['/pruefen', '/pruefen/{buchung_id:uuid}', '/konto']);

// Abläufe einmal je Lauf (--ablaeufe): AK7 (jan: zwei Gesellschaften), AK8, AK45, AK53,
// AK54 (gibt den Vorschlag der Welt frei), zuletzt der Rückweg (Runde 2)
async function ablaeufe(browser, welt) {
  const flaeche = welt.seiten.find((s) => s.vorlage === '/pruefen/{buchung_id:uuid}').pfad;
  const eintrag = (name, messung) => ({ benutzer: 'ablauf', pfad: name, thema: 'hell', breite: 1440, status: 200, messungen: { [name]: messung }, ok: messung.ok });
  const sicher = async (lauf) => { try { return await lauf(); } catch (f) { return { ok: false, fehler: String(f).slice(0, 300) }; } };
  const liste = [];
  liste.push(eintrag('ak7', await sicher(() => ak7(browser, welt, 'jan'))));
  const stand = await anmelden(browser, welt.basis, 'alle', welt.benutzer.alle);
  for (const pfad of ['/pruefen', '/freigaben', '/pruefen/regeln']) {
    for (const [breite, schema] of [[1440, 'light'], [794, 'light'], [794, 'dark']]) {
      liste.push(eintrag(`ak8 ${pfad} ${breite} ${schema}`, await sicher(() => ak8(browser, welt, stand, pfad, breite, schema))));
    }
  }
  liste.push(eintrag('ak45', await sicher(() => ak45(browser, welt, 'alle', flaeche))));
  liste.push(eintrag('ak53', await sicher(() => ak53(browser, welt, 'alle'))));
  liste.push(eintrag('ak54', await sicher(() => ak54(browser, welt, 'alle', flaeche))));
  liste.push(eintrag('rueckweg', await sicher(() => rueckweg(browser, welt, 'alle'))));
  for (const e of liste) process.stdout.write(e.ok ? '.' : 'F');
  return liste;
}

// --- Ablauf ---------------------------------------------------------------------------
function datei(text) {
  return text.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '') || 'start';
}

async function main() {
  if (!opt.welt) throw new Error('--welt PFAD/probe.json fehlt (python -m tests.browserprobe_welt)');
  const welt = JSON.parse(readFileSync(opt.welt, 'utf8'));
  const browserTyp = { chromium, firefox }[opt.browser];
  if (!browserTyp) throw new Error(`--browser ${opt.browser}: nur chromium oder firefox`);
  const axe = axeQuelle();
  const breiten = opt.breiten.split(',').map(Number);
  const themen = opt.themen.split(',');
  const auslassen = new Set(opt.auslassen.split(',').filter(Boolean));
  const benutzer = opt.benutzer ? opt.benutzer.split(',') : Object.keys(welt.benutzer);
  const filter = opt.seiten ? opt.seiten.split(',') : null;
  const tag = new Date().toISOString().slice(0, 10);
  const bildordner = path.join(opt.ziel, `${tag}-${opt.browser}`);
  mkdirSync(bildordner, { recursive: true });

  const seiten = [];
  for (const s of welt.seiten) {
    if (s.art !== 'html') continue;
    if (filter && !filter.some((f) => s.pfad === f || s.vorlage === f)) continue;
    seiten.push(s);
    if (s.vorlage === '/muster') {
      for (const t of ['hell', 'dunkel']) seiten.push({ ...s, pfad: `/muster?theme=${t}`, thema: t });
    }
  }

  if (opt.fehlerseite) {
    // die 404 im Gerüst (angemeldet) — axe, CSP und Breite auch für Fehlerseiten
    const erwartet = Object.fromEntries(Object.keys(welt.benutzer).map((n) => [n, 404]));
    seiten.push({ vorlage: '(404)', pfad: '/browserprobe-gibt-es-nicht', art: 'html', erwartet, status: 404 });
  }

  const browser = await browserTyp.launch();
  const ergebnisse = [];
  try {
    for (const name of benutzer) {
      const stand = await anmelden(browser, welt.basis, name, welt.benutzer[name]);
      const normal = await browser.newContext({ storageState: stand });
      const umgangen = await browser.newContext({ storageState: stand, bypassCSP: true });
      // grober Zeiger (pointer: coarse) für die Zielgrößen 44 × 44 — Firefox kennt isMobile nicht
      const grob = opt.browser === 'chromium'
        ? await browser.newContext({ storageState: stand, hasTouch: true, isMobile: true, viewport: { width: 390, height: 844 } })
        : null;
      for (const s of seiten) {
        if (s.erwartet[name] !== (s.status ?? 200)) continue;
        for (const thema of s.thema ? [s.thema] : themen) {
          for (const breite of breiten) {
            const eintrag = { benutzer: name, pfad: s.pfad, thema, breite, messungen: {} };
            const viewport = { width: breite, height: HOEHEN[breite] ?? 900 };
            const colorScheme = thema === 'dunkel' ? 'dark' : 'light';
            // Kontext ohne Umgehung: CSP-Meldungen, Scrollbreite, Maße, Fokus, Bild
            const seite = await normal.newPage();
            await seite.setViewportSize(viewport);
            await seite.emulateMedia({ colorScheme });
            const konsole = [];
            seite.on('console', (m) => {
              if (/Content[ -]Security[ -]Policy|Refused to/i.test(m.text())) konsole.push(m.text());
            });
            seite.on('pageerror', (e) => konsole.push(`Fehler: ${e.message}`));
            const antwort = await seite.goto(welt.basis + s.pfad, { waitUntil: 'load' });
            eintrag.status = antwort?.status();
            const fenster = await seite.evaluate(() => window.innerWidth);
            if (fenster !== breite) throw new Error(`Fenster ${fenster} statt ${breite} px`);
            if (breite <= 390) eintrag.messungen.ak1 = await MESSUNGEN.ak1(seite);
            if (s.vorlage === '/muster' && !auslassen.has('masse') && breite === 1440) {
              if (s.thema) {
                eintrag.messungen.masse = await massprobe(seite, null, thema, breite, !auslassen.has('geruest'));
              } else {
                for (const t of ['hell', 'dunkel']) {
                  eintrag.messungen[`masse_${t}`] = await massprobe(seite, `.thema-${t}`, t, breite, false);
                }
              }
            }
            if (s.vorlage === '/muster' && s.thema && breite <= 390 && !auslassen.has('masse') && !auslassen.has('geruest')) {
              eintrag.messungen.geruest_schmal = await massprobe(seite, null, thema, breite, true);
            }
            if (opt.bilder) {
              await seite.screenshot({ path: path.join(bildordner, `${name}-${datei(s.pfad)}-${breite}-${thema}.png`), fullPage: true });
            }
            if (!auslassen.has('seite')) {
              eintrag.messungen.seite = await seitenmessung(seite, breite, thema);
              if (breite !== 320) eintrag.messungen.ziele = await zielgroessen(seite, 24);
              if (breite === 390) eintrag.messungen.ak52 = await ariaTabelle(seite);
              if (breite === 1440 && thema === 'hell') eintrag.messungen.bewegung = await bewegung(seite);
            }
            // Abgeschnittenes bei jeder Breite (Runde 2); mit Textabständen einmal je Breite
            if (!auslassen.has('abschnitt')) {
              eintrag.messungen.abschnitt = await abschnitt(seite);
              if (thema === (s.thema ?? themen[0])) {
                const z = await umgangen.newPage();
                await z.setViewportSize(viewport);
                await z.emulateMedia({ colorScheme });
                await z.goto(welt.basis + s.pfad, { waitUntil: 'load' });
                eintrag.messungen.abschnitt_abstand = await abschnitt(z, true);
                await z.close();
              }
            }
            if (s.vorlage === '/muster' && !s.thema && breite === 1440 && !auslassen.has('fokus')) {
              eintrag.messungen.fokus = await MESSUNGEN.fokus(seite);
            }
            await seite.waitForTimeout(100);
            eintrag.messungen.ak5 = { ok: konsole.length === 0, meldungen: konsole };
            await seite.close();
            // Kontext mit bypassCSP: axe-core
            if (breite !== 320 && !auslassen.has('axe')) {
              const p = await umgangen.newPage();
              await p.setViewportSize(viewport);
              await p.emulateMedia({ colorScheme });
              await p.goto(welt.basis + s.pfad, { waitUntil: 'load' });
              eintrag.messungen.ak2 = await MESSUNGEN.ak2(p, { axe });
              await p.close();
            }
            // AK55: Tastatur durch /pruefen, die Arbeitsfläche und /konto
            if (TASTATUR.has(s.vorlage) && breite !== 320 && !auslassen.has('tastatur')) {
              const t = await normal.newPage();
              await t.setViewportSize(viewport);
              await t.emulateMedia({ colorScheme });
              await t.goto(welt.basis + s.pfad, { waitUntil: 'load' });
              eintrag.messungen.ak55 = await tastatur(t);
              await t.close();
            }
            // AK55 mit grobem Zeiger: Ziele ≥ 44 × 44
            if (grob && breite === 390 && !auslassen.has('seite')) {
              const g = await grob.newPage();
              await g.emulateMedia({ colorScheme });
              await g.goto(welt.basis + s.pfad, { waitUntil: 'load' });
              eintrag.messungen.ziele_grob = await zielgroessen(g, 44);
              await g.close();
            }
            // AK56: 640 × 400 (200 % Zoom) mit Textabständen — einmal je Seite und Thema
            if (breite === 1440 && !auslassen.has('zoom')) {
              const z = await umgangen.newPage();
              await z.setViewportSize({ width: 640, height: 400 });
              await z.emulateMedia({ colorScheme });
              await z.goto(welt.basis + s.pfad, { waitUntil: 'load' });
              eintrag.messungen.ak56 = await zoom(z);
              await z.close();
            }
            eintrag.ok = Object.values(eintrag.messungen).every((m) => m.ok) && eintrag.status === (s.status ?? 200);
            ergebnisse.push(eintrag);
            process.stdout.write(eintrag.ok ? '.' : 'F');
          }
        }
      }
      await normal.close();
      await umgangen.close();
      if (grob) await grob.close();
    }
    if (opt.ablaeufe) ergebnisse.push(...(await ablaeufe(browser, welt)));
    if (opt.vergleich) await vergleich(browser, welt, opt.vergleich, tag, benutzer[0]);
  } finally {
    await browser.close();
  }
  const befunde = ergebnisse.filter((e) => !e.ok);
  const bericht = { browser: opt.browser, datum: new Date().toISOString(), seiten: ergebnisse.length, befunde: befunde.length, ergebnisse };
  const ausgabe = path.join(opt.ziel, `${tag}-${opt.browser}.json`);
  writeFileSync(ausgabe, JSON.stringify(bericht, null, 2));
  console.log(`\n${ergebnisse.length} Messungen, ${befunde.length} mit Befund → ${ausgabe}`);
  for (const b of befunde) {
    const was = Object.entries(b.messungen).filter(([, m]) => !m.ok).map(([k, m]) => `${k}: ${JSON.stringify(m.verstoesse ?? m.fehler ?? m.meldungen ?? m).slice(0, 400)}`);
    console.log(`  ${b.benutzer} ${b.pfad} ${b.breite} ${b.thema} (Status ${b.status}): ${was.join('; ')}`);
  }
  process.exitCode = befunde.length ? 1 : 0;
}

// L10 Punkte 2 und 3: Bilder der Anwendung neben den Referenzbildern der Leinwand
const VERGLEICH = [
  { pfad: '/muster', breite: 1440, themen: ['beide'], leinwand: 'Bausteine', satz: 'P1: alle Komponenten der Zeichenfläche, hell und dunkel nebeneinander, dazu die Ergänzungen aus L9.' },
  { pfad: '/muster?theme=hell', breite: 390, themen: ['hell'], leinwand: 'Bausteine', satz: 'P1: ein Rahmen im echten Gerüst bei 390 px.' },
  { pfad: '/muster?theme=dunkel', breite: 390, themen: ['dunkel'], leinwand: 'Bausteine', satz: 'P1: ein Rahmen im echten Gerüst bei 390 px.' },
  { pfad: '/', breite: 1440, themen: ['hell', 'dunkel'], leinwand: 'Main', satz: 'P1: Gerüst, Seitenleiste, Kennzahl-Karten; die sechs Karten „Heute zu tun“ bringt P2.' },
  { pfad: '/', breite: 390, themen: ['hell', 'dunkel'], leinwand: 'Handy-Uebersicht', satz: 'P1: schmaler Kopf und untere Leiste; Karten mit Daten P2.' },
  { pfad: '/pruefen', breite: 1440, themen: ['hell', 'dunkel'], leinwand: 'Pruefen-Liste', satz: 'P1: Reiter und Tabelle in der Optik der Leinwand; Gruppen, Auswahl und Sammelleiste P3.' },
  { pfad: '/pruefen', breite: 390, themen: ['hell', 'dunkel'], leinwand: 'Handy-Pruefen', satz: 'P1: Tabelle als Karten; geteilte Reiter und Aktionsleiste P3.' },
  { pfad: '/freigaben', breite: 390, themen: ['hell'], leinwand: 'Handy-Freigaben', satz: 'P1: Karte je Lauf mit Codefeld; Aufklapper und USt-VA-Karte P2.' },
  { pfad: '/menue', breite: 390, themen: ['hell'], leinwand: 'Handy-Mehr', satz: 'P1 vollständig.' },
  { vorlage: '/pruefen/{buchung_id:uuid}', breite: 1440, themen: ['hell', 'dunkel'], leinwand: 'Pruefen-Arbeitsflaeche', satz: 'P1: Positionszeile, Beleg | Vorschlag-Karte und Aktionen im Gerüst; drei Schritte, Tasten 1–3 und Fokusmodus P3.' },
  { vorlage: '/pruefen/{buchung_id:uuid}', breite: 390, themen: ['hell'], leinwand: 'Handy-Pruefen', satz: 'P1: Arbeitsfläche untereinander mit unterer Leiste; Aktionsleiste und geteilte Reiter P3.' },
];

async function vergleich(browser, welt, leinwandOrdner, tag, name) {
  const ordner = path.join(opt.ziel, `${tag}-vergleich`);
  mkdirSync(ordner, { recursive: true });
  const stand = await anmelden(browser, welt.basis, name, welt.benutzer[name]);
  const kontext = await browser.newContext({ storageState: stand });
  const zeilen = [];
  for (const eintrag of VERGLEICH) {
    const v = eintrag.vorlage ? { ...eintrag, pfad: welt.seiten.find((s) => s.vorlage === eintrag.vorlage).pfad } : eintrag;
    for (const thema of v.themen) {
      const seite = await kontext.newPage();
      await seite.setViewportSize({ width: v.breite, height: HOEHEN[v.breite] ?? 900 });
      await seite.emulateMedia({ colorScheme: thema === 'dunkel' ? 'dark' : 'light' });
      const antwort = await seite.goto(welt.basis + v.pfad);
      const bild = `${datei(v.pfad)}-${v.breite}-${thema}.png`;
      if (antwort?.status() === 200) await seite.screenshot({ path: path.join(ordner, bild), fullPage: true });
      await seite.close();
      const referenzen = (thema === 'beide' ? ['hell', 'dunkel'] : [thema])
        .map((t) => path.resolve(leinwandOrdner, `${v.leinwand}-${t}.png`))
        .filter((p) => existsSync(p));
      zeilen.push({ ...v, thema, bild: antwort?.status() === 200 ? bild : null, status: antwort?.status(), referenzen });
    }
  }
  await kontext.close();
  const html = ['<!doctype html><meta charset="utf-8"><title>Vergleich Leinwand – Umsetzung</title>',
    '<style>body{font-family:system-ui;margin:24px}figure{margin:0}img{max-width:100%;border:1px solid #ccc}.paar{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:24px 0 48px}</style>',
    `<h1>Leinwand | Umsetzung (${tag})</h1>`];
  for (const z of zeilen) {
    html.push(`<h2>${z.pfad} · ${z.breite} px · ${z.thema}</h2><p>${z.satz}</p><div class="paar"><figure>`);
    for (const r of z.referenzen) html.push(`<img src="${pathToFileURL(r).href}" alt="Leinwand ${z.leinwand}">`);
    html.push(`<figcaption>Leinwand: ${z.leinwand}</figcaption></figure><figure>`);
    html.push(z.bild ? `<img src="${z.bild}" alt="Umsetzung ${z.pfad}">` : `<p>nicht vorhanden (Status ${z.status})</p>`);
    html.push('<figcaption>Umsetzung</figcaption></figure></div>');
  }
  const ziel = path.join(ordner, `${tag}-vergleich.html`);
  writeFileSync(ziel, html.join('\n'));
  console.log(`\nGegenüberstellung: ${ziel}`);
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
