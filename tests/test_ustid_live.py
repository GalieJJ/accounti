"""Echtabfrage beim BZSt mit den dokumentierten Testwerten — nicht in der CI.

ACCOUNTI_EVATR_LIVE=1 pytest tests/test_ustid_live.py
"""

import os
from datetime import datetime

import pytest

from accounti.kontakte.ustid import EvatrClient, baue_anfrage, bewerte, werte_aus

pytestmark = pytest.mark.skipif(
    os.environ.get("ACCOUNTI_EVATR_LIVE") != "1",
    reason="Echtabfrage beim BZSt nur mit ACCOUNTI_EVATR_LIVE=1",
)


def test_testwerte_des_bzst_werden_qualifiziert_bestaetigt():
    anfrage = baue_anfrage(
        "DE123456789",
        "ATU12345678",
        "Musterhaus GmbH & Co KG",
        "Musterstrasse 22",
        "12345",
        "musterort",
    )
    antwort = EvatrClient().sende(anfrage.als_dict())
    p = werte_aus(anfrage, antwort.status, antwort.text, None, datetime.now())
    b = bewerte(p)
    assert b.bestaetigt, b.grund
    assert p.bzst_id and p.bzst_zeitpunkt
    assert (p.erg_firmenname, p.erg_ort) == ("A", "A")
