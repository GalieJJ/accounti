"""DATEV-Export — Buchungsstapel im EXTF-Format (``accounti export datev``).

Gebaut aus denselben Bausteinen wie ``datev belege`` (``datev_format``,
``datev_belege.buchungsstapel_satz``), nur ohne Beleglink: Kopfzeile mit 31 Feldern,
Herkunft „RE“, Buchungstyp 1 (Finanzbuchführung), alle 125 Felder der Formatversion
13, Textfelder in Anführungszeichen mit verdoppelten inneren Anführungszeichen,
Belegfeld 1 im DATEV-Zeichenvorrat, Kostenstelle in KOST1 (Feld 37).

Ein Stapel gehört zu genau einem Wirtschaftsjahr: das Belegdatum steht als TTMM, das
Jahr ergibt sich aus „Datum vom/bis“ im Kopf, und „Datum vom/bis“ liegen im
Wirtschaftsjahr ab Feld 13 (DATEV-Format, Header 700, Felder 13, 15, 16). Buchungen
außerhalb des Zeitraums oder über die Grenze des Wirtschaftsjahrs hinweg lehnt der
Export ab — DATEV läse sie sonst im falschen Jahr.

Referenz: DATEV-Schnittstellenbeschreibung für Buchungsdaten
https://developer.datev.de/datev/platform/de/dtvf
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.export.datev_belege import buchungsstapel_satz
from accounti.export.datev_felder import BUCHUNGSSTAPEL
from accounti.export.datev_format import (
    DatevFormatError,
    Kopf,
    automatik_widerspruch,
    belegfeld1,
    feldnummer,
    kontoart,
    schreibe_extf,
)
from accounti.export.datev_stammdaten import wirtschaftsjahr_beginn
from accounti.models import Buchungssatz

_BELEGDATUM = feldnummer(BUCHUNGSSTAPEL, "Belegdatum")
# Exporte, die Buchungen als exportiert vermerken (Journal, Vorgang „export“)
EXPORTARTEN = ("datev", "datev_belege")


@dataclass
class DATEVConfig:
    """Konfiguration für den DATEV-Export."""

    berater_nummer: str  # z.B. "23426"
    mandanten_nummer: str  # z.B. "40005"
    # Beginn eines Wirtschaftsjahrs (Tag und Monat zählen, § 4a EStG); ohne: 1. Januar
    wirtschaftsjahr_beginn: date | None = None
    sachkonten_laenge: int = 4  # 4-stellig Standard, auch 5–8 möglich
    datum_von: date | None = None  # ohne: frühestes Buchungsdatum
    datum_bis: date | None = None  # ohne: spätestes Buchungsdatum
    bezeichnung: str = "accounti Export"
    waehrung: str = "EUR"
    skr: str = ""  # "03", "04" (leer: DATEV nimmt den Kontenrahmen des Mandanten)
    # DATEV-Automatikkonten (AV/AM) → Schlüssel; eine Buchung ohne Schlüssel darauf
    # bekommt BU 40 (Aufhebung der Automatik), sonst rechnete DATEV Steuer heraus
    automatikkonten: Mapping[str, int] = field(default_factory=dict)


def wirtschaftsjahr(stichtag: date, beginn: date | None = None) -> tuple[date, date]:
    """Erster und letzter Tag des Wirtschaftsjahrs, in dem ``stichtag`` liegt."""
    anfang = wirtschaftsjahr_beginn(stichtag, beginn)
    naechstes = anfang.replace(year=anfang.year + 1)  # Februar: höchstens der 28.
    return anfang, naechstes - timedelta(days=1)


def _nummer(text: str, was: str) -> int:
    if not str(text).strip().isdigit():
        raise DatevFormatError(f"{was} {text!r} ist keine Zahl")
    return int(text)


class DATEVExporter:
    """Erzeugt DATEV-konforme Buchungsstapel-Dateien."""

    FORMAT_KATEGORIE = 21  # Buchungsstapel
    FORMAT_NAME = "Buchungsstapel"
    FORMAT_VERSION = 13

    def __init__(self, config: DATEVConfig) -> None:
        self.config = config
        # vor dem Import zu klären (Automatikkonto, Kontonummer, Belegfeld 1)
        self.warnungen: list[str] = []

    def zeitraum(self, buchungen: list[Buchungssatz]) -> tuple[date, date, date]:
        """(Datum vom, Datum bis, Beginn des Wirtschaftsjahrs) — oder
        ``DatevFormatError``, wenn der Stapel nicht in ein Wirtschaftsjahr passt."""
        c = self.config
        tage = sorted(b.datum for b in buchungen)
        von = c.datum_von or (tage[0] if tage else date.today())
        bis = c.datum_bis or (tage[-1] if tage else von)
        if von > bis:
            raise DatevFormatError(f"Zeitraum {von:%d.%m.%Y}–{bis:%d.%m.%Y} ist leer")
        draussen = [t for t in tage if not von <= t <= bis]
        if draussen:
            raise DatevFormatError(
                f"{len(draussen)} Buchung(en) außerhalb des Zeitraums "
                f"{von:%d.%m.%Y}–{bis:%d.%m.%Y} (z.B. {draussen[0]:%d.%m.%Y}) — das "
                "Belegdatum stünde im falschen Jahr"
            )
        wj_anfang, wj_ende = wirtschaftsjahr(von, c.wirtschaftsjahr_beginn)
        if bis > wj_ende:
            raise DatevFormatError(
                f"Zeitraum {von:%d.%m.%Y}–{bis:%d.%m.%Y} geht über das Ende des "
                f"Wirtschaftsjahrs ({wj_ende:%d.%m.%Y}) — ein DATEV-Stapel gehört zu "
                "einem Wirtschaftsjahr; je Zeitraum exportieren (accounti export "
                "datev --period JJJJ-MM)"
            )
        return von, bis, wj_anfang

    def _pruefe(self, buchungen: list[Buchungssatz]) -> None:
        laenge = self.config.sachkonten_laenge
        angepasst: list[str] = []
        for b in buchungen:
            kurz = b.beleg_nummer or str(b.id)[:8]
            for konto in (b.soll_konto, b.haben_konto):
                if kontoart(konto, laenge) is None:
                    self.warnungen.append(
                        f"Buchung {kurz}: Konto {konto} passt nicht zur "
                        f"Sachkontenlänge {laenge} (Sachkonto bis {laenge}, "
                        f"Personenkonto {laenge + 1} Stellen) — DATEV nimmt die "
                        "Zeile so nicht an; Konto anpassen"
                    )
            if b.beleg_nummer and belegfeld1(b.beleg_nummer) != b.beleg_nummer:
                angepasst.append(f"{b.beleg_nummer!r} → {belegfeld1(b.beleg_nummer)!r}")
            warnung = automatik_widerspruch(b, self.config.automatikkonten)
            if warnung is not None:
                self.warnungen.append(warnung)
        if angepasst:
            verschieden = list(dict.fromkeys(angepasst))
            beispiele = ", ".join(verschieden[:3]) + (
                " …" if len(verschieden) > 3 else ""
            )
            self.warnungen.append(
                f"Belegfeld 1: {len(angepasst)} Belegnummer(n) auf DATEVs "
                f"Zeichenvorrat gekürzt ({beispiele}) — OPOS-Ausgleich in DATEV prüfen"
            )

    def inhalt(
        self, buchungen: list[Buchungssatz], erzeugt_am: datetime | None = None
    ) -> tuple[bytes, date, date]:
        """Dateiinhalt (Windows-1252) und Zeitraum des Stapels."""
        c = self.config
        von, bis, wj = self.zeitraum(buchungen)
        self.warnungen = []
        self._pruefe(buchungen)
        kopf = Kopf(
            kategorie=self.FORMAT_KATEGORIE,
            formatname=self.FORMAT_NAME,
            formatversion=self.FORMAT_VERSION,
            berater=_nummer(c.berater_nummer, "Beraternummer"),
            mandant=_nummer(c.mandanten_nummer, "Mandantennummer"),
            wj_beginn=wj,
            sachkontenlaenge=c.sachkonten_laenge,
            datum_von=von,
            datum_bis=bis,
            bezeichnung=c.bezeichnung[:30],
            buchungstyp=1,  # Finanzbuchführung
            rechnungslegungszweck=0,
            festschreibung=0,
            waehrung=c.waehrung,
            skr=c.skr,
            erzeugt_am=erzeugt_am or datetime.now(),
        )
        saetze = [buchungsstapel_satz(b, None, c.automatikkonten) for b in buchungen]
        inhalt = schreibe_extf(kopf, BUCHUNGSSTAPEL, saetze, {_BELEGDATUM: "%d%m"})
        return inhalt, von, bis

    def exportiere(
        self,
        buchungen: list[Buchungssatz],
        ausgabe_pfad: str | Path,
    ) -> Path:
        """Buchungsstapel als DATEV-ASCII-Datei exportieren.

        Args:
            buchungen: Liste der zu exportierenden Buchungssätze (in dieser Folge)
            ausgabe_pfad: Verzeichnis für die Ausgabedatei

        Returns:
            Pfad zur erzeugten Datei

        Raises:
            DatevFormatError: Zeitraum, Wirtschaftsjahr oder ein Wert passt nicht ins
                DATEV-Format — dann wird nichts geschrieben.
        """
        inhalt, von, bis = self.inhalt(buchungen)
        ordner = Path(ausgabe_pfad)
        ordner.mkdir(parents=True, exist_ok=True)
        datei = ordner / f"EXTF_Buchungsstapel_{von:%Y%m%d}_{bis:%Y%m%d}.csv"
        datei.write_bytes(inhalt)
        return datei


def schon_exportiert(session: Session) -> set[UUID]:
    """Buchungen, die ein früherer Export laut Journal übergeben hat.

    Der Status ``exportiert`` reicht nicht: in einem festgeschriebenen Monat nimmt
    die Buchung keinen Statuswechsel mehr an — der Export vermerkt sie dann nur im
    Journal (``markiere_exportiert``, Liste ``gesperrt``).
    """
    from accounti.pruefung.journal import journal_vorhanden, lade_journal

    if not journal_vorhanden(session.connection()):
        return set()
    ids: set[UUID] = set()
    for e in lade_journal(session, vorgang="export"):
        if e.objekt_id not in EXPORTARTEN or not e.nachher:
            continue
        try:
            nachher = json.loads(e.nachher)
        except ValueError:
            continue
        for schluessel in ("markiert", "gesperrt"):
            for wert in nachher.get(schluessel) or []:
                try:
                    ids.add(UUID(str(wert)))
                except ValueError:
                    continue
    return ids
