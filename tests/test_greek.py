import duckdb
import pytest

from gbg import greek

# (input, expected search key, why this case exists)
KEY_CASES = [
    ("ἐν", "εν", "smooth breathing + grave"),
    ("ἀρχῇ", "αρχη", "iota subscript must vanish, not become ι"),
    ("Ἰησοῦ", "ιησου", "capital with breathing + circumflex"),
    ("κατ’", "κατ", "elision with U+2019"),
    ("κατ᾽", "κατ", "elision with Greek koronis"),
    ("κατʼ", "κατ", "elision with modifier apostrophe"),
    ("Βίβλος", "βιβλοσ", "final sigma folds to medial"),
    ("ΘΕΟΣ", "θεοσ", "all caps: lower() and casefold() agree after sigma fold"),
    ("προϊόντες", "προιοντεσ", "diaeresis"),
    ("ᾠδή", "ωδη", "iota subscript under omega with breathing"),
    ("άγιος", "αγιοσ", "oxia (U+1F71), not tonos"),
    ("Ῥώμη", "ρωμη", "rough breathing on rho"),
    ("λόγος,", "λογοσ", "trailing punctuation"),
    ("τί;", "τι", "Greek question mark as ';'"),
    ("τί;", "τι", "Greek question mark as U+037E"),
]


@pytest.mark.parametrize("text,key,why", KEY_CASES)
def test_search_key(text, key, why):
    assert greek.search_key(text) == key, why


def test_casefold_happens_after_stripping():
    # casefold() first would turn U+0345 into a real iota: "εκκλησιαι".
    assert greek.search_key("ἐκκλησίᾳ") == "εκκλησια"


def test_nfc_folds_oxia_to_tonos():
    assert greek.nfc("ά") == "ά"
    assert greek.nfc("θεός") == greek.nfc("θεός")


def test_identity_keeps_accent_distinctions():
    # The key collapses these on purpose; identity must not.
    assert greek.search_key("τίς") == greek.search_key("τις")
    assert greek.nfc("τίς") != greek.nfc("τις")
    assert greek.nfc("εἰς") != greek.nfc("εἷς")


@pytest.mark.parametrize("text,key,why", KEY_CASES)
def test_sql_macro_agrees_with_python(text, key, why):
    con = duckdb.connect()
    con.execute(greek.SQL_KEY_MACRO)
    assert con.execute("SELECT gbg_key(?)", [text]).fetchone()[0] == greek.search_key(text), why
