"""Every skill stays portable and discoverable -- copied from auto-zettel-skill.

A frontmatter field outside the six portable Agent Skills fields fails
validation on packaging and upload, so a skill that drifts is one nobody can
install. The other rules catch a skill that exists but never triggers.
"""

from pathlib import Path

import pytest
import yaml

from conftest import ROOT

SKILLS_DIR = ROOT / "skills"
PORTABLE_FIELDS = {"name", "description", "license", "compatibility", "metadata",
                   "allowed-tools"}
DESCRIPTION_CAP = 1024
BODY_LINE_CAP = 500


def skill_dirs() -> list[Path]:
    return sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir())


def load(path: Path):
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    _, raw, body = text.split("---\n", 2)
    return yaml.safe_load(raw), body


@pytest.mark.parametrize("d", skill_dirs(), ids=lambda p: p.name)
def test_frontmatter(d):
    meta, body = load(d / "SKILL.md")
    assert not set(meta) - PORTABLE_FIELDS
    assert meta["name"] == d.name
    desc = meta["description"]
    assert 0 < len(desc) <= DESCRIPTION_CAP and "<" not in desc and ">" not in desc
    assert "Use when" in desc
    tools = [t.strip() for t in str(meta["allowed-tools"]).split(",") if t.strip()]
    assert tools and all(t[0].isupper() and "_" not in t for t in tools)
    assert "$ARGUMENTS" in body
    assert len(body.splitlines()) <= BODY_LINE_CAP


def test_skill_commands_exist():
    # A skill that names a subcommand the CLI does not have is a skill that fails
    # on its first step.
    from gbg.cli import COMMANDS
    names = {c[0] for c in COMMANDS}
    _, body = load(SKILLS_DIR / "gbg-query" / "SKILL.md")
    import re
    used = set(re.findall(r"\bgbg (\w+)", body))
    assert used <= names, used - names


def test_saved_queries_named_by_the_skill_exist():
    from gbg import queries
    _, body = load(SKILLS_DIR / "gbg-query" / "SKILL.md")
    for name in ("lemma_occurrences",):
        assert name in body and name in queries.load_all(ROOT)
