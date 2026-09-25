import pytest

from conftest import ROOT
from gbg import evals


def test_goldens_reproduce_on_the_fixture(fixture_db):
    assert evals.check_goldens(ROOT, fixture_db) == []


def test_every_question_is_well_formed():
    qs = evals.load(ROOT)
    assert len({q["id"] for q in qs}) == len(qs) >= 10
    for q in qs:
        assert q["scope"] in ("fixture", "nt", "any")
        g = q["golden"]
        assert len(g) == 1 and next(iter(g)) in ("ids", "rows", "value", "refusal")
        if "refusal" not in g:
            assert ("query" in q) != ("sql" in q), q["id"]


def test_a_drifted_golden_is_reported(fixture_db, monkeypatch):
    qs = evals.load(ROOT)
    q = next(q for q in qs if q["id"] == "shared-wording-2jn-3jn")
    q["golden"] = {"rows": 9}
    monkeypatch.setattr(evals, "load", lambda root: [q])
    [v] = evals.check_goldens(ROOT, fixture_db)
    assert v.rule == "golden-drift" and "8 rows, golden 9" in v.reason


@pytest.mark.parametrize("answer,ok,fabricated", [
    ("αὐτόν (sblgnt:n57001012004) refers to Onesimus, sblgnt:n57001010012.", True, False),
    ("It is Onesimus (sblgnt:n57001010012).", False, False),                    # recall 1/2
    ("Onesimus: sblgnt:n57001012004, sblgnt:n57001010012, sblgnt:n57001099001.", True, True),
])
def test_scoring_ids_and_fabrication(fixture_db, answer, ok, fabricated):
    rows, hallucinated = evals.score(ROOT, fixture_db, {"autos-phlm-12": answer})
    assert rows[0]["ok"] is (ok and not fabricated)
    assert hallucinated is fabricated


def test_scoring_refusals(fixture_db):
    good = "This build does not include Louw-Nida semantic domains (license), so I can't say."
    bad = "ἀγάπη is in domain 25.43 (sblgnt:n63001003014)."
    rows, _ = evals.score(ROOT, fixture_db, {"louw-nida-agape": good})
    assert rows[0]["ok"]
    rows, _ = evals.score(ROOT, fixture_db, {"louw-nida-agape": bad})
    assert not rows[0]["ok"]


def test_scoring_stated_numbers(fixture_db):
    rows, _ = evals.score(ROOT, fixture_db, {"shared-wording-2jn-3jn": "They share 8 trigrams."})
    assert rows[0]["ok"]
    rows, _ = evals.score(ROOT, fixture_db, {"shared-wording-2jn-3jn": "They share 18 trigrams."})
    assert not rows[0]["ok"]


@pytest.mark.parametrize("text", ["It occurs 1,307 times.", "It occurs 1307 times.",
                                  "It occurs 1\u202f307 times."])
def test_numbers_with_thousands_separators_count(fixture_db, text):
    rows, _ = evals.score(ROOT, fixture_db, {"theos-nt": text})
    assert rows[0]["ok"]
