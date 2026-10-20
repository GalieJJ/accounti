"""FinTS ist ein Zusatzpaket: ohne `accounti[fints]` eine klare Meldung."""

import sys

import pytest

from accounti.bank import fints as fints_modul
from accounti.bank.provider import ProviderError


def test_ohne_zusatzpaket_klare_meldung(monkeypatch):
    fints_modul._client_klasse.cache_clear()
    monkeypatch.setitem(sys.modules, "fints", None)
    monkeypatch.setitem(sys.modules, "fints.client", None)
    try:
        with pytest.raises(ProviderError, match=r"accounti\[fints\]"):
            fints_modul._client_klasse()
    finally:
        fints_modul._client_klasse.cache_clear()
