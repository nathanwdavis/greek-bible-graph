"""Deterministic, content-derived ids: minting and recognising them.

auto-zettel-skill mints ids from the clock (``YYYYMMDDHHMM``). That is right
for notes a person writes one at a time and wrong here twice over: a corpus
of 137,741 tokens would need 95 days of distinct minutes, and an id that
depends on *when* the build ran makes the build non-reproducible. Every id
below is a pure function of the pinned upstream data.

Two stability classes, and the difference matters to anyone citing:

* **Citable** -- book, verse, token, lemma. Stable across rebuilds and across
  upstream releases that do not renumber words. A zettel note may cite these.
* **Build-local** -- sentence and word-group ids. They are derived from the
  leftmost token a node covers (plus depth, for word groups), which is
  deterministic but moves when upstream re-brackets a clause. Tools render
  them and queries join on them; nothing should ever *cite* them.

The edition prefix is mandatory. MACULA's Nestle1904 uses the same
``n40001001001`` scheme for a different text, and the LXX will bring its own;
an unprefixed id would be a claim about no particular text.
"""

from __future__ import annotations

import re

EDITION = "sblgnt"

TOKEN_RE = re.compile(rf"^{EDITION}:n(\d{{2}})(\d{{3}})(\d{{3}})(\d{{3}})$")
VERSE_RE = re.compile(rf"^{EDITION}:([1-4A-Z][A-Z0-9]{{2}})\.(\d+)\.(\d+)$")
BOOK_RE = re.compile(rf"^{EDITION}:([1-4A-Z][A-Z0-9]{{2}})$")
SENTENCE_RE = re.compile(rf"^{EDITION}:s:n\d{{11}}$")
WG_RE = re.compile(rf"^{EDITION}:wg:n\d{{11}}\.\d+$")
LEMMA_RE = re.compile(r"^lemma:\S.*$")
#: MACULA's own token id, as it appears in xml:id and in referent lists.
XMLID_RE = re.compile(r"^n\d{11}$")
#: MACULA's sentinel for an implicit participant (an unexpressed subject or
#: frame argument). Not a token; see ``implicit`` on the edge tables.
IMPLICIT_XMLID = "n00000000000"

KINDS = {
    "token": TOKEN_RE, "verse": VERSE_RE, "book": BOOK_RE,
    "sentence": SENTENCE_RE, "wg": WG_RE, "lemma": LEMMA_RE,
}
CITABLE = ("token", "verse", "book", "lemma")


def token_id(xml_id: str) -> str:
    return f"{EDITION}:{xml_id}"


def verse_id(book: str, chapter: int, verse: int) -> str:
    return f"{EDITION}:{book}.{chapter}.{verse}"


def book_id(book: str) -> str:
    return f"{EDITION}:{book}"


def lemma_id(lemma_nfc: str) -> str:
    # Deliberately unprefixed by edition: the NT and (later) the LXX should
    # meet at the same lemma node wherever the NFC strings agree.
    return f"lemma:{lemma_nfc}"


def sentence_id(first_xml_id: str) -> str:
    return f"{EDITION}:s:{first_xml_id}"


def wg_id(first_xml_id: str, depth: int) -> str:
    # Two word groups at the same depth never share their leftmost token (they
    # would have to overlap), so (leftmost token, depth) is unique -- and an
    # upstream edit only renames groups inside the subtree it touched.
    return f"{EDITION}:wg:{first_xml_id}.{depth}"


def kind_of(ident: str) -> str | None:
    for kind, rx in KINDS.items():
        if rx.match(ident):
            return kind
    return None


def token_parts(ident: str) -> tuple[int, int, int, int]:
    """(book number, chapter, verse, word) from a token id."""
    m = TOKEN_RE.match(ident)
    if not m:
        raise ValueError(f"not a token id: {ident!r}")
    return tuple(int(g) for g in m.groups())  # type: ignore[return-value]
