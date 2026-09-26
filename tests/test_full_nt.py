"""The full SBLGNT from the pinned upstream. Run with ``pytest -m network``.

Downloads ~134 MB into cache/ on first run (then served from the cache), and
builds in ~30 s. The committed root build-manifest.json is what this proves
the build still reproduces.
"""

import subprocess
import sys

import duckdb
import pytest

from conftest import ROOT
from gbg import sources, store

pytestmark = pytest.mark.network


@pytest.fixture(scope="module")
def nt_build(tmp_path_factory):
    lock = sources.load_lock(ROOT / "sources.lock.json")
    problems = sources.fetch(lock, ROOT, log=lambda *_: None)
    assert problems == []
    out = tmp_path_factory.mktemp("nt") / "build"
    man = store.build(ROOT / "sources.lock.json", ROOT, out, log=lambda *_: None)
    return out, man


def test_counts(nt_build):
    _, man = nt_build
    rows = {k: v["rows"] for k, v in man["tables"].items()}
    assert rows["token"] == 137741
    assert rows["book"] == 27
    assert rows["verse"] == 7939
    assert rows["sentence"] == 8010
    assert rows["lemma"] == 5468
    assert man["anomalies"]["frame_arg.implicit"] == 1891


def test_pericope_adulterae_present(nt_build):
    out, _ = nt_build
    con = duckdb.connect(str(out / "gbg.duckdb"), read_only=True)
    assert con.execute("SELECT count(*) FROM verse WHERE book_id = 'sblgnt:JHN' AND "
                       "chapter = 8 AND verse BETWEEN 1 AND 11").fetchone() == (11,)


def test_committed_root_manifest_matches(nt_build):
    out = subprocess.run([sys.executable, "-m", "gbg", "build", "--check"],
                         capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0, out.stdout[-2000:] + out.stderr


def test_know_concept_spans_the_knowing_lemmas(nt_build):
    # Anchor from the raw upstream TSV, not the build: every lemma with a word
    # whose Cherith gloss normalises to "know" (gbg.english is tested apart).
    import csv
    from gbg import english, queries
    from gbg.greek import nfc
    tsv = ROOT / "cache" / "macula-greek" / sources.load_lock(
        ROOT / "sources.lock.json").source("macula-greek").commit / store.TSV_PATH
    with open(tsv, encoding="utf-8") as fh:
        want = {nfc(r["lemma"]) for r in csv.DictReader(fh, delimiter="\t",
                                                          quoting=csv.QUOTE_NONE)
                if "know" in (english.gloss_terms(r["english"] or None)[0] or [])}
    # The lemmas a reader would name, from the Greek itself:
    assert {"οἶδα", "γινώσκω", "ἐπιγινώσκω", "ἐπίσταμαι", "γνωρίζω", "προγινώσκω",
            "ἀγνοέω", "καρδιογνώστης"} <= want
    res = queries.run_saved(ROOT, nt_build[0] / "gbg.duckdb", "lemmas_by_gloss",
                            {"words": "know"}, limit=10_000)
    assert {r[res.columns.index("lemma")] for r in res.rows} == want


def test_proximity_neighbours_of_ginosko(nt_build):
    # From the upstream file alone: G1097's Greek neighbours within 0.45. (Upstream
    # also pairs it with Hebrew numbers -- H3045 is yada, "know" -- which the NT
    # build counts rather than loads.)
    import csv
    from gbg import queries
    path = ROOT / "cache" / "macula-greek" / sources.load_lock(
        ROOT / "sources.lock.json").source("macula-greek").commit / store.PROXIMITY_PATH
    with open(path, encoding="utf-8") as fh:
        pairs = [(a, b, float(d)) for a, b, d in list(csv.reader(fh, delimiter="\t"))[1:]]
    near = {b if a == "G1097" else a for a, b, d in pairs if "G1097" in (a, b) and d <= 0.45}
    near = {n for n in near if n.startswith("G")}
    assert near == {"G1921", "G1492", "G1922", "G1987", "G50", "G4267", "G3539"}
    res = queries.run_saved(ROOT, nt_build[0] / "gbg.duckdb", "similar_lemmas",
                            {"lemma": "γινώσκω", "max_distance": "0.45"}, limit=10_000)
    # G1492 is carried by οἶδα and ὁράω, so seven numbers give eight lemmas.
    assert {r[res.columns.index("lemma")] for r in res.rows} == {
        "ἐπιγινώσκω", "οἶδα", "ὁράω", "ἐπίγνωσις", "ἐπίσταμαι", "ἀγνοέω", "προγινώσκω", "νοέω"}


def test_contrary_to_fact_textbook_cases(nt_build):
    # Anchors from the grammars, not from the query: second-class conditionals
    # every NT grammar cites. Plus the two shapes the query documents it misses.
    from gbg import queries
    res = queries.run_saved(ROOT, nt_build[0] / "gbg.duckdb", "contrary_to_fact", {},
                            limit=10_000)
    verses = {r[res.columns.index("verse_id")] for r in res.rows}
    assert {f"sblgnt:{v}" for v in (
        "MAT.11.21", "MAT.11.23", "MRK.13.20", "LUK.7.39", "JHN.5.46", "JHN.8.42",
        "JHN.11.21", "JHN.18.36", "1CO.2.8", "GAL.1.10", "HEB.4.8", "HEB.11.15")} <= verses
    assert "sblgnt:JHN.14.2" not in verses   # elided protasis (εἰ δὲ μή)
    assert "sblgnt:LUK.17.6" not in verses   # mixed: present protasis


def test_exception_signal_on_the_no_one_knows_texts(nt_build):
    from gbg import queries
    res = queries.run_saved(ROOT, nt_build[0] / "gbg.duckdb", "predicate_participants",
                            {"lemmas": "οἶδα, γινώσκω, ἐπιγινώσκω"}, limit=10_000)
    rows = [dict(zip(res.columns, r)) for r in res.rows]
    exc = {(r["predicate_ref"], r["referent_lemma"]) for r in rows if r["signal"] == "exception"}
    # "no one knows ... except the Father / the Son / the Spirit of God" -- read off the text
    assert {("MRK 13:32!10", "πατήρ"), ("MAT 24:36!9", "πατήρ"), ("MAT 11:27!10", "πατήρ"),
            ("MAT 11:27!21", "υἱός"), ("1CO 2:11!23", "πνεῦμα")} <= exc
    assert any(r["predicate_ref"] == "MRK 13:32!10" and r["negated"] for r in rows)
    # Known miss, documented in the query: upstream attaches Luke 10:22's εἰ μή clause
    # inside the object clause. If this starts passing, update the query's header.
    assert not any(ref.startswith("LUK 10:22") for ref, _ in exc)


def test_voice_decides_agent_and_patient(nt_build):
    # From the text: "known by God" -- God is the agent, in the ὑπό phrase.
    from gbg import queries
    db = nt_build[0] / "gbg.duckdb"

    def rows(**params):
        res = queries.run_saved(ROOT, db, "predicate_participants", params, limit=10_000)
        return [dict(zip(res.columns, r)) for r in res.rows]
    assert {(r["signal"], r["referent_lemma"]) for r in rows(lemmas="γινώσκω",
            scope="1 Cor 8:3")} == {("by", "θεός")}
    assert ("by", "θεός") in {(r["signal"], r["referent_lemma"])
                              for r in rows(lemmas="γινώσκω", scope="Gal 4:9")}
    # 1 Pet 1:20 προεγνωσμένου (passive): Christ is the one foreknown, not the knower.
    assert not any(r["referent_lemma"] == "Χριστός" and r["signal"] != "frame"
                   for r in rows(lemmas="προγινώσκω", scope="1 Pet 1:20"))
    assert any(r["referent_lemma"] == "Χριστός"
               for r in rows(lemmas="προγινώσκω", scope="1 Pet 1:20", role="patient"))
    # Rom 11:34 "who has known the mind of the Lord?" -- a denial in question form
    assert all(r["question"] for r in rows(lemmas="γινώσκω", scope="Rom 11:34"))
    assert not any(r["question"] for r in rows(lemmas="γινώσκω", scope="1 Cor 8:3"))
    # Rev 19:12 "a name no one knows except he himself": a lone-word exception
    assert any(r["signal"] == "exception" for r in rows(lemmas="οἶδα", scope="Rev 19:12"))
    # εἰδώς is lemmatised under ὁράω; the gloss filter takes only its "know" sense
    know = rows(lemmas="ὁράω", words="know", scope="John 13")
    assert {r["predicate_ref"] for r in know} >= {"JHN 13:1!7", "JHN 13:3!1"}
    assert all(r["predicate"].startswith("εἰδ") for r in know)
