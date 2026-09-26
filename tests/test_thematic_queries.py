"""predicate_participants, contrary_to_fact and hits_in_context against anchors
computed WITHOUT them: by walking the fixture's lowfat XML directly.
"""

import re
import xml.etree.ElementTree as ET

import duckdb
import pytest

from conftest import FIXTURES, ROOT
from gbg import queries

XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
LOWFAT = FIXTURES / "macula" / "SBLGNT" / "lowfat"
IMPLICIT = "n00000000000"


def run(db, name, **params):
    res = queries.run_saved(ROOT, db, name, {k: str(v) for k, v in params.items()},
                            limit=10_000)
    return [dict(zip(res.columns, r)) for r in res.rows]


class Trees:
    """An independent reading of the fixture trees: parents, words, first referents."""

    def __init__(self):
        self.parent, self.words = {}, {}
        for f in sorted(LOWFAT.glob("*.xml")):
            for el in ET.parse(f).getroot().iter():
                for ch in el:
                    self.parent[ch] = el
                if el.tag == "w":
                    self.words[el.get(XML_ID)] = el

    def descendants(self, el, depth=None):
        """Words under el, with their distance (1 = child)."""
        out, stack = [], [(el, 0)]
        while stack:
            node, d = stack.pop()
            for ch in node:
                if ch.tag == "w":
                    out.append((ch, d + 1))
                elif ch.tag == "wg" and (depth is None or d + 1 < depth):
                    stack.append((ch, d + 1))
        return out

    def terminal(self, xml_id):
        seen = [xml_id]
        while True:
            refs = (self.words[seen[-1]].get("referent") or "").split()
            if not refs or refs[0] in seen or refs[0] == IMPLICIT:
                return seen[-1]
            seen.append(refs[0])

    def clause(self, w):
        if w.get("role") == "v":
            return self.parent[w]
        node = self.parent.get(w)
        while node is not None and node.tag == "wg":
            if node.get("role") == "v":
                return self.parent[node]
            node = self.parent.get(node)
        return self.parent[w]

    def agents(self, w) -> set[tuple[str, str | None]]:
        """(signal, terminal referent xml:id or None for implicit), agent role.

        A passive verb's grammatical subject is its patient, so it is not an agent.
        """
        out = set()
        cl = self.clause(w)
        # passive in meaning: voice passive AND Robinson voice letter P (not a deponent)
        m = re.match(r"V-2?[A-Z]([A-Z])", w.get("morph") or "")
        active = not (w.get("voice") == "passive" and m and m.group(1) == "P")
        for ch in cl:
            if active and ch.tag == "wg" and ch.get("role") == "s":
                for x, _ in self.descendants(ch):
                    if x.get("case") == "nominative" and x.get("class") != "det":
                        out.add(("tree", self.terminal(x.get(XML_ID))))
            elif active and ch.tag == "w" and ch.get("role") == "s":
                out.add(("tree", self.terminal(ch.get(XML_ID))))
            elif not active and ch.tag == "wg" and ch.get("role") == "adv" and any(
                    x.tag == "w" and x.get("lemma") == "ὑπό" for x in ch):
                for x, _ in self.descendants(ch):
                    if x.get("case") == "genitive" and x.get("class") in ("noun", "pron"):
                        out.add(("by", self.terminal(x.get(XML_ID))))
        for t in (w.get("subjref") or "").split() if active else []:
            out.add(("subjref", None if t == IMPLICIT else self.terminal(t)))
        for part in (w.get("frame") or "").split():
            role, _, targets = part.partition(":")
            if role == "A0":
                for t in targets.split(";"):
                    out.add(("frame", None if t == IMPLICIT else self.terminal(t)))
        if w.get("class") == "noun":
            for x, d in self.descendants(self.parent[w], depth=2):
                if (d <= 2 and x is not w and x.get("case") == "genitive"
                        and x.get("class") in ("noun", "pron")):
                    out.add(("genitive", self.terminal(x.get(XML_ID))))
        return out


@pytest.fixture(scope="module")
def trees():
    return Trees()


@pytest.mark.parametrize("lemma", ["ἀγαπάω", "οἶδα", "γινώσκω", "ἀγάπη", "δέσμιος", "οἶκος"])
def test_predicate_participants_matches_the_xml(fixture_db, trees, lemma):
    want = {(f"sblgnt:{i}", sig, None if r is None else f"sblgnt:{r}")
            for i, w in trees.words.items() if w.get("lemma") == lemma
            for sig, r in trees.agents(w)}
    assert want, f"no anchor for {lemma}"
    got = {(r["predicate_id"], r["signal"], r["referent_id"])
           for r in run(fixture_db, "predicate_participants", lemmas=lemma)}
    assert got == want


def test_predicate_participants_referents_filter_keeps_implicit(fixture_db):
    every = run(fixture_db, "predicate_participants", lemmas="γινώσκω, ἀγαπάω")
    kept = run(fixture_db, "predicate_participants", lemmas="γινώσκω, ἀγαπάω",
               referents="πρεσβύτερος")
    assert kept == [r for r in every
                    if r["referent_id"] is None or r["referent_lemma"] == "πρεσβύτερος"]
    assert any(r["implicit"] for r in kept) and any(r["referent_id"] for r in kept)


def test_predicate_participants_agree_counts_signals(fixture_db):
    rows = run(fixture_db, "predicate_participants", lemmas="ἀγαπάω", scope="3 John")
    # 3 John 1: ἀγαπῶ with ἐγώ written out (tree) and A0 (frame), both -> the Elder.
    assert {(r["signal"], r["referent"], r["agree"]) for r in rows} == {
        ("tree", "πρεσβύτερος", 2), ("frame", "πρεσβύτερος", 2)}


def test_hits_in_context_groups_hits_by_sentence(fixture_db):
    rows = run(fixture_db, "hits_in_context",
               tokens="PHM 1:20!5, sblgnt:n57001020008, 3JN 1:1!8")
    # Phlm 20 is split across two sentences (the fixture's own anchor), so two
    # hits in one verse give two passages; 3 John 1 gives a third.
    assert [(r["first_verse"], r["last_verse"], r["hit_verses"]) for r in rows] == [
        ("sblgnt:PHM.1.20", "sblgnt:PHM.1.20", ["sblgnt:PHM.1.20"]),
        ("sblgnt:PHM.1.20", "sblgnt:PHM.1.20", ["sblgnt:PHM.1.20"]),
        ("sblgnt:3JN.1.1", "sblgnt:3JN.1.1", ["sblgnt:3JN.1.1"]),
    ]
    assert rows[0]["greek"].startswith("ναί")
    con = duckdb.connect(str(fixture_db), read_only=True)
    n = con.execute("SELECT count(*) FROM token WHERE sentence_id = "
                    "(SELECT sentence_id FROM token WHERE ref = 'PHM 1:20!5')").fetchone()[0]
    assert len(rows[0]["english"].split(" ")) >= n  # one gloss (or ·) per word, in order


def test_contrary_to_fact_finds_none_in_the_fixture(fixture_db):
    # Philemon and the Johannine letters have no εἰ + past indicative ... ἄν
    # (checked by reading; ἄν occurs nowhere in the fixture at all).
    assert not any(w.get("lemma") == "ἄν" for w in Trees().words.values())
    assert run(fixture_db, "contrary_to_fact") == []
