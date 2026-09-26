"""gbg analysis: a clean analysis passes; each rule, planted alone, fires alone.

auto-zettel-skill's "clean artifact, break exactly one thing" pattern, applied
to the checked record of an interpretation.
"""

import copy

import duckdb
import pytest
import yaml

from conftest import ROOT
from gbg import analysis, cli


def fixture_build_id(fixture_db) -> str:
    con = duckdb.connect(str(fixture_db), read_only=True)
    try:
        return con.execute("SELECT value FROM meta WHERE key = 'build_id'").fetchone()[0]
    finally:
        con.close()


def clean(fixture_db) -> dict:
    return {
        "title": "Who loves in 2 and 3 John",
        "question": "Where in 2 and 3 John is the Elder the one who loves?",
        "build": fixture_build_id(fixture_db),
        "taxonomy": {"labels": {"L": "love is spoken of", "E": "the Elder is the lover"},
                     "implies": {"E": ["L"]}},
        "retrieval": [{"id": "love-verbs", "query": "predicate_participants",
                       "params": {"lemmas": "ἀγαπάω"}, "rows": 19,
                       "candidates": "predicate_id"}],
        "passages": [
            {"cite": "2 John 1", "ids": ["sblgnt:2JN.1.1"], "evidence": ["sblgnt:n63001001011"],
             "labels": ["E", "L"], "basis": "ἀγαπῶ: ἐγώ subject, refers to πρεσβύτερος.",
             "reading": "The Elder's own love for the elect lady."},
            {"cite": "3 John 1", "ids": ["sblgnt:3JN.1.1"], "evidence": ["sblgnt:n64001001008"],
             "labels": ["E", "L"], "basis": "ἀγαπῶ: ἐγώ subject, refers to πρεσβύτερος."},
        ],
        "rejected": [{"cite": "2 John 5", "ids": ["sblgnt:2JN.1.5"],
                      "reason": "we love one another: the community, not the Elder alone."}],
        "blind_spots": ["Only ἀγαπάω was searched; φιλέω and ἀγάπη were not."],
    }


def rules(tmp_path, fixture_db, a: dict) -> set[str]:
    p = tmp_path / "analysis.yaml"
    p.write_text(yaml.safe_dump(a, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {v.rule for v in analysis.check(p, fixture_db, ROOT)}


def test_clean_analysis_passes(tmp_path, fixture_db):
    assert rules(tmp_path, fixture_db, clean(fixture_db)) == set()


def _p0(a):
    return a["passages"][0]


PLANTS = {
    "build-stale": lambda a: a.update(build="0000000000000000"),
    "id-fabricated": lambda a: _p0(a)["evidence"].append("sblgnt:n63001001099"),
    "cite-unresolved": lambda a: _p0(a).update(cite="2 John 99"),
    "cite-mismatch": lambda a: _p0(a)["ids"].append("sblgnt:2JN.1.2"),
    "evidence-outside": lambda a: _p0(a).update(evidence=["sblgnt:n63001005018"]),
    "evidence-missing": lambda a: _p0(a).update(evidence=[]),
    "basis-missing": lambda a: _p0(a).update(basis=" "),
    "label-missing": lambda a: _p0(a).update(labels=[]),
    "label-unknown": lambda a: _p0(a)["labels"].append("Z"),
    "label-implies": lambda a: _p0(a).update(labels=["E"]),
    "reason-missing": lambda a: a["rejected"][0].update(reason=""),
    "retrieval-drift": lambda a: a["retrieval"][0].update(rows=18),
    "retrieval-invalid": lambda a: a["retrieval"][0].update(candidates="no_such_column"),
    "retrieval-truncated": lambda a: a["retrieval"].append(
        {"id": "big", "sql": "SELECT range AS n FROM range(10001)", "rows": 10000}),
    "candidate-unaccounted": lambda a: a.update(rejected=[]),
    "entry-malformed": lambda a: a["passages"].append("not a mapping"),
}


@pytest.mark.parametrize("rule", sorted(PLANTS))
def test_each_rule_fires_alone(tmp_path, fixture_db, rule):
    a = copy.deepcopy(clean(fixture_db))
    PLANTS[rule](a)
    assert rules(tmp_path, fixture_db, a) == {rule}


def test_every_rule_has_a_plant():
    import re
    src = (ROOT / "gbg" / "analysis.py").read_text(encoding="utf-8")
    assert set(re.findall(r'v\("([a-z-]+)"', src)) == set(PLANTS)


@pytest.mark.parametrize("bad,fragment", [
    ("- just a list\n", "mapping"),
    ("question: q\nbuild: b\ntaxonomy: {}\nretrieval: []\npassages: []\n", "taxonomy.labels"),
    ("question: q\n", "'build' must be"),
])
def test_not_an_analysis_is_a_usage_error(tmp_path, fixture_db, bad, fragment):
    p = tmp_path / "a.yaml"
    p.write_text(bad, encoding="utf-8")
    with pytest.raises(cli.UsageError, match=fragment):
        analysis.check(p, fixture_db, ROOT)


def test_render_shows_text_labels_and_rejections(tmp_path, fixture_db):
    p = tmp_path / "a.yaml"
    p.write_text(yaml.safe_dump(clean(fixture_db), allow_unicode=True), encoding="utf-8")
    md = analysis.render(p, fixture_db, ROOT)
    assert md.startswith("# Who loves in 2 and 3 John")
    assert "### 2 John 1 — E, L" in md and "`sblgnt:2JN.1.1`" in md
    assert "Ὁ πρεσβύτερος" in md                        # the Greek of 2 John 1
    assert "**Reading (interpretation):**" in md       # interpretation labelled as such
    assert "- **E** (2): 2 John 1; 3 John 1" in md
    assert "| 2 John 5 |" in md and "What this analysis cannot see" in md
    # passages come in canonical order whatever the file's order
    a = clean(fixture_db)
    a["passages"].reverse()
    p.write_text(yaml.safe_dump(a, allow_unicode=True), encoding="utf-8")
    md2 = analysis.render(p, fixture_db, ROOT)
    assert md2.index("### 2 John 1") < md2.index("### 3 John 1")
