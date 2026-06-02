# MVP Bank-Auto-Kontierung — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the end-to-end pipeline that turns a German bank statement CSV into DATEV-conformant, auto-classified bookings (rules + LLM), persisted in SQLite.

**Architecture:** One-directional pipeline `Import → Klassifikation → Buchung → Persistenz → Export`, matching `docs/architektur.md`. Each stage is a focused module with a clear interface, tested in isolation. Pydantic models (`models/`) are the domain objects; SQLAlchemy models are persistence only.

**Tech Stack:** Python 3.11+, Pydantic v2, Typer (CLI), SQLAlchemy 2.0 + Alembic (SQLite, Postgres-ready), LiteLLM (Claude default / Ollama), pytest.

**Spec:** `docs/specs/2026-06-02-mvp-bank-auto-kontierung.md`

---

## File Structure

| Path | Responsibility |
|------|----------------|
| `src/accounti/importers/__init__.py` | `BankImporter` base + `BANK_IMPORTERS` registry |
| `src/accounti/importers/sparkasse.py` | Sparkasse CSV → `Transaktion` |
| `config/regeln.yaml` | User-editable classification rules |
| `src/accounti/klassifikation/regeln_loader.py` | YAML → `list[Regel]` |
| `src/accounti/klassifikation/llm.py` | Real `LLMEngine` (LiteLLM + PII masking) |
| `src/accounti/buchung/mapper.py` | `Klassifikationsergebnis` → `Buchungssatz` (net/tax split) |
| `src/accounti/db/__init__.py` | Engine/session factory, `init_db` |
| `src/accounti/db/tabellen.py` | SQLAlchemy ORM tables |
| `src/accounti/db/repository.py` | Save/load domain objects |
| `src/accounti/export/datev.py` | Conformance fixes (existing file) |
| `src/accounti/cli.py` | Wire real pipeline into commands (existing file) |
| `tests/test_*.py` | One test module per component |

Tasks are ordered by dependency so each produces working, testable software.

---

## Task 1: Sparkasse CSV Importer

**Files:**
- Create: `src/accounti/importers/__init__.py`
- Create: `src/accounti/importers/sparkasse.py`
- Test: `tests/test_importers_sparkasse.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_importers_sparkasse.py
from decimal import Decimal
from pathlib import Path

from accounti.importers.sparkasse import SparkasseImporter
from accounti.models import TransaktionQuelle

BEISPIEL = Path(__file__).resolve().parents[1] / "examples" / "beispiel_sparkasse.csv"


def test_importiert_alle_zeilen():
    txs = SparkasseImporter().importiere(BEISPIEL)
    assert len(txs) == 8


def test_parst_betrag_und_datum_deutsch():
    txs = SparkasseImporter().importiere(BEISPIEL)
    erste = txs[0]
    assert erste.betrag == Decimal("1250.00")        # "1.250,00"
    assert erste.datum.isoformat() == "2026-04-15"    # "15.04.26"
    assert erste.quelle is TransaktionQuelle.BANK


def test_negativer_betrag():
    txs = SparkasseImporter().importiere(BEISPIEL)
    aws = next(t for t in txs if "AWS" in t.verwendungszweck)
    assert aws.betrag == Decimal("-89.50")


def test_gegenkonto_name_gesetzt():
    txs = SparkasseImporter().importiere(BEISPIEL)
    assert txs[0].gegenkonto_name == "Amazon Payments Europe S.C.A."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_importers_sparkasse.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'accounti.importers'`

- [ ] **Step 3: Write the base + registry**

```python
# src/accounti/importers/__init__.py
"""Importer — wandeln Rohdaten einer Quelle in Transaktion-Objekte um."""
from __future__ import annotations

from pathlib import Path

from accounti.models import Transaktion


class BankImporter:
    """Basisklasse für Bank-Importer. Kennt nur das Format, keine Buchungslogik."""

    name: str = "base"

    def importiere(self, pfad: Path) -> list[Transaktion]:
        raise NotImplementedError


BANK_IMPORTERS: dict[str, type[BankImporter]] = {}
```

- [ ] **Step 4: Write the Sparkasse importer**

```python
# src/accounti/importers/sparkasse.py
"""Sparkasse-CSV-Importer (CSV-CAMT-Format)."""
from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from accounti.importers import BANK_IMPORTERS, BankImporter
from accounti.models import Transaktion, TransaktionQuelle


def _lies_text(pfad: Path) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return pfad.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return pfad.read_text(encoding="latin-1")


def parse_betrag(roh: str) -> Decimal:
    """Deutsches Zahlenformat: '1.250,00' / '-89,50' → Decimal."""
    return Decimal(roh.strip().replace(".", "").replace(",", "."))


def parse_datum(roh: str) -> date:
    """Deutsches Datum 'TT.MM.JJ' → date."""
    return datetime.strptime(roh.strip(), "%d.%m.%y").date()


class SparkasseImporter(BankImporter):
    name = "sparkasse"

    def importiere(self, pfad: Path) -> list[Transaktion]:
        text = _lies_text(Path(pfad))
        reader = csv.DictReader(text.splitlines(), delimiter=";")
        transaktionen: list[Transaktion] = []
        for row in reader:
            if not row.get("Buchungstag"):
                continue
            transaktionen.append(
                Transaktion(
                    datum=parse_datum(row["Buchungstag"]),
                    betrag=parse_betrag(row["Betrag"]),
                    waehrung=(row.get("Währung") or "EUR").strip(),
                    verwendungszweck=(row.get("Verwendungszweck") or "").strip(),
                    gegenkonto_name=(row.get("Begünstigter/Zahlungspflichtiger") or "").strip()
                    or None,
                    gegenkonto_iban=(row.get("Kontonummer") or "").strip() or None,
                    quelle=TransaktionQuelle.BANK,
                    quelle_referenz=None,
                    rohtext=";".join(row.values()),
                )
            )
        return transaktionen


BANK_IMPORTERS[SparkasseImporter.name] = SparkasseImporter
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_importers_sparkasse.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add src/accounti/importers tests/test_importers_sparkasse.py
git commit -m "feat(importers): Sparkasse CSV importer -> Transaktion"
```

---

## Task 2: YAML Rule Loading

**Files:**
- Create: `config/regeln.yaml`
- Create: `src/accounti/klassifikation/regeln_loader.py`
- Test: `tests/test_regeln_loader.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_regeln_loader.py
from pathlib import Path

from accounti.klassifikation.regeln_loader import lade_regeln
from accounti.models import Transaktion, TransaktionQuelle


def _tx(zweck: str) -> Transaktion:
    return Transaktion(
        datum="2026-04-10", betrag="-39.99", verwendungszweck=zweck,
        quelle=TransaktionQuelle.BANK, rohtext=zweck,
    )


def test_laedt_regeln_aus_yaml(tmp_path: Path):
    yaml_datei = tmp_path / "regeln.yaml"
    yaml_datei.write_text(
        "- name: telekom\n"
        "  muster: 'TELEKOM'\n"
        "  feld: verwendungszweck\n"
        "  soll_konto: '4920'\n"
        "  haben_konto: '1200'\n"
        "  steuer_schluessel: 9\n"
        "  buchungstext: 'Telefon/Internet'\n",
        encoding="utf-8",
    )
    regeln = lade_regeln(yaml_datei)
    assert len(regeln) == 1
    assert regeln[0].passt(_tx("TELEKOM MOBILFUNK APRIL")) is True


def test_fehlende_datei_gibt_leere_liste(tmp_path: Path):
    assert lade_regeln(tmp_path / "gibtsnicht.yaml") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_regeln_loader.py -v`
Expected: FAIL — `ModuleNotFoundError: ...regeln_loader`

- [ ] **Step 3: Write the loader**

```python
# src/accounti/klassifikation/regeln_loader.py
"""Lädt Kontierungsregeln aus config/regeln.yaml."""
from __future__ import annotations

from pathlib import Path

import yaml

from accounti.klassifikation.engine import Regel


def lade_regeln(pfad: Path) -> list[Regel]:
    pfad = Path(pfad)
    if not pfad.exists():
        return []
    daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or []
    regeln: list[Regel] = []
    for eintrag in daten:
        regeln.append(
            Regel(
                name=eintrag["name"],
                muster=eintrag["muster"],
                soll_konto=str(eintrag["soll_konto"]),
                haben_konto=str(eintrag["haben_konto"]),
                steuer_schluessel=eintrag.get("steuer_schluessel"),
                buchungstext=eintrag.get("buchungstext"),
                feld=eintrag.get("feld", "verwendungszweck"),
            )
        )
    return regeln
```

- [ ] **Step 4: Create the seed config**

```yaml
# config/regeln.yaml
# Kontierungsregeln (SKR03). Reihenfolge = Priorität (erste passende gewinnt).
- name: telekom
  muster: 'TELEKOM|VODAFONE|O2|1UND1|1&1'
  feld: verwendungszweck
  soll_konto: '4920'      # Telefon
  haben_konto: '1200'
  steuer_schluessel: 9
  buchungstext: 'Telefon/Internet'

- name: bueromaterial
  muster: 'BUEROMATERIAL|BÜROMATERIAL|STAPLES'
  feld: verwendungszweck
  soll_konto: '4930'      # Bürobedarf
  haben_konto: '1200'
  steuer_schluessel: 9
  buchungstext: 'Büromaterial'

- name: ebay_erloes
  muster: 'EBAY'
  feld: verwendungszweck
  soll_konto: '1200'
  haben_konto: '8400'
  steuer_schluessel: 3
  buchungstext: 'eBay Erlöse'
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_regeln_loader.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add src/accounti/klassifikation/regeln_loader.py config/regeln.yaml tests/test_regeln_loader.py
git commit -m "feat(klassifikation): load rules from config/regeln.yaml"
```

---

## Task 3: Buchung Mapper (Klassifikationsergebnis → Buchungssatz)

**Files:**
- Create: `src/accounti/buchung/mapper.py`
- Test: `tests/test_buchung_mapper.py`

The mapper turns a classification result + the original transaction into a full
`Buchungssatz`, splitting gross into net + tax using the DATEV `steuer_schluessel`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_buchung_mapper.py
from decimal import Decimal

from accounti.buchung.mapper import zu_buchungssatz
from accounti.models import (
    BuchungStatus, Klassifikationsergebnis, Transaktion, TransaktionQuelle,
)


def _tx(betrag: str) -> Transaktion:
    return Transaktion(
        datum="2026-04-15", betrag=betrag, verwendungszweck="TEST",
        quelle=TransaktionQuelle.BANK, rohtext="TEST",
    )


def _erg(soll: str, haben: str, schluessel, conf: float) -> Klassifikationsergebnis:
    return Klassifikationsergebnis(
        transaktion_id="00000000-0000-0000-0000-000000000000",
        soll_konto=soll, haben_konto=haben, steuer_schluessel=schluessel,
        buchungstext="TEST", confidence=conf, begruendung="x", quelle="regelwerk",
    )


def test_vorsteuer_split_19():
    # Ausgabe 119,00 brutto, VSt 19% (Schlüssel 9) -> netto 100,00, Steuer 19,00
    tx = _tx("-119.00")
    b = zu_buchungssatz(tx, _erg("4930", "1200", 9, 1.0))
    assert b.betrag_netto == Decimal("100.00")
    assert b.steuer_betrag == Decimal("19.00")
    assert b.steuer_schluessel == 9


def test_umsatzsteuer_split_19():
    # Erlös 119,00 brutto, USt 19% (Schlüssel 3) -> netto 100,00, Steuer 19,00
    tx = _tx("119.00")
    b = zu_buchungssatz(tx, _erg("1200", "8400", 3, 1.0))
    assert b.betrag_netto == Decimal("100.00")
    assert b.steuer_betrag == Decimal("19.00")


def test_ohne_steuer():
    tx = _tx("-320.00")
    b = zu_buchungssatz(tx, _erg("4360", "1200", None, 1.0))
    assert b.betrag_netto == Decimal("320.00")
    assert b.steuer_betrag is None


def test_status_aus_confidence():
    tx = _tx("-119.00")
    hoch = zu_buchungssatz(tx, _erg("4930", "1200", 9, 0.99), auto_schwelle=0.95)
    niedrig = zu_buchungssatz(tx, _erg("4930", "1200", 9, 0.50), auto_schwelle=0.95)
    assert hoch.status is BuchungStatus.AUTO_GEBUCHT
    assert niedrig.status is BuchungStatus.ZUR_PRUEFUNG
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_buchung_mapper.py -v`
Expected: FAIL — `ModuleNotFoundError: ...buchung.mapper`

- [ ] **Step 3: Write the mapper**

```python
# src/accounti/buchung/mapper.py
"""Mappt ein Klassifikationsergebnis auf einen vollständigen Buchungssatz."""
from __future__ import annotations

from decimal import Decimal

from accounti.models import (
    BuchungStatus, Buchungssatz, Klassifikationsergebnis, Transaktion,
)
from accounti.steuer.umsatzsteuer import UStBerechner

# DATEV BU-Schlüssel -> (Steuersatz, ist_vorsteuer)
_SCHLUESSEL_SATZ: dict[int, tuple[Decimal, bool]] = {
    3: (Decimal("19"), False),   # USt 19%
    2: (Decimal("7"), False),    # USt 7%
    9: (Decimal("19"), True),    # VSt 19%
    8: (Decimal("7"), True),     # VSt 7%
}


def zu_buchungssatz(
    transaktion: Transaktion,
    ergebnis: Klassifikationsergebnis,
    auto_schwelle: float = 0.95,
) -> Buchungssatz:
    berechner = UStBerechner()
    brutto = abs(transaktion.betrag)
    schluessel = ergebnis.steuer_schluessel

    if schluessel in _SCHLUESSEL_SATZ:
        satz, _ist_vst = _SCHLUESSEL_SATZ[schluessel]
        netto = berechner.brutto_zu_netto(brutto, satz)
        steuer_betrag: Decimal | None = brutto - netto
    else:
        netto = brutto
        steuer_betrag = None

    if ergebnis.confidence >= auto_schwelle:
        status = BuchungStatus.AUTO_GEBUCHT
    else:
        status = BuchungStatus.ZUR_PRUEFUNG

    return Buchungssatz(
        transaktion_id=transaktion.id,
        datum=transaktion.datum,
        soll_konto=ergebnis.soll_konto,
        haben_konto=ergebnis.haben_konto,
        betrag_netto=netto,
        steuer_schluessel=schluessel,
        steuer_betrag=steuer_betrag,
        buchungstext=ergebnis.buchungstext,
        status=status,
        confidence=ergebnis.confidence,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_buchung_mapper.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/accounti/buchung/mapper.py tests/test_buchung_mapper.py
git commit -m "feat(buchung): map classification result to Buchungssatz with tax split"
```

---

## Task 4: DATEV Export Conformance

**Files:**
- Modify: `src/accounti/export/datev.py`
- Test: `tests/test_datev_konformitaet.py`

Real DATEV EXTF rows quote only text — amounts and account numbers are unquoted —
and leave WKZ Umsatz empty. Current code uses `QUOTE_ALL`. Switch to
`QUOTE_MINIMAL` with explicit quoting of text fields, and empty WKZ per row.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_datev_konformitaet.py
from datetime import date
from decimal import Decimal

from accounti.export.datev import DATEVConfig, DATEVExporter
from accounti.models import Buchungssatz


def _buchung() -> Buchungssatz:
    return Buchungssatz(
        transaktion_id="00000000-0000-0000-0000-000000000000",
        datum=date(2026, 4, 15), soll_konto="4930", haben_konto="1200",
        betrag_netto=Decimal("100.00"), steuer_schluessel=9,
        steuer_betrag=Decimal("19.00"), buchungstext="Büromaterial",
    )


def _datenzeile(tmp_path) -> str:
    cfg = DATEVConfig(berater_nummer="23426", mandanten_nummer="40005")
    datei = DATEVExporter(cfg).exportiere([_buchung()], tmp_path)
    return datei.read_text(encoding="cp1252").splitlines()[2]


def test_betrag_nicht_gequotet(tmp_path):
    zeile = _datenzeile(tmp_path)
    assert zeile.startswith("119,00;")          # nicht "\"119,00\""


def test_konten_nicht_gequotet(tmp_path):
    felder = _datenzeile(tmp_path).split(";")
    assert felder[6] == "4930"                   # Konto, ohne Quotes
    assert felder[7] == "1200"                   # Gegenkonto, ohne Quotes


def test_text_gequotet(tmp_path):
    assert '"Büromaterial"' in _datenzeile(tmp_path)


def test_wkz_umsatz_leer(tmp_path):
    felder = _datenzeile(tmp_path).split(";")
    assert felder[2] == ""                        # WKZ Umsatz leer
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_datev_konformitaet.py -v`
Expected: FAIL — amounts/accounts are quoted, WKZ is "EUR".

- [ ] **Step 3: Update `_buchung_zu_zeile` (WKZ leer)**

In `src/accounti/export/datev.py`, in `_buchung_zu_zeile`, change the WKZ field:

```python
            "WKZ Umsatz": "",   # Währung steht im Header, nicht pro Zeile
```

- [ ] **Step 4: Switch quoting to DATEV style**

Replace the writer setup and header/caption writing in `exportiere`. DATEV quotes
only text fields, so use `QUOTE_MINIMAL` and pre-quote text columns. Replace the
`output`/`writer` block with:

```python
        # DATEV: nur Textfelder gequotet, Beträge/Konten ohne Quotes.
        text_spalten = {
            "Soll/Haben-Kennzeichen", "WKZ Umsatz", "WKZ Basis-Umsatz",
            "Buchungstext", "Diverse Adressnummer", "Geschäftspartnerbank",
            "Beleglink", "Beleginfo - Art 1", "Beleginfo - Inhalt 1",
        }

        def quote_text(spalte: str, wert: str) -> str:
            return f'"{wert}"' if (spalte in text_spalten and wert != "") else wert

        zeilen: list[str] = [self._erzeuge_header()]
        zeilen.append(";".join(spalten))  # Spaltenüberschriften unquoted
        for buchung in buchungen:
            roh = self._buchung_zu_zeile(buchung)
            zeilen.append(";".join(quote_text(s, roh[s]) for s in spalten))

        inhalt = "\r\n".join(zeilen) + "\r\n"
        datei.write_text(inhalt, encoding="cp1252", newline="")
        return datei
```

Remove the now-unused `csv` and `io` imports if no longer referenced.

- [ ] **Step 5: Run tests to verify all pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_datev_konformitaet.py tests/test_datev_export.py -v`
Expected: PASS. Update `tests/test_datev_export.py` assertions if they assumed
`QUOTE_ALL` (the line-count test stays valid: header + captions + N rows).

- [ ] **Step 6: Commit**

```bash
git add src/accounti/export/datev.py tests/test_datev_konformitaet.py tests/test_datev_export.py
git commit -m "fix(export): DATEV-conformant quoting (amounts/accounts unquoted, empty WKZ)"
```

---

## Task 5: Real LLM Classification Stage

**Files:**
- Create: `src/accounti/klassifikation/llm.py`
- Modify: `src/accounti/klassifikation/engine.py` (use new LLM stage)
- Test: `tests/test_llm_klassifikation.py`

Replace the `NotImplementedError` stub with a LiteLLM-backed engine. The LLM is
mocked in tests. PII (IBAN, names) is masked before the prompt is built.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_llm_klassifikation.py
from unittest.mock import patch

from accounti.klassifikation.llm import LLMEngine, maskiere_pii
from accounti.models import Transaktion, TransaktionQuelle


def _tx() -> Transaktion:
    return Transaktion(
        datum="2026-04-10", betrag="-39.99",
        verwendungszweck="TELEKOM DE12345678901234567890 Kundennr 4711",
        gegenkonto_name="Deutsche Telekom AG",
        quelle=TransaktionQuelle.BANK, rohtext="x",
    )


def test_maskiert_iban():
    assert "DE12345678901234567890" not in maskiere_pii(_tx().verwendungszweck)


def test_llm_ergebnis_wird_geparst():
    antwort = (
        '{"soll_konto": "4920", "haben_konto": "1200", "steuer_schluessel": 9, '
        '"buchungstext": "Telefon", "confidence": 0.9, "begruendung": "Telekom"}'
    )
    with patch("accounti.klassifikation.llm.completion") as mock:
        mock.return_value = {"choices": [{"message": {"content": antwort}}]}
        erg = LLMEngine(model="anthropic/claude-test").klassifiziere(_tx())
    assert erg is not None
    assert erg.soll_konto == "4920"
    assert erg.quelle == "llm"
    assert erg.confidence == 0.9


def test_llm_fehler_gibt_none():
    with patch("accounti.klassifikation.llm.completion", side_effect=RuntimeError):
        erg = LLMEngine(model="anthropic/claude-test").klassifiziere(_tx())
    assert erg is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_llm_klassifikation.py -v`
Expected: FAIL — `ModuleNotFoundError: ...klassifikation.llm`

- [ ] **Step 3: Write the LLM engine**

```python
# src/accounti/klassifikation/llm.py
"""LLM-Klassifikationsstufe über LiteLLM (Claude default / Ollama)."""
from __future__ import annotations

import json
import re

from litellm import completion

from accounti.models import Klassifikationsergebnis, Transaktion

_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")
_ZAHLENFOLGE = re.compile(r"\b\d{6,}\b")


def maskiere_pii(text: str) -> str:
    text = _IBAN.sub("[IBAN]", text)
    text = _ZAHLENFOLGE.sub("[NR]", text)
    return text


_PROMPT = """Du bist Buchhaltungs-Assistent für SKR03 (Deutschland).
Kontiere diese Bankbuchung. Antworte NUR mit JSON:
{{"soll_konto","haben_konto","steuer_schluessel","buchungstext","confidence","begruendung"}}
Betrag: {betrag} EUR
Verwendungszweck: {zweck}
Empfänger: {empfaenger}"""


class LLMEngine:
    def __init__(
        self,
        model: str = "anthropic/claude-sonnet-4-20250514",
        confidence_schwelle: float = 0.85,
    ) -> None:
        self.model = model
        self.confidence_schwelle = confidence_schwelle

    def klassifiziere(self, transaktion: Transaktion) -> Klassifikationsergebnis | None:
        prompt = _PROMPT.format(
            betrag=transaktion.betrag,
            zweck=maskiere_pii(transaktion.verwendungszweck),
            empfaenger=maskiere_pii(transaktion.gegenkonto_name or ""),
        )
        try:
            antwort = completion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
            )
            inhalt = antwort["choices"][0]["message"]["content"]
            daten = json.loads(inhalt)
        except Exception:
            return None

        return Klassifikationsergebnis(
            transaktion_id=transaktion.id,
            soll_konto=str(daten["soll_konto"]),
            haben_konto=str(daten["haben_konto"]),
            steuer_schluessel=daten.get("steuer_schluessel"),
            buchungstext=daten.get("buchungstext", transaktion.verwendungszweck[:60]),
            confidence=float(daten.get("confidence", 0.0)),
            begruendung=daten.get("begruendung", ""),
            quelle="llm",
        )
```

- [ ] **Step 4: Wire it into the orchestrator**

In `src/accounti/klassifikation/engine.py`, replace the old stub `LLMEngine` class
with an import from the new module, and activate Stufe 2 in
`KlassifikationsEngine.klassifiziere`:

```python
# near the top, replace the in-file LLMEngine class with:
from accounti.klassifikation.llm import LLMEngine  # noqa: F401
```

```python
    # in KlassifikationsEngine.klassifiziere, replace the commented Stufe-2 block:
        if self.llm is not None:
            return self.llm.klassifiziere(transaktion)
        return None
```

Delete the old `class LLMEngine` definition (with `raise NotImplementedError`) from
`engine.py` to avoid two definitions.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_llm_klassifikation.py tests/test_klassifikation.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/accounti/klassifikation/llm.py src/accounti/klassifikation/engine.py tests/test_llm_klassifikation.py
git commit -m "feat(klassifikation): real LLM stage via LiteLLM with PII masking"
```

---

## Task 6: SQLite Persistence (Postgres-ready)

**Files:**
- Create: `src/accounti/db/__init__.py`
- Create: `src/accounti/db/tabellen.py`
- Create: `src/accounti/db/repository.py`
- Test: `tests/test_db_repository.py`

ORM tables mirror the domain models. Portable column types only (String, Date,
Numeric, Float) so the same code runs on SQLite and Postgres.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db_repository.py
from datetime import date
from decimal import Decimal

from accounti.db import session_factory, init_db
from accounti.db.repository import speichere_transaktion, lade_transaktionen
from accounti.models import Transaktion, TransaktionQuelle


def test_roundtrip_transaktion():
    engine, Session = session_factory("sqlite:///:memory:")
    init_db(engine)
    tx = Transaktion(
        datum=date(2026, 4, 15), betrag=Decimal("-89.50"),
        verwendungszweck="AWS", quelle=TransaktionQuelle.BANK, rohtext="x",
    )
    with Session() as s:
        speichere_transaktion(s, tx)
        s.commit()
    with Session() as s:
        geladen = lade_transaktionen(s)
    assert len(geladen) == 1
    assert geladen[0].betrag == Decimal("-89.50")
    assert geladen[0].verwendungszweck == "AWS"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_db_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: ...db`

- [ ] **Step 3: Write engine/session factory**

```python
# src/accounti/db/__init__.py
"""Datenbank-Setup. SQLite-Default, Postgres-ready via SQLAlchemy."""
from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def session_factory(url: str = "sqlite:///accounti.db") -> tuple[Engine, sessionmaker]:
    engine = create_engine(url)
    return engine, sessionmaker(bind=engine)


def init_db(engine: Engine) -> None:
    from accounti.db import tabellen  # noqa: F401  (registers tables)

    Base.metadata.create_all(engine)
```

- [ ] **Step 4: Write the ORM tables**

```python
# src/accounti/db/tabellen.py
"""SQLAlchemy-Tabellen (Persistenzschicht, portabel SQLite/Postgres)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from accounti.db import Base


class TransaktionRow(Base):
    __tablename__ = "transaktionen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    datum: Mapped[date] = mapped_column(Date)
    betrag: Mapped[str] = mapped_column(Numeric(14, 2))
    waehrung: Mapped[str] = mapped_column(String(3), default="EUR")
    verwendungszweck: Mapped[str] = mapped_column(String(500))
    gegenkonto_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    gegenkonto_iban: Mapped[str | None] = mapped_column(String(34), nullable=True)
    quelle: Mapped[str] = mapped_column(String(20))
    rohtext: Mapped[str] = mapped_column(String(2000))
```

- [ ] **Step 5: Write the repository**

```python
# src/accounti/db/repository.py
"""Mapping zwischen Domänen- (Pydantic) und Persistenz- (ORM) Modellen."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from accounti.db.tabellen import TransaktionRow
from accounti.models import Transaktion, TransaktionQuelle


def speichere_transaktion(session: Session, tx: Transaktion) -> None:
    session.add(
        TransaktionRow(
            id=str(tx.id), datum=tx.datum, betrag=tx.betrag, waehrung=tx.waehrung,
            verwendungszweck=tx.verwendungszweck, gegenkonto_name=tx.gegenkonto_name,
            gegenkonto_iban=tx.gegenkonto_iban, quelle=tx.quelle.value, rohtext=tx.rohtext,
        )
    )


def lade_transaktionen(session: Session) -> list[Transaktion]:
    rows = session.query(TransaktionRow).all()
    return [
        Transaktion(
            id=r.id, datum=r.datum, betrag=Decimal(str(r.betrag)), waehrung=r.waehrung,
            verwendungszweck=r.verwendungszweck, gegenkonto_name=r.gegenkonto_name,
            gegenkonto_iban=r.gegenkonto_iban, quelle=TransaktionQuelle(r.quelle),
            rohtext=r.rohtext,
        )
        for r in rows
    ]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_db_repository.py -v`
Expected: PASS

- [ ] **Step 7: Initialize Alembic (Postgres-ready migrations)**

Run: `.\.venv\Scripts\alembic.exe init alembic`
Then in `alembic/env.py`, set `target_metadata = Base.metadata` (import from
`accounti.db`), and in `alembic.ini` set `sqlalchemy.url = sqlite:///accounti.db`.
Generate the first migration:
`.\.venv\Scripts\alembic.exe revision --autogenerate -m "initial schema"`

- [ ] **Step 8: Commit**

```bash
git add src/accounti/db tests/test_db_repository.py alembic alembic.ini
git commit -m "feat(db): SQLite persistence with SQLAlchemy (Postgres-ready) + Alembic"
```

---

## Task 7: CLI Wiring

**Files:**
- Modify: `src/accounti/cli.py`
- Test: `tests/test_cli_pipeline.py`

Replace the stub bodies of `db init`, `import bank`, and `export datev` with real
calls. Use Typer's `CliRunner` for an end-to-end smoke test on the example CSV.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_pipeline.py
from pathlib import Path

from typer.testing import CliRunner

from accounti.cli import app

runner = CliRunner()
BEISPIEL = Path(__file__).resolve().parents[1] / "examples" / "beispiel_sparkasse.csv"


def test_import_bank_meldet_anzahl(tmp_path):
    db = tmp_path / "accounti.db"
    runner.invoke(app, ["db", "init", "--db", f"sqlite:///{db}"])
    res = runner.invoke(
        app, ["import", "bank", str(BEISPIEL), "--db", f"sqlite:///{db}"]
    )
    assert res.exit_code == 0
    assert "8" in res.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_cli_pipeline.py -v`
Expected: FAIL — stub prints "Noch nicht implementiert", no DB option.

- [ ] **Step 3: Implement `db init`**

Replace the `db_init` body in `cli.py`:

```python
@db_app.command("init")
def db_init(db: str = typer.Option("sqlite:///accounti.db", help="DB-URL")) -> None:
    """Datenbank initialisieren."""
    from accounti.db import init_db, session_factory

    engine, _ = session_factory(db)
    init_db(engine)
    console.print(f"[green]Datenbank initialisiert:[/green] {db}")
```

- [ ] **Step 4: Implement `import bank`**

Replace the `import_bank` body:

```python
@import_app.command("bank")
def import_bank(
    datei: str = typer.Argument(help="Pfad zur Bank-CSV"),
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
    format: str = typer.Option("sparkasse", help="Bankformat"),
) -> None:
    """Banktransaktionen importieren."""
    from accounti.db import init_db, session_factory
    from accounti.db.repository import speichere_transaktion
    from accounti.importers import BANK_IMPORTERS

    importer = BANK_IMPORTERS[format]()
    transaktionen = importer.importiere(datei)
    engine, Session = session_factory(db)
    init_db(engine)
    with Session() as s:
        for tx in transaktionen:
            speichere_transaktion(s, tx)
        s.commit()
    console.print(f"[green]{len(transaktionen)}[/green] Transaktionen importiert.")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_cli_pipeline.py -v`
Expected: PASS

- [ ] **Step 6: Run the full suite + lint**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Run: `.\.venv\Scripts\ruff.exe check src tests`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/accounti/cli.py tests/test_cli_pipeline.py
git commit -m "feat(cli): wire real db-init and bank-import commands"
```

---

## Task 8: Classify + Export CLI (end-to-end) and Feedback

**Files:**
- Modify: `src/accounti/cli.py`
- Test: `tests/test_cli_end_to_end.py`

Wire `classify` (rules + optional LLM → Buchungssätze) and `export datev` to read
from the DB, then add a minimal feedback command that appends a correction to
`config/regeln.yaml`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_end_to_end.py
from pathlib import Path

from typer.testing import CliRunner

from accounti.cli import app

runner = CliRunner()
BEISPIEL = Path(__file__).resolve().parents[1] / "examples" / "beispiel_sparkasse.csv"


def test_import_classify_export(tmp_path):
    url = f"sqlite:///{tmp_path / 'a.db'}"
    runner.invoke(app, ["db", "init", "--db", url])
    runner.invoke(app, ["import", "bank", str(BEISPIEL), "--db", url])
    c = runner.invoke(app, ["classify", "--db", url, "--no-llm"])
    assert c.exit_code == 0
    out = tmp_path / "export"
    e = runner.invoke(
        app,
        ["export", "datev", "--db", url, "--berater", "23426",
         "--mandant", "40005", "--output", str(out)],
    )
    assert e.exit_code == 0
    dateien = list(out.glob("EXTF_*.csv"))
    assert len(dateien) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_cli_end_to_end.py -v`
Expected: FAIL — `classify`/`export` are stubs with no `--db`.

- [ ] **Step 3: Add a Buchungssatz repository helper**

Add to `src/accounti/db/tabellen.py` a `BuchungssatzRow` (columns: `id` String(36) pk,
`transaktion_id` String(36), `datum` Date, `soll_konto`/`haben_konto` String(10),
`betrag_netto` Numeric(14,2), `steuer_schluessel` Integer nullable, `steuer_betrag`
Numeric(14,2) nullable, `buchungstext` String(60), `status` String(20), `confidence`
Float). Add `speichere_buchung`, `lade_buchungen` to `repository.py` mirroring the
Transaktion roundtrip. (Follow the exact pattern from Task 6.)

- [ ] **Step 4: Implement `classify`**

```python
@app.command()
def classify(
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
    llm: bool = typer.Option(True, "--llm/--no-llm", help="LLM-Stufe nutzen"),
) -> None:
    """Transaktionen automatisch kontieren."""
    from accounti.buchung.mapper import zu_buchungssatz
    from accounti.db import session_factory
    from accounti.db.repository import lade_transaktionen, speichere_buchung
    from accounti.klassifikation.engine import KlassifikationsEngine, RegelwerkEngine
    from accounti.klassifikation.llm import LLMEngine
    from accounti.klassifikation.regeln_loader import lade_regeln

    regeln = lade_regeln("config/regeln.yaml") or None
    engine = KlassifikationsEngine(
        regelwerk=RegelwerkEngine(regeln),
        llm=LLMEngine() if llm else None,
    )
    _, Session = session_factory(db)
    auto = offen = 0
    with Session() as s:
        for tx in lade_transaktionen(s):
            erg = engine.klassifiziere(tx)
            if erg is None:
                offen += 1
                continue
            speichere_buchung(s, zu_buchungssatz(tx, erg))
            auto += 1
        s.commit()
    console.print(f"[green]{auto}[/green] kontiert, [yellow]{offen}[/yellow] offen.")
```

- [ ] **Step 5: Implement `export datev`**

```python
@export_app.command("datev")
def export_datev(
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
    berater: str = typer.Option(..., help="DATEV Beraternummer"),
    mandant: str = typer.Option(..., help="DATEV Mandantennummer"),
    output: str = typer.Option("./export", help="Ausgabeverzeichnis"),
) -> None:
    """DATEV-konformen Buchungsstapel exportieren."""
    from accounti.db import session_factory
    from accounti.db.repository import lade_buchungen
    from accounti.export.datev import DATEVConfig, DATEVExporter

    _, Session = session_factory(db)
    with Session() as s:
        buchungen = lade_buchungen(s)
    cfg = DATEVConfig(berater_nummer=berater, mandanten_nummer=mandant)
    datei = DATEVExporter(cfg).exportiere(buchungen, output)
    console.print(f"[green]Export:[/green] {datei} ({len(buchungen)} Buchungen)")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_cli_end_to_end.py -v`
Expected: PASS

- [ ] **Step 7: Add feedback command**

```python
@app.command()
def lerne(
    muster: str = typer.Option(..., help="Text-Muster (Regex)"),
    soll: str = typer.Option(..., help="Soll-Konto"),
    haben: str = typer.Option(..., help="Haben-Konto"),
    name: str = typer.Option(..., help="Regel-Name"),
    steuer: int = typer.Option(None, help="Steuerschlüssel"),
) -> None:
    """Korrektur als neue Regel speichern (Lernschleife)."""
    import yaml

    pfad = Path("config/regeln.yaml")
    regeln = yaml.safe_load(pfad.read_text(encoding="utf-8")) if pfad.exists() else []
    regeln.append({
        "name": name, "muster": muster, "feld": "verwendungszweck",
        "soll_konto": soll, "haben_konto": haben, "steuer_schluessel": steuer,
        "buchungstext": name,
    })
    pfad.write_text(yaml.safe_dump(regeln, allow_unicode=True), encoding="utf-8")
    console.print(f"[green]Regel '{name}' gespeichert.[/green]")
```

- [ ] **Step 8: Full suite + lint + commit**

```bash
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check src tests
git add src/accounti/cli.py src/accounti/db tests/test_cli_end_to_end.py
git commit -m "feat(cli): end-to-end classify/export + feedback learning command"
```

---

## Final Verification

- [ ] Run the whole suite: `.\.venv\Scripts\python.exe -m pytest -q` → all green (53 existing + new).
- [ ] `.\.venv\Scripts\ruff.exe check src tests` → clean.
- [ ] Manual smoke test:
  ```bash
  .\.venv\Scripts\accounti.exe db init
  .\.venv\Scripts\accounti.exe import bank examples\beispiel_sparkasse.csv
  .\.venv\Scripts\accounti.exe classify --no-llm
  .\.venv\Scripts\accounti.exe export datev --berater 23426 --mandant 40005
  ```
- [ ] Open the produced `EXTF_*.csv` and confirm amounts/accounts are unquoted, text quoted, CRLF line endings.
- [ ] Push branch and open a PR against `main`.

## Spec Coverage Check

- Importer (§4.1) → Task 1 ✓
- YAML rules (§4.2) → Task 2 ✓
- LLM stage + PII masking (§4.2) → Task 5 ✓
- Buchung mapper + tax split (§4.3) → Task 3 ✓
- DB SQLite/Postgres-ready (§4.4) → Task 6 ✓
- DATEV conformance (§4.5) → Task 4 ✓
- CLI wiring (§4.6) → Tasks 7, 8 ✓
- Feedback/learning (§3 step 7) → Task 8 ✓
- Acceptance criteria 1–5 (§7) → covered by Tasks 7–8 + Final Verification ✓
