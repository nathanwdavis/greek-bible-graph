"""The book table: codes, names, abbreviations, and which corpus has what.

Designed against the whole Greek Bible now, though only the NT is built,
for one reason: an alias table that grows later changes how existing input
parses. If "Jud" meant Jude today and became ambiguous the day Judith and
Judges arrive, every note that cited "Jud 3" would silently change meaning.
So the LXX canon is here from the start, ambiguity is decided once, and an
ambiguous alias is an error listing the candidates -- never a guess.

Lookup order (see :func:`lookup`):

1. An exact all-caps USFM code (``JUD``) is unambiguous by definition.
2. Everything else -- SBL abbreviations, OSIS ids, full names, common short
   forms -- is matched case- and space-insensitively against the alias table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Book:
    code: str            # USFM, which MACULA's refs also use
    num: int             # MACULA xml:id book number for the NT (40-66); canonical order otherwise
    name: str
    sbl: str             # SBL Handbook abbreviation, used for display
    osis: str
    corpus: str          # "nt" | "ot" (in both MT and LXX) | "lxx" (Greek-only books)
    single_chapter: bool = False
    aliases: tuple[str, ...] = field(default=())


def _b(code, num, name, sbl, osis, corpus, *aliases, single=False):
    return Book(code, num, name, sbl, osis, corpus, single, tuple(aliases))


BOOKS: tuple[Book, ...] = (
    # --- Old Testament (MT and LXX) -----------------------------------------
    _b("GEN", 1, "Genesis", "Gen", "Gen", "ot", "Gn"),
    _b("EXO", 2, "Exodus", "Exod", "Exod", "ot", "Ex", "Exo"),
    _b("LEV", 3, "Leviticus", "Lev", "Lev", "ot", "Lv"),
    _b("NUM", 4, "Numbers", "Num", "Num", "ot", "Nm"),
    _b("DEU", 5, "Deuteronomy", "Deut", "Deut", "ot", "Dt"),
    _b("JOS", 6, "Joshua", "Josh", "Josh", "ot"),
    _b("JDG", 7, "Judges", "Judg", "Judg", "ot", "Jdg"),
    _b("RUT", 8, "Ruth", "Ruth", "Ruth", "ot", "Ru"),
    _b("1SA", 9, "1 Samuel", "1 Sam", "1Sam", "ot", "1 Kgdms", "1 Kingdoms", "1 Reigns"),
    _b("2SA", 10, "2 Samuel", "2 Sam", "2Sam", "ot", "2 Kgdms", "2 Kingdoms", "2 Reigns"),
    _b("1KI", 11, "1 Kings", "1 Kgs", "1Kgs", "ot", "3 Kgdms", "3 Kingdoms", "3 Reigns"),
    _b("2KI", 12, "2 Kings", "2 Kgs", "2Kgs", "ot", "4 Kgdms", "4 Kingdoms", "4 Reigns"),
    _b("1CH", 13, "1 Chronicles", "1 Chr", "1Chr", "ot", "1 Paraleipomenon", "1 Par"),
    _b("2CH", 14, "2 Chronicles", "2 Chr", "2Chr", "ot", "2 Paraleipomenon", "2 Par"),
    _b("EZR", 15, "Ezra", "Ezra", "Ezra", "ot", "2 Esdras", "Esdras B"),
    _b("NEH", 16, "Nehemiah", "Neh", "Neh", "ot"),
    _b("EST", 17, "Esther", "Esth", "Esth", "ot"),
    _b("JOB", 18, "Job", "Job", "Job", "ot", "Jb"),
    _b("PSA", 19, "Psalms", "Ps", "Ps", "ot", "Pss", "Psalm", "Psa"),
    _b("PRO", 20, "Proverbs", "Prov", "Prov", "ot", "Prv"),
    _b("ECC", 21, "Ecclesiastes", "Eccl", "Eccl", "ot", "Qoh", "Qoheleth"),
    _b("SNG", 22, "Song of Songs", "Song", "Song", "ot", "Song of Solomon", "Cant", "Canticles"),
    _b("ISA", 23, "Isaiah", "Isa", "Isa", "ot", "Is"),
    _b("JER", 24, "Jeremiah", "Jer", "Jer", "ot"),
    _b("LAM", 25, "Lamentations", "Lam", "Lam", "ot"),
    _b("EZK", 26, "Ezekiel", "Ezek", "Ezek", "ot", "Eze", "Ezk"),
    _b("DAN", 27, "Daniel", "Dan", "Dan", "ot", "Dn"),
    _b("HOS", 28, "Hosea", "Hos", "Hos", "ot"),
    _b("JOL", 29, "Joel", "Joel", "Joel", "ot"),
    _b("AMO", 30, "Amos", "Amos", "Amos", "ot"),
    _b("OBA", 31, "Obadiah", "Obad", "Obad", "ot", "Ob", single=True),
    _b("JON", 32, "Jonah", "Jonah", "Jonah", "ot", "Jon"),
    _b("MIC", 33, "Micah", "Mic", "Mic", "ot"),
    _b("NAM", 34, "Nahum", "Nah", "Nah", "ot"),
    _b("HAB", 35, "Habakkuk", "Hab", "Hab", "ot"),
    _b("ZEP", 36, "Zephaniah", "Zeph", "Zeph", "ot"),
    _b("HAG", 37, "Haggai", "Hag", "Hag", "ot"),
    _b("ZEC", 38, "Zechariah", "Zech", "Zech", "ot"),
    _b("MAL", 39, "Malachi", "Mal", "Mal", "ot"),
    # --- New Testament: num is MACULA's xml:id book number ------------------
    _b("MAT", 40, "Matthew", "Matt", "Matt", "nt", "Mt"),
    _b("MRK", 41, "Mark", "Mark", "Mark", "nt", "Mk", "Mar"),
    _b("LUK", 42, "Luke", "Luke", "Luke", "nt", "Lk", "Luk"),
    _b("JHN", 43, "John", "John", "John", "nt", "Jn", "Joh"),
    _b("ACT", 44, "Acts", "Acts", "Acts", "nt", "Ac"),
    _b("ROM", 45, "Romans", "Rom", "Rom", "nt", "Rm"),
    _b("1CO", 46, "1 Corinthians", "1 Cor", "1Cor", "nt"),
    _b("2CO", 47, "2 Corinthians", "2 Cor", "2Cor", "nt"),
    _b("GAL", 48, "Galatians", "Gal", "Gal", "nt"),
    _b("EPH", 49, "Ephesians", "Eph", "Eph", "nt"),
    _b("PHP", 50, "Philippians", "Phil", "Phil", "nt", "Php"),
    _b("COL", 51, "Colossians", "Col", "Col", "nt"),
    _b("1TH", 52, "1 Thessalonians", "1 Thess", "1Thess", "nt", "1 Thes", "1 Th"),
    _b("2TH", 53, "2 Thessalonians", "2 Thess", "2Thess", "nt", "2 Thes", "2 Th"),
    _b("1TI", 54, "1 Timothy", "1 Tim", "1Tim", "nt", "1 Tm"),
    _b("2TI", 55, "2 Timothy", "2 Tim", "2Tim", "nt", "2 Tm"),
    _b("TIT", 56, "Titus", "Titus", "Titus", "nt", "Tit"),
    _b("PHM", 57, "Philemon", "Phlm", "Phlm", "nt", "Phm", "Philem", single=True),
    _b("HEB", 58, "Hebrews", "Heb", "Heb", "nt"),
    _b("JAS", 59, "James", "Jas", "Jas", "nt", "Jm"),
    _b("1PE", 60, "1 Peter", "1 Pet", "1Pet", "nt", "1 Pt"),
    _b("2PE", 61, "2 Peter", "2 Pet", "2Pet", "nt", "2 Pt"),
    _b("1JN", 62, "1 John", "1 John", "1John", "nt", "1 Jn"),
    _b("2JN", 63, "2 John", "2 John", "2John", "nt", "2 Jn", single=True),
    _b("3JN", 64, "3 John", "3 John", "3John", "nt", "3 Jn", single=True),
    _b("JUD", 65, "Jude", "Jude", "Jude", "nt", single=True),
    _b("REV", 66, "Revelation", "Rev", "Rev", "nt", "Rv", "Apocalypse", "Apoc"),
    # --- Greek-only books of the LXX (deuterocanon / apocrypha) -------------
    _b("TOB", 67, "Tobit", "Tob", "Tob", "lxx", "Tb"),
    _b("JDT", 68, "Judith", "Jdt", "Jdt", "lxx", "Jth"),
    _b("ESG", 69, "Esther (Greek)", "Add Esth", "AddEsth", "lxx", "Greek Esther", "Esther Greek"),
    _b("WIS", 70, "Wisdom of Solomon", "Wis", "Wis", "lxx", "Wisdom", "Ws"),
    _b("SIR", 71, "Sirach", "Sir", "Sir", "lxx", "Ecclesiasticus", "Ben Sira"),
    _b("BAR", 72, "Baruch", "Bar", "Bar", "lxx"),
    _b("LJE", 73, "Letter of Jeremiah", "Ep Jer", "EpJer", "lxx", "Epistle of Jeremiah", single=True),
    _b("S3Y", 74, "Song of the Three Young Men", "Pr Azar", "PrAzar", "lxx", "Song of Three", "Prayer of Azariah"),
    _b("SUS", 75, "Susanna", "Sus", "Sus", "lxx", single=True),
    _b("BEL", 76, "Bel and the Dragon", "Bel", "Bel", "lxx", single=True),
    _b("1MA", 77, "1 Maccabees", "1 Macc", "1Macc", "lxx", "1 Mac"),
    _b("2MA", 78, "2 Maccabees", "2 Macc", "2Macc", "lxx", "2 Mac"),
    _b("3MA", 79, "3 Maccabees", "3 Macc", "3Macc", "lxx", "3 Mac"),
    _b("4MA", 80, "4 Maccabees", "4 Macc", "4Macc", "lxx", "4 Mac"),
    _b("1ES", 81, "1 Esdras", "1 Esd", "1Esd", "lxx", "Esdras A"),
    _b("MAN", 82, "Prayer of Manasseh", "Pr Man", "PrMan", "lxx", single=True),
    _b("PS2", 83, "Psalm 151", "Ps 151", "AddPs", "lxx", single=True),
    _b("ODA", 84, "Odes", "Odes", "Odes", "lxx", "Odae"),
    _b("PSS", 85, "Psalms of Solomon", "Pss Sol", "PssSol", "lxx", "Ps Sol"),
)

#: Short forms people really type that genuinely mean more than one book.
#: Listed explicitly: ambiguity is a decision, not an accident of the table.
AMBIGUOUS: dict[str, tuple[str, ...]] = {
    "jud": ("JUD", "JDT", "JDG"),
    "ph": ("PHP", "PHM"),
    "phi": ("PHP", "PHM"),
    "jo": ("JHN", "JOB", "JOL", "JON"),
    "ma": ("MAT", "MAL"),
    "es": ("EST", "ESG", "1ES"),
    "sa": ("1SA", "2SA"),
}

BY_CODE: dict[str, Book] = {b.code: b for b in BOOKS}
NT_BY_NUM: dict[int, Book] = {b.num: b for b in BOOKS if b.corpus == "nt"}


class UnknownBook(ValueError):
    pass


class AmbiguousBook(ValueError):
    def __init__(self, text: str, candidates: tuple[str, ...]):
        self.candidates = candidates
        names = ", ".join(f"{BY_CODE[c].sbl} ({c})" for c in candidates)
        super().__init__(f"{text!r} is ambiguous: {names}")


def norm_alias(text: str) -> str:
    """Case-, space- and period-insensitive: "1 Cor." == "1cor" == "1 COR"."""
    return re.sub(r"[\s.]+", "", text).casefold()


def _names(b: Book) -> set[str]:
    return {norm_alias(x) for x in (b.name, b.sbl, b.osis, *b.aliases)}


def _alias_table() -> dict[str, set[str]]:
    """Names first; a lowercased USFM code only where no name claims it.

    USFM codes are machine identifiers and sometimes collide with a real
    abbreviation: SBL's "Pss" is Psalms, USFM's ``PSS`` is the Psalms of
    Solomon. The human abbreviation wins case-insensitively; the exact
    all-caps code still reaches the other book (step 1 of :func:`lookup`).
    """
    table: dict[str, set[str]] = {}
    for b in BOOKS:
        for a in _names(b):
            table.setdefault(a, set()).add(b.code)
    for b in BOOKS:
        table.setdefault(norm_alias(b.code), {b.code})
    for a, codes in AMBIGUOUS.items():
        table[a] = set(codes)
    return table


_ALIASES = _alias_table()


def lookup(text: str) -> Book:
    """Resolve a book name as typed. Raises UnknownBook or AmbiguousBook."""
    raw = text.strip().rstrip(".")
    if raw in BY_CODE:  # exact USFM, all caps: never ambiguous
        return BY_CODE[raw]
    codes = _ALIASES.get(norm_alias(raw))
    if not codes:
        raise UnknownBook(f"unknown book {text!r}")
    if len(codes) > 1:
        order = [b.code for b in BOOKS]
        raise AmbiguousBook(text, tuple(sorted(codes, key=order.index)))
    return BY_CODE[next(iter(codes))]


def _check_table() -> None:
    """Import-time guard: two books may not claim the same alias by accident."""
    seen: dict[str, str] = {}
    for b in BOOKS:
        for a in _names(b):
            if a in AMBIGUOUS:
                continue
            if a in seen and seen[a] != b.code:
                raise AssertionError(f"alias {a!r} claimed by {seen[a]} and {b.code}; "
                                     "list it in AMBIGUOUS if that is intended")
            seen[a] = b.code


_check_table()
