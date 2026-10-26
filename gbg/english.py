"""English gloss terms: the one definition of how a gloss becomes search stems.

The build has no semantic domains (Louw-Nida is not openly licensed), but it
does carry a contextual English gloss on nearly every word: Cherith's
``english`` is short and dictionary-like (γινώσκω -> know / understand / find
out / "had sexual relations with"), so it works as a per-word sense label. To
search it by meaning, "knew", "known" and "knowing" must meet at one term, and
the translator's scaffolding ("[how]", "made ~ known") must not count.

``gloss_terms`` does that, in an order each step depends on:

1. lowercase;
2. drop bracketed insertions -- the translator's additions, not the word;
3. ``~`` (Cherith's mark for a split phrase, "made ~ known") becomes a space;
4. split into words (hyphens split: "heart-knowing" is heart + know);
5. a negator before the first content word ("not know", "without knowing")
   sets ``negated`` rather than becoming a term -- ἀγνοέω glossed "not know"
   is a word ABOUT knowing, and a search should find it and say so;
6. stopwords (articles, pronouns, auxiliaries, prepositions) are dropped;
7. an irregular form maps to its base BEFORE stemming (a stemmer leaves
   "knew" and "hidden" alone);
8. Snowball's English stemmer (Porter2), pinned exactly in pyproject.toml
   because a stemmer upgrade would silently change every stored term.

Terms are stems ("knowledg", "predestin"), not words. Nobody types them:
``query_terms`` puts a user's plain English through steps 1-8 so that
``know, hide`` matches the stored terms. Stems do not merge derivations --
"know" and "knowledge" stay apart -- so a search names both.

Glosses are a translator's choices (Berean chose "predestined"); a search
over them measures the translation as much as the Greek. Answers must say so.
"""

from __future__ import annotations

import re

import snowballstemmer

_STEMMER = snowballstemmer.stemmer("english")

NEGATORS = frozenset({"not", "without"})

STOPWORDS = frozenset("""
a an the
i me my mine myself you your yours yourself yourselves he him his himself she her hers herself
it its itself we us our ours ourselves they them their theirs themselves
this that these those who whom whose which what
am is are was were be been being
have has had having do does did done doing
will would shall should may might must can could let
to of in on at by for with from into onto upon out up down off over under about
and or but nor so as than then
""".split())

#: Inflected form -> base form, for the forms a suffix-stripping stemmer
#: cannot reach. Ambiguous forms map to the sense a Bible gloss nearly always
#: means ("left" -> leave, "found" -> find, "lying" -> lie).
IRREGULAR: dict[str, str] = {
    "arose": "arise", "arisen": "arise", "ate": "eat", "eaten": "eat", "awoke": "awake",
    "became": "become", "began": "begin", "begun": "begin", "beheld": "behold",
    "bent": "bend", "besought": "beseech", "bit": "bite", "bitten": "bite",
    "blew": "blow", "blown": "blow", "bore": "bear", "born": "bear", "borne": "bear",
    "bought": "buy", "bound": "bind", "broke": "break", "broken": "break",
    "brought": "bring", "built": "build", "burnt": "burn", "came": "come",
    "caught": "catch", "chose": "choose", "chosen": "choose",
    "clothed": "clothe", "clung": "cling", "dealt": "deal", "dug": "dig", "drew": "draw",
    "drawn": "draw", "drank": "drink", "drunk": "drink", "drove": "drive",
    "driven": "drive", "dwelt": "dwell", "fed": "feed", "fell": "fall", "fallen": "fall",
    "felt": "feel", "fled": "flee", "flew": "fly", "flown": "fly",
    "foreknew": "foreknow", "foreknown": "foreknow", "foresaw": "foresee",
    "foreseen": "foresee", "forgave": "forgive", "forgiven": "forgive",
    "forgot": "forget", "forgotten": "forget", "forsook": "forsake",
    "forsaken": "forsake", "fought": "fight", "found": "find", "froze": "freeze",
    "gave": "give", "given": "give", "went": "go", "gone": "go", "grew": "grow",
    "grown": "grow", "hung": "hang", "heard": "hear", "hid": "hide", "hidden": "hide",
    "held": "hold", "kept": "keep", "knelt": "kneel", "knew": "know", "known": "know",
    "laid": "lay", "lain": "lie", "lying": "lie", "led": "lead",
    "left": "leave", "lent": "lend", "lit": "light", "lost": "lose", "made": "make",
    "meant": "mean", "met": "meet", "mistook": "mistake", "overcame": "overcome",
    "overtook": "overtake", "paid": "pay", "ran": "run", "rode": "ride",
    "ridden": "ride", "rose": "rise", "risen": "rise", "rang": "ring", "rung": "ring",
    "said": "say", "sang": "sing", "sung": "sing", "sank": "sink", "sunk": "sink",
    "sat": "sit", "saw": "see", "seen": "see", "sought": "seek", "sold": "sell",
    "sent": "send", "shook": "shake", "shaken": "shake", "shone": "shine",
    "shot": "shoot", "slew": "slay", "slain": "slay", "slept": "sleep",
    "sown": "sow", "spoke": "speak", "spoken": "speak", "spent": "spend",
    "spat": "spit", "sprang": "spring", "sprung": "spring",
    "stood": "stand", "stole": "steal", "stolen": "steal", "struck": "strike",
    "stricken": "strike", "strove": "strive", "striven": "strive", "swore": "swear",
    "sworn": "swear", "swept": "sweep", "took": "take", "taken": "take",
    "taught": "teach", "tore": "tear", "torn": "tear", "told": "tell",
    "thought": "think", "threw": "throw", "thrown": "throw", "trod": "tread",
    "trodden": "tread", "understood": "understand", "undertook": "undertake",
    "upheld": "uphold", "wept": "weep", "withheld": "withhold", "withstood": "withstand",
    "woke": "wake", "woken": "wake", "wore": "wear", "worn": "wear", "won": "win",
    "wound": "wind", "wrote": "write", "written": "write", "wrought": "work",
    "men": "man", "women": "woman", "children": "child", "brethren": "brother",
    "feet": "foot", "teeth": "tooth", "oxen": "ox", "mice": "mouse", "lice": "louse",
}

_WORD = re.compile(r"[a-z]+(?:'[a-z]+)?")


def _words(text: str) -> list[str]:
    s = text.lower().replace("’", "'")
    s = re.sub(r"\[[^\]]*\]", " ", s)          # step 2: translator insertions
    s = s.replace("~", " ")                     # step 3: split-phrase mark
    return _WORD.findall(s.replace("-", " "))  # step 4


def stem(word: str) -> str:
    """Steps 7-8 for one lowercase word."""
    return _STEMMER.stemWord(IRREGULAR.get(word, word))


def gloss_terms(gloss: str | None) -> tuple[list[str] | None, bool]:
    """(distinct stems in order, negated) for one gloss; (None, False) for no gloss."""
    if gloss is None:
        return None, False
    terms: list[str] = []
    negated = False
    for w in _words(gloss):
        if w in NEGATORS:
            # Only a negator ahead of the content counts as negating it.
            negated = negated or not terms
            continue
        if w in STOPWORDS:
            continue
        t = stem(w)
        if t not in terms:
            terms.append(t)
    return terms, negated


def query_terms(text: str) -> list[str]:
    """Plain English as a user types it ("know, hide, reveal") -> stored terms.

    The same steps as a gloss, word by word; stopwords are dropped, and a
    query that is ONLY stopwords is refused by the caller, not silently empty.
    """
    out: list[str] = []
    for w in _words(text):
        if w in STOPWORDS or w in NEGATORS:
            continue
        t = stem(w)
        if t not in out:
            out.append(t)
    return out
