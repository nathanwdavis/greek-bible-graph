"""Saved queries, held to anchor facts computed WITHOUT this code.

A golden that is simply the query's own earlier output can be regenerated to
match anything. So each anchor below is derived independently -- by walking
the fixture's lowfat XML directly, or from facts about the Greek text -- and
the query must agree with it.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

import duckdb
import pytest

from conftest import FIXTURES, ROOT
from gbg import db, queries

XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
LOWFAT = FIXTURES / "macula" / "SBLGNT" / "lowfat"


def run(fixture_db, name, **params):
    res = queries.run_saved(ROOT, fixture_db, name, {k: str(v) for k, v in params.items()},
                            limit=10_000)
    return [dict(zip(res.columns, r)) for r in res.rows]


def xml_sentences(book_file: str) -> list[list[dict]]:
    """Independent reading of the fixture: sentences as lists of word attrs."""
    root = ET.parse(LOWFAT / book_file).getroot()
    out = []
    for s in root.iter("sentence"):
        words = [dict(w.attrib, id=w.attrib[XML_ID]) for w in s.iter("w")]
        out.append(sorted(words, key=lambda w: w["id"]))
    return out


def test_every_saved_query_has_a_valid_header():
    saved = queries.load_all(ROOT)
    assert {"lemma_occurrences", "lemma_by_book", "subject_lemma_tree",
            "subject_lemma_subjref", "referent_chain", "frame_args",
            "shared_lemma_trigrams", "verses_split_across_sentences"} <= set(saved)
    for s in saved.values():
        assert s.description and s.cites and s.sql


def test_lemma_occurrences_anchor(fixture_db):
    rows = run(fixture_db, "lemma_occurrences", lemma="θεός", scope="Phlm")
    assert [r["ref"] for r in rows] == ["PHM 1:3!6", "PHM 1:4!3"]


def test_lemma_param_is_nfc_normalised(fixture_db):
    # θε + U+1F79 (omicron with oxia) is how some keyboards type θεός.
    assert len(run(fixture_db, "lemma_occurrences", lemma="θεός")) == 7


def test_lemma_by_book_anchor(fixture_db):
    rows = run(fixture_db, "lemma_by_book", lemma="θεός")
    assert [(r["book_id"], r["n"]) for r in rows] == [
        ("sblgnt:PHM", 2), ("sblgnt:2JN", 2), ("sblgnt:3JN", 3)]


def test_shared_trigrams_match_an_independent_count(fixture_db):
    def trigrams(book_file):
        grams = set()
        for words in xml_sentences(book_file):
            lemmas = [w["lemma"] for w in words]
            grams |= {tuple(lemmas[i:i + 3]) for i in range(len(lemmas) - 2)}
        return grams
    expected = trigrams("24-2john.xml") & trigrams("25-3john.xml")
    rows = run(fixture_db, "shared_lemma_trigrams", a="2 John", b="3 John")
    assert {tuple(r["trigram"].split()) for r in rows} == expected
    assert ("στόμα", "πρός", "στόμα") in expected and len(expected) == 8


def test_verses_split_across_sentences_matches_the_xml(fixture_db):
    per_verse: dict[str, set[int]] = {}
    for i, words in enumerate(xml_sentences("18-philemon.xml")):
        for w in words:
            per_verse.setdefault(w["ref"].split("!")[0], set()).add(i)
    expected = sorted(v for v, s in per_verse.items() if len(s) > 1)
    rows = run(fixture_db, "verses_split_across_sentences", scope="Phlm")
    assert [r["verse_id"] for r in rows] == ["sblgnt:" + v.replace(" ", ".").replace(":", ".")
                                              for v in expected] == ["sblgnt:PHM.1.20"]


def test_subject_tree_vs_subjref_answer_different_questions(fixture_db):
    tree = run(fixture_db, "subject_lemma_tree", lemma="ἐγώ", scope="Phlm")
    # Phlm 20: ἐγώ σου ὀναίμην -- ἐγώ is the grammatical subject of ὀναίμην.
    assert {"verb_id": "sblgnt:n57001020005", "subject_id": "sblgnt:n57001020003"}.items() <= \
        next(r for r in tree if r["verb_id"] == "sblgnt:n57001020005").items()
    coref = run(fixture_db, "subject_lemma_subjref", lemma="Παῦλος")
    # Phlm 4 Εὐχαριστῶ: its subject is not in the verse at all -- it is Παῦλος in 1:1.
    first = coref[0]
    assert (first["verb_ref"], first["subject_ref"]) == ("PHM 1:4!1", "PHM 1:1!1")
    assert any(r["verb_ref"].split("!")[0] != r["subject_ref"].split("!")[0] for r in coref)


def test_frame_args_anchor(fixture_db):
    rows = run(fixture_db, "frame_args", verb_lemma="ἀγαπάω", scope="3 John")
    # 3 John 1: ὃν ἐγὼ ἀγαπῶ -- the lover (A0) is ἐγώ.
    assert [(r["predicate_ref"], r["argument"]) for r in rows] == [("3JN 1:1!8", "ἐγὼ")]


def test_referent_chain_terminates_on_a_cycle(db_copy):
    a, b = "sblgnt:n57001001001", "sblgnt:n57001001002"
    con = duckdb.connect(str(db_copy))
    con.execute("DELETE FROM refers_to WHERE src IN (?, ?)", [a, b])
    con.execute("INSERT INTO refers_to VALUES (?, ?, false, 1, 'data', NULL, 'test'), "
                "(?, ?, false, 1, 'data', NULL, 'test')", [a, b, b, a])
    con.close()
    rows = run(db_copy, "referent_chain", token=a)
    assert [r["id"] for r in rows] == [a, b]


def test_referent_chain_accepts_a_macula_ref(fixture_db):
    rows = run(fixture_db, "referent_chain", token="PHM 1:12!3")
    assert rows[0]["id"] == "sblgnt:n57001012003" and len(rows) >= 2


@pytest.mark.parametrize("name,params,fragment", [
    ("lemma_occurrences", {}, "is required"),
    ("lemma_occurrences", {"lemma": "θεός", "bogus": "1"}, "unknown parameter"),
    ("lemma_occurrences", {"lemma": "θεός", "scope": "Jud 3"}, "ambiguous"),
    ("lemma_occurrences", {"lemma": "θεός", "scope": "Rom 1"}, "not in this edition"),
    ("referent_chain", {"token": "Phlm 12"}, "not a single word"),
    ("nope", {}, "no saved query"),
])
def test_parameter_errors_are_usage_errors(fixture_db, name, params, fragment):
    with pytest.raises(queries.cli.UsageError, match=fragment):
        queries.run_saved(ROOT, fixture_db, name, params)


# --- SQL/PGQ twins -----------------------------------------------------------------

pgq = pytest.mark.skipif(not db.pgq_available(), reason="DuckPGQ extension unavailable")


@pgq
@pytest.mark.pgq
@pytest.mark.parametrize("name,params,keep", [
    ("frame_args", {"verb_lemma": "ἀγαπάω"}, lambda r: not r["implicit"]),
    ("frame_args", {"verb_lemma": "λέγω", "role": "A1"}, lambda r: not r["implicit"]),
    ("subject_lemma_subjref", {"lemma": "Παῦλος"}, lambda r: True),
])
def test_pgq_twin_matches_sql(fixture_db, name, params, keep):
    sql_rows = [r for r in run(fixture_db, name, **params) if keep(r)]
    res = queries.run_saved(ROOT, fixture_db, name, params, pgq=True, limit=10_000)
    pgq_rows = [dict(zip(res.columns, r)) for r in res.rows]
    assert pgq_rows == sql_rows and pgq_rows
