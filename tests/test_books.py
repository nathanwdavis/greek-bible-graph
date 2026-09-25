import pytest

from gbg import books


@pytest.mark.parametrize("text,code", [
    ("Phlm", "PHM"), ("phm", "PHM"), ("Philemon", "PHM"), ("PHM", "PHM"),
    ("1 Cor.", "1CO"), ("1cor", "1CO"), ("1 Corinthians", "1CO"),
    ("JUD", "JUD"), ("Jude", "JUD"), ("Jn", "JHN"), ("2 Jn", "2JN"),
    ("3 Kgdms", "1KI"), ("Song of Songs", "SNG"), ("Esth", "EST"),
    ("Pss", "PSA"),     # SBL's plural of Psalms...
    ("PSS", "PSS"),     # ...while the exact USFM code is the Psalms of Solomon
    ("mat", "MAT"),     # a lowercased USFM code works where no name claims it
])
def test_lookup(text, code):
    assert books.lookup(text).code == code


@pytest.mark.parametrize("text,candidates", [
    ("Jud", {"JUD", "JDT", "JDG"}),
    ("Ph", {"PHP", "PHM"}),
])
def test_ambiguous_aliases_refuse_to_guess(text, candidates):
    with pytest.raises(books.AmbiguousBook) as exc:
        books.lookup(text)
    assert set(exc.value.candidates) == candidates


def test_unknown():
    with pytest.raises(books.UnknownBook):
        books.lookup("Xyz")


def test_nt_numbers_match_macula():
    # MACULA's xml:id book numbers run MAT=40 .. REV=66 in canonical order.
    nt = [b for b in books.BOOKS if b.corpus == "nt"]
    assert [b.num for b in nt] == list(range(40, 67))
    assert (nt[0].code, nt[-1].code) == ("MAT", "REV")


def test_single_chapter_books():
    assert {b.code for b in books.BOOKS if b.corpus == "nt" and b.single_chapter} == {
        "PHM", "2JN", "3JN", "JUD"}
