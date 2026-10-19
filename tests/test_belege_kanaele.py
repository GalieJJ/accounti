from accounti.belege.kanaele import BELEG_KANAELE
from accounti.belege.kanaele.ordner import OrdnerKanal
from accounti.belege.kanaele.upload import UploadKanal


def test_registry_kennt_ordner_und_upload():
    assert BELEG_KANAELE["ordner"] is OrdnerKanal
    assert BELEG_KANAELE["upload"] is UploadKanal
    assert all(k.beschreibung for k in BELEG_KANAELE.values())


def test_ordner_liefert_nur_regulaere_sichtbare_dateien(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"A")
    (tmp_path / "b.jpg").write_bytes(b"B")
    (tmp_path / ".versteckt").write_bytes(b"X")
    (tmp_path / "unterordner").mkdir()
    (tmp_path / "unterordner" / "c.pdf").write_bytes(b"C")

    roh = list(OrdnerKanal(tmp_path).abholen())

    assert [r.dateiname for r in roh] == ["a.pdf", "b.jpg"]
    assert roh[0].inhalt == b"A"
    assert roh[0].kanal == "ordner"
    assert roh[0].herkunft == str(tmp_path / "a.pdf")


def test_ordner_verschiebt_bestaetigte_dateien(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"A")
    kanal = OrdnerKanal(tmp_path)
    (roh,) = list(kanal.abholen())

    kanal.bestaetige(roh)

    assert not (tmp_path / "a.pdf").exists()
    assert (tmp_path / "verarbeitet" / "a.pdf").read_bytes() == b"A"
    assert list(kanal.abholen()) == []


def test_ordner_ueberschreibt_nichts_in_verarbeitet(tmp_path):
    (tmp_path / "verarbeitet").mkdir()
    (tmp_path / "verarbeitet" / "a.pdf").write_bytes(b"ALT")
    (tmp_path / "a.pdf").write_bytes(b"NEU")
    kanal = OrdnerKanal(tmp_path)
    (roh,) = list(kanal.abholen())

    kanal.bestaetige(roh)

    assert (tmp_path / "verarbeitet" / "a.pdf").read_bytes() == b"ALT"
    assert sorted(p.name for p in (tmp_path / "verarbeitet").iterdir()) == [
        "a-1.pdf",
        "a.pdf",
    ]


def test_upload_liefert_dateien_und_laesst_sie_liegen(tmp_path):
    datei = tmp_path / "r.pdf"
    datei.write_bytes(b"R")
    kanal = UploadKanal([datei])
    (roh,) = list(kanal.abholen())
    kanal.bestaetige(roh)
    assert roh.kanal == "upload"
    assert roh.inhalt == b"R"
    assert datei.exists()
