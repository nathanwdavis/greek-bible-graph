import pytest

from gbg import refs

# (input, canonical, SBL display, partial)
OK = [
    ("Rom 3:21-26", "ROM 3:21-26", "Rom 3:21–26", False),
    ("Rom 3:21–4:2", "ROM 3:21-4:2", "Rom 3:21–4:2", False),
    ("Rom 3", "ROM 3", "Rom 3", False),
    ("Rom 3-4", "ROM 3-4", "Rom 3–4", False),
    ("Rom 3:21-26, 28; 5:1", "ROM 3:21-26; ROM 3:28; ROM 5:1",
     "Rom 3:21–26; Rom 3:28; Rom 5:1", False),
    ("Rom 3; 5", "ROM 3; ROM 5", "Rom 3; Rom 5", False),
    ("Rom 3.21", "ROM 3:21", "Rom 3:21", False),
    ("Rom 3:21a", "ROM 3:21", "Rom 3:21", True),
    ("Phlm 10", "PHM 1:10", "Phlm 10", False),      # single-chapter book: a verse
    ("Phlm 1:10", "PHM 1:10", "Phlm 10", False),
    ("Phlm 8-10", "PHM 1:8-10", "Phlm 8–10", False),
    ("Phlm", "PHM", "Philemon", False),
    ("1 Cor. 13:4-7", "1CO 13:4-7", "1 Cor 13:4–7", False),
    ("3 John 14", "3JN 1:14", "3 John 14", False),
    ("  Jn   1:1 ", "JHN 1:1", "John 1:1", False),
    ("PHM 1:1!3", "PHM 1:1!3", "Phlm 1", False),
    ("PHM 1:1!3-5", "PHM 1:1!3-5", "Phlm 1", False),
    ("sblgnt:PHM.1.1", "PHM 1:1", "Phlm 1", False),
    ("sblgnt:n57001001003", "PHM 1:1!3", "Phlm 1", False),
    ("sblgnt:PHM", "PHM", "Philemon", False),
]


@pytest.mark.parametrize("text,canonical,sbl,partial", OK)
def test_parse(text, canonical, sbl, partial):
    p = refs.parse(text)
    assert p.canonical() == canonical
    assert p.sbl() == sbl
    assert p.partial is partial


@pytest.mark.parametrize("text,fragment", [
    ("Rom 3:21ff", "open-ended"),
    ("Rom 3:21f.", "open-ended"),
    ("Jud 3", "ambiguous"),
    ("Rom 3:26-21", "backwards"),
    ("Xyz 1:1", "unknown book"),
    ("Rom 0:1", "count from 1"),
    ("lemma:θεός", "lemma id"),
    ("Rom 3a", "half verse"),
    ("Rom 3:x", "cannot read"),
    ("", "empty"),
])
def test_refuses(text, fragment):
    with pytest.raises(refs.RefError) as exc:
        refs.parse(text)
    assert fragment in str(exc.value)
