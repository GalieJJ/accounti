from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from accounti.bank.abgleich import (
    Stufe,
    bewerte_paar,
    gleiche_ab,
    ist_ruecklastschrift,
    namens_treffer,
)
from accounti.models import (
    Beleg,
    Belegart,
    Belegrichtung,
    BelegStatus,
    Transaktion,
    TransaktionQuelle,
)

TAG = date(2026, 3, 12)


def quittung(brutto="59.50", **kw):
    werte = {
        "belegart": Belegart.QUITTUNG,
        "richtung": Belegrichtung.EINGANG,
        "belegdatum": TAG,
        "lieferant_name": "Shell Station Kiel",
        "brutto": Decimal(brutto),
        "datei_hash": uuid4().hex * 2,
        "dateiname": "quittung.jpg",
        "kanal": "ordner",
        "herkunft": "test",
        "aufbewahren_bis": date(2036, 12, 31),
        "status": BelegStatus.ERFASST,
    }
    werte.update(kw)
    return Beleg(**werte)


def umsatz(betrag="-59.50", tag=1, **kw):
    werte = {
        "datum": date(2026, 3, 12 + tag) if tag >= 0 else date(2026, 3, 12 + tag),
        "betrag": Decimal(betrag),
        "verwendungszweck": "KARTENZAHLUNG GIROCARD 12.03. SHELL 4711 KIEL",
        "gegenkonto_name": "SHELL DEUTSCHLAND OIL",
        "quelle": TransaktionQuelle.BANK,
        "rohtext": "",
    }
    werte.update(kw)
    return Transaktion(**werte)


# --- Paarbewertung --------------------------------------------------------------


def test_referenz():
    b = quittung(belegnummer="Q-2026-00042", lieferant_name="Kiosk")
    tx = umsatz(verwendungszweck="Beleg Q2026 00042", gegenkonto_name="SumUp")
    k = bewerte_paar(tx, b)
    assert k is not None and k.stufe is Stufe.REFERENZ
    assert k.confidence == 1.0 and k.differenz == 0


def test_exakt_mit_namen():
    k = bewerte_paar(umsatz(), quittung())
    assert k is not None and k.stufe is Stufe.EXAKT
    assert "Shell Station Kiel" in k.begruendung


def test_exakt_mit_iban():
    iban = "DE02120300000000202051"
    b = quittung(lieferant_name="Parkhaus GmbH", iban=iban)
    tx = umsatz(
        gegenkonto_name="APCOA", verwendungszweck="Parken", gegenkonto_iban=iban
    )
    k = bewerte_paar(tx, b)
    assert k is not None and k.stufe is Stufe.EXAKT
    assert "IBAN" in k.begruendung


def test_betrag_ohne_namen_ist_nur_vorschlag():
    tx = umsatz(gegenkonto_name="SumUp", verwendungszweck="SUMUP *KIOSK 12")
    k = bewerte_paar(tx, quittung())
    assert k is not None and k.stufe is Stufe.UNSCHARF


def test_zu_spaet_fuer_exakt():
    k = bewerte_paar(umsatz(tag=12), quittung())
    assert k is not None and k.stufe is Stufe.UNSCHARF


@pytest.mark.parametrize("tag", [-4, 31])
def test_ausserhalb_des_zeitfensters(tag):
    if tag < 0:
        tx = umsatz(tag=0).model_copy(update={"datum": date(2026, 3, 8)})
    else:
        tx = umsatz(tag=0).model_copy(update={"datum": date(2026, 4, 12)})
    assert bewerte_paar(tx, quittung()) is None


def test_falsche_richtung():
    assert bewerte_paar(umsatz(betrag="59.50"), quittung()) is None
    ausgang = quittung(richtung=Belegrichtung.AUSGANG)
    assert bewerte_paar(umsatz(), ausgang) is None
    k = bewerte_paar(umsatz(betrag="59.50"), ausgang)
    assert k is not None and k.stufe is Stufe.EXAKT


def test_gutschrift():
    erstattung = quittung(brutto="-19.99")
    k = bewerte_paar(umsatz(betrag="19.99"), erstattung)
    assert k is not None and k.stufe is Stufe.EXAKT
    assert bewerte_paar(umsatz(betrag="-19.99"), erstattung) is None


def test_rundungsdifferenz():
    k = bewerte_paar(umsatz(betrag="-59.51"), quittung())
    assert k is not None and k.stufe is Stufe.UNSCHARF
    assert k.differenz == Decimal("0.01")


def test_trinkgeld_nur_mit_namen():
    b = quittung(brutto="49.80", lieferant_name="Trattoria Roma")
    mit = umsatz(betrag="-55.00", gegenkonto_name="TRATTORIA ROMA KIEL")
    k = bewerte_paar(mit, b)
    assert k is not None and k.stufe is Stufe.UNSCHARF
    assert k.differenz == Decimal("5.20")
    ohne = umsatz(betrag="-55.00", gegenkonto_name="SumUp", verwendungszweck="x")
    assert bewerte_paar(ohne, b) is None
    zu_viel = umsatz(betrag="-60.00", gegenkonto_name="TRATTORIA ROMA KIEL")
    assert bewerte_paar(zu_viel, b) is None


def test_ohne_betrag_kein_abgleich():
    assert bewerte_paar(umsatz(), quittung(brutto="0")) is None
    assert (
        bewerte_paar(umsatz(), quittung().model_copy(update={"brutto": None})) is None
    )


@pytest.mark.parametrize(
    ("lieferant", "gegenseite", "erwartet"),
    [
        ("Shell Station Kiel", "SHELL DEUTSCHLAND OIL KIEL", True),
        ("Bürobedarf Müller GmbH", "BUEROBEDARF MUELLER", True),
        ("Shell Station Kiel", "ARAL TANKSTELLE KIEL", False),
        ("Kiosk", "SUMUP KIOSK AM MARKT", True),
        (None, "SHELL", False),
    ],
)
def test_namens_treffer(lieferant, gegenseite, erwartet):
    assert namens_treffer(lieferant, gegenseite) is erwartet


@pytest.mark.parametrize(
    ("zweck", "erwartet"),
    [
        ("RUECKLASTSCHRIFT MANGELS DECKUNG", True),
        ("Rücklastschrift Entgelt", True),
        ("RUECKBUCHUNG KARTENZAHLUNG", True),
        ("Rückbelastung", True),
        ("KARTENZAHLUNG GIROCARD", False),
    ],
)
def test_ruecklastschrift(zweck, erwartet):
    assert ist_ruecklastschrift(umsatz(verwendungszweck=zweck)) is erwartet


# --- Gesamtabgleich ----------------------------------------------------------------


def test_eindeutiges_wird_automatisch():
    b, tx = quittung(), umsatz()
    ergebnis = gleiche_ab([tx], [b])
    (k,) = ergebnis.automatisch
    assert (k.transaktion, k.beleg) == (tx, b)
    assert ergebnis.vorschlaege == [] and ergebnis.ohne_treffer == 0


def test_zwei_gleiche_quittungen_am_selben_tag_werden_vorgeschlagen():
    """Akzeptanz 4: keine willkürliche Zuordnung, sondern zwei Vorschläge."""
    b1, b2, tx = quittung(), quittung(), umsatz()
    ergebnis = gleiche_ab([tx], [b1, b2])
    assert ergebnis.automatisch == []
    assert {k.beleg.id for k in ergebnis.vorschlaege} == {b1.id, b2.id}


def test_zwei_gleiche_paare_werden_nicht_verteilt():
    b1, b2 = quittung(), quittung()
    t1, t2 = umsatz(), umsatz()
    ergebnis = gleiche_ab([t1, t2], [b1, b2])
    assert ergebnis.automatisch == []
    assert len(ergebnis.vorschlaege) == 4


def test_name_unterscheidet_gleiche_betraege():
    shell = quittung()
    aral = quittung(lieferant_name="Aral Tankstelle Kiel")
    tx = umsatz()
    ergebnis = gleiche_ab([tx], [shell, aral])
    (k,) = ergebnis.automatisch
    assert k.beleg == shell
    assert ergebnis.vorschlaege == []  # der Beleg-Kandidat ohne Namen ist mitvergeben


def test_referenz_geht_vor():
    b = quittung(belegnummer="Q-2026-00042")
    mit_referenz = umsatz(tag=3, verwendungszweck="Q-2026-00042 Shell")
    nur_name = umsatz()
    ergebnis = gleiche_ab([nur_name, mit_referenz], [b])
    (k,) = ergebnis.automatisch
    assert (k.transaktion, k.stufe) == (mit_referenz, Stufe.REFERENZ)
    assert ergebnis.vorschlaege == [] and ergebnis.ohne_treffer == 1


def test_ruecklastschrift_wird_gemeldet_nicht_abgeglichen():
    erstattung = quittung(brutto="-59.50")
    rueck = umsatz(betrag="59.50", verwendungszweck="RUECKLASTSCHRIFT SHELL KIEL")
    ergebnis = gleiche_ab([rueck], [erstattung])
    assert ergebnis.automatisch == [] and ergebnis.vorschlaege == []
    assert ergebnis.ruecklastschriften == [rueck]


def test_abgelehnte_paare_kommen_nicht_wieder():
    b, tx = quittung(), umsatz()
    ergebnis = gleiche_ab([tx], [b], abgelehnt={(tx.id, b.id)})
    assert ergebnis.automatisch == [] and ergebnis.vorschlaege == []
    assert ergebnis.ohne_treffer == 1


def test_hoechstens_drei_vorschlaege_je_umsatz():
    belege = [quittung() for _ in range(5)]
    ergebnis = gleiche_ab([umsatz()], belege)
    assert len(ergebnis.vorschlaege) == 3
