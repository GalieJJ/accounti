import os
from pathlib import Path

import pytest

from accounti.erechnung.erzeuger.cii import schreibe_cii
from accounti.erechnung.kosit import (
    KositNichtVerfuegbarError,
    KositPruefer,
    werte_bericht_aus,
)
from tests.test_erechnung_aufbau import _bau
from tests.test_erechnung_erzeuger import FAELLE

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "erechnung"
PRUEFER = KositPruefer()
# In der CI (ACCOUNTI_KOSIT_PFLICHT=1) wird nicht übersprungen: Fehlt das Prüftool,
# scheitern die Tests.
NUR_MIT_KOSIT = pytest.mark.skipif(
    not PRUEFER.verfuegbar() and not os.environ.get("ACCOUNTI_KOSIT_PFLICHT"),
    reason="KoSIT-Prüftool fehlt (scripts/kosit_installieren.sh)",
)

BERICHT = b"""<?xml version="1.0" encoding="UTF-8"?>
<rep:report xmlns:rep="http://www.xoev.de/de/validator/varl/1" valid="false">
  <rep:scenarioMatched>
    <rep:validationStepResult id="val-sch.1" valid="false">
      <rep:message level="error" code="BR-S-09">[BR-S-09]-Steuerbetrag falsch
      </rep:message>
      <rep:message level="warning" code="BR-DE-21">[BR-DE-21]-Hinweis</rep:message>
    </rep:validationStepResult>
  </rep:scenarioMatched>
  <rep:assessment><rep:reject/></rep:assessment>
</rep:report>"""


def test_bericht_wird_ausgewertet():
    e = werte_bericht_aus(BERICHT)
    assert e.akzeptiert is False
    assert [(m.stufe, m.code) for m in e.meldungen] == [
        ("error", "BR-S-09"),
        ("warning", "BR-DE-21"),
    ]
    assert [m.code for m in e.fehler] == ["BR-S-09"]
    assert "Steuerbetrag falsch" in e.meldungen[0].text


def test_akzeptierter_bericht():
    xml = BERICHT.replace(b"<rep:reject/>", b"<rep:accept/>").replace(
        b'valid="false"', b'valid="true"'
    )
    assert werte_bericht_aus(xml).akzeptiert is True


def test_ohne_installation(tmp_path):
    pruefer = KositPruefer(tmp_path)
    assert not pruefer.verfuegbar()
    with pytest.raises(KositNichtVerfuegbarError, match="kosit_installieren"):
        pruefer.pruefe(b"<x/>")


@NUR_MIT_KOSIT
def test_erzeugte_rechnungen_sind_konform():
    """Akzeptanz 4 — das offizielle Prüfwerkzeug akzeptiert, was accounti schreibt."""
    dateien = {f"{name}.xml": schreibe_cii(_bau(e)) for name, e in FAELLE.items()}
    ergebnisse = PRUEFER.pruefe_mehrere(dateien)
    for name, ergebnis in ergebnisse.items():
        assert ergebnis.akzeptiert, (name, [str(m) for m in ergebnis.meldungen])


@NUR_MIT_KOSIT
def test_eingangs_fixtures_und_rechenfehler():
    ergebnisse = PRUEFER.pruefe_mehrere(
        {
            n: (FIXTURES / n).read_bytes()
            for n in (
                "xrechnung_cii.xml",
                "xrechnung_ubl.xml",
                "fehler_rechenprobe_cii.xml",
            )
        }
    )
    assert ergebnisse["xrechnung_cii.xml"].akzeptiert
    assert ergebnisse["xrechnung_ubl.xml"].akzeptiert
    abgelehnt = ergebnisse["fehler_rechenprobe_cii.xml"]
    assert not abgelehnt.akzeptiert
    assert "BR-S-09" in {m.code for m in abgelehnt.fehler}
