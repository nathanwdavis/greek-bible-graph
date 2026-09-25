import json
import subprocess
import sys

import pytest

from conftest import ROOT
from gbg import db, refs, resolve


@pytest.fixture
def con(fixture_db):
    c = db.connect(fixture_db)
    yield c
    c.close()


def test_single_chapter_verse(con):
    r = resolve.resolve(con, "Phlm 10")
    assert r.found and r.verses == ["sblgnt:PHM.1.10"] and r.sbl == "Phlm 10"


def test_whole_book_and_ranges(con):
    assert len(resolve.resolve(con, "Phlm").verses) == 25
    assert resolve.resolve(con, "Phlm 1-3").verses == [f"sblgnt:PHM.1.{v}" for v in (1, 2, 3)]
    assert resolve.resolve(con, "2 John 12-13").verses == ["sblgnt:2JN.1.12", "sblgnt:2JN.1.13"]


def test_token_bounds(con):
    r = resolve.resolve(con, "Phlm 1-2")
    assert (r.first_token, r.last_token, r.n_tokens) == (
        "sblgnt:n57001001001", "sblgnt:n57001002015", 29)


def test_ids_resolve_in_reverse(con):
    r = resolve.resolve(con, "sblgnt:n57001010007")
    assert r.found and r.extra["surface"] == "ὃν" and r.extra["verse_id"] == "sblgnt:PHM.1.10"


def test_absent_is_not_an_error_but_not_found(con):
    assert not resolve.resolve(con, "Phlm 26").found
    r = resolve.resolve(con, "Rom 1:1")  # a real book, not in the fixture edition
    assert not r.found and "not in this edition" in r.missing[0]


def test_partial_verse_is_flagged(con):
    assert resolve.resolve(con, "Phlm 10a").partial


def test_lemma(con):
    r = resolve.resolve(con, "lemma:θεός")
    assert r.found and r.n_tokens == 7
    assert not resolve.resolve(con, "lemma:Ἰερουσαλήμ").found  # not in Phlm / 2-3 John


def test_malformed_raises(con):
    with pytest.raises(refs.RefError):
        resolve.resolve(con, "Jud 3")


@pytest.mark.parametrize("ref,code", [("Phlm 10", 0), ("Phlm 26", 1), ("Jud 3", 2)])
def test_cli_exit_codes(fixture_db, ref, code):
    out = subprocess.run([sys.executable, "-m", "gbg", "resolve", "--db", str(fixture_db), ref,
                          "--json"], capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == code, out.stdout + out.stderr
    if code == 0:
        data = json.loads(out.stdout)
        assert data["verses"] == ["sblgnt:PHM.1.10"] and data["build_id"]
