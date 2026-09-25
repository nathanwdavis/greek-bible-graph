"""MACULA "lowfat" syntax trees -> sentences, word groups, per-token tree facts.

Lowfat nests ``book > sentence > wg* > w``: a word group (``wg``) carries a
class (clause, noun phrase, ...), a rule, and a role in its parent; a word
(``w``) is a token, identified by ``xml:id`` exactly as in the TSV.

Structural facts this parser relies on, measured over all 27 books:

* Every sentence has exactly one root node. In 8,009 of 8,010 it is a word
  group; in one it is a lone word. So "root" means root *node*, and a token
  can have no parent word group.
* Trees are deep -- up to 156 levels -- so the walk is iterative.
* Sentences and verses are independent hierarchies over the same tokens:
  Phlm 1:1-2 is one sentence, Phlm 1:20 is split across two. Verse
  membership is therefore taken from each word's own ``ref``; the
  ``<milestone>`` elements inside ``<p>`` are mis-placed (``PHM 1:2`` sits
  before Παῦλος) and are ignored along with the rest of ``<p>``.
* Tree order is not surface order (words are re-ordered into constituents;
  6,038 are marked ``discontinuous``). ``tree_ord`` records the former;
  surface order comes from the id.
* Word groups have no ids. They are minted as (leftmost token, depth) --
  see ``ids.wg_id`` -- and are build-local, never citable. Macula's own
  ``nodeId`` survives on a minority of groups and is kept as an attribute.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import ids
from .rows import FIELDS, clean

XML_ID = "{http://www.w3.org/XML/1998/namespace}id"

#: wg attribute -> our column. ``Rule`` (capitalised) appears on the groups
#: that also carry a ``nodeId``; it is the same field and is coalesced.
WG_ATTRS = {"class": "class", "rule": "rule", "Rule": "rule", "role": "role", "type": "type",
            "articular": "articular", "junction": "junction", "predication": "predication",
            "clauseType": "clause_type", "nodeId": "upstream_node_id"}
#: Tree-only token facts lowfat has and the TSV lacks.
W_TREE_ATTRS = {"discontinuous": "discontinuous", "rule": "rule", "junction": "junction"}



class LowfatError(ValueError):
    pass


@dataclass
class LowfatResult:
    sentences: list[dict] = field(default_factory=list)
    wgs: list[dict] = field(default_factory=list)
    #: xml_id -> tree facts for that token
    token_tree: dict[str, dict] = field(default_factory=dict)
    #: xml_id -> raw word record (same field names as the TSV); rows are built
    #: from these, and the TSV's copy is checked against them
    token_attrs: dict[str, dict] = field(default_factory=dict)
    dominance: list[tuple[str, str, int]] = field(default_factory=list)
    anomalies: Counter = field(default_factory=Counter)


def _walk_sentence(sentence: ET.Element, book: str, res: LowfatResult) -> None:
    roots = [c for c in sentence if c.tag in ("wg", "w")]
    if len(roots) != 1:
        raise LowfatError(f"{book}: a sentence has {len(roots)} root nodes, expected 1")

    # Pass 1: every word under each node, to find leftmost tokens (ids sort in
    # surface order: fixed-width digits).
    leftmost: dict[int, str] = {}
    words: list[ET.Element] = []

    def collect(el: ET.Element) -> str:
        stack = [(el, iter(el))]
        firsts: dict[int, str] = {}
        if el.tag == "w":
            words.append(el)
            return el.attrib[XML_ID]
        while stack:
            node, it = stack[-1]
            child = next(it, None)
            if child is None:
                stack.pop()
                first = firsts.get(id(node))
                if first is None:
                    raise LowfatError(f"{book}: empty word group")
                leftmost[id(node)] = first
                if stack:
                    parent = stack[-1][0]
                    if id(parent) not in firsts or first < firsts[id(parent)]:
                        firsts[id(parent)] = first
                continue
            if child.tag == "w":
                words.append(child)
                x = child.attrib.get(XML_ID)
                if not x:
                    raise LowfatError(f"{book}: a word without xml:id")
                if id(node) not in firsts or x < firsts[id(node)]:
                    firsts[id(node)] = x
            elif child.tag == "wg":
                stack.append((child, iter(child)))
            else:
                raise LowfatError(f"{book}: unexpected <{child.tag}> inside a word group")
        return leftmost[id(el)]

    first = collect(roots[0])
    sid = ids.sentence_id(first)
    root_wg = ids.wg_id(first, 0) if roots[0].tag == "wg" else None
    res.sentences.append({"id": sid, "book": book, "root_wg": root_wg})

    # Pass 2: preorder walk emitting groups, token tree facts and dominance.
    wg_ord = 0
    tok_ord = 0
    # stack items: (element, depth, parent_wg_id, ancestors[list of wg ids], child_ord)
    stack = [(roots[0], 0, None, [], 1)]
    while stack:
        el, depth, parent, ancestors, child_ord = stack.pop()
        if el.tag == "w":
            x = el.attrib[XML_ID]
            tok_ord += 1
            tree = {"sentence_id": sid, "parent_wg": parent, "depth": depth,
                    "child_ord": child_ord, "tree_ord": tok_ord,
                    "discontinuous": el.attrib.get("discontinuous") == "true"}
            for a, col in W_TREE_ATTRS.items():
                if col != "discontinuous":
                    tree[col] = el.attrib.get(a)
            if x in res.token_tree:
                raise LowfatError(f"{book}: token {x} appears twice in the trees")
            res.token_tree[x] = tree
            rec = {f: el.attrib.get(f) for f in FIELDS if f != "text"}
            rec["text"] = el.text
            res.token_attrs[x] = clean(rec)
            n = len(ancestors)
            for i, anc in enumerate(ancestors):
                res.dominance.append((anc, ids.token_id(x), n - i))
            continue
        wg_ord += 1
        wid = ids.wg_id(leftmost[id(el)], depth)
        row = {"id": wid, "sentence_id": sid, "parent_wg": parent, "depth": depth,
               "child_ord": child_ord, "tree_ord": wg_ord}
        for a, col in WG_ATTRS.items():
            v = el.attrib.get(a)
            if v is not None:
                if row.get(col) not in (None, v):
                    res.anomalies["wg.rule_and_Rule_disagree"] += 1
                row[col] = v
        for col in set(WG_ATTRS.values()):
            row.setdefault(col, None)
        if (row["role"] or "").startswith("err"):
            # Six SBLGNT groups carry an annotator's error note ("err__subordinated
            # simple cl., parent rule: ...") where the role belongs. Kept verbatim --
            # rewriting upstream data here would be a guess -- and counted, so the
            # manifest shows when upstream fixes them.
            res.anomalies["wg.role_is_upstream_error_note"] += 1
        res.wgs.append(row)
        kids = [c for c in el if c.tag in ("wg", "w")]
        # Push in reverse so the first child is processed first (preorder).
        for k, child in reversed(list(enumerate(kids, 1))):
            stack.append((child, depth + 1, wid, ancestors + [wid], k))


def parse_book(path: Path, res: LowfatResult | None = None) -> LowfatResult:
    res = res or LowfatResult()
    book = None
    for event, el in ET.iterparse(path, events=("start", "end")):
        if event == "start" and el.tag == "book":
            book = el.attrib.get("id")
            if not book:
                raise LowfatError(f"{path}: <book> without id")
        elif event == "end" and el.tag == "sentence":
            _walk_sentence(el, book, res)
            el.clear()
    return res


def parse(paths: list[Path]) -> LowfatResult:
    res = LowfatResult()
    for p in paths:
        parse_book(p, res)
    return res
