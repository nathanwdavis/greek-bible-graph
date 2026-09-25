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
