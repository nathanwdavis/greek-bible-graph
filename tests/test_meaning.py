"""The meaning layers -- gloss terms and Clear proximity -- against the raw fixture.

Anchors are computed from the fixture's own files (the TSV and Proximity.tsv),
never from the build's SQL or the saved queries under test.
"""

import csv
from collections import Counter

import duckdb
import pytest

from conftest import FIXTURES, ROOT
from gbg import cli, english, queries

MACULA = FIXTURES / "macula"


def tsv_rows() -> list[dict]:
    with open(MACULA / "SBLGNT" / "tsv" / "macula-greek-SBLGNT.tsv", encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t", quoting=csv.QUOTE_NONE))


def proximity_rows() -> list[tuple[str, str, float]]:
    with open(MACULA / "sources" / "Clear" / "synonyms" / "Proximity.tsv",
              encoding="utf-8") as fh:
        r = csv.reader(fh, delimiter="\t", quoting=csv.QUOTE_NONE)
        next(r)
        return [(a, b, float(d)) for a, b, d in r]


def lemma_strongs() -> dict[str, set[str]]:
    """'G<number>' -> lemmas carrying it, from the raw TSV (NFC as upstream spells it)."""
    from gbg.greek import nfc
    out: dict[str, set[str]] = {}
    for r in tsv_rows():
        out.setdefault("G" + r["strong"], set()).add(nfc(r["lemma"]))
    return out


def run(fixture_db, name, **params):
    res = queries.run_saved(ROOT, fixture_db, name, {k: str(v) for k, v in params.items()},
                            limit=10_000)
    return [dict(zip(res.columns, r)) for r in res.rows]


# --- token.english_terms ---------------------------------------------------------

def test_english_terms_are_the_normalised_upstream_gloss(fixture_db):
    # The plumbing (staging, '|' join/split, NULL vs empty) must not change a term.
    want = {f"sblgnt:{r['xml:id']}": english.gloss_terms(r["english"] or None)
            for r in tsv_rows()}
    con = duckdb.connect(str(fixture_db), read_only=True)
    got = {i: (terms, neg or False) for i, terms, neg in
           con.execute("SELECT id, english_terms, english_negated FROM token").fetchall()}
    assert got == want


# --- lemma_proximity ------------------------------------------------------------------

def test_proximity_edges_are_every_mappable_greek_pair(fixture_db):
    ls = lemma_strongs()
    want = {(f"lemma:{x}", f"lemma:{y}", a, b, d)
            for a, b, d in proximity_rows() if a in ls and b in ls
            for x in ls[a] for y in ls[b]}
    con = duckdb.connect(str(fixture_db), read_only=True)
    got = set(con.execute("SELECT src, dst, src_strong, dst_strong, distance "
                          "FROM lemma_proximity").fetchall())
    assert got == want and len(want) > 0


def test_proximity_rows_it_cannot_load_are_counted(fixture_build):
    ls = lemma_strongs()
    rows = proximity_rows()
    greek = [(a, b) for a, b, _ in rows if a.startswith("G") and b.startswith("G")]
    an = fixture_build[1]["anomalies"]
    assert an["lemma_proximity.rows_not_greek"] == len(rows) - len(greek)
    assert an["lemma_proximity.rows_greek_unmapped"] == sum(
        1 for a, b in greek if a not in ls or b not in ls)
    assert an["lemma_proximity.self_pairs"] == sum(
        1 for a, b, _ in rows if a in ls and b in ls for x in ls[a] for y in ls[b] if x == y)


# --- saved queries ------------------------------------------------------------------

def test_lemmas_by_gloss_anchor(fixture_db):
    # Independent: which lemmas' Cherith glosses, normalised, contain "love"?
    want = Counter(r["lemma"] for r in tsv_rows()
                   if "love" in (english.gloss_terms(r["english"] or None)[0] or []))
    assert len(want) >= 2
    rows = run(fixture_db, "lemmas_by_gloss", words="loved")
    assert {r["lemma"]: r["n_matching"] for r in rows} == dict(want)
    assert all(r["matched_terms"] == ["love"] for r in rows)


def test_lemmas_by_gloss_scope_limits_matching_tokens(fixture_db):
    want = Counter(r["lemma"] for r in tsv_rows() if r["ref"].startswith("3JN")
                   and "love" in (english.gloss_terms(r["english"] or None)[0] or []))
    assert want
    rows = run(fixture_db, "lemmas_by_gloss", words="love", scope="3 John")
    assert {r["lemma"]: r["n_matching"] for r in rows} == dict(want)


def test_similar_lemmas_reads_both_directions(fixture_db):
    ls = lemma_strongs()
    target = "ἀγαπάω"
    mine = {s for s, lems in ls.items() if target in lems}
    want: dict[str, float] = {}
    for a, b, d in proximity_rows():
        for x, y in ((a, b), (b, a)):
            if x in mine and y in ls and d <= 0.8:
                for lem in ls[y] - {target}:
                    want[lem] = min(d, want.get(lem, 1.0))
    # ἀγαπητός ("beloved") shares no gloss term with ἀγαπάω: only proximity finds it.
    assert "ἀγαπητός" in want
    rows = run(fixture_db, "similar_lemmas", lemma=target)
    assert {r["lemma"]: r["distance"] for r in rows} == want
    assert [r["distance"] for r in rows] == sorted(r["distance"] for r in rows)


def test_english_param_refuses_only_stopwords(fixture_db):
    with pytest.raises(cli.UsageError, match="no content words"):
        run(fixture_db, "lemmas_by_gloss", words="the, of")
