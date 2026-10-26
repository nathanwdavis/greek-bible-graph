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
        assert len(g) == 1 and next(iter(g)) in ("ids", "rows", "value", "refusal", "recall")
        if "recall" in g:
            # a thematic golden: an independent verse list and a floor, no reference needed
            assert 0 < g["recall"]["min"] <= 1 and g["recall"]["ids"], q["id"]
            assert ("query" in q) + ("sql" in q) <= 1, q["id"]
        elif "refusal" not in g:
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


@pytest.mark.parametrize("qid,answer,ok", [
    ("louw-nida-agape", "This build does not include Louw-Nida semantic domains (license), "
                        "so I can't say.", True),
    # Declining while citing real context is good practice, not a failure.
    ("louw-nida-agape", "I can't answer that: Louw-Nida domains are not in this build. The graph "
                        "does have lemma:ἀγάπη (sblgnt:n63001003014).", True),
    # (The fixture has no Acts, so this decline cites nothing; the scorer checks
    # that cited ids exist, not that they are relevant.)
    ("acts-8-37", "Acts 8:37 is not in this edition, so I cannot quote it.", True),
    # Naming the topic is not declining: this answers anyway.
    ("louw-nida-agape", "ἀγάπη is in domain 25.43 (sblgnt:n63001003014).", False),
    # A fabricated id sinks even a proper decline.
    ("louw-nida-agape", "Louw-Nida is not in this build (see sblgnt:n57099099099).", False),
])
def test_scoring_refusals(fixture_db, qid, answer, ok):
    rows, _ = evals.score(ROOT, fixture_db, {qid: answer})
    assert rows[0]["ok"] is ok


def test_number_words_state_the_number(fixture_db):
    rows, _ = evals.score(ROOT, fixture_db, {"ego-grammatical-subject": "Four verbs, namely ..."})
    assert rows[0]["ok"]
    rows, _ = evals.score(ROOT, fixture_db, {"ego-grammatical-subject": "Five verbs, namely ..."})
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


def test_number_words_stop_at_twenty(fixture_db):
    # The contract is digits, or a number word up to twenty -- not compound phrases.
    rows, _ = evals.score(ROOT, fixture_db, {"agape-nt": "It occurs one hundred sixteen times."})
    assert not rows[0]["ok"]


RECALL_Q = {"id": "love-2jn", "scope": "fixture", "question": "Where is love spoken of in 2 John?",
            "golden": {"recall": {"min": 0.5, "ids": [
                "sblgnt:2JN.1.1", "sblgnt:2JN.1.3", "sblgnt:2JN.1.5", "sblgnt:2JN.1.6"]}}}


@pytest.mark.parametrize("answer,ok,fabricated", [
    # a word id counts for its verse: n63001001011 is in 2 John 1
    ("2 John 1 (sblgnt:n63001001011) and 5 (sblgnt:2JN.1.5).", True, False),
    ("Only 2 John 1: sblgnt:2JN.1.1.", False, False),                        # 1/4 < 0.5
    ("sblgnt:2JN.1.1, sblgnt:2JN.1.5, sblgnt:2JN.1.99", False, True),         # fabricated
])
def test_scoring_recall(fixture_db, monkeypatch, answer, ok, fabricated):
    monkeypatch.setattr(evals, "load", lambda root: [RECALL_Q])
    rows, hallucinated = evals.score(ROOT, fixture_db, {"love-2jn": answer})
    assert rows[0]["ok"] is ok and hallucinated is fabricated


def test_recall_golden_naming_a_missing_verse_is_invalid(fixture_db, monkeypatch):
    q = {**RECALL_Q, "golden": {"recall": {"min": 0.5, "ids": ["sblgnt:2JN.1.99"]}}}
    monkeypatch.setattr(evals, "load", lambda root: [q])
    [v] = evals.check_goldens(ROOT, fixture_db)
    assert v.rule == "golden-invalid" and "2JN.1.99" in v.reason
