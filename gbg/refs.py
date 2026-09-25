"""Scripture references as people and datasets write them -> structured spans.

auto-zettel-skill's locator is free text that the gates only check is
non-empty (``lint_links.py`` rule ``missing-locator``); FR-9 cites scripture
"by book-chapter-verse per SBL" but nothing parses it. That is fine for a page
number in a PDF and fatal for a corpus you want to *join* on. This module is
the parser half of the fix; ``gbg resolve`` is the half that checks a parsed
reference against the built edition.

Parsing is pure -- no database. It accepts:

* SBL style: ``Rom 3:21-26``, ``Rom 3:21–4:2`` (hyphen or en dash),
  ``Rom 3`` / ``Rom 3-4`` (whole chapters), lists with ``,`` (same chapter)
  and ``;`` (new chapter): ``Rom 3:21-26, 28; 5:1``. ``Rom 3.21`` too.
* Half verses ``Rom 3:21a`` -- widened to the whole verse, flagged ``partial``
  so a caller can say so rather than silently over-cite.
* Single-chapter books per SBL: ``Phlm 10`` is 1:10, not chapter 10.
* A bare book: ``Phlm`` is the whole book.
* MACULA refs: ``PHM 1:1!3`` (one word), ``PHM 1:1!3-5`` (words).
* Ids: ``sblgnt:PHM.1.1``, ``sblgnt:n57001001003``, ``sblgnt:PHM``.

It refuses ``ff``/``f.``: an open-ended range cannot be resolved honestly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import books, ids


class RefError(ValueError):
    """Malformed or ambiguous input (``gbg resolve`` exit 2)."""


@dataclass(frozen=True)
class Span:
    """A contiguous stretch of one book.

    ``verse`` components are ``None`` for whole-chapter spans; ``chapter`` is
    ``None`` too for a whole-book span. Word bounds come only from MACULA refs
    and token ids.
    """

    book: str
    c1: int | None = None
    v1: int | None = None
    c2: int | None = None
    v2: int | None = None
    w1: int | None = None
    w2: int | None = None
    partial: bool = False

    @property
    def whole_book(self) -> bool:
        return self.c1 is None

    def canonical(self) -> str:
        """USFM-coded, hyphenated, never abbreviated: ``ROM 3:21-26``."""
        if self.whole_book:
            return self.book
        if self.v1 is None:
            return self.book + f" {self.c1}" + (f"-{self.c2}" if self.c2 != self.c1 else "")
        out = f"{self.book} {self.c1}:{self.v1}"
        if self.w1 is not None:
            out += f"!{self.w1}" + (f"-{self.w2}" if self.w2 != self.w1 else "")
            return out
        if (self.c2, self.v2) != (self.c1, self.v1):
            out += f"-{self.v2}" if self.c2 == self.c1 else f"-{self.c2}:{self.v2}"
        return out

    def sbl(self) -> str:
        """Display form per the SBL Handbook: ``Rom 3:21–26``, ``Phlm 10``."""
        b = books.BY_CODE[self.book]
        if self.whole_book:
            return b.name
        dash = "–"
        if self.v1 is None:
            return f"{b.sbl} {self.c1}" + (f"{dash}{self.c2}" if self.c2 != self.c1 else "")
        single = b.single_chapter and self.c1 == 1 and self.c2 == 1
        loc = f"{self.v1}" if single else f"{self.c1}:{self.v1}"
        if (self.c2, self.v2) != (self.c1, self.v1):
            if self.c2 == self.c1:
                loc += f"{dash}{self.v2}"
            else:
                loc += f"{dash}{self.c2}:{self.v2}"
        return f"{b.sbl} {loc}"


@dataclass(frozen=True)
class Passage:
    text: str
    spans: tuple[Span, ...]

    @property
    def partial(self) -> bool:
        return any(s.partial for s in self.spans)

    def canonical(self) -> str:
        return "; ".join(s.canonical() for s in self.spans)

    def sbl(self) -> str:
        return "; ".join(s.sbl() for s in self.spans)


_MACULA = re.compile(r"^([1-4A-Z][A-Z0-9]{2}) (\d+):(\d+)!(\d+)(?:-(\d+))?$")
_HEAD = re.compile(r"^(?P<book>(?:[1-4]\s*)?[^\d]+?)\s*(?P<loc>\d.*)?$")
_CV = re.compile(r"^(\d+)[:.](\d+)([abc])?(?:-(?:(\d+)[:.])?(\d+)([abc])?)?$")
_N = re.compile(r"^(\d+)([abc])?(?:-(\d+)([abc])?)?$")
_DASHES = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-",
                         "—": "-", "−": "-"})


def _book(text: str) -> books.Book:
    try:
        return books.lookup(text)
    except books.AmbiguousBook as exc:
        raise RefError(str(exc)) from None
    except books.UnknownBook as exc:
        raise RefError(str(exc)) from None


def _from_id(text: str) -> Passage | None:
    kind = ids.kind_of(text)
    if kind == "token":
        bnum, c, v, w = ids.token_parts(text)
        book = books.NT_BY_NUM.get(bnum)
        if not book:
            raise RefError(f"token id {text!r} names no NT book")
        return Passage(text, (Span(book.code, c, v, c, v, w, w),))
    if kind == "verse":
        m = ids.VERSE_RE.match(text)
        book = _book(m.group(1))
        c, v = int(m.group(2)), int(m.group(3))
        return Passage(text, (Span(book.code, c, v, c, v),))
    if kind == "book":
        return Passage(text, (Span(_book(ids.BOOK_RE.match(text).group(1)).code),))
    if kind is not None:
        raise RefError(f"{text!r} is a {kind} id, not a passage")
    return None


def _check_order(span: Span, text: str) -> Span:
    if span.c1 is not None:
        start = (span.c1, span.v1 or 0, span.w1 or 0)
        end = (span.c2, span.v2 or 0, span.w2 or 0)
        if end < start:
            raise RefError(f"range runs backwards in {text!r}")
        if 0 in (span.c1, span.c2) or (span.v1 is not None and 0 in (span.v1, span.v2)):
            raise RefError(f"chapters and verses count from 1 in {text!r}")
    return span


def parse(text: str) -> Passage:
    """Parse a reference. Raises RefError on anything it cannot read exactly."""
    s = " ".join(text.split())
    if not s:
        raise RefError("empty reference")
    by_id = _from_id(s)
    if by_id:
        return by_id

    m = _MACULA.match(s)
    if m:
        book = _book(m.group(1))
        c, v, w1 = int(m.group(2)), int(m.group(3)), int(m.group(4))
        w2 = int(m.group(5)) if m.group(5) else w1
        return Passage(text, (_check_order(Span(book.code, c, v, c, v, w1, w2), text),))

    head = _HEAD.match(s)
    if not head:
        raise RefError(f"cannot read {text!r} as a reference")
    book = _book(head.group("book").strip())
    loc = head.group("loc")
    if loc is None:
        return Passage(text, (Span(book.code),))
    if re.search(r"\d\s*f{1,2}\.?\s*(?:[,;]|$)", loc):
        raise RefError(f"open-ended 'f'/'ff' in {text!r}: give an explicit range")

    loc = loc.translate(_DASHES).replace(" ", "")
    spans: list[Span] = []
    chapter: int | None = None
    sep = ";"
    for piece in re.split(r"([,;])", loc):
        if piece in (",", ";"):
            sep = piece
            continue
        if not piece:
            raise RefError(f"empty item in {text!r}")
        cv = _CV.match(piece)
        n = _N.match(piece) if not cv else None
        if cv:
            c1, v1 = int(cv.group(1)), int(cv.group(2))
            c2 = int(cv.group(4)) if cv.group(4) else c1
            v2 = int(cv.group(5)) if cv.group(5) else v1
            partial = bool(cv.group(3) or cv.group(6))
            spans.append(_check_order(Span(book.code, c1, v1, c2, v2, partial=partial), text))
            chapter = c2
        elif n:
            a, b = int(n.group(1)), int(n.group(3)) if n.group(3) else int(n.group(1))
            partial = bool(n.group(2) or n.group(4))
            if book.single_chapter:
                spans.append(_check_order(Span(book.code, 1, a, 1, b, partial=partial), text))
                chapter = 1
            elif sep == "," and chapter is not None:
                spans.append(_check_order(Span(book.code, chapter, a, chapter, b,
                                               partial=partial), text))
            else:
                if partial:
                    raise RefError(f"a/b/c marks a half verse, not a chapter, in {text!r}")
                spans.append(_check_order(Span(book.code, a, None, b, None), text))
                chapter = b
        else:
            raise RefError(f"cannot read {piece!r} in {text!r}")
    return Passage(text, tuple(spans))
