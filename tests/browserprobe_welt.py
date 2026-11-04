"""Wegwerf-Bestand für die Browserprobe (Spec 10c A112; Plan P1, Schritt 5).

``python -m tests.browserprobe_welt --port 8473 --ziel DIR`` baut in einem **neuen,
leeren** Ordner zwei Gesellschaften mit Benutzern je Rolle (``jan`` buchhalter,
``fritz`` freigeber, ``leo`` betrachter, ``vera`` verwalter, ``alle`` mit allen
Rollen), eine Prüfschlange mit PDF-, Bild- und E-Rechnungsbeleg, eine freigegebene
Buchung, eine gelernte Regel und einen Zahlungslauf im Entwurf. Es schreibt
``DIR/probe.json`` (Basis-URL, je Benutzer Passwort, TOTP-Geheimnis und
Wiederherstellungscodes, jede GET-Seite mit Beispiel-IDs und dem erwarteten Status je
Benutzer) und startet die App mit uvicorn auf ``127.0.0.1``. Die Uhr ist echt — die
Probe rechnet die TOTP-Codes selbst (``node:crypto``).

Nur für die Entwicklung: Passwörter und Geheimnisse stehen im Klartext in
``probe.json`` (steht in ``.gitignore``); die Datenbanken sind Wegwerf-SQLite im
Ordner. Nicht im Abbild (``Dockerfile`` kopiert ``tests/`` nicht).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from accounti.api.app import erstelle_app
from accounti.api.einstellungen import ServerEinstellungen
from accounti.auth.totp import base32
from accounti.models import BuchungStatus
from accounti.models.auth import Recht, Rolle, rechte_der_rollen
from tests.api_hilfe import Uhr, Webwelt, webwelt
from tests.auth_hilfe import PASSWORT
from tests.gesellschaft_hilfe import zahlungslauf
from tests.pruefen_hilfe import Queuewelt, pdf, tiff

WURZEL = Path(__file__).resolve().parents[1]
PORT = 8473
# Benutzer der Probe: Name → Rollen in Gesellschaft a (jan und alle auch in b)
BENUTZER: dict[str, tuple[Rolle, ...]] = {
    "jan": (Rolle.BUCHHALTER,),
    "fritz": (Rolle.FREIGEBER,),
    "leo": (Rolle.BETRACHTER,),
    "vera": (Rolle.VERWALTER,),
    "alle": tuple(Rolle),
}
# GET-Routen, die kein HTML liefern bzw. ohne HX-Request weiterleiten
DATEIEN = {
    "/belege/{beleg_id:uuid}/datei",
    "/belege/{beleg_id:uuid}/seite/{n}.png",
    "/belege/{beleg_id:uuid}/download",
}
FRAGMENTE = {"/muster/beispiel"}  # ohne HX-Request 303


class Echtzeit(Uhr):
    """Die Uhr der Welt läuft echt: Der Browser rechnet die Codes zur Wanduhr."""

    def __init__(self) -> None:  # noqa: D107 - keine feste Zeit
        pass

    @property  # type: ignore[override]
    def jetzt(self) -> datetime:
        return datetime.now().replace(microsecond=0)

    def __call__(self) -> datetime:
        return datetime.now()

    def weiter(self, sekunden: float = 30) -> None:
        """Die Wanduhr läuft von selbst."""


@dataclass
class Welt:
    web: Webwelt
    ids: dict[str, str]
    seiten: list[dict[str, Any]] = field(default_factory=list)

    def probe(self, basis: str) -> dict[str, Any]:
        return {
            "basis": basis,
            "benutzer": {
                name: {
                    "passwort": PASSWORT,
                    "geheimnis": base32(p.geheimnis),
                    "rollen": [r.value for r in BENUTZER[name]],
                    "codes": p.codes,
                }
                for name, p in self.web.personen.items()
            },
            "seiten": self.seiten,
        }


def _bestand(w: Webwelt, ziel: Path) -> dict[str, str]:
    qw = Queuewelt(w, ziel)
    beleg = qw.beleg(pdf())
    bild = qw.beleg(tiff((40, 30)), ".tif", belegnummer="SCAN-1")
    xml = (WURZEL / "examples" / "erechnung" / "xrechnung_ubl.xml").read_bytes()
    erechnung = qw.beleg(xml, ".xml", belegnummer="XR-1")
    tx = qw.umsatz()
    vorschlag = qw.buchung(beleg_id=beleg.id, transaktion_id=tx.id)
    qw.buchung(beleg_id=bild.id, buchungstext="Scan", datum=date(2026, 10, 2))
    qw.buchung(
        beleg_id=erechnung.id, buchungstext="E-Rechnung", datum=date(2026, 10, 3)
    )
    frei = qw.buchung(status=BuchungStatus.GEPRUEFT, datum=date(2026, 10, 2))
    with qw.fabrik()() as s:
        from accounti.klassifikation.lernen import lerne_regex

        lerne_regex(s, "telekom", "telekom", "4920", "1200", 9, "t")
        s.commit()
    zahlungslauf(w.umgebung, "a")
    return {
        "vorschlag": str(vorschlag.id),
        "frei": str(frei.id),
        "beleg": str(beleg.id),
        "bild": str(bild.id),
    }


def _pfad(vorlage: str, ids: dict[str, str]) -> str:
    buchung = ids["vorschlag"] if vorlage.startswith("/pruefen/") else ids["frei"]
    beleg = ids["bild"] if "/seite/" in vorlage else ids["beleg"]
    return (
        vorlage.replace("{buchung_id:uuid}", buchung)
        .replace("{beleg_id:uuid}", beleg)
        .replace("{n}", "1")
        .replace("{thema}", "pruefen")
    )


def _erwartet(recht: object, rollen: tuple[Rolle, ...]) -> int:
    from tests.test_api_rechte_matrix import ANGEMELDET, OFFEN, EinesVon

    rechte = rechte_der_rollen(list(rollen))
    if recht in (OFFEN, ANGEMELDET):
        return 200
    if isinstance(recht, EinesVon):
        return 200 if recht & rechte else 403
    assert isinstance(recht, Recht), recht
    return 200 if recht in rechte else 403


def baue(ziel: Path) -> Welt:
    """Bestand im neuen, leeren Ordner ``ziel`` (ohne Server)."""
    from tests.test_api_rechte_matrix import SEITEN

    if ziel.exists() and any(ziel.iterdir()):
        raise SystemExit(f"{ziel} ist nicht leer — die Welt braucht einen neuen Ordner")
    ziel.mkdir(parents=True, exist_ok=True)
    w = webwelt(ziel, uhr=Echtzeit())
    for name, rollen in BENUTZER.items():
        w.person(name, *rollen)
    w.rolle("jan", "b", Rolle.BUCHHALTER)
    w.rolle("alle", "b", Rolle.BUCHHALTER)
    welt = Welt(w, _bestand(w, ziel))
    app = erstelle_app(w.dienste)
    for e in sorted(app.state.endpunkte, key=lambda e: e.pfad):
        if e.methode != "GET" or e.pfad.startswith("/api/") or e.pfad == "/gesund":
            continue
        art = (
            "datei"
            if e.pfad in DATEIEN
            else "fragment"
            if e.pfad in FRAGMENTE
            else "html"
        )
        welt.seiten.append(
            {
                "vorlage": e.pfad,
                "pfad": _pfad(e.pfad, welt.ids),
                "art": art,
                "erwartet": {
                    name: _erwartet(SEITEN[("GET", e.pfad)], rollen)
                    for name, rollen in BENUTZER.items()
                },
            }
        )
    return welt


def main(argv: list[str] | None = None) -> None:  # pragma: no cover - startet Server
    import uvicorn

    from accounti.auth import passwort
    from tests.auth_hilfe import BILLIG

    teile = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    teile.add_argument("--port", type=int, default=PORT)
    teile.add_argument("--ziel", type=Path, required=True)
    args = teile.parse_args(argv)
    passwort.KOSTEN = BILLIG  # Wegwerf-Bestand: scrypt billig wie in den Tests
    welt = baue(args.ziel)
    # ohne TLS: Cookies ohne Secure und ohne __Host- (nur 127.0.0.1)
    welt.web.dienste.server = ServerEinstellungen(cookie_sicher=False)
    basis = f"http://127.0.0.1:{args.port}"
    (args.ziel / "probe.json").write_text(
        json.dumps(welt.probe(basis), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    sys.stdout.write(f"Welt in {args.ziel}, {len(welt.seiten)} GET-Seiten — {basis}\n")
    sys.stdout.flush()
    uvicorn.run(
        erstelle_app(welt.web.dienste),
        host="127.0.0.1",
        port=args.port,
        access_log=False,
        log_level="warning",
        server_header=False,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
