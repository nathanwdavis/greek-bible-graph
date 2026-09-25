"""Greek text normalisation: one definition, in Python and in SQL.

Two different questions get two different functions, and conflating them is
the bug this module exists to prevent:

* **Identity** -- is this the same lemma? -- uses :func:`nfc`. Accents and
  case are meaningful: τίς (who?) and τις (someone) are different words, as
  are εἰς (into) and εἷς (one). Upstream is not even consistent about the
  code points: 102 lemma values and 32 surface forms in MACULA's SBLGNT use
  oxia (U+1F71...) where the rest use tonos (U+03AC...). NFC folds those.

* **Lookup** -- what did the person typing without polytonic input mean? --
  uses :func:`search_key`. It strips everything a keyboard cannot easily type,
  so it is one-to-many by design (32 accent-stripped collisions among NT
  lemmas); a caller that looks up by key must report every match, never pick.

``search_key`` exists twice: here, and as the SQL macro ``gbg_key`` stored in
every built database (:data:`SQL_KEY_MACRO`). The macro is what makes the
database usable from any DuckDB client without this package -- and Python
UDFs would drag in numpy. The two MUST agree; ``tests/test_greek.py`` pins
them to each other on every lemma and surface form in the fixture, and the
``lemma-key`` lint re-checks the stored keys against the macro on every build.
"""

from __future__ import annotations

import unicodedata

#: Every apostrophe an elided form (κατ’, ἀπ’, δι’) turns up with in the wild:
#: right single quote, modifier apostrophe, Greek koronis, Greek psili, ASCII.
ELISION = "’ʼ᾽᾿'"

#: Greek punctuation as typed or pasted. U+0387 (ano teleia) and U+037E (Greek
#: question mark) are canonically equivalent to U+00B7 and ';', so NFC/NFD
#: already maps them; they are listed so a non-normalised caller is safe too.
PUNCT = ",.·;·;"

_DROP = frozenset(ELISION + PUNCT)


def nfc(s: str) -> str:
    """Canonical composition: the identity form every stored string uses."""
    return unicodedata.normalize("NFC", s)


def search_key(s: str) -> str:
    """Accent-, breathing-, case- and punctuation-insensitive lookup key.

    The order is load-bearing, and each step is pinned by a test:

    1. NFD, not NFKD -- NFKD turns a standalone koronis into space + U+0313.
    2. Drop combining marks: accents, breathings, diaeresis, iota subscript.
    3. casefold() AFTER stripping -- casefolding first turns the combining
       iota subscript (U+0345) into a full ι ("εκκλησιαι").
    4. Final sigma to medial: ς and σ are one letter.
    5. Drop elision marks and punctuation.
    """
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.casefold()
    s = s.replace("ς", "σ")
    return "".join(c for c in s if c not in _DROP)


def _sql_char_class(chars: str) -> str:
    # Inside a regex character class only ] \ ^ - are special; none of ours
    # are. The single quote must be doubled for the SQL string literal.
    return "[" + chars.replace("'", "''") + "]"


#: The SQL twin of :func:`search_key`, stored in every built database.
#: DuckDB's strip_accents drops the same combining marks; lower() on Greek
#: agrees with casefold() once final sigma is folded.
SQL_KEY_MACRO = (
    "CREATE OR REPLACE MACRO gbg_key(s) AS "
    "regexp_replace(replace(lower(strip_accents(nfc_normalize(s))), 'ς', 'σ'), "
    f"'{_sql_char_class(ELISION + PUNCT)}', '', 'g')"
)

#: Identity normalisation, also stored as a macro so ad-hoc SQL can write
#: ``WHERE lemma = gbg_nfc('θεός')`` without caring how it was typed.
SQL_NFC_MACRO = "CREATE OR REPLACE MACRO gbg_nfc(s) AS nfc_normalize(s)"
