"""Topical indexes: the parsers step by step, the build against anchors read off
the raw fixture lines, and the counts of what cannot be placed.
"""

import io
import zipfile

import duckdb
import pytest

from conftest import ROOT, copy_fixture, replace_in
from gbg import parse_topics as pt
from gbg import queries, store


def naves(tmp_path, entry: str, subject: str = "TEST") -> pt.Topics:
    p = tmp_path / "n.csv"
    body = entry.replace('"', '""')
    p.write_text(f'section,subject,entry\nT,{subject},"{body}"\n', encoding="utf-8")
    return pt.parse_naves(p)


def spans(t: pt.Topics, topic: str):
    return [(s["book"], s["c1"], s["v1"], s["c2"], s["v2"]) for s in t.spans
            if s["topic"] == topic]


# --- Nave's parser -------------------------------------------------------------

def test_subtopics_nest_by_five_space_indent(tmp_path):
    t = naves(tmp_path, "-Appearances of\n     -To Adam GEN 3:8\n     -To Moses EXO 3:2\n-Other")
    assert [(x["id"], x["parent"], x["depth"], x["path"]) for x in t.topics] == [
        ("topic:naves:test", None, 0, "TEST"),
        ("topic:naves:test/1", "topic:naves:test", 1, "TEST > Appearances of"),
        ("topic:naves:test/2", "topic:naves:test/1", 2, "TEST > Appearances of > To Adam"),
        ("topic:naves:test/3", "topic:naves:test/1", 2, "TEST > Appearances of > To Moses"),
        ("topic:naves:test/4", "topic:naves:test", 1, "TEST > Other"),
    ]


def test_book_carries_across_semicolons(tmp_path):
    t = naves(tmp_path, "-X EXO 6:23,25; 1CH 6:3-15; 24")
    assert spans(t, "topic:naves:test/1") == [
        ("EXO", 6, 23, 6, 23), ("EXO", 6, 25, 6, 25), ("1CH", 6, 3, 6, 15),
        ("1CH", 24, None, 24, None)]


def test_a_reference_in_the_label_is_not_swallowed(tmp_path):
    # "OF" then "1SA": the digit is a lookahead, so 1SA is still found
    t = naves(tmp_path, "-FOREKNOWLEDGE OF 1SA 23:10-12; ACT 2:23")
    assert t.topics[1]["title"] == "FOREKNOWLEDGE OF"
    assert spans(t, "topic:naves:test/1") == [("1SA", 23, 10, 23, 12), ("ACT", 2, 23, 2, 23)]


def test_upstream_spellings_and_separators(tmp_path):
    # book names Jude / So, a "with" connective, and ". " between books
    t = naves(tmp_path, "-X 2PE 2:4; Jude 1:6; So 8:6; with 2KI 17; GAL 3:8. GEN 17:7")
    assert spans(t, "topic:naves:test/1") == [
        ("2PE", 2, 4, 2, 4), ("JUD", 1, 6, 1, 6), ("SNG", 8, 6, 8, 6),
        ("2KI", 17, None, 17, None), ("GAL", 3, 8, 3, 8), ("GEN", 17, 7, 17, 7)]
    assert not t.anomalies["naves.refs_malformed"]


def test_see_lines_and_malformed_refs_are_counted(tmp_path):
    t = naves(tmp_path, "-X HEB 1JHN 3:17\n-See GOD, OMNISCIENT")
    assert t.anomalies["naves.see_lines"] == 1
    assert t.anomalies["naves.refs_malformed"] == 1
    assert [x["title"] for x in t.topics] == ["TEST", "X"]


def test_a_truncated_cell_is_counted(tmp_path):
    t = naves(tmp_path, "-X HEB 4:13\n" + "-Y" * (pt.CELL_LIMIT // 2))
    assert t.anomalies["naves.entries_truncated"] == 1


# --- OpenBible parser ------------------------------------------------------------

def openbible(tmp_path, rows: list[str]) -> pt.Topics:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("topic-scores.txt", "Topic\tOSIS\tQuality Score\t# header\n"
                   + "".join(r + "\n" for r in rows))
    p = tmp_path / "t.zip"
    p.write_bytes(buf.getvalue())
    return pt.parse_openbible(p)


def test_openbible_ranges_votes_and_slugs(tmp_path):
    t = openbible(tmp_path, ["God's eyes\tHeb.4.13\t6", "God's eyes\tPs.139.1-Ps.139.4\t3",
                             "gods eyes\tMatt.10.30\t2", "x\tRom.8.28-Rom.9.1\t1",
                             "x\tPs.23\t1"])
    assert [x["id"] for x in t.topics] == [
        "topic:openbible:god-s-eyes", "topic:openbible:gods-eyes", "topic:openbible:x"]
    assert [(s["topic"], s["ord"], s["book"], s["c1"], s["v1"], s["c2"], s["v2"], s["votes"])
            for s in t.spans] == [
        ("topic:openbible:god-s-eyes", 1, "HEB", 4, 13, 4, 13, 6),
        ("topic:openbible:god-s-eyes", 2, "PSA", 139, 1, 139, 4, 3),
        ("topic:openbible:gods-eyes", 1, "MAT", 10, 30, 10, 30, 2),
        ("topic:openbible:x", 1, "ROM", 8, 28, 9, 1, 1),
        ("topic:openbible:x", 2, "PSA", 23, None, 23, None, 1)]


def test_openbible_slug_collisions_get_a_suffix_and_a_count(tmp_path):
    t = openbible(tmp_path, ["Faith!\tHeb.11.1\t1", "faith\tHeb.11.6\t1"])
    assert [x["id"] for x in t.topics] == ["topic:openbible:faith", "topic:openbible:faith-2"]
    assert t.anomalies["openbible.title_slug_collisions"] == 1


def test_openbible_malformed_rows_are_counted(tmp_path):
    t = openbible(tmp_path, ["a\tHeb.4.13-Rom.1.1\t1", "a\tNope.1.1\t1", "a\tHeb.4.13\tx",
                             "short"])
    assert t.anomalies["openbible.rows_malformed"] == 4 and t.spans == []


# --- the build, against lines read off the raw fixture ------------------------------

def run(db, name, **params):
    res = queries.run_saved(ROOT, db, name, {k: str(v) for k, v in params.items()},
                            limit=10_000)
    return [dict(zip(res.columns, r)) for r in res.rows]


def test_naves_anchor_onesimus(fixture_db):
    # raw: O,ONESIMUS,-A fugitive slave and subsequent convert of Paul COL 4:9; PHM 1:10
    rows = run(fixture_db, "topic_verses", topics="topic:naves:onesimus/1")
    assert [(r["verse_id"], r["ref"]) for r in rows] == [("sblgnt:PHM.1.10", "PHM 1:10")]
    rows = run(fixture_db, "topics_matching", pattern="^ONESIMUS")
    assert {r["topic"] for r in rows if r["source"] == "naves"} == {
        "ONESIMUS", "ONESIMUS > A fugitive slave and subsequent convert of Paul"}


def test_openbible_anchor_refreshing(fixture_db):
    # raw: 12 rows for "refreshing"; the only fixture book among them is Phlm.1.7 (2 votes)
    rows = run(fixture_db, "topic_verses", topics="topic:openbible:refreshing")
    assert [(r["verse_id"], r["votes"]) for r in rows] == [("sblgnt:PHM.1.7", 2)]


def test_verse_topics_lists_both_indexes(fixture_db):
    rows = run(fixture_db, "verse_topics", verses="Phlm 10; 2 John 9")
    assert {r["source"] for r in rows if r["verse_id"] == "sblgnt:2JN.1.9"} == {
        "naves", "openbible"}
    assert "topic:naves:onesimus/1" in {r["topic_id"] for r in rows
                                        if r["verse_id"] == "sblgnt:PHM.1.10"}


def test_unplaceable_spans_are_counted_not_loaded(tmp_path):
    # Plant a Philemon verse that does not exist (Philemon has 25) into a raw Nave's
    # line. No comma: the line is an unquoted CSV row.
    def mutate(macula):
        replace_in(macula.parent / "naves" / store.NAVES_PATH,
                   "convert of Paul COL 4:9; PHM 1:10", "convert of Paul COL 4:9; PHM 1:10; 1:26")
    lock = copy_fixture(tmp_path, mutate)
    man = store.build(lock, ROOT, tmp_path / "build", log=lambda *_: None)
    assert man["anomalies"]["naves.spans_verse_not_in_edition"] == 1
    con = duckdb.connect(str(tmp_path / "build" / "gbg.duckdb"), read_only=True)
    assert con.execute("SELECT list(dst) FROM naves_topic_verse WHERE src = "
                       "'topic:naves:onesimus/1'").fetchone()[0] == ["sblgnt:PHM.1.10"]


@pytest.mark.parametrize("name", ["naves", "openbible-topics"])
def test_topical_sources_are_open_and_attributed(name):
    from gbg import licenses, sources
    src = sources.load_lock(ROOT / "sources.lock.json").source(name)
    assert licenses.is_open(src.license) and all(licenses.is_open(c.license)
                                                 for c in src.components)
    assert src.attribution in (ROOT / "NOTICE.md").read_text(encoding="utf-8")
