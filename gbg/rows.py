"""Raw MACULA word records -> token rows, many-to-many edges, anomaly counts.

MACULA publishes every word twice: as a row of the flat TSV, and as a ``<w>``
element of the lowfat trees, with the same field names. The build reads both,
builds rows from the TREE copy, and uses the TSV as an independent cross-check
(``store.agreement``). Over the full SBLGNT the two disagree on 19 fields, and
on every one that can be adjudicated the tree copy is right: the TSV glues
punctuation into seven words (``εἰσιν;;``, ``ἀλλ’·``, ``ἐπ᾿`` with a bare-space
``after``, where ~18,000 other rows put it in ``after``), misspells one gloss
("minster"), and drops one word's role. The disagreements are pinned in the
manifest, so a new upstream commit that changes them is a reviewed diff.

Three details here have each cost someone a day elsewhere:

* ``subjref`` / ``referent`` are space-separated id lists, and ``frame`` is
  ``ROLE:id;id ROLE:id`` -- whitespace between roles, ``;`` between the ids
  filling one role. ``n00000000000`` is MACULA's sentinel for an implicit
  participant (an unexpressed argument), not a token: it becomes an edge with
  ``implicit = true`` and a NULL target, never a dangling reference.
* ``subjref`` is COREFERENCE -- the resolved referent of a verb's subject --
  not the syntactic subject. Most of its targets sit outside the verb's
  verse. The syntactic subject lives in the tree (``wg/@role = 's'``). The
  edge is therefore named ``has_subject``, and the schema doc warns about it.
* An empty attribute (``english=""``) and an empty TSV cell are the same
  absence. Both become ``None`` before anything compares them.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from . import books, ids
from .greek import nfc

#: Upstream field -> our column. Upstream names are shared by TSV and lowfat;
#: ``text`` is the TSV column and the ``<w>`` element's text.
COLUMNS = {
    "ref": "ref", "role": "role", "class": "pos", "type": "type",
    "english": "english", "gloss": "gloss", "text": "surface", "after": "after",
    "lemma": "lemma", "normalized": "normalized", "strong": "strong", "morph": "morph",
    "person": "person", "number": "number", "gender": "gender", "case": "gcase",
    "tense": "tense", "voice": "voice", "mood": "mood", "degree": "degree",
}
#: Fields that become edges rather than token attributes.
EDGE_FIELDS = ("frame", "subjref", "referent")
#: Every field a raw word record carries (what the two sources are compared on).
FIELDS = (*COLUMNS, *EDGE_FIELDS)
#: Identity strings: stored NFC, compared NFC.
NFC_FIELDS = ("text", "lemma", "normalized")


@dataclass
class Rows:
    tokens: list[dict] = field(default_factory=list)
    refers_to: list[dict] = field(default_factory=list)
    has_subject: list[dict] = field(default_factory=list)
    frame_arg: list[dict] = field(default_factory=list)
    anomalies: Counter = field(default_factory=Counter)


def clean(record: dict) -> dict:
    """Empty -> None; identity strings stay as written (NFC happens in build)."""
    return {f: (record.get(f) or None) for f in FIELDS}


def _edge(src: str, target: str, ordinal: int, anomalies: Counter, kind: str, **extra) -> dict:
    implicit = target == ids.IMPLICIT_XMLID
    if not implicit and not ids.XMLID_RE.match(target):
        anomalies[f"{kind}.malformed_target"] += 1
    dst = None if implicit else ids.token_id(target)
    if dst == src:
        anomalies[f"{kind}.self_reference"] += 1
    if implicit:
        anomalies[f"{kind}.implicit"] += 1
    return {"src": src, "dst": dst, "implicit": implicit, "ord": ordinal,
            "tier": "data", "confidence": None, "source": "macula-greek", **extra}


def build(records: dict[str, dict]) -> Rows:
    """Token and edge rows from ``xml_id -> raw record``, in id (surface) order."""
    res = Rows()
    for xml_id in sorted(records):
        raw = records[xml_id]
        if not ids.XMLID_RE.match(xml_id):
            raise ValueError(f"bad xml:id {xml_id!r}")
        tok = {ours: raw.get(up) for up, ours in COLUMNS.items()}
        for up in NFC_FIELDS:
            ours = COLUMNS[up]
            v = tok[ours]
            if v is not None and nfc(v) != v:
                res.anomalies[f"input_not_nfc.{up}"] += 1
                tok[ours] = nfc(v)
        book = books.NT_BY_NUM.get(int(xml_id[1:3]))
        if book is None:
            raise ValueError(f"{xml_id}: book number is not an NT book")
        tid = ids.token_id(xml_id)
        tok.update(id=tid, xml_id=xml_id, book=book.code, chapter=int(xml_id[3:6]),
                   verse=int(xml_id[6:9]), word=int(xml_id[9:12]))
        res.tokens.append(tok)

        for n, t in enumerate((raw.get("referent") or "").split(), 1):
            res.refers_to.append(_edge(tid, t, n, res.anomalies, "refers_to"))
        for n, t in enumerate((raw.get("subjref") or "").split(), 1):
            res.has_subject.append(_edge(tid, t, n, res.anomalies, "has_subject"))
        n = 0
        for part in (raw.get("frame") or "").split():
            role, sep, targets = part.partition(":")
            if not sep or not role:
                res.anomalies["frame_arg.malformed"] += 1
                continue
            if not targets:
                # Upstream names a role with no filler ("A2:"): twice in the
                # SBLGNT. Counted, not invented.
                res.anomalies["frame_arg.empty_role"] += 1
                continue
            for t in targets.split(";"):
                n += 1
                res.frame_arg.append(_edge(tid, t, n, res.anomalies, "frame_arg",
                                           arg_role=role))
    return res
