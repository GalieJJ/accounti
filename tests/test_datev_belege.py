"""DATEV-Belegpaket: Belegbilder hängen beim Empfänger am Buchungssatz (Akzeptanz 5).

Die Empfänger-Simulation macht, was DATEV beim Import tut: Sie liest den
Buchungsstapel, nimmt aus dem Feld „Beleglink“ (``BEDI "<GUID>"``) die GUID, sucht
das Dokument mit dieser GUID in der ``document.xml`` des Belegpakets und öffnet dessen
Datei.
"""

import csv
import hashlib
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from accounti.belege.archiv import BelegArchiv
from accounti.belege.kanaele import RohBeleg
from accounti.belege.pipeline import nimm_auf
from accounti.db import init_db, session_factory
from accounti.db.repository import (
    lade_beleg,
    speichere_abgleich,
    speichere_beleg,
    speichere_buchung,
    speichere_transaktion,
)
from accounti.export.datev_belege import BelegexportError, exportiere_belegpaket
from accounti.export.datev_felder import BUCHUNGSSTAPEL
from accounti.export.datev_stammdaten import DatevMandant
from accounti.models import (
    AbgleichStatus,
    Beleg,
    Belegabgleich,
    Belegart,
    BelegStatus,
    Buchungssatz,
    BuchungStatus,
    Transaktion,
    TransaktionQuelle,
)

NS = {"d": "http://xml.datev.de/bedi/tps/document/v06.0"}
MANDANT = DatevMandant(berater=29098, mandant=55003, wj_beginn=date(2026, 1, 1))
ERZEUGT = datetime(2026, 9, 2, 10, 0, 0)
D = Decimal
PDF = b"%PDF-1.4\n% Rechnung R-2026-0815\n1 0 obj << >> endobj\n%%EOF\n"
JPG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00Quittung Tankstelle\xff\xd9"


def _beleg(s, archiv, name, inhalt, art, nummer):
    def erkenner(_roh, beleg):
        return beleg.model_copy(
            update={
                "belegart": art,
                "status": BelegStatus.ERFASST,
                "belegnummer": nummer,
                "belegdatum": date(2026, 8, 3),
                "lieferant_name": "Beispiel Lieferant GmbH",
            }
        )

    eingang = nimm_auf(
        s, archiv, RohBeleg(name, inhalt, "upload", name), erkenner=erkenner
    )
    return lade_beleg(s, eingang.beleg_id)


def _buchung(s, nummer, tag=5, monat=8, **kw):
    werte = {
        "datum": date(2026, monat, tag),
        "soll_konto": "4930",
        "haben_konto": "70001",
        "betrag_netto": D("100.00"),
        "steuer_schluessel": 9,
        "steuer_betrag": D("19.00"),
        "buchungstext": f"Buchung {nummer}",
        "beleg_nummer": nummer,
        "status": BuchungStatus.AUTO_GEBUCHT,
    }
    werte.update(kw)
    b = Buchungssatz(**werte)
    speichere_buchung(s, b)
    return b


@pytest.fixture
def paket(tmp_path):
    engine, make = session_factory(f"sqlite:///{tmp_path / 'b.db'}")
    init_db(engine)
    archiv = BelegArchiv(tmp_path / "archiv")
    with make() as s:
        rechnung = _beleg(
            s, archiv, "R-2026-0815.pdf", PDF, Belegart.EINGANGSRECHNUNG, "R-2026-0815"
        )
        quittung = _beleg(
            s, archiv, "Tankquittung.jpg", JPG, Belegart.QUITTUNG, "Q-4711"
        )
        verloren = Beleg(
            datei_hash="0" * 64,
            dateiname="weg.pdf",
            kanal="upload",
            herkunft="x",
            aufbewahren_bis=date(2036, 12, 31),
            status=BelegStatus.ERFASST,
            belegnummer="R-9",
        )
        speichere_beleg(s, verloren)
        bericht = _beleg(
            s, archiv, "abrechnung.txt", b"settlement", Belegart.SONSTIGES, "A-1"
        )
        tx = Transaktion(
            datum=date(2026, 8, 6),
            betrag=D("-59.50"),
            verwendungszweck="TANKSTELLE",
            quelle=TransaktionQuelle.BANK,
            rohtext="",
        )
        speichere_transaktion(s, tx)
        speichere_abgleich(
            s,
            Belegabgleich(
                transaktion_id=tx.id,
                beleg_id=quittung.id,
                stufe="exakt",
                status=AbgleichStatus.BESTAETIGT,
                confidence=1.0,
                begruendung="Test",
            ),
        )
        buchungen = {
            "rechnung": _buchung(s, "R-2026-0815", beleg_id=rechnung.id),
            "quittung": _buchung(
                s,
                "Q-4711",
                tag=6,
                transaktion_id=tx.id,
                soll_konto="4530",
                haben_konto="1200",
                betrag_netto=D("50.00"),
                steuer_betrag=D("9.50"),
            ),
            "gebuehr": _buchung(
                s,
                "KTO-08",
                tag=31,
                soll_konto="4970",
                haben_konto="1200",
                betrag_netto=D("5.90"),
                steuer_schluessel=None,
                steuer_betrag=None,
            ),
            "verloren": _buchung(s, "R-9", tag=7, beleg_id=verloren.id),
            "bericht": _buchung(s, "A-1", tag=8, beleg_id=bericht.id),
            "pruefung": _buchung(
                s,
                "OFFEN",
                tag=9,
                beleg_id=rechnung.id,
                status=BuchungStatus.ZUR_PRUEFUNG,
            ),
            "september": _buchung(s, "SEP", tag=1, monat=9, beleg_id=rechnung.id),
        }
        s.commit()
        ergebnis = exportiere_belegpaket(
            s,
            archiv,
            MANDANT,
            date(2026, 8, 1),
            date(2026, 8, 31),
            tmp_path / "aus" / "belege-08.zip",
            erzeugt_am=ERZEUGT,
        )
        belege = {"rechnung": rechnung, "quittung": quittung}
    return ergebnis, buchungen, belege


def empfaenger(stapel_pfad, zip_pfad):
    """Belegfeld 1 → Inhalt der verknüpften Datei (oder None ohne Beleglink)."""
    zeilen = stapel_pfad.read_bytes().decode("cp1252").split("\r\n")[2:-1]
    with zipfile.ZipFile(zip_pfad) as z:
        archiv = ET.fromstring(z.read("document.xml"))
        dateien = {
            d.get("guid"): [
                e.get("name")
                for e in d.findall("d:extension", NS)
                if e.get("{http://www.w3.org/2001/XMLSchema-instance}type") == "File"
            ]
            for d in archiv.findall("d:content/d:document", NS)
        }
        ergebnis = {}
        for werte in csv.reader(zeilen, delimiter=";"):
            link = werte[19]
            if not link:
                ergebnis[werte[10]] = None
                continue
            treffer = re.fullmatch(
                r'BEDI "([0-9A-F]{8}(?:-[0-9A-F]{4}){3}-[0-9A-F]{12})"', link
            )
            assert treffer, link
            (name,) = dateien[treffer[1]]
            ergebnis[werte[10]] = z.read(name)
    return ergebnis


def test_akzeptanz_5_belege_haengen_am_buchungssatz(paket):
    ergebnis, _, belege = paket
    zuordnung = empfaenger(ergebnis.stapel_pfad, ergebnis.zip_pfad)
    # Rechnung über beleg_id, Quittung über den bestätigten Belegabgleich
    assert hashlib.sha256(zuordnung["R-2026-0815"]).hexdigest() == (
        belege["rechnung"].datei_hash
    )
    assert zuordnung["Q-4711"] == JPG
    # ohne Beleg, Beleg verloren, Format von DATEV nicht angenommen: kein Link
    assert zuordnung["KTO-08"] is None
    assert zuordnung["R-9"] is None
    assert zuordnung["A-1"] is None
    # nur freigegebene Buchungen des Zeitraums
    assert set(zuordnung) == {"R-2026-0815", "Q-4711", "KTO-08", "R-9", "A-1"}
    assert (ergebnis.buchungen, ergebnis.belege, ergebnis.verknuepft) == (5, 2, 2)
    texte = " ".join(ergebnis.befunde)
    assert "R-9" in texte and "nicht im Archiv" in texte
    assert "A-1" in texte and ".txt" in texte


def test_document_xml_nach_datev_vorgaben(paket):
    ergebnis, _, belege = paket
    with zipfile.ZipFile(ergebnis.zip_pfad) as z:
        namen = z.namelist()
        archiv = ET.fromstring(z.read("document.xml"))
    assert "document.xml" in namen and len(namen) == 3
    assert all(n.isascii() and "/" not in n for n in namen)  # flach, nur ASCII
    assert archiv.tag == "{http://xml.datev.de/bedi/tps/document/v06.0}archive"
    assert archiv.get("version") == "6.0"
    assert archiv.find("d:header/d:consultantNumber", NS).text == "29098"
    assert archiv.find("d:header/d:clientNumber", NS).text == "55003"
    dokumente = {d.get("guid"): d for d in archiv.findall("d:content/d:document", NS)}
    rechnung = dokumente[str(belege["rechnung"].id).upper()]
    assert rechnung.get("type") == "1"  # Rechnungseingang
    assert rechnung.get("processID") == "2"  # archivieren, nicht noch einmal buchen
    assert dokumente[str(belege["quittung"].id).upper()].get("type") is None
    ebenen = [e.get("name") for e in rechnung.findall("d:repository/d:level", NS)]
    assert ebenen == ["accounti", "Belege 2026", "08 August"]


def test_buchungsstapel_mit_beleglink(paket):
    ergebnis, _, belege = paket
    zeilen = ergebnis.stapel_pfad.read_bytes().decode("cp1252").split("\r\n")
    kopf = zeilen[0].split(";")
    assert kopf[2:5] == ["21", '"Buchungsstapel"', "13"]
    assert kopf[14:16] == ["20260801", "20260831"]
    assert zeilen[1] == ";".join(f.name for f in BUCHUNGSSTAPEL)
    rechnung = next(z for z in zeilen if '"R-2026-0815"' in z).split(";")
    assert len(rechnung) == 125
    guid = str(belege["rechnung"].id).upper()
    assert rechnung[19] == f'"BEDI ""{guid}"""'
    assert rechnung[:10] == [
        "119,00",
        '"S"',
        '""',
        "",
        "",
        '""',
        "4930",
        "70001",
        '"9"',
        "0508",
    ]


def test_belegfeld1_im_datev_zeichenvorrat(tmp_path):
    engine, make = session_factory(f"sqlite:///{tmp_path / 'b.db'}")
    init_db(engine)
    archiv = BelegArchiv(tmp_path / "archiv")
    with make() as s:
        b = _beleg(s, archiv, "r.pdf", PDF, Belegart.EINGANGSRECHNUNG, "RE 2026.17")
        _buchung(s, "RE 2026.17", beleg_id=b.id)
        _buchung(s, "R-1", tag=6)
        ergebnis = exportiere_belegpaket(
            s,
            archiv,
            MANDANT,
            date(2026, 8, 1),
            date(2026, 8, 31),
            tmp_path / "x.zip",
        )
    zuordnung = empfaenger(ergebnis.stapel_pfad, ergebnis.zip_pfad)
    assert set(zuordnung) == {"RE202617", "R-1"}
    assert zuordnung["RE202617"] == PDF
    (befund,) = [x for x in ergebnis.befunde if "Belegfeld 1" in x]
    assert "1 Belegnummer" in befund and "'RE 2026.17' → 'RE202617'" in befund


def test_ohne_belege_kein_leeres_paket(tmp_path):
    """Die XSD verlangt mindestens ein Dokument — ohne Belege gibt es kein ZIP."""
    engine, make = session_factory(f"sqlite:///{tmp_path / 'b.db'}")
    init_db(engine)
    with make() as s:
        _buchung(s, "KTO-08")
        ergebnis = exportiere_belegpaket(
            s,
            BelegArchiv(tmp_path / "archiv"),
            MANDANT,
            date(2026, 8, 1),
            date(2026, 8, 31),
            tmp_path / "x.zip",
        )
    assert ergebnis.zip_pfad is None and not (tmp_path / "x.zip").exists()
    assert ergebnis.stapel_pfad.exists() and ergebnis.buchungen == 1


def test_zu_viele_belege(tmp_path, monkeypatch):
    import accounti.export.datev_belege as modul

    engine, make = session_factory(f"sqlite:///{tmp_path / 'b.db'}")
    init_db(engine)
    archiv = BelegArchiv(tmp_path / "archiv")
    monkeypatch.setattr(modul, "MAX_DOKUMENTE", 1)
    with make() as s:
        for i in range(2):
            b = _beleg(
                s,
                archiv,
                f"r{i}.pdf",
                PDF + bytes([i]),
                Belegart.EINGANGSRECHNUNG,
                f"R{i}",
            )
            _buchung(s, f"R{i}", beleg_id=b.id)
        with pytest.raises(BelegexportError, match="4999|1 Dokument"):
            exportiere_belegpaket(
                s,
                archiv,
                MANDANT,
                date(2026, 8, 1),
                date(2026, 8, 31),
                tmp_path / "x.zip",
            )


JAVA_PRUEFUNG = """
import javax.xml.XMLConstants;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.SchemaFactory;
import java.io.File;
public class Pruefe {
  public static void main(String[] a) throws Exception {
    SchemaFactory.newInstance(XMLConstants.W3C_XML_SCHEMA_NS_URI)
      .newSchema(new File(a[0])).newValidator()
      .validate(new StreamSource(new File(a[1])));
    System.out.println("gueltig");
  }
}
"""


@pytest.mark.skipif(
    not os.environ.get("ACCOUNTI_DATEV_XSD") or shutil.which("java") is None,
    reason="DATEV-XSD (ACCOUNTI_DATEV_XSD) oder Java fehlt",
)
def test_document_xml_gegen_datev_xsd(paket, tmp_path):
    ergebnis, _, _ = paket
    with zipfile.ZipFile(ergebnis.zip_pfad) as z:
        (tmp_path / "document.xml").write_bytes(z.read("document.xml"))
    (tmp_path / "Pruefe.java").write_text(JAVA_PRUEFUNG, encoding="utf-8")
    xsd = Path(os.environ["ACCOUNTI_DATEV_XSD"]) / "Document_v060.xsd"
    lauf = subprocess.run(
        [
            "java",
            str(tmp_path / "Pruefe.java"),
            str(xsd),
            str(tmp_path / "document.xml"),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert lauf.returncode == 0, lauf.stderr
    assert "gueltig" in lauf.stdout


def test_storno_im_buchungsstapel_mit_bezug_in_belegfeld_2():
    from uuid import uuid4

    from accounti.export.datev_belege import buchungsstapel_satz
    from accounti.export.datev_felder import BUCHUNGSSTAPEL
    from accounti.export.datev_format import feldnummer
    from accounti.models import Buchungssatz, BuchungStatus

    original = uuid4()
    storno = Buchungssatz(
        datum=date(2026, 8, 3),
        soll_konto="1200",
        haben_konto="4930",
        betrag_netto=Decimal("10.00"),
        buchungstext="Storno Papier",
        status=BuchungStatus.GEPRUEFT,
        storno_von=original,
    )
    satz = buchungsstapel_satz(storno, None)
    assert satz[feldnummer(BUCHUNGSSTAPEL, "Belegfeld 2")] == (
        "ST" + original.hex[:8].upper()
    )
    ohne = storno.model_copy(update={"storno_von": None})
    assert (
        buchungsstapel_satz(ohne, None)[feldnummer(BUCHUNGSSTAPEL, "Belegfeld 2")]
        is None
    )
