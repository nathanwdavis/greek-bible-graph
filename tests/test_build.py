import json
import shutil
import subprocess
import sys

import duckdb
import pytest

from conftest import FIXTURE_LOCK, FIXTURES, ROOT, copy_fixture, replace_in
from gbg import manifest, store

TSV = "SBLGNT/tsv/macula-greek-SBLGNT.tsv"
PHM = "SBLGNT/lowfat/18-philemon.xml"


def q(db, sql, *params):
    con = duckdb.connect(str(db), read_only=True)
    try:
        return con.execute(sql, list(params)).fetchall()
    finally:
        con.close()


def test_counts(fixture_build):
    _, man = fixture_build
    rows = {k: v["rows"] for k, v in man["tables"].items()}
    assert rows["token"] == 798 and rows["book"] == 3 and rows["verse"] == 53


def test_anchor_facts(fixture_db):
    # Counted independently of this code: θεός is 2x in Philemon, 2x in 2 John,
    # 3x in 3 John.
    assert q(fixture_db, "SELECT book_id, count(*) FROM token WHERE lemma = 'θεός' "
                         "GROUP BY 1 ORDER BY 1") == [
        ("sblgnt:2JN", 2), ("sblgnt:3JN", 3), ("sblgnt:PHM", 2)]


def test_verse_text_reconstructs_spacing_and_elision(fixture_db):
    [(text,)] = q(fixture_db, "SELECT text FROM verse WHERE id = 'sblgnt:PHM.1.2'")
    assert "τῇ κατ’ οἶκόν σου ἐκκλησίᾳ·" in text
    assert not text.endswith(" ")


def test_verses_and_sentences_cross(fixture_db):
    # Phlm 1:1-2 is one sentence; Phlm 1:20 is split across two.
    assert q(fixture_db, "SELECT count(DISTINCT verse_id) FROM token WHERE sentence_id = "
                         "'sblgnt:s:n57001001001'") == [(2,)]
    assert q(fixture_db, "SELECT count(DISTINCT sentence_id) FROM token WHERE verse_id = "
                         "'sblgnt:PHM.1.20'") == [(2,)]


def test_implicit_participants_have_no_target(fixture_db):
    assert q(fixture_db, "SELECT count(*) FROM frame_arg WHERE implicit AND dst IS NULL") == [(11,)]
    assert q(fixture_db, "SELECT count(*) FROM frame_arg WHERE implicit <> (dst IS NULL)") == [(0,)]


def test_macros_are_stored_in_the_database(fixture_db):
    assert q(fixture_db, "SELECT gbg_key('Θεός')") == [("θεοσ",)]


def test_no_excluded_column_anywhere(fixture_db):
    cols = {c for (c,) in q(fixture_db, "SELECT column_name FROM information_schema.columns")}
    assert not cols & {"domain", "ln"}


def test_parquet_export(fixture_build):
    out, _ = fixture_build
    con = duckdb.connect()
    n = con.execute(f"SELECT count(*) FROM '{out / 'parquet' / 'token.parquet'}'").fetchone()
    assert n == (798,)


def test_build_is_deterministic(tmp_path, fixture_build):
    _, first = fixture_build
    second = store.build(FIXTURE_LOCK, ROOT, tmp_path / "b", log=lambda *_: None)
    assert manifest.serialize(first) == manifest.serialize(second)


def test_committed_fixture_manifest_matches():
    out = subprocess.run([sys.executable, "-m", "gbg", "build", "--check", "--lock",
                          str(FIXTURE_LOCK)], capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0, out.stdout + out.stderr


def test_check_exits_2_and_diffs_on_any_change(tmp_path):
    lock = copy_fixture(tmp_path, lambda d: replace_in(
        d / PHM, 'lemma="δέσμιος"', 'lemma="δεσμός"'))
    shutil.copy(FIXTURES / "build-manifest.json", tmp_path / "build-manifest.json")
    out = subprocess.run([sys.executable, "-m", "gbg", "build", "--check", "--lock", str(lock)],
                         capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 2
    assert "content_sha256" in out.stdout and "never hand-edit" in out.stderr


def test_tree_copy_wins_and_the_disagreement_is_counted(tmp_path):
    # Plant a TSV-only typo: the build must keep the tree's value and count it.
    def mutate(d):
        replace_in(d / TSV, "\t[the] house\t", "\t[the] hous\t")
    lock = copy_fixture(tmp_path, mutate)
    man = store.build(lock, ROOT, tmp_path / "b", log=lambda *_: None)
    assert man["anomalies"].get("tsv_lowfat_mismatch.gloss") == 1


def test_differing_coverage_is_fatal(tmp_path):
    def drop_last_row(d):
        p = d / TSV
        lines = p.read_text(encoding="utf-8").rstrip("\n").split("\n")
        p.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    lock = copy_fixture(tmp_path, drop_last_row)
    with pytest.raises(store.BuildError, match="cover different tokens"):
        store.build(lock, ROOT, tmp_path / "b", log=lambda *_: None)


def test_non_open_component_is_refused(tmp_path):
    lock = copy_fixture(tmp_path)
    data = json.loads(lock.read_text(encoding="utf-8"))
    data["sources"]["macula-greek"]["components"]["cherith"]["license"] = \
        "LicenseRef-UsedWithPermission"
    lock.write_text(json.dumps(data, ensure_ascii=False))
    with pytest.raises(store.BuildError, match="license-not-open"):
        store.build(lock, ROOT, tmp_path / "b", log=lambda *_: None)


def test_hash_mismatch_is_refused(tmp_path):
    lock = copy_fixture(tmp_path)
    replace_in(tmp_path / "macula" / PHM, "Παῦλος", "Σαῦλος")
    with pytest.raises(store.BuildError, match="sha256"):
        store.build(lock, ROOT, tmp_path / "b", log=lambda *_: None)


def test_refuses_to_replace_a_foreign_directory(tmp_path):
    victim = tmp_path / "notes"
    victim.mkdir()
    (victim / "important.md").write_text("do not delete")
    with pytest.raises(store.BuildError, match="refusing to replace"):
        store.build(FIXTURE_LOCK, ROOT, victim, log=lambda *_: None)
    assert (victim / "important.md").exists()


def test_referent_cycles_counts_distinct_cycles():
    e = lambda s, d: {"src": s, "dst": d, "ord": 1}  # noqa: E731
    assert store.referent_cycles([e("a", "b"), e("b", "a"), e("c", "a"), e("d", "d")]) == 2
    assert store.referent_cycles([e("a", "b"), e("b", "c")]) == 0
