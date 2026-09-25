import subprocess
import sys

from conftest import ROOT
from gbg import db, interlinear


def gbg(*args):
    return subprocess.run([sys.executable, "-m", "gbg", *args], capture_output=True, text=True,
                          cwd=ROOT)


def test_stacked_view(fixture_db):
    out = gbg("ref", "--db", str(fixture_db), "Phlm 2", "--width", "200")
    assert out.returncode == 0
    lines = out.stdout.splitlines()
    assert lines[0] == "PHM 1:2  (sblgnt:PHM.1.2)"
    assert "κατ’" in lines[1] and "οἶκόν" in lines[1] and lines[1].rstrip().endswith("ἐκκλησίᾳ·")
    assert "N-DSF" in lines[3]


def test_wrapping_respects_width(fixture_db):
    out = gbg("ref", "--db", str(fixture_db), "Phlm 1", "--width", "40")
    assert all(len(line) <= 40 for line in out.stdout.splitlines()[1:])


def test_word_range_as_rows(fixture_db):
    out = gbg("ref", "--db", str(fixture_db), "PHM 1:1!3-5", "--tsv")
    rows = out.stdout.strip().splitlines()
    assert rows[0].startswith("id\tref") and len(rows) == 4
    assert rows[1].split("\t")[:3] == ["sblgnt:n57001001003", "PHM 1:1!3", "Χριστοῦ"]


def test_tree_shows_both_sentences_of_phlm_20(fixture_db):
    out = gbg("ref", "--db", str(fixture_db), "Phlm 20", "--tree")
    assert out.stdout.count("sentence sblgnt:s:") == 2
    assert "role=s" in out.stdout


def test_missing_gloss_stays_blank(fixture_db):
    con = db.connect(fixture_db)
    try:
        rows, _ = interlinear.tokens(con, "3 John 15")
    finally:
        con.close()
    blank = [r for r in rows if r["gloss"] is None]
    assert blank, "fixture should contain a word with no Berean gloss"
    text = interlinear.render_stacked(rows, 400)
    assert "None" not in text


def test_absent_passage_exits_1(fixture_db):
    assert gbg("ref", "--db", str(fixture_db), "Phlm 30").returncode == 1
