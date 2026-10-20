import pytest

from accounti.elster.steuernummer import (
    SteuernummerError,
    elster_steuernummer,
    finanzamtsnummer,
)

# Beispiele je Land: Wikipedia „Steuernummer“ (Bundesschema 13-stellig)
BEISPIELE = [
    ("BW", "93/815/08152", "2893081508152"),
    ("BY", "181/815/08155", "9181081508155"),
    ("BY", "198/113/10010", "9198011310010"),  # Teststeuernummer (ERiC-Handbuch 6.5.1)
    ("BE", "21/815/08150", "1121081508150"),
    ("BB", "048/815/08155", "3048081508155"),
    ("HB", "75 815 08152", "2475081508152"),
    ("HH", "02/815/08156", "2202081508156"),
    ("HE", "013 815 08153", "2613081508153"),
    ("MV", "079/815/08151", "4079081508151"),
    ("NI", "24/815/08151", "2324081508151"),
    ("NW", "133/8150/8159", "5133081508159"),
    ("RP", "22/815/08154", "2722081508154"),
    ("SL", "010/815/08182", "1010081508182"),
    ("SN", "201/123/12340", "3201012312340"),
    ("ST", "101/815/08154", "3101081508154"),
    ("SH", "29 815 08158", "2129081508158"),
    ("TH", "151/815/08156", "4151081508156"),
]


@pytest.mark.parametrize(("land", "nummer", "elster"), BEISPIELE)
def test_landesformat_zu_elster(land, nummer, elster):
    assert elster_steuernummer(nummer, land) == elster
    assert finanzamtsnummer(elster) == elster[:4]


def test_bereits_im_elster_format():
    assert elster_steuernummer("9181081508155") == "9181081508155"
    assert elster_steuernummer("918181508155") == "9181081508155"  # 12-stellig


@pytest.mark.parametrize(
    ("nummer", "land", "grund"),
    [
        ("181/815/08155", None, "Bundesland"),
        ("12345", "BY", "Stellen"),
        ("181/815/08155", "XX", "Bundesland"),
        ("2893081508152", "BY", "passt nicht"),  # BW-Nummer, Land Bayern
        ("91810815081x5", None, "Ziffern"),
    ],
)
def test_fehler(nummer, land, grund):
    with pytest.raises(SteuernummerError, match=grund):
        elster_steuernummer(nummer, land)
