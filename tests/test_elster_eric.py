"""ERiC-Adapter über ctypes — gegen eine im Test gebaute C-Attrappe von libericapi.

Die Attrappe bildet nur die Aufrufschnittstelle der Mt-API nach (Instanz,
Rückgabepuffer, Zertifikat, EricMtBearbeiteVorgang, Fehlertext); sie spricht kein Netz
an.
"""

import shutil
import subprocess
from datetime import date
from decimal import Decimal

import pytest

from accounti.elster.datensatz import TESTMERKER, Absender, Kopf, ustva_xml
from accounti.elster.eric import EricUebermittler
from accounti.steuer.voranmeldung import UStVoranmeldung
from accounti.steuer.zeitraum import Zeitraum

ATTRAPPE_C = r"""
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { char *inhalt; } Puffer;
typedef struct {
    uint32_t version, vorschau, ersteSeite, duplexDruck;
    const char *pdfName, *fussText;
    void *pdfCallback, *pdfCallbackBenutzerdaten;
} Druck;
typedef struct {
    uint32_t version, zertifikatHandle;
    const char *pin, *abrufCode;
} Krypto;

static int instanz = 42;

void *EricMtInstanzErzeugen(const char *plugins, const char *log) {
    return plugins && log ? &instanz : NULL;
}
int EricMtInstanzFreigeben(void *i) { return i == &instanz ? 0 : 1; }
void *EricMtRueckgabepufferErzeugen(void *i) {
    Puffer *p = calloc(1, sizeof(Puffer));
    p->inhalt = strdup("");
    return p;
}
const char *EricMtRueckgabepufferInhalt(void *i, void *p) {
    return ((Puffer *)p)->inhalt;
}
int EricMtRueckgabepufferFreigeben(void *i, void *p) {
    free(((Puffer *)p)->inhalt);
    free(p);
    return 0;
}
static void setze(void *p, const char *text) {
    free(((Puffer *)p)->inhalt);
    ((Puffer *)p)->inhalt = strdup(text);
}
int EricMtGetHandleToCertificate(void *i, uint32_t *h, uint32_t *pin,
                                 const char *pfad) {
    if (strstr(pfad, ".pfx") == NULL) return 610201016;
    *h = 7;
    if (pin) *pin = 0;
    return 0;
}
int EricMtCloseHandleToCertificate(void *i, uint32_t h) { return h == 7 ? 0 : 1; }
int EricMtHoleFehlerText(void *i, int kode, void *p) {
    char text[128];
    snprintf(text, sizeof text, "Fehlertext der Attrappe zu %d", kode);
    setze(p, text);
    return 0;
}
int EricMtBearbeiteVorgang(void *i, const char *xml, const char *datenart,
                           uint32_t flags, const Druck *druck, const Krypto *krypto,
                           void *transfer, void *rueckgabe, void *antwort) {
    if (strcmp(datenart, "UStVA_2026") != 0) {
        /* ein anderer Fehlercode, und trotzdem kommen Hinweise zurück */
        setze(rueckgabe, "<EricBearbeiteVorgang><Hinweis><Text>Hinweis trotz Fehler"
                         "</Text></Hinweis></EricBearbeiteVorgang>");
        return 610001042;
    }
    if (strstr(xml, "<HerstellerID>74931<")) return 610301202;
    if (strstr(xml, "<Kz83>") == NULL) {
        setze(rueckgabe, "<EricBearbeiteVorgang><FehlerRegelpruefung>"
                         "<Text>Kz83 fehlt</Text></FehlerRegelpruefung>"
                         "</EricBearbeiteVorgang>");
        return 610001002;
    }
    if (flags & 4) {
        if (!krypto || krypto->zertifikatHandle != 7 || strcmp(krypto->pin, "123456"))
            return 610201016;
        char text[512];
        snprintf(text, sizeof text,
                 "<EricBearbeiteVorgang><Erfolg><Telenummer/></Erfolg><Transfers>"
                 "<Transfer><TransferTicket>et-attrappe-%u-%u</TransferTicket>"
                 "</Transfer></Transfers></EricBearbeiteVorgang>",
                 krypto->version, druck ? druck->version : 0);
        setze(rueckgabe, text);
        setze(antwort, "<Elster xmlns=\"http://www.elster.de/elsterxml/schema/v11\">"
                       "<TransferHeader version=\"11\"><RC><Rueckgabe><Code>0</Code>"
                       "<Text>Daten wurden erfolgreich angenommen.</Text></Rueckgabe>"
                       "</RC></TransferHeader></Elster>");
        if ((flags & 32) && druck && druck->pdfName) {
            FILE *f = fopen(druck->pdfName, "wb");
            fputs("%PDF-1.4 Attrappe", f);
            fclose(f);
        }
        return 0;
    }
    if (flags & 128) {
        setze(rueckgabe, "<EricBearbeiteVorgang><Hinweis><Text>Hinweis der Attrappe"
                         "</Text></Hinweis></EricBearbeiteVorgang>");
        return 610001003; /* ERIC_GLOBAL_HINWEISE */
    }
    return 0;
}
"""


@pytest.fixture(scope="module")
def bibliothek(tmp_path_factory):
    compiler = shutil.which("cc") or shutil.which("gcc")
    if compiler is None:
        pytest.skip("kein C-Compiler für die ERiC-Attrappe")
    ordner = tmp_path_factory.mktemp("eric")
    quelle = ordner / "attrappe.c"
    quelle.write_text(ATTRAPPE_C, encoding="utf-8")
    ziel = ordner / "libericapi.so"
    subprocess.run(
        [compiler, "-shared", "-fPIC", "-o", str(ziel), str(quelle)], check=True
    )
    return ziel


def eric(bibliothek, tmp_path, pin="123456"):
    zertifikat = tmp_path / "elster.pfx"
    zertifikat.write_bytes(b"pfx")
    return EricUebermittler(
        bibliothek=str(bibliothek),
        zertifikat=str(zertifikat),
        pin=pin,
        log=str(tmp_path),
    )


def datensatz(hersteller_id="12345", testmerker=TESTMERKER):
    va = UStVoranmeldung(zeitraum="2026-08")
    va.addiere(81, Decimal("1000"))
    return ustva_xml(
        va,
        Zeitraum.lies("2026-08"),
        "9181081508155",
        Absender("Galerie Muster GmbH", "Kunstweg 1", "80331", "München"),
        Kopf(hersteller_id, "accounti", "0.1.0", testmerker),
        date(2026, 9, 7),
    )


def test_pruefen_ohne_versand_mit_hinweis(bibliothek, tmp_path):
    e = eric(bibliothek, tmp_path).pruefe(datensatz(), "UStVA_2026")
    assert e.erfolgreich, e
    assert e.hinweise == ("Hinweis der Attrappe",)
    assert e.ticket is None


def test_pruefen_mit_plausibilitaetsfehler(bibliothek, tmp_path):
    xml = datensatz().replace("<Kz83>190.00</Kz83>", "")
    e = eric(bibliothek, tmp_path).pruefe(xml, "UStVA_2026")
    assert not e.erfolgreich
    assert "Kz83 fehlt" in e.fehler
    assert "FehlerRegelpruefung" in e.pruefbericht


def test_senden_mit_zertifikat_ticket_und_pdf(bibliothek, tmp_path):
    e = eric(bibliothek, tmp_path).sende(datensatz(testmerker=None), "UStVA_2026")
    assert e.erfolgreich, e
    assert e.ticket == "et-attrappe-2-2"  # Strukturversionen kamen über ctypes an
    assert e.pdf.startswith(b"%PDF")
    assert "erfolgreich angenommen" in e.server_antwort
    assert not list(tmp_path.glob("*.pdf"))  # temporäres PDF aufgeräumt


def test_falsche_pin(bibliothek, tmp_path):
    e = eric(bibliothek, tmp_path, pin="000000").sende(datensatz(), "UStVA_2026")
    assert not e.erfolgreich
    assert "610201016" in e.fehler and "Fehlertext der Attrappe" in e.fehler


def test_gesperrte_test_hersteller_id(bibliothek, tmp_path):
    e = eric(bibliothek, tmp_path).pruefe(datensatz("74931"), "UStVA_2026")
    assert not e.erfolgreich
    assert "Test-Hersteller-ID" in e.fehler and "gesperrt" in e.fehler


def test_unbekannte_datenartversion(bibliothek, tmp_path):
    """Nur ERIC_GLOBAL_HINWEISE heißt „gültig mit Hinweisen“ — ein anderer
    Fehlercode bleibt ein Fehler, auch wenn Hinweise zurückkommen."""
    e = eric(bibliothek, tmp_path).pruefe(datensatz(), "UStVA_2099")
    assert not e.erfolgreich and "Plugin" in e.fehler
    assert e.hinweise == ("Hinweis trotz Fehler",)


def test_plugin_verzeichnis_wie_im_eric_paket(tmp_path):
    e = EricUebermittler(
        bibliothek="/opt/eric/lib/libericapi.so", zertifikat="x.pfx", pin="1"
    )
    assert e.plugins == "/opt/eric/lib/plugins2"


def test_bibliothek_nicht_ladbar(tmp_path):
    kaputt = tmp_path / "libericapi.so"
    kaputt.write_bytes(b"keine Bibliothek")
    e = eric(kaputt, tmp_path).pruefe(datensatz(), "UStVA_2026")
    assert not e.erfolgreich and "nicht ladbar" in e.fehler
