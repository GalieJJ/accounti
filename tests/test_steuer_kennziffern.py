"""Kennziffern aus Buchungssätzen: Steuerschlüssel, Kennzifferkonten, Vorzeichen."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from accounti.models import Buchungssatz, BuchungStatus, Kontakt
from accounti.steuer.kennziffern import Kontenplan, ermittle
from accounti.steuer.zeitraum import Zeitraum

D = Decimal

AUGUST = Zeitraum.lies("2026-08")
TAG = date(2026, 8, 14)

KUNDE_DE = Kontakt(name="Kunde DE", debitor_konto="10001")
KUNDE_AT = Kontakt(
    name="Rahmen Wien", land="AT", ust_id="ATU12345678", debitor_konto="10002"
)
LIEFERANT_AT = Kontakt(name="Agentur Wien", land="AT", kreditor_konto="70002")
LIEFERANT_DE = Kontakt(name="Bau GmbH", kreditor_konto="70001")
KONTAKTE = [KUNDE_DE, KUNDE_AT, LIEFERANT_AT, LIEFERANT_DE]


def b(soll, haben, netto, schluessel=None, steuer=None, **kw):
    return Buchungssatz(
        datum=kw.pop("datum", TAG),
        soll_konto=soll,
        haben_konto=haben,
        betrag_netto=D(netto),
        steuer_schluessel=schluessel,
        steuer_betrag=D(steuer) if steuer is not None else None,
        buchungstext="Test",
        status=kw.pop("status", BuchungStatus.AUTO_GEBUCHT),
        **kw,
    )


def test_konstellationen_skr03():
    rechnung_ig = uuid4()
    buchungen = [
        b("10001", "8400", "1000.50", 3, "190.10"),  # Inland 19 %
        b("1200", "8300", "100.00", 2, "7.00"),  # Inland 7 % über die Bank
        b("8400", "10001", "50.00", 3, "9.50"),  # Gutschrift
        b("8736", "10001", "10.00", 3, "1.90"),  # gewährtes Skonto
        b("4930", "70001", "100.00", 9, "19.00"),  # Vorsteuer
        b("70001", "3736", "5.00", 9, "0.95"),  # erhaltenes Skonto
        b("10002", "8125", "5000.00", beleg_id=rechnung_ig),  # ig. Lieferung
        b("8730", "10002", "20.00", beleg_id=rechnung_ig),  # Skonto darauf
        b("10002", "8336", "300.00"),  # EU-Leistung, Empfänger schuldet
        b("10001", "8120", "700.00"),  # Ausfuhr
        b("1200", "8320", "200.00"),  # OSS Frankreich
        b("4900", "70002", "1000.00", 94, "190.00"),  # § 13b Abs. 1 (EU)
        b("4900", "70001", "400.00", 94, "76.00"),  # § 13b Abs. 2 (Inland)
        b("3425", "70002", "500.00", 19, "95.00"),  # ig. Erwerb 19 %
        b("1200", "10001", "1190.60"),  # Zahlung: keine Kennziffer
        b("1780", "70009", "500.00"),  # Zahllast: keine Kennziffer
        b("10001", "8400", "999.00", 3, "189.81", datum=date(2026, 9, 1)),  # außerhalb
    ]
    e = ermittle(buchungen, AUGUST, Kontenplan(), KONTAKTE)
    va = e.voranmeldung
    assert va.werte == {
        81: D("940.50"),  # 1000,50 − 50 − 10
        86: D("100.00"),
        66: D("18.05"),  # 19,00 − 0,95
        41: D("4980.00"),  # 5000 − 20 Skonto
        21: D("300.00"),
        43: D("700.00"),
        45: D("200.00"),
        46: D("1000.00"),
        47: D("190.00"),
        84: D("400.00"),
        85: D("76.00"),
        67: D("266.00"),
        89: D("500.00"),
        61: D("95.00"),
    }
    assert e.ohne_kennziffer == [] and e.offen == []
    assert e.gebuchte_umsatzsteuer == D("185.70")  # 190,10 + 7 − 9,50 − 1,90
    eu = sorted((u.art, u.betrag, u.kontakt.name if u.kontakt else None) for u in e.eu)
    assert eu == [
        ("L", D("-20.00"), "Rahmen Wien"),
        ("L", D("5000.00"), "Rahmen Wien"),
        ("S", D("300.00"), "Rahmen Wien"),
    ]


def test_offene_buchungen_zaehlen_nicht():
    buchungen = [
        b("10001", "8400", "100", 3, "19", status=BuchungStatus.ZUR_PRUEFUNG),
        b("10001", "8400", "200", 3, "38", status=BuchungStatus.GEPRUEFT),
        b("10001", "8400", "300", 3, "57", status=BuchungStatus.EXPORTIERT),
    ]
    e = ermittle(buchungen, AUGUST, Kontenplan(), KONTAKTE)
    assert e.voranmeldung.werte == {81: D("500")}
    assert [x.betrag_netto for x in e.offen] == [D("100")]


def test_erloes_ohne_steuerschluessel_hat_keine_kennziffer():
    buchungen = [
        b("10001", "8200", "100"),  # Erlöse ohne Schlüssel
        b("10001", "8400", "100", 5, "16"),  # Schlüssel ohne Kennziffer
        b("4900", "1200", "50"),  # Aufwand ohne Vorsteuer: kein Befund
    ]
    e = ermittle(buchungen, AUGUST, Kontenplan(), KONTAKTE)
    assert e.voranmeldung.werte == {}
    gruende = [grund for _, grund in e.ohne_kennziffer]
    assert "8200 ohne Steuerschlüssel" in gruende[0]
    assert "Steuerschlüssel 5" in gruende[1]


def test_eigene_kennzifferkonten_und_steuerrelevante_bereiche():
    plan = Kontenplan(
        kennziffern_konten={"8150": 43}, steuerrelevant=((8000, 8999), (2700, 2749))
    )
    buchungen = [b("10001", "8150", "100"), b("1200", "2700", "10")]
    e = ermittle(buchungen, AUGUST, plan, KONTAKTE)
    assert e.voranmeldung.werte == {43: D("100")}
    assert [x.haben_konto for x, _ in e.ohne_kennziffer] == ["2700"]


def test_skr04():
    plan = Kontenplan(kontenrahmen="SKR04")
    buchungen = [
        b("10001", "4400", "100", 3, "19"),
        b("10002", "4125", "50"),
        b("6300", "70001", "10", 9, "1.90"),
        b("1800", "4200", "5"),  # SKR04-Erlöskonto ohne Schlüssel
    ]
    e = ermittle(buchungen, AUGUST, plan, KONTAKTE)
    assert e.voranmeldung.werte == {81: D("100"), 41: D("50"), 66: D("1.90")}
    assert [x.haben_konto for x, _ in e.ohne_kennziffer] == ["4200"]


def test_abnehmer_ueber_offenen_posten_des_belegs():
    beleg = uuid4()
    e = ermittle(
        [b("1200", "8125", "100", beleg_id=beleg)],
        AUGUST,
        Kontenplan(),
        KONTAKTE,
        beleg_kontakte={beleg: KUNDE_AT.id},
    )
    assert e.eu[0].kontakt == KUNDE_AT


def test_quartal():
    q3 = Zeitraum.lies("2026-Q3")
    buchungen = [
        b("10001", "8400", "100", 3, "19", datum=date(2026, 7, 1)),
        b("10001", "8400", "100", 3, "19", datum=date(2026, 9, 30)),
        b("10001", "8400", "100", 3, "19", datum=date(2026, 10, 1)),
    ]
    assert ermittle(buchungen, q3, Kontenplan()).voranmeldung.werte == {81: D("200")}


# --- Belegregel nur für echte Minderungen (Akzeptanz 2) ------------------------------


def test_haben_buchung_ohne_schluessel_mindert_keine_rechnung():
    """Eine Erlösbuchung im Haben ist keine Minderung — auch nicht auf einem Beleg
    mit ig. Lieferung. Sonst fehlt die Umsatzsteuer, und Kz 41 und ZM sind zu hoch."""
    beleg = uuid4()
    buchungen = [
        b("10002", "8125", "5000.00", beleg_id=beleg),
        b("10002", "8200", "300.00", beleg_id=beleg, status=BuchungStatus.GEPRUEFT),
    ]
    e = ermittle(buchungen, AUGUST, Kontenplan(), KONTAKTE)
    assert e.voranmeldung.werte == {41: D("5000.00")}
    assert [x.haben_konto for x, _ in e.ohne_kennziffer] == ["8200"]
    assert [u.betrag for u in e.eu] == [D("5000.00")]


def test_steuerfreie_rechnung_mit_zweitem_erloes_ohne_schluessel():
    beleg = uuid4()
    buchungen = [
        b("10001", "8100", "1000.00", beleg_id=beleg),
        b("10001", "8400", "500.00", beleg_id=beleg),
    ]
    e = ermittle(buchungen, AUGUST, Kontenplan(), KONTAKTE)
    assert e.voranmeldung.werte == {48: D("1000.00")}
    assert [x.haben_konto for x, _ in e.ohne_kennziffer] == ["8400"]


def test_umbuchung_vom_funktionskonto_auf_erloes_ohne_schluessel():
    e = ermittle([b("8125", "8400", "1000.00")], AUGUST, Kontenplan(), KONTAKTE)
    assert e.voranmeldung.werte == {}
    ((buchung, grund),) = e.ohne_kennziffer
    assert "8400" in grund


def test_umbuchung_zwischen_funktionskonten_zaehlt_beide_seiten():
    e = ermittle([b("8120", "8125", "400.00")], AUGUST, Kontenplan(), KONTAKTE)
    assert e.voranmeldung.werte == {41: D("400.00"), 43: D("-400.00")}


def test_minderungen_folgen_der_rechnung():
    """Soll-Buchung auf einem Erlöskonto und Erlösschmälerungskonten (beide Seiten)."""
    beleg = uuid4()
    buchungen = [
        b("10002", "8125", "5000.00", beleg_id=beleg),
        b("8730", "10002", "100.00", beleg_id=beleg),  # Skonto
        b("10002", "8730", "40.00", beleg_id=beleg),  # Skonto teilweise storniert
        b("8200", "10002", "10.00", beleg_id=beleg),  # Gutschrift ohne Schlüssel
    ]
    e = ermittle(buchungen, AUGUST, Kontenplan(), KONTAKTE)
    assert e.voranmeldung.werte == {41: D("4930.00")}
    assert e.ohne_kennziffer == []


# --- Vorzeichen ohne Personen- oder Geldkonto ---------------------------------------


def test_storno_ueber_zwischenkonten_mindert_den_umsatz():
    plan = Kontenplan(kontenrahmen="SKR04")
    buchungen = [
        b("1460", "4400", "1000.00", 3, "190.00"),  # Geldtransit
        b("4400", "1460", "1000.00", 3, "190.00"),  # Storno
        b("1370", "4400", "500.00", 3, "95.00"),  # durchlaufende Posten
        b("4400", "1370", "500.00", 3, "95.00"),
        b("1500", "4400", "200.00", 3, "38.00"),  # sonstiges Konto: Erlöskonto zählt
        b("4400", "1500", "200.00", 3, "38.00"),
        b("6300", "1460", "100.00", 9, "19.00"),
        b("1460", "6300", "100.00", 9, "19.00"),
    ]
    e = ermittle(buchungen, AUGUST, plan, KONTAKTE)
    assert e.voranmeldung.wert(81) == 0 and e.voranmeldung.wert(66) == 0
    assert e.gebuchte_umsatzsteuer == 0


def test_storno_ueber_durchlaufende_posten_skr03():
    buchungen = [
        b("1590", "8400", "1000.00", 3, "190.00"),
        b("8400", "1590", "1000.00", 3, "190.00"),
    ]
    e = ermittle(buchungen, AUGUST, Kontenplan(), KONTAKTE)
    assert e.voranmeldung.wert(81) == 0 and e.gebuchte_umsatzsteuer == 0


# --- eigene Kennzifferkonten: Seite je Kennziffer -----------------------------------


def test_eingangsseite_ueber_kennzifferkonten_mit_richtigem_vorzeichen():
    plan = Kontenplan(kennziffern_konten={"3550": 91, "3420": 90, "1588": 62})
    buchungen = [
        b("3550", "70001", "2000.00"),  # steuerfreier ig. Erwerb
        b("3420", "70002", "1500.00"),  # ig. Erwerb 0 %
        b("70001", "3550", "100.00"),  # Gutschrift darauf
        b("1588", "1200", "1900.00"),  # Einfuhrumsatzsteuer
    ]
    e = ermittle(buchungen, AUGUST, plan, KONTAKTE)
    assert e.voranmeldung.werte == {
        91: D("1900.00"),
        90: D("1500.00"),
        62: D("1900.00"),
    }
    assert e.ohne_kennziffer == [] and e.warnungen == []


def test_steuerkonto_ohne_kennziffer_ist_eine_warnung():
    buchungen = [
        b("1588", "1200", "1900.00"),  # EUSt ohne Zuordnung
        b("1780", "70009", "500.00"),  # Zahllast: kein Befund
        b("70009", "1200", "500.00"),
    ]
    e = ermittle(buchungen, AUGUST, Kontenplan(), KONTAKTE)
    assert e.voranmeldung.werte == {}
    (warnung,) = e.warnungen
    assert "1588" in warnung and "kennziffern_konten" in warnung
    skr04 = ermittle(
        [b("1433", "1800", "50.00"), b("3820", "70009", "500.00")],
        AUGUST,
        Kontenplan(kontenrahmen="SKR04"),
        KONTAKTE,
    )
    assert len(skr04.warnungen) == 1 and "1433" in skr04.warnungen[0]


# --- nicht steuerbare Erträge sind keine Umsatzerlöse -------------------------------


def test_nicht_steuerbare_ertraege_ohne_schluessel_sind_kein_fehler():
    skr03 = [
        b("7110", "8980", "1000.00"),  # Bestandsveränderung
        b("0480", "8990", "500.00"),  # aktivierte Eigenleistung
    ]
    e = ermittle(skr03, AUGUST, Kontenplan(), KONTAKTE)
    assert e.ohne_kennziffer == [] and e.voranmeldung.werte == {}
    skr04 = [
        b("3070", "4930", "800.00"),  # Auflösung einer Rückstellung
        b("1800", "4970", "250.00"),  # Versicherungsentschädigung
    ]
    e = ermittle(skr04, AUGUST, Kontenplan(kontenrahmen="SKR04"), KONTAKTE)
    assert e.ohne_kennziffer == [] and e.voranmeldung.werte == {}


# --- § 13b Abs. 1 über den Kontakt des Belegs ---------------------------------------

GOOGLE = Kontakt(name="Google Ireland", land="IE", kreditor_konto="70010")


def test_eu_leistung_ueber_die_bank_findet_den_leistenden_ueber_den_beleg():
    beleg = uuid4()
    buchung = b("4600", "1200", "1000.00", 94, "190.00", beleg_id=beleg)
    e = ermittle(
        [buchung],
        AUGUST,
        Kontenplan(),
        [*KONTAKTE, GOOGLE],
        beleg_kontakte={beleg: GOOGLE.id},
    )
    assert e.voranmeldung.werte == {46: D("1000.00"), 47: D("190.00"), 67: D("190.00")}
    assert e.warnungen == []


def test_unbekannter_leistender_bei_13b_ist_eine_warnung():
    e = ermittle(
        [b("4600", "1200", "1000.00", 94, "190.00")], AUGUST, Kontenplan(), KONTAKTE
    )
    assert e.voranmeldung.wert(84) == D("1000.00")
    (warnung,) = e.warnungen
    assert "Leistender unbekannt" in warnung


# --- Altbuchungen von EU-Leistungen auf 8338/8339 -----------------------------------


def test_nicht_steuerbar_an_eu_unternehmer_ist_eine_warnung():
    buchungen = [
        b("10002", "8338", "300.00"),  # Wien mit USt-IdNr.: gehört auf 8336
        b("10001", "8339", "100.00"),  # Inlandskunde: kein Befund
    ]
    e = ermittle(buchungen, AUGUST, Kontenplan(), KONTAKTE)
    assert e.voranmeldung.werte == {45: D("400.00")}
    (warnung,) = e.warnungen
    assert "8338" in warnung and "8336" in warnung and "ATU12345678" in warnung


# --- SKR04: steuerpflichtige Erlöse unter den sonstigen Erträgen (Runde 2) -----------


def test_skr04_steuerpflichtige_sonstige_ertraege_ohne_schluessel_sperren():
    """DATEV-Automatikkonten mit Umsatzsteuer liegen in SKR04 auch in 48xx/49xx/688x —
    ihre SKR03-Gegenstücke (8611, 8640, 8820, 8801, 2752) erkennt die Ermittlung."""
    plan = Kontenplan(kontenrahmen="SKR04")
    buchungen = [
        b("1800", "4845", "10000.00"),  # Anlagenverkauf 19 % (Buchgewinn)
        b("6020", "4947", "500.00"),  # Kfz-Gestellung 19 %
        b("1800", "6885", "800.00"),  # Anlagenverkauf 19 % (Buchverlust)
        b("1800", "4862", "1200.00"),  # Vermietung 19 %
        b("1800", "4836", "300.00"),  # sonstige Erträge regelmäßig 19 %
        b("1800", "4833", "50.00"),  # andere Nebenerlöse (Umsatzerlöse)
    ]
    e = ermittle(buchungen, AUGUST, plan, KONTAKTE)
    assert e.voranmeldung.werte == {}
    assert [x.haben_konto for x, _ in e.ohne_kennziffer] == [
        "4833",
        "4836",
        "4845",
        "4862",
        "6885",
        "4947",
    ]


def test_skr04_nicht_steuerbare_ertraege_bleiben_ohne_befund():
    plan = Kontenplan(kontenrahmen="SKR04")
    buchungen = [
        b("1800", "4840", "20.00"),  # Währungsumrechnung
        b("4855", "0520", "3000.00"),  # Restbuchwert bei Buchgewinn
        b("1800", "4838", "40.00"),  # erstattete Vorsteuer anderer Länder
        b("3070", "4930", "800.00"),  # Auflösung einer Rückstellung
        b("1800", "4970", "250.00"),  # Versicherungsentschädigung
    ]
    e = ermittle(buchungen, AUGUST, plan, KONTAKTE)
    assert e.ohne_kennziffer == [] and e.voranmeldung.werte == {}


def test_skr04_storno_eines_sachbezugs_ueber_die_lohnverrechnung():
    """Weder 3790 noch 4947 ist ein Gegenkonto: das Erlöskonto entscheidet."""
    plan = Kontenplan(kontenrahmen="SKR04")
    buchungen = [
        b("3790", "4947", "1000.00", 3, "190.00"),
        b("4947", "3790", "1000.00", 3, "190.00"),  # Storno
    ]
    e = ermittle(buchungen, AUGUST, plan, KONTAKTE)
    assert e.voranmeldung.wert(81) == 0 and e.gebuchte_umsatzsteuer == 0
    skr03 = ermittle(
        [
            b("1755", "8611", "1000.00", 3, "190.00"),
            b("8611", "1755", "1000.00", 3, "190.00"),
        ],
        AUGUST,
        Kontenplan(),
        KONTAKTE,
    )
    assert skr03.voranmeldung.wert(81) == 0 and skr03.gebuchte_umsatzsteuer == 0


def test_skr03_vermietung_ohne_schluessel_sperrt():
    e = ermittle([b("1200", "2752", "1200.00")], AUGUST, Kontenplan(), KONTAKTE)
    assert [x.haben_konto for x, _ in e.ohne_kennziffer] == ["2752"]


# --- Belegregel: Mischrechnung und Umbuchung (Runde 2) ------------------------------


def test_gutschrift_ohne_schluessel_auf_einer_mischrechnung_sperrt():
    """Die Rechnung hat Kz 41 und Kz 81: wohin die Gutschrift gehört, ist offen."""
    beleg = uuid4()
    gutschrift = b("8400", "10002", "1000.00", beleg_id=beleg)
    buchungen = [
        b("10002", "8125", "5000.00", beleg_id=beleg),
        b("10002", "8400", "1000.00", 3, "190.00", beleg_id=beleg),
        gutschrift,
    ]
    e = ermittle(buchungen, AUGUST, Kontenplan(), KONTAKTE)
    assert e.voranmeldung.werte == {41: D("5000.00"), 81: D("1000.00")}
    ((buchung, grund),) = e.ohne_kennziffer
    assert buchung.id == gutschrift.id and "mehreren Kennziffern" in grund
    assert [u.betrag for u in e.eu] == [D("5000.00")]


def test_minderung_einer_steuerpflichtigen_rechnung_braucht_den_schluessel():
    """Ohne Schlüssel fehlt die Korrektur der Umsatzsteuer (§ 17 UStG)."""
    beleg = uuid4()
    buchungen = [
        b("10001", "8400", "1000.00", 3, "190.00", beleg_id=beleg),
        b("8730", "10001", "20.00", beleg_id=beleg),
    ]
    e = ermittle(buchungen, AUGUST, Kontenplan(), KONTAKTE)
    assert e.voranmeldung.werte == {81: D("1000.00")}
    ((buchung, grund),) = e.ohne_kennziffer
    assert buchung.soll_konto == "8730" and "Steuerschlüssel" in grund


def test_umbuchung_vom_erloes_auf_ein_funktionskonto_ist_keine_minderung():
    """``8400 an 8125`` auf einem Beleg mit ig. Lieferung sperrt wie ohne Beleg."""
    beleg = uuid4()
    umbuchung = b("8400", "8125", "1000.00", beleg_id=beleg)
    buchungen = [b("10002", "8125", "5000.00", beleg_id=beleg), umbuchung]
    e = ermittle(buchungen, AUGUST, Kontenplan(), KONTAKTE)
    assert e.voranmeldung.werte == {41: D("5000.00")}
    ((buchung, grund),) = e.ohne_kennziffer
    assert buchung.id == umbuchung.id and "8400" in grund
    assert [u.betrag for u in e.eu] == [D("5000.00")]


def test_minderung_nur_gegen_personen_oder_geldkonto():
    """Eine Umbuchung vom Erlösschmälerungs- auf ein anderes Sachkonto ist keine
    Minderung der Rechnung."""
    beleg = uuid4()
    umbuchung = b("8730", "2700", "100.00", beleg_id=beleg)  # an sonstige Erträge
    buchungen = [
        b("10002", "8125", "5000.00", beleg_id=beleg),
        b("8730", "1200", "30.00", beleg_id=beleg),  # Skonto über die Bank: Minderung
        umbuchung,
    ]
    e = ermittle(buchungen, AUGUST, Kontenplan(), KONTAKTE)
    assert e.voranmeldung.werte == {41: D("4970.00")}
    ((buchung, grund),) = e.ohne_kennziffer
    assert buchung.id == umbuchung.id and "2700" in grund


def test_skonto_aus_dem_ausgleich_einer_mischrechnung():
    """opos/ausgleich teilt das Skonto nach Steuersätzen: Der steuerpflichtige Teil
    steht mit Schlüssel in derselben Transaktion, der Rest ohne Schlüssel gehört zur
    einzigen steuerfreien Kennziffer der Rechnung (Kz 41)."""
    beleg, tx = uuid4(), uuid4()
    buchungen = [
        b("10002", "8125", "5000.00", beleg_id=beleg),
        b("10002", "8400", "1000.00", 3, "190.00", beleg_id=beleg),
        b("1200", "10002", "6066.20", transaktion_id=tx, beleg_id=beleg),
        b("8730", "10002", "100.00", transaktion_id=tx, beleg_id=beleg),
        b("8736", "10002", "20.00", 3, "3.80", transaktion_id=tx, beleg_id=beleg),
    ]
    e = ermittle(buchungen, AUGUST, Kontenplan(), KONTAKTE)
    assert e.ohne_kennziffer == []
    assert e.voranmeldung.werte[41] == D("4900.00")
    assert e.voranmeldung.werte[81] == D("980.00")
    assert sum(u.betrag for u in e.eu) == D("4900.00")


def test_manuelle_minderung_einer_mischrechnung_bleibt_mehrdeutig():
    """Ohne die aufgeteilte Ausgleichsbuchung lässt sich nicht sagen, welchen Teil
    der Rechnung die Minderung trifft — die Freigabe bleibt gesperrt."""
    beleg = uuid4()
    buchungen = [
        b("10002", "8125", "5000.00", beleg_id=beleg),
        b("10002", "8400", "1000.00", 3, "190.00", beleg_id=beleg),
        b("8730", "10002", "100.00", beleg_id=beleg),
    ]
    e = ermittle(buchungen, AUGUST, Kontenplan(), KONTAKTE)
    ((buchung, grund),) = e.ohne_kennziffer
    assert buchung.soll_konto == "8730" and "mehreren Kennziffern" in grund
