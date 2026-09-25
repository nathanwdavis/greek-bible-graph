import pytest

from gbg import ids


@pytest.mark.parametrize("ident,kind", [
    ("sblgnt:n57001001001", "token"),
    ("sblgnt:PHM.1.20", "verse"),
    ("sblgnt:1CO.13.4", "verse"),
    ("sblgnt:PHM", "book"),
    ("sblgnt:s:n57001001001", "sentence"),
    ("sblgnt:wg:n57001001001.2", "wg"),
    ("lemma:θεός", "lemma"),
    ("n57001001001", None),          # bare MACULA id: no edition, not citable
    ("sblgnt:n5700100100", None),    # wrong width
])
def test_kind_of(ident, kind):
    assert ids.kind_of(ident) == kind


def test_minting_round_trips():
    assert ids.token_id("n57001001001") == "sblgnt:n57001001001"
    assert ids.token_parts("sblgnt:n57001020003") == (57, 1, 20, 3)
    assert ids.verse_id("PHM", 1, 20) == "sblgnt:PHM.1.20"
    assert ids.wg_id("n57001001001", 2) == "sblgnt:wg:n57001001001.2"
    assert ids.lemma_id("θεός") == "lemma:θεός"


def test_only_stable_kinds_are_citable():
    assert set(ids.CITABLE) == {"token", "verse", "book", "lemma"}
