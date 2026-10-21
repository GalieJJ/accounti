"""Abschlusszuordnung der Konten: Kontoart, Geldkonten, Steuerkonten, EÜR-Kennzahl."""

from decimal import Decimal

import pytest

from accounti.abschluss.kontenrahmen import (
    Kontenart,
    KontenrahmenError,
    lade_kontenrahmen,
)

SKR03 = lade_kontenrahmen("SKR03")
SKR04 = lade_kontenrahmen("SKR04")


@pytest.mark.parametrize(
    ("konto", "euer", "bilanz"),
    [
        ("0420", Kontenart.BESTAND, Kontenart.BESTAND),
        ("1200", Kontenart.BESTAND, Kontenart.BESTAND),
        ("1576", Kontenart.ERFOLG, Kontenart.BESTAND),  # Steuerkonto
        ("1780", Kontenart.ERFOLG, Kontenart.BESTAND),
        ("177720", Kontenart.ERFOLG, Kontenart.BESTAND),  # 6-stellig: OSS-USt
        ("1800", Kontenart.PRIVAT, Kontenart.PRIVAT),
        ("4930", Kontenart.ERFOLG, Kontenart.ERFOLG),
        ("3980", Kontenart.BESTAND, Kontenart.BESTAND),
        ("8400", Kontenart.ERFOLG, Kontenart.ERFOLG),
        ("9000", Kontenart.VORTRAG, Kontenart.VORTRAG),
        ("70001", Kontenart.BESTAND, Kontenart.BESTAND),  # Personenkonto
    ],
)
def test_kontoart_skr03(konto, euer, bilanz):
    assert SKR03.art(konto, "euer") is euer
    assert SKR03.art(konto, "bilanz") is bilanz


def test_kontoart_skr04():
    assert SKR04.art("6220", "euer") is Kontenart.ERFOLG
    assert SKR04.art("1406", "bilanz") is Kontenart.BESTAND
    assert SKR04.art("1406", "euer") is Kontenart.ERFOLG
    assert SKR04.art("2100", "euer") is Kontenart.PRIVAT
    assert SKR04.art("2010", "euer") is Kontenart.BESTAND


def test_geldkonten():
    for konto in ("1000", "1200", "1360", "1400", "1600", "10001", "70001"):
        assert SKR03.ist_geldkonto(konto), konto
    for konto in ("4930", "1576", "0420", "8400", "1800"):
        assert not SKR03.ist_geldkonto(konto), konto
    assert SKR04.ist_geldkonto("1800") and not SKR04.ist_geldkonto("6815")


def test_steuerkonten():
    assert [SKR03.steuerkonto(s) for s in (9, 8, 3, 2, 40, None)] == [
        "1576",
        "1571",
        "1776",
        "1771",
        None,
        None,
    ]
    assert [SKR04.steuerkonto(s) for s in (9, 8, 3, 2)] == [
        "1406",
        "1401",
        "3806",
        "3801",
    ]
    assert SKR03.ist_vorsteuer(9) and not SKR03.ist_vorsteuer(3)


@pytest.mark.parametrize(
    ("konto", "saldo", "kz"),
    [
        ("8400", "-100", "112"),
        ("8125", "-100", "103"),
        ("8820", "-100", "102"),
        ("8921", "-100", "106"),
        ("4930", "100", "229"),
        ("4830", "100", "130"),
        ("4855", "100", "132"),
        ("4862", "100", "137"),
        ("2315", "100", "135"),
        ("1576", "100", "185"),
        ("1776", "-100", "140"),
        ("1780", "100", "186"),
        ("1780", "-100", "141"),
        ("4635", "100", "164"),
        ("4806", "100", "228"),  # engste Spanne gewinnt
        ("4999", "100", "183"),
        ("0420", "100", None),
    ],
)
def test_euer_kennzahl_skr03(konto, saldo, kz):
    assert SKR03.euer_kz(konto, Decimal(saldo)) == kz


def test_euer_kennzahl_skr04():
    assert SKR04.euer_kz("4400", Decimal("-1")) == "112"
    assert SKR04.euer_kz("6220", Decimal("1")) == "130"
    assert SKR04.euer_kz("6895", Decimal("1")) == "135"
    assert SKR04.euer_kz("6805", Decimal("1")) == "280"
    assert SKR04.euer_kz("3820", Decimal("-1")) == "141"


def test_vortragskonten_und_namen():
    assert SKR03.vortragskonto("1200", (10000, 69999), (70000, 99999)) == "9000"
    assert SKR03.vortragskonto("10001", (10000, 69999), (70000, 99999)) == "9008"
    assert SKR03.vortragskonto("70001", (10000, 69999), (70000, 99999)) == "9009"
    assert SKR03.bezeichnung("0980") == "Aktive Rechnungsabgrenzung"
    assert SKR03.bezeichnung("4711") == ""


def test_eigene_zuordnung_und_unbekannter_kontenrahmen(tmp_path):
    datei = tmp_path / "zuordnung.yaml"
    datei.write_text(
        "name: eigen\narten:\n  - {von: '0000', bis: '9999', art: erfolg}\n"
        "euer:\n  - {von: '4000', bis: '4999', kz: '183'}\n",
        encoding="utf-8",
    )
    eigen = lade_kontenrahmen("SKR03", datei)
    assert eigen.art("0420", "euer") is Kontenart.ERFOLG
    assert eigen.euer_kz("4930", Decimal("1")) == "183"
    with pytest.raises(KontenrahmenError, match="SKR99"):
        lade_kontenrahmen("SKR99")


@pytest.mark.parametrize(
    ("konto", "art"),
    [
        ("1788", Kontenart.BESTAND),  # Einfuhrumsatzsteuer aufgeschoben
        ("1792", Kontenart.BESTAND),  # Sonstige Verrechnungskonten (Interimskonten)
        ("1793", Kontenart.BESTAND),  # Verrechnungskonto geleistete Anzahlungen
        ("1795", Kontenart.BESTAND),  # Verbindlichkeiten soziale Sicherheit § 4/3
        ("1796", Kontenart.BESTAND),  # Ausgegebene Geschenkgutscheine
        ("1791", Kontenart.ERFOLG),  # Umsatzsteuer frühere Jahre
        ("1794", Kontenart.ERFOLG),  # USt Dreiecksgeschäft
    ],
)
def test_ust_bereich_skr03_ohne_fremde_konten(konto, art):
    assert SKR03.art(konto, "euer") is art
    assert SKR03.art(konto, "bilanz") is Kontenart.BESTAND


@pytest.mark.parametrize(
    "konto",
    ["2100", "2150", "2180", "2200", "2250", "2280", "2300", "2350", "2399"]
    + ["2500", "2550", "2580", "2600", "2650", "2680", "2700", "2750"],
)
def test_privatkonten_skr04_vollhafter_und_teilhafter(konto):
    assert SKR04.art(konto, "euer") is Kontenart.PRIVAT
    assert SKR04.art(konto, "bilanz") is Kontenart.PRIVAT


def test_steuerbereich_skr04_nur_vorsteuer():
    for konto in ("1400", "1406", "1410", "1433", "1434", "1436"):
        assert SKR04.art(konto, "euer") is Kontenart.ERFOLG, konto
    # Forderungen aus Gewerbesteuerüberzahlungen, USt-Forderungen: keine Vorsteuer
    for konto in ("1435", "1420", "1421", "1427"):
        assert SKR04.art(konto, "euer") is Kontenart.BESTAND, konto
    assert SKR04.art("2010", "euer") is Kontenart.BESTAND
    assert SKR04.art("2900", "euer") is Kontenart.BESTAND


@pytest.mark.parametrize(
    ("konto", "saldo", "kz"),
    [
        # Gewerbesteuer: keine Betriebsausgabe (§ 4 Abs. 5b EStG) → „nicht abziehbar“
        ("4320", "100", "168"),
        ("2280", "100", "168"),
        ("2281", "100", "168"),
        ("2282", "-100", "168"),  # Erstattung Vorjahre
        ("2284", "-100", "168"),
        ("4397", "100", "168"),  # nicht abzugsfähige Verspätungszuschläge
        # abzugsfähige: übrige steuerliche Nebenleistungen gehören in Zeile 60 (Kz 183),
        # nicht zu den Beiträgen/Abgaben (Anleitung zur Anlage EÜR 2025, zu Zeile 58)
        ("4396", "100", "183"),
        # Steuern vom Einkommen: weder Betriebseinnahme noch -ausgabe
        ("2200", "100", "-"),
        ("2208", "100", "-"),
        ("2213", "100", "-"),
        ("2285", "100", "183"),  # sonstige Steuern Vorjahre bleiben Betriebsausgabe
        ("4638", "100", "174"),  # Geschenke ausschließlich betrieblich genutzt
        ("4810", "100", "222"),  # Mietleasing bewegliche WG
        ("4805", "100", "225"),
        ("4853", "100", "138"),  # Kürzung § 7g Abs. 2
        ("4851", "100", "134"),
        # Kleinunternehmer: im Kontenrahmen 2026 Konto 8192 (8195–8196 reserviert)
        ("8192", "-100", "111"),
        ("8190", "-100", "104"),  # Durchschnittssätze § 24 UStG
        ("8191", "-100", "112"),
        # im Inland steuerpflichtige EU-Lieferungen 7 % (8330 ist 2026 reserviert)
        ("8310", "-100", "112"),
        ("8340", "-100", "112"),  # Erlöse 16 % USt
        ("8338", "-100", "103"),
        # USt als letzter Abnehmer im Dreiecksgeschäft: Gegenstück zur Vorsteuer 1573,
        # beide in Zeile 57, damit Zeile 17 nicht aufgebläht wird (vorher 140)
        ("1794", "-100", "185"),
    ],
)
def test_euer_kennzahl_skr03_einzelregeln(konto, saldo, kz):
    assert SKR03.euer_kz(konto, Decimal(saldo)) == kz


@pytest.mark.parametrize(
    ("konto", "saldo", "kz"),
    [
        ("7610", "100", "168"),  # Gewerbesteuer
        ("7640", "100", "168"),
        ("7642", "-100", "168"),
        ("7600", "100", "-"),  # Körperschaftsteuer
        ("7608", "100", "-"),  # Solidaritätszuschlag
        ("7630", "100", "-"),  # Kapitalertragsteuer
        ("7650", "100", "183"),  # sonstige Betriebssteuern
        ("7685", "100", "145"),  # Kfz-Steuer
        ("6437", "100", "168"),
        ("6436", "100", "183"),  # wie SKR03 4396: Zeile 60
        ("6625", "100", "174"),
        ("6243", "100", "138"),
        ("4184", "-100", "111"),  # Kleinunternehmer 2026 (4185–4188 reserviert)
        ("4180", "-100", "104"),
    ],
)
def test_euer_kennzahl_skr04_einzelregeln(konto, saldo, kz):
    assert SKR04.euer_kz(konto, Decimal(saldo)) == kz


# Leitkonten: gesicherte Zuordnung je Kennzahl der Anlage EÜR. Quellen (Stand 2026):
#   KR     DATEV-Kontenrahmen SKR 03 (Art.-Nr. 11174) / SKR 04 (11175), Gültig für 2026
#   KR-EÜR DATEV-Kontenrahmen für Gewinnermittlung nach § 4 Abs. 3 EStG, SKR 03 (11079)
#          / SKR 04 (11080), Gültig für 2026 — Spalte „Posten in der Gewinnermittlung“
#   Anl    Anlage EÜR 2025 mit Anleitung, BMF-Schreiben vom 29.08.2025 (BStBl I S. 1652)
#   DATEV  Hilfe-Dokumente 1036862 (Kfz/Fahrtkosten), 1029703 (Schuldzinsen),
#          1037171 (Vorsteuer ohne Zahlung)
# Saldo: positiv = Soll (Aufwand), negativ = Haben (Ertrag)
LEITKONTEN_SKR03 = [
    # Betriebseinnahmen nach Umsatzsteuer (Anl Zeilen 12–16)
    ("8400", "-100", "112"),  # Erlöse 19 % USt
    ("8192", "-100", "111"),  # steuerfreie Erlöse Kleinunternehmer (KR)
    ("8198", "-100", "112"),  # Umsatzerlöse § 25 UStG 19 % USt (KR)
    ("8290", "-100", "103"),  # Erlöse 0 % USt: § 12 Abs. 3 UStG → Zeile 16 (Anl)
    ("8334", "-100", "112"),  # Erlöse 7 % USt (KR)
    ("8320", "-100", "103"),  # im anderen EU-Land steuerpflichtig (OSS)
    ("8625", "-100", "103"),  # sonstige Erträge steuerfrei § 4 Nr. 2–7 UStG (KR)
    ("8614", "-100", "103"),  # verrechnete Sachbezüge ohne USt (KR)
    ("8950", "-100", "103"),  # nicht steuerbare Umsätze (Innenumsätze) (KR, Anl)
    ("2752", "-100", "112"),  # Vermietung und Verpachtung 19 % USt (KR)
    ("2650", "-100", "103"),  # Zinserträge: umsatzsteuerfrei (Anl Zeile 16)
    # Erlösschmälerungen mindern die Kennzahl der Erlöse (KR-EÜR Posten „Einnahmen“)
    ("8736", "100", "112"),  # gewährte Skonti 19 % USt
    ("8705", "100", "103"),  # Erlösschmälerungen steuerfreie Umsätze § 4 Nr. 1a UStG
    ("8707", "100", "111"),  # Erlösschmälerungen Umsätze § 19 Abs. 1 UStG
    ("8743", "100", "103"),  # Skonti aus steuerfreien ig. Lieferungen
    ("2406", "100", "112"),  # Forderungsverluste 19 % USt (KR-EÜR Posten „Einnahmen“)
    ("2402", "100", "103"),  # Forderungsverluste aus steuerfreien EU-Lieferungen
    # Anlagenverkäufe, Entnahmen (Anl Zeilen 19–21)
    ("8820", "-100", "102"),  # Erlöse Sachanlageverkäufe 19 % USt (Buchgewinn)
    ("8850", "-100", "112"),  # Umlaufvermögen § 4 Abs. 3 S. 4 EStG 19 %: kein AV (Anl)
    ("8921", "-100", "106"),  # private Kfz-Nutzung 19 % (DATEV 1036862)
    ("8910", "-100", "108"),  # Warenentnahme 19 % USt
    # Bestandsveränderungen: keine Betriebseinnahme (fehlen im KR-EÜR)
    ("8980", "-100", "-"),
    # aktivierte Eigenleistungen: nicht umsatzsteuerbar, daher nur Zeile 16 möglich;
    # ob sie Betriebseinnahme sind, ist offen (yaml: prüfen)
    ("8990", "-100", "103"),
    # Wareneingang, Fremdleistungen (Anl Zeilen 27, 29)
    ("3400", "100", "100"),  # Wareneingang 19 % Vorsteuer
    ("4000", "100", "100"),  # Material- und Stoffverbrauch (KR-EÜR: Roh-, Hilfs- …)
    ("3990", "-100", "100"),  # verrechnete Stoffkosten (Gegenkonto zu 4000–4099)
    ("2327", "100", "100"),  # Abgang UV § 4 Abs. 3 S. 4 EStG (Anl AVEÜR Zeile 95)
    ("3100", "100", "110"),  # Fremdleistungen
    ("4909", "100", "110"),  # Fremdleistungen/Fremdarbeiten (Anl Zeile 29)
    ("4760", "100", "110"),  # Verkaufsprovisionen: Provisionen → Zeile 29 (Anl)
    ("4710", "100", "227"),  # Verpackungsmaterial
    ("4969", "100", "226"),  # Abraum- und Abfallbeseitigung
    # Raumkosten (Anl Zeilen 39–42, 65–66)
    ("4212", "100", "152"),  # doppelte Haushaltsführung Unternehmer
    ("2375", "100", "151"),  # Grundsteuer (Anl zu Zeile 41)
    ("4366", "100", "151"),  # Versicherungen für Gebäude: nicht Zeile 49 (Anl)
    ("4801", "100", "151"),  # Reparaturen Bauten: Zeile 48 ohne Gebäude (Anl)
    ("4287", "100", "163"),  # Tagespauschale häusliche Wohnung
    ("4288", "100", "172"),  # häusliches Arbeitszimmer, abziehbar
    ("4289", "100", "162"),  # häusliches Arbeitszimmer, nicht abziehbar
    ("4833", "100", "172"),  # AfA Arbeitszimmer → Zeile 65 (Anl AVEÜR Zeile 31)
    # Abschreibungen (Anl Zeilen 31–38)
    ("4830", "100", "130"),
    ("4841", "100", "136"),  # AfaA Gebäude
    ("4856", "100", "134"),  # Sonderabschreibung § 7b EStG
    ("4855", "100", "132"),  # GWG
    ("2310", "100", "135"),  # Restbuchwert
    # Zinsen (Anl Zeilen 55–56; DATEV 1029703)
    ("2110", "100", "234"),
    ("2126", "100", "232"),  # Zinsen zur Finanzierung des Anlagevermögens
    ("2113", "100", "234"),  # § 4 Abs. 4a: übriger Schuldzins, Hinzurechnung Z. 96
    # Steuern
    ("4320", "100", "168"),  # Gewerbesteuer: nicht abziehbar (§ 4 Abs. 5b EStG)
    ("2102", "100", "168"),  # Nebenleistungen zu Steuern § 4 Abs. 5b EStG
    ("2103", "100", "183"),  # abzugsfähige Nebenleistungen: Zeile 60 (Anl zu Zeile 58)
    ("2208", "100", "-"),  # Solidaritätszuschlag
    ("8959", "100", "183"),  # direkt mit dem Umsatz verbundene Steuern (Aufwand)
    # Kfz (DATEV 1036862)
    ("4510", "100", "145"),
    ("4570", "100", "144"),
    ("4530", "100", "146"),
    ("4673", "100", "146"),  # Reisekosten Unternehmer Fahrtkosten
    ("4590", "100", "147"),
    ("4678", "100", "176"),  # Wege Wohnung–Betriebsstätte: Entfernungspauschale
    ("4680", "-100", "142"),  # … Haben: mindert die Kfz-Kosten (Zeile 72)
    ("4679", "100", "-"),  # … nicht abziehbarer Anteil: Differenz der Zeilen 72/73
    # Reisekosten, Bewirtung, Geschenke (Anl Zeilen 44, 62–64, 67)
    ("4676", "100", "221"),
    ("4672", "100", "168"),  # Reisekosten Unternehmer, nicht abziehbarer Anteil
    ("4674", "100", "171"),
    ("4681", "100", "171"),  # Verpflegungsmehraufwand doppelte Haushaltsführung
    ("4630", "100", "174"),  # Geschenke abzugsfähig
    ("4635", "100", "164"),  # Geschenke nicht abzugsfähig
    ("4650", "100", "175"),  # Bewirtung, abziehbarer Teil
    ("4654", "100", "165"),  # Bewirtung, nicht abziehbar
    ("4651", "100", "177"),  # sonstige eingeschränkt abziehbare BA, abziehbar
    ("4652", "100", "168"),  # … nicht abziehbar
    ("4655", "100", "168"),  # nicht abzugsfähige BA aus Werbe-/Repräsentationskosten
    ("2308", "100", "168"),  # sonstige nicht abziehbare Aufwendungen
    ("4653", "100", "183"),  # Aufmerksamkeiten: keine Bewirtung (R 4.10 Abs. 5 EStR)
    # Übrige
    ("4958", "100", "222"),  # Vergütung Gesellschafter für bewegliche WG: Miete
    ("2383", "100", "-"),  # Spenden: Sonderausgaben, keine Betriebsausgabe
    ("4990", "100", "-"),  # kalkulatorischer Unternehmerlohn: keine Ausgabe
    ("2890", "-100", "-"),  # … und seine Verrechnung
    ("2797", "-100", "-"),  # Entnahme aus Rücklagen: Ergebnisverwendung
    ("1556", "100", "185"),  # Vorsteuer § 15a Abs. 1 (KR-EÜR Posten „Vorsteuer“)
    ("1783", "-100", "140"),  # unberechtigt ausgewiesene USt: vereinnahmt (Zeile 17)
    # Ergebnisanteile Personengesellschaften (KR-EÜR Fußnote 23): Zeile 91, nicht in
    # den Zeilen 12–75 (Anleitung zu Zeile 91)
    ("2603", "-100", "-"),
    ("2614", "-100", "-"),
    ("2618", "-100", "-"),
    ("4872", "100", "-"),
    # Umsatzsteuer (KR-EÜR Posten „Umsatzsteuer“, „Einnahmen“, „Neutrale Aufwendungen“)
    ("1766", "-100", "140"),  # USt nicht fällig 19 % (wie SKR04 3816)
    ("1767", "-100", "140"),  # USt aus im anderen EU-Land stpfl. Lieferungen (OSS)
    ("1768", "-100", "140"),
    ("1728", "-100", "140"),  # USt elektronische Dienstleistungen anderes EU-Land
    ("1798", "-100", "140"),  # USt nur OSS
    ("1754", "100", "186"),  # Steuerzahlungen an andere Länder
    ("1729", "100", "186"),  # Steuerzahlungen aus im anderen EU-Land stpfl. Leistungen
    ("1782", "-100", "140"),  # Nachsteuer: keine Erstattung vom Finanzamt (Zeile 18)
    ("1782", "100", "140"),
    ("1789", "-100", "186"),  # USt laufendes Jahr gleicht 1780 aus (DATEV 1037179)
    ("1789", "100", "186"),
    # USt mit gleich hoher Vorsteuer (§ 13b, ig. Erwerb, Dreieck, Auslagerung):
    # beide in Zeile 57, Rechnungen ohne Vorsteuer (Anl zu Zeile 57)
    ("1774", "-100", "185"),
    ("1787", "-100", "185"),
    ("1784", "-100", "185"),
    ("1769", "-100", "185"),
    ("1779", "-100", "140"),  # ig. Erwerb ohne Vorsteuerabzug: kein Gegenstück
    # Konten ohne Steuersatz nach DATEV-Posten: „Neutrale Erträge“ → 103,
    # „Sonstige Erlöse“/„Einnahmen“ → 112
    ("8603", "-100", "103"),
    ("8606", "-100", "103"),
    ("8605", "-100", "112"),
    ("8607", "-100", "112"),
    ("8590", "-100", "112"),
    ("8610", "-100", "112"),
    # §§ 25, 25a UStG „ohne USt“: steuerpflichtiger Umsatz, Marge als BMG
    ("8189", "-100", "112"),
    ("8193", "-100", "112"),
    ("8197", "-100", "112"),
    ("8194", "-100", "103"),  # Reiseleistungen § 25 Abs. 2 UStG steuerfrei
    ("2732", "-100", "112"),  # abgeschriebene Forderungen (§ 17 Abs. 2 Nr. 1 UStG)
    ("8500", "-100", None),  # Sonderbetriebseinnahme (Fußnote 28: Sonderbilanz)
    ("4964", "100", "183"),  # Lizenzen: keine beweglichen Wirtschaftsgüter
    ("3950", "100", "-"),  # Bestandsveränderungen Waren (fehlen im KR-EÜR)
    ("3960", "100", "-"),
    ("3955", "100", "100"),  # Bestandsveränderungen RHB (im KR-EÜR)
    # Rücklagen (Anl Zeilen 22 und 59, Übertrag der Kz 124 und 190)
    ("2342", "100", "190"),  # Einstellung § 6b Abs. 3 EStG
    ("2344", "100", "190"),  # Einstellung R 6.6 EStR
    ("2339", "100", "190"),  # Ausgleichsposten § 4g EStG
    ("2727", "-100", "124"),  # Auflösung § 6b Abs. 3 EStG
    ("2737", "-100", "124"),  # Auflösung § 4g EStG
    ("2345", "100", None),  # sonstige steuerliche Rücklagen: keine Zeile
    ("2740", "-100", None),
]

# Konten, die der Kontenrahmen 2026 reserviert hat; Buchungen bis 2025 behalten ihre
# bisherige Kennzahl
ALTKONTEN = [
    ("SKR03", "8195", "-100", "111"),  # Kleinunternehmer bis 2025
    ("SKR03", "8196", "-100", "112"),  # Geldspielautomaten 19 % USt
    ("SKR03", "8330", "-100", "112"),
    ("SKR04", "4185", "-100", "111"),
    ("SKR04", "4186", "-100", "112"),
]


@pytest.mark.parametrize(("kr", "konto", "saldo", "kz"), ALTKONTEN)
def test_euer_altkonten(kr, konto, saldo, kz):
    rahmen = {"SKR03": SKR03, "SKR04": SKR04}[kr]
    assert rahmen.euer_kz(konto, Decimal(saldo)) == kz


@pytest.mark.parametrize(("konto", "saldo", "kz"), LEITKONTEN_SKR03)
def test_euer_leitkonten_skr03(konto, saldo, kz):
    assert SKR03.euer_kz(konto, Decimal(saldo)) == kz


LEITKONTEN_SKR04 = [
    # Betriebseinnahmen nach Umsatzsteuer
    ("4400", "-100", "112"),
    ("4184", "-100", "111"),  # Kleinunternehmer (KR)
    ("4133", "-100", "112"),  # § 25 UStG 19 % USt
    ("4290", "-100", "103"),  # Erlöse 0 % USt (Anl Zeile 16)
    ("4321", "-100", "103"),  # im anderen EU-Land steuerpflichtige Lieferungen (OSS)
    ("4331", "-100", "103"),  # elektronische Dienstleistungen im anderen EU-Land
    ("4334", "-100", "112"),  # Erlöse 7 % USt
    ("4564", "-100", "103"),  # Provisionsumsätze steuerfrei § 4 Nr. 8 ff. UStG
    ("4690", "-100", "103"),  # nicht steuerbare Umsätze (Innenumsätze)
    ("4836", "-100", "112"),  # sonstige Erträge betrieblich und regelmäßig 19 % USt
    ("4862", "-100", "112"),  # Vermietung und Verpachtung 19 % USt
    ("4945", "-100", "112"),  # Sachbezüge 19 % USt (Waren)
    ("4847", "-100", "103"),  # Erträge aus der Währungsumrechnung (KR)
    ("7100", "-100", "103"),  # Zinserträge
    # Erlösschmälerungen
    ("4720", "100", "112"),  # Erlösschmälerungen 19 % USt
    ("4736", "100", "112"),  # gewährte Skonti 19 % USt
    ("4707", "100", "111"),  # Erlösschmälerungen § 19 Abs. 1 UStG
    ("4743", "100", "103"),  # Skonti aus steuerfreien ig. Lieferungen
    ("6936", "100", "112"),  # Forderungsverluste 19 % USt (KR-EÜR „Einnahmen“)
    ("6932", "100", "103"),  # Forderungsverluste aus steuerfreien EU-Lieferungen
    ("6280", "100", "112"),  # Forderungsverluste (soweit unüblich hoch)
    # Anlagenverkäufe, Entnahmen
    ("4844", "-100", "102"),  # Sachanlageverkauf steuerfrei § 4 Nr. 1a (Buchgewinn)
    ("4851", "-100", "102"),  # Verkauf Finanzanlagen (Buchgewinn): Anlagevermögen
    ("6884", "-100", "102"),  # Sachanlageverkauf steuerfrei § 4 Nr. 1a (Buchverlust)
    ("4645", "-100", "106"),  # private Kfz-Nutzung 19 % (DATEV 1036862)
    ("4610", "-100", "108"),  # Warenentnahme
    ("4800", "-100", "-"),  # Bestandsveränderungen (fehlen im KR-EÜR)
    # Wareneingang, Fremdleistungen
    ("5400", "100", "100"),
    ("6907", "100", "100"),  # Abgang UV § 4 Abs. 3 S. 4 EStG (Anl AVEÜR Zeile 95)
    ("5900", "100", "110"),
    ("6303", "100", "110"),  # Fremdleistungen/Fremdarbeiten
    ("6770", "100", "110"),  # Verkaufsprovisionen
    ("6790", "100", "183"),  # Aufwand für Gewährleistungen: keine Verpackung/Transport
    ("6859", "100", "226"),  # Abraum- und Abfallbeseitigung
    # Personal
    ("6020", "100", "120"),
    ("6440", "100", "120"),  # Ausgleichsabgabe SchwbG (KR-EÜR „Gesetzliche soziale …“)
    # Raumkosten
    ("6305", "100", "150"),  # Raumkosten
    ("6312", "100", "152"),  # doppelte Haushaltsführung
    ("7680", "100", "151"),  # Grundsteuer
    ("6405", "100", "151"),  # Versicherungen für Gebäude
    ("6450", "100", "151"),  # Reparaturen Bauten
    ("6347", "100", "163"),
    ("6348", "100", "172"),
    ("6349", "100", "162"),
    ("6223", "100", "172"),  # AfA Arbeitszimmer
    # Abschreibungen
    ("6220", "100", "130"),
    ("6231", "100", "136"),  # AfaA Gebäude
    ("6260", "100", "132"),
    ("6895", "100", "135"),
    # Miete/Leasing, EDV
    ("6498", "100", "222"),  # Mietleasing bewegliche WG für technische Anlagen
    ("6833", "100", "222"),  # Vergütung Gesellschafter für bewegliche WG
    ("6495", "100", "228"),
    # Zinsen
    ("7310", "100", "234"),
    ("7326", "100", "232"),  # Zinsen zur Finanzierung des Anlagevermögens
    ("7313", "100", "234"),
    # Steuern
    ("7610", "100", "168"),
    ("7302", "100", "168"),  # Nebenleistungen zu Steuern § 4 Abs. 5b EStG
    ("7303", "100", "183"),  # abzugsfähige Nebenleistungen
    ("7608", "100", "-"),
    ("4699", "100", "183"),  # direkt mit dem Umsatz verbundene Steuern
    # Kfz
    ("6520", "100", "145"),
    ("6560", "100", "144"),
    ("6530", "100", "146"),
    ("6673", "100", "146"),  # Reisekosten Unternehmer Fahrtkosten (DATEV 1036862)
    ("6590", "100", "147"),
    ("6688", "100", "176"),
    ("6690", "-100", "142"),
    ("6689", "100", "-"),
    # Reisekosten, Bewirtung, Geschenke
    ("6680", "100", "221"),  # Übernachtung und Reisenebenkosten Unternehmer
    ("6672", "100", "168"),
    ("6674", "100", "171"),  # Verpflegungsmehraufwand Unternehmer
    ("6691", "100", "171"),
    ("6610", "100", "174"),
    ("6620", "100", "164"),
    ("6640", "100", "175"),
    ("6644", "100", "165"),
    ("6641", "100", "177"),
    ("6642", "100", "168"),
    ("6645", "100", "168"),
    ("6968", "100", "168"),  # sonstige nicht abziehbare Aufwendungen
    ("6643", "100", "183"),  # Aufmerksamkeiten
    # Übrige
    ("6393", "100", "-"),  # Spenden
    ("6970", "100", "-"),  # kalkulatorischer Unternehmerlohn
    ("7751", "-100", "-"),  # Entnahme aus Rücklagen
    # Vorsteuer, Umsatzsteuer
    ("1396", "100", "185"),  # Vorsteuer § 15a Abs. 1 (KR-EÜR „Vorsteuer“)
    ("1480", "-100", "185"),  # Gegenkonto Vorsteuer § 4 Abs. 3 EStG (DATEV 1037171)
    ("1481", "100", "185"),  # Auflösung Vorsteuer aus Vorjahr § 4 Abs. 3 EStG
    ("3831", "-100", "140"),  # USt aus im Inland stpfl. EU-Lieferungen, nur OSS
    ("3851", "-100", "140"),  # unberechtigt ausgewiesene USt
    # Ergebnisanteile Personengesellschaften (KR-EÜR Fußnote 23)
    ("7003", "-100", "-"),
    ("7004", "-100", "-"),
    ("7008", "-100", "-"),
    ("7208", "100", "-"),
    # Umsatzsteuer
    ("3798", "-100", "140"),  # USt elektronische Dienstleistungen anderes EU-Land
    ("3854", "100", "186"),  # Steuerzahlungen an andere Länder
    ("3799", "100", "186"),
    ("3832", "-100", "140"),  # Nachsteuer
    ("3840", "-100", "186"),  # USt laufendes Jahr
    ("3804", "-100", "185"),  # USt ig. Erwerb 19 %
    ("3837", "-100", "185"),  # USt § 13b UStG 19 %
    ("3819", "-100", "185"),  # USt Dreiecksgeschäft letzter Abnehmer
    ("3839", "-100", "185"),  # USt Auslagerung Umsatzsteuerlager
    ("3809", "-100", "140"),  # ig. Erwerb ohne Vorsteuerabzug
    # Konten ohne Steuersatz nach DATEV-Posten
    ("4830", "-100", "103"),
    ("4832", "-100", "103"),
    ("4835", "-100", "112"),
    ("4833", "-100", "112"),
    ("4940", "-100", "112"),
    ("4946", "-100", "112"),
    ("4131", "-100", "112"),
    ("4132", "-100", "112"),
    ("4138", "-100", "112"),
    ("4139", "-100", "103"),
    ("4925", "-100", "112"),
    ("4500", "-100", None),
    ("6837", "100", "183"),
    ("5880", "100", "-"),
    ("5881", "100", "-"),
    ("5885", "100", "100"),
    # Rücklagen
    ("6922", "100", "190"),
    ("6928", "100", "190"),
    ("6929", "100", "190"),
    ("4927", "-100", "124"),
    ("4938", "-100", "124"),
    ("6927", "100", None),
    ("4935", "-100", None),
]


@pytest.mark.parametrize(("konto", "saldo", "kz"), LEITKONTEN_SKR04)
def test_euer_leitkonten_skr04(konto, saldo, kz):
    assert SKR04.euer_kz(konto, Decimal(saldo)) == kz


@pytest.mark.parametrize(
    ("kr", "konto", "euer", "bilanz"),
    [
        # Privat (Einzelunternehmen, Vollhafter)
        ("SKR03", "1800", Kontenart.PRIVAT, Kontenart.PRIVAT),
        ("SKR03", "1890", Kontenart.PRIVAT, Kontenart.PRIVAT),
        ("SKR04", "2100", Kontenart.PRIVAT, Kontenart.PRIVAT),
        ("SKR04", "2180", Kontenart.PRIVAT, Kontenart.PRIVAT),
        # Bestände in der Bilanz, Bestandsveränderungen und Gegenkonten in der GuV
        ("SKR03", "3980", Kontenart.BESTAND, Kontenart.BESTAND),
        ("SKR03", "3990", Kontenart.ERFOLG, Kontenart.ERFOLG),  # verr. Stoffkosten
        ("SKR03", "7110", Kontenart.BESTAND, Kontenart.BESTAND),
        ("SKR03", "8980", Kontenart.ERFOLG, Kontenart.ERFOLG),
        ("SKR04", "1140", Kontenart.BESTAND, Kontenart.BESTAND),
        ("SKR04", "4800", Kontenart.ERFOLG, Kontenart.ERFOLG),
        ("SKR04", "5860", Kontenart.ERFOLG, Kontenart.ERFOLG),
        # Vorsteuer: bei EÜR erfolgswirksam (KR-EÜR Posten „Vorsteuer“), sonst Bestand
        ("SKR03", "1528", Kontenart.ERFOLG, Kontenart.BESTAND),  # § 15a Abs. 2
        ("SKR03", "1559", Kontenart.ERFOLG, Kontenart.BESTAND),  # § 15a Abs. 1
        ("SKR03", "1560", Kontenart.ERFOLG, Kontenart.BESTAND),  # aufzuteilende VSt
        ("SKR03", "1580", Kontenart.ERFOLG, Kontenart.BESTAND),
        ("SKR04", "1376", Kontenart.ERFOLG, Kontenart.BESTAND),
        ("SKR04", "1399", Kontenart.ERFOLG, Kontenart.BESTAND),
        ("SKR04", "1480", Kontenart.ERFOLG, Kontenart.BESTAND),  # DATEV 1037171
        ("SKR04", "1481", Kontenart.ERFOLG, Kontenart.BESTAND),
        ("SKR04", "1378", Kontenart.BESTAND, Kontenart.BESTAND),  # Rückdeckungsanspr.
        ("SKR04", "1486", Kontenart.BESTAND, Kontenart.BESTAND),  # Verrechnungskonto
        # Umsatzsteuer
        ("SKR03", "1783", Kontenart.ERFOLG, Kontenart.BESTAND),
        ("SKR04", "3851", Kontenart.ERFOLG, Kontenart.BESTAND),
        # Steuerzahlungen an andere Länder (KR-EÜR Posten „Neutrale Aufwendungen“)
        ("SKR04", "3854", Kontenart.ERFOLG, Kontenart.BESTAND),
        ("SKR03", "1754", Kontenart.ERFOLG, Kontenart.BESTAND),
        ("SKR03", "1729", Kontenart.ERFOLG, Kontenart.BESTAND),
        ("SKR04", "3799", Kontenart.ERFOLG, Kontenart.BESTAND),
        # USt nicht fällig, OSS, Auslagerung: wie die SKR04-Gegenstücke 3810–3839
        ("SKR03", "1760", Kontenart.ERFOLG, Kontenart.BESTAND),
        ("SKR03", "1767", Kontenart.ERFOLG, Kontenart.BESTAND),
        ("SKR03", "1769", Kontenart.ERFOLG, Kontenart.BESTAND),
        ("SKR03", "1798", Kontenart.ERFOLG, Kontenart.BESTAND),
        ("SKR03", "1728", Kontenart.ERFOLG, Kontenart.BESTAND),
        ("SKR04", "3798", Kontenart.ERFOLG, Kontenart.BESTAND),
        ("SKR03", "1797", Kontenart.BESTAND, Kontenart.BESTAND),  # Verbindlichkeit
        ("SKR03", "1730", Kontenart.BESTAND, Kontenart.BESTAND),  # Kreditkarten
        # Vortrag
        ("SKR03", "9000", Kontenart.VORTRAG, Kontenart.VORTRAG),
        ("SKR04", "9008", Kontenart.VORTRAG, Kontenart.VORTRAG),
    ],
)
def test_kontoart_leitkonten(kr, konto, euer, bilanz):
    rahmen = {"SKR03": SKR03, "SKR04": SKR04}[kr]
    assert rahmen.art(konto, "euer") is euer
    assert rahmen.art(konto, "bilanz") is bilanz


# SKR03 ↔ SKR04: gleich bezeichnete Konten der DATEV-Kontenrahmen für § 4 Abs. 3 EStG
# 2026 (11079/11080; automatisch über die Bezeichnung zugeordnet) sowie von Hand
# ergänzte Gegenstücke. Gleicher Kontenzweck → gleiche Kontoart und EÜR-Kennzahl.
PAARE = """
8400:4400 8125:4125 8120:4120 8100:4100 8192:4184 8190:4180 8191:4136 8198:4133
8189:4131 8290:4290 8320:4320 8336:4336 8337:4337 8338:4338 8510:4560 8514:4564
8570:4570 8590:4940 8595:4945 8603:4830 8605:4835 8606:4832 8607:4833 8610:4946
8611:4947 8614:4949 8705:4705 8707:4707 8736:4736 8743:4743 8800:6889 8850:4865
8851:4866 8900:4600 8921:4645 8924:4639 8950:4690 8955:4695 8959:4699 8990:4820
2400:6930 2402:6932 2406:6936 2600:7000 2618:7008 2650:7100 2660:4840 2732:4925
2742:4970 2744:4980 2747:4982 2752:4862 2727:4927 2737:4938 2740:4935 2342:6922
2339:6929 2345:6927 2100:7300 2102:7302 2103:7303 2105:7308 2113:7313 2124:7324
2126:7326 2200:7600 2208:7608 2281:7641 2285:7690 2308:6968 2310:6895 2315:4855
2327:6907 2350:6352 2380:6390 2383:6393 2890:6980 3000:5100 3100:5900 3123:5923
3550:5550 3730:5730 3800:5800 3850:5840 4000:5000 4100:6000 4130:6110 4139:6440
4140:6130 4210:6310 4212:6312 4240:6325 4260:6335 4287:6347 4288:6348 4289:6349
4320:7610 4340:7650 4360:6400 4366:6405 4396:6436 4397:6437 4520:6520 4530:6530
4570:6560 4590:6590 4595:6595 4630:6610 4632:6612 4635:6620 4638:6625 4639:6629
4640:6630 4650:6640 4651:6641 4652:6642 4653:6643 4654:6644 4655:6645 4660:6650
4672:6672 4673:6673 4674:6674 4676:6680 4678:6688 4679:6689 4680:6690 4681:6691
4700:6700 4710:6710 4730:6740 4760:6770 4780:6780 4790:6790 4800:6460 4801:6450
4806:6495 4810:6498 4822:6200 4830:6220 4831:6221 4832:6222 4833:6223 4841:6231
4850:6240 4853:6243 4855:6260 4856:6245 4860:6262 4862:6264 4872:7208 4909:6303
4945:6821 4946:6822 4950:6825 4958:6833 4960:6835 4964:6837 4969:6859 4970:6855
4980:6850 4985:6845 4990:6970 1528:1376 1548:1434 1556:1396 1560:1410 1571:1401
1576:1406 1577:1407 1580:1480 1581:1481 1588:1433 1754:3854 1729:3799 1728:3798
1760:3810 1766:3816 1767:3817 1768:3818 1769:3839 1771:3801 1774:3804 1776:3806
1779:3809 1780:3820 1782:3832 1783:3851 1784:3834 1787:3837 1789:3840 1790:3841
1794:3819 1798:3831
8300:4300 8334:4334 8625:4842 8640:4836 8700:4700 8720:4720 8820:4845 8910:4610
8960:4810 8980:4800 2375:7680 3400:5400 3950:5881 3955:5885 3960:5880 3990:5860
4200:6305 4300:6860 4510:7685 4560:6580 4600:6600 4670:6670 4910:6800 4920:6805
4930:6815 1800:2100 1890:2180
"""


@pytest.mark.parametrize(
    ("skr03", "skr04"), [tuple(p.split(":")) for p in PAARE.split()]
)
def test_paritaet_skr03_skr04(skr03, skr04):
    for gewinnermittlung in ("euer", "bilanz"):
        assert SKR03.art(skr03, gewinnermittlung) is SKR04.art(skr04, gewinnermittlung)
    if SKR03.art(skr03, "euer") is Kontenart.ERFOLG:
        for saldo in (Decimal(1), Decimal(-1)):
            assert SKR03.euer_kz(skr03, saldo) == SKR04.euer_kz(skr04, saldo)
