"""Topical indexes -> topic rows and reference spans.

Gloss terms and synonym distances find passages that USE a concept's words;
neither finds one that is about the concept in other words ("all things are
naked and laid bare to his eyes", Heb 4:13). Human topical indexes do, so two
are loaded, each as its own source with its own license and anomaly counts:

* **Nave's Topical Bible** (1896), as BibleData's CSV: ``section, subject,
  entry``. An entry is lines of ``-subtopic REFS``, nested by indentation (five
  spaces a level), with references in upper-case book codes and chapter
  carry-over (``EXO 6:23,25; 1CH 6:3-15,50-53; 24``). ``-See X`` lines are
  cross-references to other topics, counted rather than followed.
* **OpenBible.info topics**: ``Topic, OSIS range, votes``, flat, from readers'
  votes -- broad and noisy, so the score is kept on every edge.

Nothing here decides what is in this edition: references are parsed into
spans, and the build resolves them against the verse table in SQL, counting
what it cannot place (Old Testament, not in the SBLGNT, malformed).
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import books, refs

NAVES_INDENT = 5
#: Nave's writes two books by name rather than code. Listed, not guessed: every
#: other reference in the file starts with a code from books.BY_CODE.
NAVES_BOOKS = {"Jude": "JUD", "So": "SNG"}
#: The CSV's longest cell is cut at 32,767 characters (a spreadsheet limit):
#: "JESUS, THE CHRIST" loses its later subtopics. Counted, not repaired.
CELL_LIMIT = 32767


@dataclass
class Topics:
    topics: list[dict] = field(default_factory=list)   # id, title, parent, depth, line, path
    spans: list[dict] = field(default_factory=list)    # topic, ord, ref, book, c1, v1, c2, v2, votes
    anomalies: Counter = field(default_factory=Counter)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "topic"


def _spans(ref_text: str, book: str | None = None):
    """Nave's references -> spans, carrying the book across ``;``.

    Yields (ref, span) and returns via StopIteration nothing else; a part that
    cannot be read yields (ref, None).
    """
    # ";" separates references; some entries use ". " before a new book instead
    for part in (p.strip() for p in re.split(r";|\.\s+(?=[1-4]?[A-Z]{2,3} \d)", ref_text)):
        # "EZR with 2KI 17": a connective between references, not a reference
        part = re.sub(r"^with\s+", "", part)
        if not part:
            continue
        m = re.match(r"^([1-4]?[A-Za-z]{2,4})\s+(\d.*)$", part)
        code = m and NAVES_BOOKS.get(m.group(1), m.group(1))
        if m and code in books.BY_CODE:
            book, rest = code, m.group(2)
        else:
            rest = part
        if book is None:
            yield part, None
            continue
        text = f"{book} {rest}"
        try:
            for s in refs.parse(text).spans:
                yield text, s
        except refs.RefError:
            yield text, None


# A book code followed by a chapter number starts the reference list of a line.
# A lookahead, not a match, for the digit: "OF 1SA 23:10" must not consume the "1"
# of 1SA while trying (and rejecting) "OF".
_FIRST_REF = re.compile(r"(?<![A-Za-z0-9])([1-4]?[A-Z]{2,3}|Jude|So)(?= \d)")


def _split_line(text: str) -> tuple[str, str]:
    for m in _FIRST_REF.finditer(text):
        if NAVES_BOOKS.get(m.group(1), m.group(1)) in books.BY_CODE:
            return text[:m.start()].strip(" ,;:"), text[m.start():]
    return text.strip(), ""


def parse_naves(path: Path) -> Topics:
    out = Topics()
    csv.field_size_limit(1 << 30)
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    seen: set[str] = set()
    for row in rows:
        subject = row["subject"].strip()
        tid = f"topic:naves:{slug(subject)}"
        if tid in seen:
            out.anomalies["naves.subject_slug_collisions"] += 1
            continue
        seen.add(tid)
        out.topics.append({"id": tid, "title": subject, "parent": None, "depth": 0,
                           "line": 0, "path": subject})
        if len(row["entry"]) >= CELL_LIMIT:
            out.anomalies["naves.entries_truncated"] += 1
        stack = [(tid, subject)]                       # ancestors by depth
        for n, raw in enumerate(row["entry"].split("\n"), 1):
            if not raw.strip():
                continue
            indent = len(raw) - len(raw.lstrip(" "))
            body = raw.strip()
            if not body.startswith("-"):
                out.anomalies["naves.lines_without_dash"] += 1
                body = "-" + body
            depth = indent // NAVES_INDENT + 1
            label, reftext = _split_line(body[1:].strip())
            if label.lower().startswith("see ") and not reftext:
                out.anomalies["naves.see_lines"] += 1
                continue
            del stack[depth:]
            parent_id, parent_path = stack[-1] if stack else (tid, subject)
            if len(stack) < depth:
                out.anomalies["naves.indent_skips"] += 1
            sid = f"{tid}/{n}"
            path_text = f"{parent_path} > {label}"
            out.topics.append({"id": sid, "title": label, "parent": parent_id,
                               "depth": min(depth, len(stack)), "line": n, "path": path_text})
            stack.append((sid, path_text))
            for ord_, (ref, span) in enumerate(_spans(reftext), 1):
                if span is None:
                    out.anomalies["naves.refs_malformed"] += 1
                    continue
                out.spans.append(_span_row(sid, ord_, ref, span))
    return out


def _span_row(topic: str, ord_: int, ref: str, span, votes: int | None = None) -> dict:
    return {"topic": topic, "ord": ord_, "ref": ref, "book": span.book,
            "c1": span.c1, "v1": span.v1, "c2": span.c2, "v2": span.v2, "votes": votes}


_OSIS = re.compile(r"^([1-4]?[A-Za-z]+)\.(\d+)(?:\.(\d+))?$")


def parse_openbible(path: Path) -> Topics:
    """topic-scores.zip: one TSV, a header line, then Topic / OSIS range / votes."""
    out = Topics()
    by_osis = {b.osis: b.code for b in books.BOOKS if b.osis}
    with zipfile.ZipFile(path) as z:
        [name] = [n for n in z.namelist() if n.endswith(".txt")]
        text = z.read(name).decode("utf-8")
    lines = text.splitlines()
    ids: dict[str, str] = {}
    counts: Counter = Counter()
    for line in lines[1:]:
        if not line.strip():
            continue
        cells = line.split("\t")
        if len(cells) < 3:
            out.anomalies["openbible.rows_malformed"] += 1
            continue
        title, osis, score = cells[0].strip(), cells[1].strip(), cells[2].strip()
        tid = ids.get(title)
        if tid is None:
            base = f"topic:openbible:{slug(title)}"
            tid, k = base, 1
            while tid in ids.values():
                k += 1
                tid = f"{base}-{k}"
            if k > 1:
                out.anomalies["openbible.title_slug_collisions"] += 1
            ids[title] = tid
            out.topics.append({"id": tid, "title": title, "parent": None, "depth": 0,
                               "line": 0, "path": title})
        counts[tid] += 1
        ends = osis.split("-")
        parsed = [_OSIS.match(e) for e in ends]
        if len(ends) > 2 or not all(parsed):
            out.anomalies["openbible.rows_malformed"] += 1
            continue
        (b1, c1, v1), (b2, c2, v2) = (parsed[0].groups(), parsed[-1].groups())
        code1, code2 = by_osis.get(b1), by_osis.get(b2)
        if code1 is None or code1 != code2:
            out.anomalies["openbible.rows_malformed"] += 1
            continue
        span = refs.Span(book=code1, c1=int(c1), v1=int(v1) if v1 else None,
                         c2=int(c2), v2=int(v2) if v2 else None)
        try:
            votes = int(score)
        except ValueError:
            out.anomalies["openbible.rows_malformed"] += 1
            continue
        out.spans.append(_span_row(tid, counts[tid], osis, span, votes))
    return out


def fixture_subset_naves(text: str, codes: set[str]) -> str:
    """Rows whose entry cites any of the given book codes (for the test fixture)."""
    csv.field_size_limit(1 << 30)
    rows = list(csv.reader(io.StringIO(text)))
    rx = re.compile(r"(?<![A-Za-z0-9])(" + "|".join(sorted(codes)) + r") \d")
    keep = [rows[0]] + [r for r in rows[1:] if rx.search(r[2])]
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(keep)
    return buf.getvalue()
