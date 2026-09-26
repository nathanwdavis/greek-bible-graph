"""Shared fixtures. Grows with the build; see the fixture-DB fixtures below."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import hashlib
import json
import shutil

import pytest

FIXTURES = ROOT / "tests" / "fixtures"
FIXTURE_LOCK = FIXTURES / "fixture.lock.json"


def copy_fixture(dest: Path, mutate=None) -> Path:
    """Copy the fixture sources to ``dest``, optionally mutate them, re-hash the lock.

    ``mutate(macula_dir)`` edits files in place; the copied lock's sha256s are
    then recomputed so the build accepts the change and the test sees exactly
    the effect of the mutation -- auto-zettel-skill's "clean repo with exactly
    one thing broken" pattern, applied to source data.
    """
    lock = json.loads(FIXTURE_LOCK.read_text(encoding="utf-8"))
    for src in lock["sources"].values():
        shutil.copytree(FIXTURES / src["local_dir"], dest / src["local_dir"])
    if mutate:
        mutate(dest / "macula")
    for src in lock["sources"].values():
        for f in src["files"]:
            data = (dest / src["local_dir"] / f["path"]).read_bytes()
            f["sha256"] = hashlib.sha256(data).hexdigest()
            f["bytes"] = len(data)
    (dest / "fixture.lock.json").write_text(json.dumps(lock, ensure_ascii=False))
    return dest / "fixture.lock.json"


def replace_in(path: Path, old: str, new: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not in {path.name}"
    path.write_text(text.replace(old, new, count), encoding="utf-8")


@pytest.fixture(scope="session")
def fixture_build(tmp_path_factory):
    """The fixture, built once per session: (build dir, manifest)."""
    from gbg import store
    out = tmp_path_factory.mktemp("fixture") / "build"
    man = store.build(FIXTURE_LOCK, ROOT, out, log=lambda *_: None)
    return out, man


@pytest.fixture(scope="session")
def fixture_db(fixture_build):
    return fixture_build[0] / "gbg.duckdb"


@pytest.fixture
def db_copy(fixture_db, tmp_path):
    """A writable copy of the fixture database, for planting one violation."""
    dst = tmp_path / "gbg.duckdb"
    shutil.copy(fixture_db, dst)
    return dst
