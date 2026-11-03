// Browserprobe der Oberfläche (Spec 10c A112, AK1/AK2/AK5 …; Plan P1, Schritte 5 und 14).
//
//   node scripts/browserprobe/probe.mjs --welt DIR/probe.json [--browser chromium]
//        [--benutzer jan,fritz] [--seiten /muster,/pruefen] [--breiten 1440,390,320]
//        [--themen hell,dunkel] [--auslassen geruest] [--bilder]
//        [--vergleich scripts/browserprobe/ergebnisse/leinwand]
//
// Meldet sich je Benutzer an (TOTP aus probe.json mit node:crypto), öffnet jede
// erlaubte HTML-Seite der Welt je Breite und Thema und misst: kein waagrechtes Scrollen
// (AK1, 320/390 px), axe-core 4.14.0 mit WCAG 2.0–2.2 A/AA (AK2, 1440/390 px, in einem
// Kontext mit bypassCSP), keine CSP-Meldung in der Konsole (AK5, Kontext ohne
// Umgehung). Auf /muster dazu der Fokus nach dem Austausch (A104) und die Maßprobe
// (L10 Punkt 4) in beiden Themenrahmen und mit ?theme=. --vergleich legt Bilder der
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
const HOEHEN = { 1440: 900, 390: 844, 320: 568 };

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

  const browser = await browserTyp.launch();
  const ergebnisse = [];
  try {
    for (const name of benutzer) {
      const stand = await anmelden(browser, welt.basis, name, welt.benutzer[name]);
      const normal = await browser.newContext({ storageState: stand });
      const umgangen = await browser.newContext({ storageState: stand, bypassCSP: true });
      for (const s of seiten) {
        if (s.erwartet[name] !== 200) continue;
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
            eintrag.ok = Object.values(eintrag.messungen).every((m) => m.ok) && eintrag.status === 200;
            ergebnisse.push(eintrag);
            process.stdout.write(eintrag.ok ? '.' : 'F');
          }
        }
      }
      await normal.close();
      await umgangen.close();
    }
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
];

async function vergleich(browser, welt, leinwandOrdner, tag, name) {
  const ordner = path.join(opt.ziel, `${tag}-vergleich`);
  mkdirSync(ordner, { recursive: true });
  const stand = await anmelden(browser, welt.basis, name, welt.benutzer[name]);
  const kontext = await browser.newContext({ storageState: stand });
  const zeilen = [];
  for (const v of VERGLEICH) {
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
