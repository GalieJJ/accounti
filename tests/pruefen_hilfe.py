"""Testwelt der Supervisions-Queue (Baustein 10b, Paket 3).

Zwei Gesellschaften (a: SKR03, b: SKR04 mit Bank 1800), Personen mit allen Rollen,
unsichere Buchungen über den echten Kontierungslauf mit LLM-Attrappe (Confidence
0,62 und Begründung), Belege im Archiv der Gesellschaft.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from accounti.belege.archiv import BelegArchiv
from accounti.buchung.kontierung import kontiere_umsaetze
from accounti.db import session_factory
from accounti.db.repository import (
    lade_buchungen,
    speichere_beleg,
    speichere_buchung,
    speichere_transaktion,
)
from accounti.klassifikation.engine import KlassifikationsEngine
from accounti.konfiguration import Buchhaltung
from accounti.models import (
    Beleg,
    Belegart,
    BelegStatus,
    Buchungssatz,
    BuchungStatus,
    Klassifikationsergebnis,
    Transaktion,
    TransaktionQuelle,
)
from accounti.models.auth import Rolle
from tests.api_hilfe import Webwelt, formularwert, webwelt
from tests.pdf_hilfe import pdf_mit_text

LLM_BEGRUENDUNG = "Bürobedarf laut Gegenpartei; Betrag typisch für Verbrauchsmaterial"


class LLMAttrappe:
    """Antwortet wie die LLM-Stufe (Konto 4980, Confidence 0,62) — ohne Netz."""

    model = "attrappe/kontierer-1"

    def __init__(
        self, soll: str = "4980", confidence: float = 0.62, bank: str = "1200"
    ) -> None:
        self.soll = soll
        self.confidence = confidence
        self.bank = bank
        self.gefragt: list[str] = []

    def klassifiziere(self, tx: Transaktion) -> Klassifikationsergebnis:
        self.gefragt.append(tx.verwendungszweck)
        ausgabe = tx.betrag < 0
        return Klassifikationsergebnis(
            transaktion_id=tx.id,
            soll_konto=self.soll if ausgabe else self.bank,
            haben_konto=self.bank if ausgabe else "8400",
            steuer_schluessel=9 if ausgabe else 3,
            buchungstext=tx.verwendungszweck[:60],
            confidence=self.confidence,
            begruendung=LLM_BEGRUENDUNG,
            quelle="llm",
            modell=self.model,
        )


@dataclass
class Queuewelt:
    web: Webwelt
    tmp: Path

    def fabrik(self, kuerzel: str = "a") -> sessionmaker[Session]:
        _, fabrik = session_factory(self.web.umgebung.db[kuerzel])
        return fabrik

    def archiv(self, kuerzel: str = "a") -> BelegArchiv:
        return BelegArchiv(self.web.umgebung.archiv[kuerzel])

    def umsatz(
        self,
        betrag: str = "-59.50",
        tag: date = date(2026, 10, 1),
        zweck: str = "RE 4711 Büromaterial",
        name: str | None = "Bürobedarf Müller GmbH",
        kuerzel: str = "a",
        **kw: Any,
    ) -> Transaktion:
        tx = Transaktion(
            datum=tag,
            betrag=Decimal(betrag),
            verwendungszweck=zweck,
            gegenkonto_name=name,
            quelle=TransaktionQuelle.BANK,
            rohtext=zweck,
            **kw,
        )
        with self.fabrik(kuerzel)() as s:
            speichere_transaktion(s, tx)
            s.commit()
        return tx

    def kontiere(
        self, kuerzel: str = "a", llm: LLMAttrappe | None = None
    ) -> list[Buchungssatz]:
        """Der echte Kontierungslauf mit LLM-Attrappe — neue Buchungen."""
        with self.fabrik(kuerzel)() as s:
            vorher = {b.id for b in lade_buchungen(s)}
            if llm is None:
                llm = LLMAttrappe("6815", bank="1800") if kuerzel == "b" else None
            engine = KlassifikationsEngine(llm=llm or LLMAttrappe())  # type: ignore[arg-type]
            bh = Buchhaltung(
                kontenrahmen="SKR04" if kuerzel == "b" else "SKR03",
                bank_konto="1800" if kuerzel == "b" else "1200",
            )
            kontiere_umsaetze(s, engine, bh)
            s.commit()
            return sorted(
                (b for b in lade_buchungen(s) if b.id not in vorher),
                key=lambda b: (b.datum, str(b.id)),
            )

    def unsicher(self, kuerzel: str = "a", **kw: Any) -> Buchungssatz:
        tx = self.umsatz(kuerzel=kuerzel, **kw)
        (b,) = [b for b in self.kontiere(kuerzel) if b.transaktion_id == tx.id]
        assert b.status is BuchungStatus.ZUR_PRUEFUNG
        return b

    def beleg(
        self,
        inhalt: bytes,
        endung: str = ".pdf",
        kuerzel: str = "a",
        **kw: Any,
    ) -> Beleg:
        datei_hash = self.archiv(kuerzel).ablegen(inhalt, endung)
        werte: dict[str, Any] = {
            "belegart": Belegart.EINGANGSRECHNUNG,
            "belegnummer": "RE-4711",
            "belegdatum": date(2026, 9, 28),
            "lieferant_name": "Bürobedarf Müller GmbH",
            "netto": Decimal("50.00"),
            "steuer": Decimal("9.50"),
            "brutto": Decimal("59.50"),
            "datei_hash": datei_hash,
            "dateiname": f"rechnung{endung}",
            "kanal": "upload",
            "herkunft": "test",
            "eingegangen_am": datetime(2026, 9, 29, 9, 0),
            "aufbewahren_bis": date(2036, 12, 31),
            "status": BelegStatus.ERFASST,
        }
        werte.update(kw)
        b = Beleg.model_validate(werte)
        with self.fabrik(kuerzel)() as s:
            speichere_beleg(s, b)
            s.commit()
        return b

    def buchung(self, kuerzel: str = "a", **kw: Any) -> Buchungssatz:
        werte: dict[str, Any] = {
            "datum": date(2026, 10, 1),
            "soll_konto": "4980",
            "haben_konto": "1200",
            "betrag_netto": Decimal("50.00"),
            "steuer_schluessel": 9,
            "steuer_betrag": Decimal("9.50"),
            "buchungstext": "Bürobedarf",
            "status": BuchungStatus.ZUR_PRUEFUNG,
            "confidence": 0.5,
        }
        for kurz, lang in (("soll", "soll_konto"), ("haben", "haben_konto")):
            if kurz in kw:
                kw[lang] = kw.pop(kurz)
        werte.update(kw)
        b = Buchungssatz.model_validate(werte)
        with self.fabrik(kuerzel)() as s:
            speichere_buchung(s, b)
            s.commit()
        return b

    def sql(self, anweisung: str, kuerzel: str = "a", **werte: Any) -> list[Any]:
        with self.fabrik(kuerzel)() as s:
            zeilen = s.execute(text(anweisung), werte)
            ergebnis = list(zeilen) if zeilen.returns_rows else []
            s.commit()
        return ergebnis


def queuewelt(tmp_path: Path, **auth: object) -> Queuewelt:
    w = webwelt(tmp_path, **auth)
    w.person("jan", Rolle.BUCHHALTER)
    w.person("fritz", Rolle.FREIGEBER)
    w.person("leo", Rolle.BETRACHTER)
    w.person("vera", Rolle.VERWALTER)
    w.rolle("jan", "b", Rolle.BUCHHALTER)
    # Gesellschaft b bucht gegen 1800 (SKR04)
    pfad = w.umgebung.config["b"]
    pfad.write_text(
        pfad.read_text(encoding="utf-8").replace(
            "buchhaltung:\n  kontenrahmen: SKR04\n",
            "buchhaltung:\n  kontenrahmen: SKR04\n  bank_konto: '1800'\n",
        ),
        encoding="utf-8",
    )
    return Queuewelt(w, tmp_path)


def stand_aus(html: str) -> str:
    return formularwert(html, "stand")


def png(breite: int = 4, hoehe: int = 3) -> bytes:
    from PIL import Image

    ausgabe = io.BytesIO()
    Image.new("RGB", (breite, hoehe), (200, 30, 30)).save(ausgabe, format="PNG")
    return ausgabe.getvalue()


def jpeg() -> bytes:
    from PIL import Image

    ausgabe = io.BytesIO()
    Image.new("RGB", (4, 3), (10, 30, 200)).save(ausgabe, format="JPEG")
    return ausgabe.getvalue()


def tiff(*groessen: tuple[int, int], modus: str = "RGB") -> bytes:
    from PIL import Image

    seiten = [Image.new(modus, g) for g in (groessen or ((5, 4),))]
    ausgabe = io.BytesIO()
    seiten[0].save(
        ausgabe,
        format="TIFF",
        save_all=True,
        append_images=seiten[1:],
        compression="tiff_deflate",  # große, einfarbige Seiten bleiben klein
    )
    return ausgabe.getvalue()


def pdf(text_: str = "Rechnung RE-4711 Bürobedarf Müller GmbH") -> bytes:
    return pdf_mit_text(text_)
