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
from collections.abc import Collection, Mapping
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
    # Bereiche der Personenkonten (buchhaltung.debitoren_von … kreditoren_bis): sie
    # sind eine Stelle länger als die Sachkonten
    personenkonten: tuple[tuple[int, int], ...] = ((10000, 69999), (70000, 99999))
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

    def _ist_personenkonto(self, konto: str) -> bool:
        return konto.isdigit() and any(
            von <= int(konto) <= bis for von, bis in self.config.personenkonten
        )

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
        # ein Personenkonto, das kürzer ist, läse DATEV als Sachkonto — bei Länge 6
        # oder 8 etwa die 5-stelligen Debitoren (Runde 6, g5w-konten N2); je Konto
        # einmal
        self.warnungen += [
            f"Personenkonto {konto} (buchhaltung.debitoren/kreditoren) passt nicht zur "
            f"Sachkontenlänge {laenge} (erwartet {laenge + 1} Stellen, "
            "mandant.sachkonten_laenge) — DATEV liest es als Sachkonto"
            for konto in sorted(
                {k for b in buchungen for k in (b.soll_konto, b.haben_konto)}
            )
            if self._ist_personenkonto(konto)
            and kontoart(konto, laenge) is not None
            and len(konto) != laenge + 1
        ]
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
        vergeben: Collection[str] = (),
    ) -> Path:
        """Buchungsstapel als DATEV-ASCII-Datei exportieren.

        Args:
            buchungen: Liste der zu exportierenden Buchungssätze (in dieser Folge)
            ausgabe_pfad: Verzeichnis für die Ausgabedatei
            vergeben: Dateinamen, die frühere Exporte schon hatten (Journal,
                ``exportierte_dateien``) — sie werden übersprungen, auch wenn die
                Datei nicht mehr im Ordner liegt (nach dem Hochladen weggeräumt):
                sonst trügen zwei Stapel denselben Namen und im selben Archivordner
                überschriebe der neue den alten

        Returns:
            Pfad zur erzeugten Datei — eine vorhandene wird nie überschrieben: der
            nächste Stapel desselben Zeitraums heißt ``…_2.csv``, ``…_3.csv`` usw.
            Ein zweiter Export bringt nur die noch nicht exportierten Buchungen; mit
            demselben Namen wäre der erste Stapel verloren, und der SHA-256 im
            Journal (``markiere_exportiert``) verwiese auf eine Datei, die es so nicht
            mehr gibt — die Übergabe bliebe nicht nachvollziehbar (§ 145 Abs. 1 AO,
            GoBD Rz. 30 ff.).

        Raises:
            DatevFormatError: Zeitraum, Wirtschaftsjahr oder ein Wert passt nicht ins
                DATEV-Format — dann wird nichts geschrieben.
        """
        inhalt, von, bis = self.inhalt(buchungen)
        ordner = Path(ausgabe_pfad)
        ordner.mkdir(parents=True, exist_ok=True)
        stamm = f"EXTF_Buchungsstapel_{von:%Y%m%d}_{bis:%Y%m%d}"
        nr = 1
        while True:
            datei = ordner / (f"{stamm}.csv" if nr == 1 else f"{stamm}_{nr}.csv")
            if datei.name in vergeben:
                nr += 1
                continue
            try:
                # "x": anlegen oder scheitern — auch zwei gleichzeitige Exporte
                # überschreiben einander nicht
                with datei.open("xb") as ziel:
                    ziel.write(inhalt)
            except FileExistsError:
                nr += 1
                continue
            return datei


def _exporte(session: Session) -> list[dict[str, object]]:
    """Journaleinträge ``export`` (Buchungsstapel, Belegpaket) als Daten."""
    from accounti.pruefung.journal import journal_vorhanden, lade_journal

    if not journal_vorhanden(session.connection()):
        return []
    daten = []
    for e in lade_journal(session, vorgang="export"):
        if e.objekt_id not in EXPORTARTEN or not e.nachher:
            continue
        try:
            nachher = json.loads(e.nachher)
        except ValueError:
            continue
        if isinstance(nachher, dict):
            daten.append(nachher)
    return daten


def exportierte_dateien(session: Session) -> set[str]:
    """Dateinamen früherer Exporte laut Journal — für die laufende Nummer des
    nächsten Stapels (``DATEVExporter.exportiere``)."""
    return {str(d["datei"]) for d in _exporte(session) if d.get("datei")}


def stapel_des_monats(session: Session, von: date, bis: date) -> list[str]:
    """Dateinamen der Stapel, die laut Journal Buchungen mit Datum von ``von`` bis
    ``bis`` übergaben, in der Reihenfolge der Exporte — die ``export datev --period
    … --erneut --alle`` zusammen ersetzt: sein Stapel enthält alle Buchungen des
    Zeitraums (Nachprüfung 4 E, L-d)."""
    from accounti.db.tabellen import BuchungssatzRow

    exporte = _exporte(session)
    if not exporte:
        return []
    im_zeitraum = {
        zeile_id
        for (zeile_id,) in session.query(BuchungssatzRow.id).filter(
            BuchungssatzRow.datum >= von, BuchungssatzRow.datum <= bis
        )
    }
    dateien: list[str] = []
    for nachher in exporte:
        datei = nachher.get("datei")
        if not datei or str(datei) in dateien:
            continue
        for schluessel in ("markiert", "gesperrt", "ungeprueft"):
            werte = nachher.get(schluessel)
            if isinstance(werte, list) and im_zeitraum.intersection(map(str, werte)):
                dateien.append(str(datei))
                break
    return dateien


def schon_exportiert(session: Session) -> set[UUID]:
    """Buchungen, die ein früherer Export laut Journal übergeben hat.

    Der Status ``exportiert`` reicht nicht: in einem festgeschriebenen Monat nimmt
    die Buchung keinen Statuswechsel mehr an, und eine ungeprüfte (``--alle``) wird
    nicht ``exportiert`` — der Export vermerkt beide nur im Journal
    (``markiere_exportiert``, Listen ``gesperrt`` und ``ungeprueft``).
    """
    ids: set[UUID] = set()
    for nachher in _exporte(session):
        for schluessel in ("markiert", "gesperrt", "ungeprueft"):
            werte = nachher.get(schluessel)
            for wert in werte if isinstance(werte, list) else []:
                try:
                    ids.add(UUID(str(wert)))
                except ValueError:
                    continue
    return ids
