"""THE graph: every table, column and edge, declared once.

This borrows auto-zettel-skill's hardest-won structural rule
(``scripts/zettel_lib/graph.py``): four tools walked the note graph four
slightly different ways until the walk lived in one module, because "a graph
read four slightly different ways is a graph nobody can reason about". Here
the same principle is taken one step further -- the graph is *data*, and
everything that needs to know its shape is generated from this module:

* the DDL the build creates (``store.py``);
* the ``edge`` view that unions every relation, and the ``--pgq`` property
  graph (``db.py``);
* the ``dangling-edge`` lint, one check per declared reference (``lint.py``);
* the license lint: every column names the upstream component its data comes
  from, or ``gbg`` for values this build computes (``lint.py``);
* the schema document Claude reads before writing SQL (``schemadoc.py``).

Relations come in two shapes, deliberately. A 1:1 relation (a token's verse,
its parent word group, its lemma) is a foreign-key column: Claude writes
``token.lemma = 'θεός'``, not a three-way join. Only many-to-many or
attributed relations get their own edge table. That also sidesteps a
polymorphic "child" edge (word group -> word group | token), which neither
SQL/PGQ nor typed property-graph engines accept: the tree is two foreign keys,
``wg.parent_wg`` and ``token.parent_wg``.

Every edge table carries ``tier`` -- where the edge came from, mirroring
graph.py's split between curated links and observed mentions:

    data      asserted by the upstream dataset (everything in the NT build)
    asserted  asserted by a person in a note (reserved: zettel citations)
    computed  proposed by an algorithm; NEVER in a canonical table -- it
              belongs in a proposed_* table awaiting review

and a nullable ``confidence``, because "upstream data" is not always certain
(the LXX morphology is statistical). Tier says who; confidence says how sure.
"""

from __future__ import annotations

from dataclasses import dataclass

TIERS = ("data", "asserted", "computed")
#: The component name for values this build computes (ids, ordinals, counts).
GBG = "gbg"


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    doc: str
    component: str                 # upstream component, or GBG
    ref: str | None = None         # referenced table (its ``id``), if a foreign key
    label: str | None = None       # edge label when ``ref`` is set
    nullable: bool = True
    enum: bool = False             # schema doc lists the distinct values


@dataclass(frozen=True)
class Table:
    name: str
    kind: str                      # "node" | "edge" | "index"
    doc: str
    columns: tuple[Column, ...]
    pk: tuple[str, ...]            # canonical row order, for hashing and export

    def column(self, name: str) -> Column:
        for c in self.columns:
            if c.name == name:
                return c
        raise KeyError(name)

    @property
    def refs(self) -> tuple[Column, ...]:
        return tuple(c for c in self.columns if c.ref)


def C(name, type_, doc, component=GBG, **kw) -> Column:
    return Column(name, type_, doc, component, **kw)


MC = "macula-clear"
TXT = "sblgnt-text"

EDGE_COLS = (
    C("tier", "VARCHAR", "Where the edge came from: data | asserted | computed.",
      nullable=False, enum=True),
    C("confidence", "DOUBLE", "Certainty in [0,1] when the source states one; NULL otherwise."),
    C("source", "VARCHAR", "Source that asserted the edge (a sources.lock.json name).",
      nullable=False, enum=True),
)

TABLES: tuple[Table, ...] = (
    Table("book", "node", "The 27 books of the SBLGNT.", (
        C("id", "VARCHAR", "Book id, e.g. sblgnt:PHM.", nullable=False),
        C("code", "VARCHAR", "USFM code, e.g. PHM.", nullable=False),
        C("num", "INTEGER", "MACULA book number (MAT=40 .. REV=66).", nullable=False),
        C("name", "VARCHAR", "English name.", nullable=False),
        C("sbl", "VARCHAR", "SBL Handbook abbreviation, e.g. Phlm.", nullable=False),
        C("ord", "INTEGER", "Canonical order, 1-based.", nullable=False),
        C("n_chapters", "INTEGER", "Chapters in this edition.", nullable=False),
        C("n_verses", "INTEGER", "Verses in this edition.", nullable=False),
        C("n_tokens", "INTEGER", "Words in this edition.", nullable=False),
    ), ("id",)),

    Table("verse", "node",
          "One verse. Verses and sentences are INDEPENDENT hierarchies over the same "
          "tokens: a sentence may span verses and a verse may be split across sentences.", (
        C("id", "VARCHAR", "Verse id, e.g. sblgnt:PHM.1.20. Citable.", nullable=False),
        C("book_id", "VARCHAR", "Book.", ref="book", label="IN_BOOK", nullable=False),
        C("chapter", "INTEGER", "Chapter number.", nullable=False),
        C("verse", "INTEGER", "Verse number.", nullable=False),
        C("ord", "INTEGER", "Global verse order, 1-based.", nullable=False),
        C("first_token", "VARCHAR", "First token (surface order).", ref="token",
          label="FIRST_TOKEN", nullable=False),
        C("last_token", "VARCHAR", "Last token (surface order).", ref="token",
          label="LAST_TOKEN", nullable=False),
        C("n_tokens", "INTEGER", "Words in the verse.", nullable=False),
        C("text", "VARCHAR", "The verse's Greek text with punctuation.", TXT, nullable=False),
    ), ("id",)),

    Table("sentence", "node",
          "One sentence as MACULA's syntax trees divide the text. Ids are build-local: "
          "do not cite them.", (
        C("id", "VARCHAR", "Sentence id, sblgnt:s:<leftmost token>. Not citable.", nullable=False),
        C("book_id", "VARCHAR", "Book.", ref="book", label="IN_BOOK", nullable=False),
        C("ord", "INTEGER", "Global sentence order, 1-based.", nullable=False),
        C("root_wg", "VARCHAR", "Root word group; NULL when the root is a lone word.",
          ref="wg", label="ROOT"),
        C("first_token", "VARCHAR", "First token (surface order).", ref="token",
          label="FIRST_TOKEN", nullable=False),
        C("last_token", "VARCHAR", "Last token (surface order).", ref="token",
          label="LAST_TOKEN", nullable=False),
        C("n_tokens", "INTEGER", "Words in the sentence.", nullable=False),
        C("text", "VARCHAR", "The sentence's Greek text with punctuation.", TXT, nullable=False),
    ), ("id",)),

    Table("wg", "node",
          "A word group (syntactic constituent) in MACULA's trees. Ids are build-local: "
          "do not cite them; cite the tokens a group covers.", (
        C("id", "VARCHAR", "Word-group id, sblgnt:wg:<leftmost token>.<depth>. Not citable.",
          nullable=False),
        C("sentence_id", "VARCHAR", "Sentence.", ref="sentence", label="IN_SENTENCE",
          nullable=False),
        C("parent_wg", "VARCHAR", "Parent word group; NULL for a sentence root.", ref="wg",
          label="CHILD_OF"),
        C("depth", "INTEGER", "0 for the sentence root.", nullable=False),
        C("child_ord", "INTEGER", "Position among the parent's children, 1-based.",
          nullable=False),
        C("tree_ord", "INTEGER", "Preorder position among word groups in the sentence.",
          nullable=False),
        C("class", "VARCHAR", "Constituent class: cl (clause), np, vp, pp, adjp, advp, ...",
          MC, enum=True),
        C("rule", "VARCHAR", "MACULA phrase-structure rule, e.g. S-V-O, NpaNp.", MC),
        C("role", "VARCHAR", "Role in the parent clause: s (subject), v, o, io, adv, p, "
          "vc, aux, o2.", MC, enum=True),
        C("type", "VARCHAR", "Group type, e.g. apposition, group.", MC, enum=True),
        C("articular", "VARCHAR", "'true' when the group is articular.", MC, enum=True),
        C("junction", "VARCHAR", "Junction type, e.g. apposition, coordinate.", MC, enum=True),
        C("predication", "VARCHAR", "'elided' when the clause's predicate is elided.", MC,
          enum=True),
        C("clause_type", "VARCHAR", "Clause type where MACULA states one.", MC, enum=True),
        C("upstream_node_id", "VARCHAR", "MACULA's nodeId, on the minority of groups that "
          "keep one.", MC),
        C("first_token", "VARCHAR", "Leftmost covered token (surface order).", ref="token",
          label="FIRST_TOKEN", nullable=False),
        C("last_token", "VARCHAR", "Rightmost covered token (surface order).", ref="token",
          label="LAST_TOKEN", nullable=False),
        C("n_tokens", "INTEGER", "Tokens the group dominates.", nullable=False),
        C("contiguous", "BOOLEAN", "False when the group's tokens are not adjacent in the text.",
          nullable=False),
    ), ("id",)),

    Table("token", "node", "One word of the SBLGNT, with MACULA's annotations.", (
        C("id", "VARCHAR", "Token id, sblgnt:<xml:id>, e.g. sblgnt:n57001001001. Citable.",
          nullable=False),
        C("xml_id", "VARCHAR", "MACULA's xml:id.", MC, nullable=False),
        C("ref", "VARCHAR", "MACULA ref, BOOK C:V!W, e.g. PHM 1:1!1.", MC, nullable=False),
        C("book_id", "VARCHAR", "Book.", ref="book", label="IN_BOOK", nullable=False),
        C("verse_id", "VARCHAR", "Verse.", ref="verse", label="IN_VERSE", nullable=False),
        C("sentence_id", "VARCHAR", "Sentence.", ref="sentence", label="IN_SENTENCE",
          nullable=False),
        C("parent_wg", "VARCHAR", "Parent word group in the tree; NULL for a lone-word "
          "sentence.", ref="wg", label="CHILD_OF"),
        C("lemma_id", "VARCHAR", "Lemma node.", ref="lemma", label="HAS_LEMMA", nullable=False),
        C("next_id", "VARCHAR", "Next token in the same book (surface order).", ref="token",
          label="NEXT"),
        C("ord", "INTEGER", "Global surface order, 1-based.", nullable=False),
        C("chapter", "INTEGER", "Chapter.", nullable=False),
        C("verse", "INTEGER", "Verse.", nullable=False),
        C("word", "INTEGER", "Word number within the verse, 1-based.", nullable=False),
        C("depth", "INTEGER", "Depth in the syntax tree (parent's depth + 1).", nullable=False),
        C("child_ord", "INTEGER", "Position among the parent's children, 1-based.",
          nullable=False),
        C("tree_ord", "INTEGER", "Position in tree (constituent) order within the sentence.",
          nullable=False),
        C("surface", "VARCHAR", "The word as printed, NFC.", TXT, nullable=False),
        C("after", "VARCHAR", "What follows the word: a space, or punctuation (then a space).",
          TXT, nullable=False, enum=True),
        C("normalized", "VARCHAR", "Normalised surface form (NFC).", TXT, nullable=False),
        C("surface_key", "VARCHAR", "gbg_key(surface): accent/case-free lookup key.", TXT,
          nullable=False),
        C("lemma", "VARCHAR", "Dictionary form, NFC. Accent- and case-sensitive.", MC,
          nullable=False),
        C("lemma_key", "VARCHAR", "gbg_key(lemma): accent/case-free lookup key (one-to-many).",
          MC, nullable=False),
        C("strong", "VARCHAR", "Strong's number(s); compounds look like 1537+4053.", MC,
          nullable=False),
        C("morph", "VARCHAR", "Robinson-style morphology code, e.g. N-NSM, V-AAI-3S.", MC,
          nullable=False),
        C("pos", "VARCHAR", "Part of speech: noun, verb, det, conj, pron, prep, adj, adv, "
          "ptcl, num, intj.", MC, nullable=False, enum=True),
        C("type", "VARCHAR", "Sub-type, e.g. proper / common for nouns.", MC, enum=True),
        C("person", "VARCHAR", "first | second | third.", MC, enum=True),
        C("number", "VARCHAR", "singular | plural.", MC, enum=True),
        C("gender", "VARCHAR", "masculine | feminine | neuter.", MC, enum=True),
        C("gcase", "VARCHAR", "Grammatical case (named gcase: CASE is an SQL keyword).", MC,
          enum=True),
        C("tense", "VARCHAR", "aorist, present, imperfect, perfect, future, pluperfect.", MC,
          enum=True),
        C("voice", "VARCHAR", "active | middle | passive (and deponent variants).", MC,
          enum=True),
        C("mood", "VARCHAR", "indicative, subjunctive, imperative, optative, infinitive, "
          "participle.", MC, enum=True),
        C("degree", "VARCHAR", "comparative | superlative.", MC, enum=True),
        C("role", "VARCHAR", "The word's own role when it is a direct clause constituent "
          "(v, s, o, adv, ...). NULL when the role belongs to a group above it.", MC,
          enum=True),
        C("rule", "VARCHAR", "Rule, on words that stand as a constituent on their own.", MC),
        C("junction", "VARCHAR", "Junction type on the word, where stated.", MC, enum=True),
        C("discontinuous", "BOOLEAN", "True when the word sits away from its constituent.",
          MC, nullable=False),
        C("gloss", "VARCHAR", "Berean Interlinear contextual gloss (public domain).", "berean"),
        C("english", "VARCHAR", "Cherith English gloss (CC BY 4.0).", "cherith"),
    ), ("id",)),

    Table("lemma", "node", "One dictionary form. Shared across corpora by NFC string.", (
        C("id", "VARCHAR", "Lemma id, lemma:<NFC lemma>. Citable.", nullable=False),
        C("lemma", "VARCHAR", "The lemma, NFC.", MC, nullable=False),
        C("key", "VARCHAR", "gbg_key(lemma). Several lemmas can share a key (τίς/τις).", MC,
          nullable=False),
        C("n_tokens", "INTEGER", "Occurrences in this edition.", nullable=False),
        C("strongs", "VARCHAR[]", "Distinct Strong's numbers its tokens carry (sorted).", MC,
          nullable=False),
    ), ("id",)),

    Table("refers_to", "edge",
          "Coreference: the word (usually a pronoun) refers to the target word. From "
          "MACULA's referent column. Chains can cycle: guard recursive queries.", (
        C("src", "VARCHAR", "Referring token.", ref="token", label="REFERS_TO", nullable=False),
        C("dst", "VARCHAR", "Referent token; NULL when implicit.", ref="token",
          label="REFERS_TO"),
        C("implicit", "BOOLEAN", "True for an unexpressed participant (dst is NULL).",
          nullable=False),
        C("ord", "INTEGER", "Position in the upstream list.", nullable=False),
        *EDGE_COLS,
    ), ("src", "ord")),

    Table("has_subject", "edge",
          "Coreference-resolved SUBJECT of a verb, from MACULA's subjref column. This is NOT "
          "the syntactic subject: most targets lie outside the verb's verse. For the "
          "syntactic subject use the tree (a sibling group with role = 's').", (
        C("src", "VARCHAR", "Verb token.", ref="token", label="HAS_SUBJECT", nullable=False),
        C("dst", "VARCHAR", "Subject referent token; NULL when implicit.", ref="token",
          label="HAS_SUBJECT"),
        C("implicit", "BOOLEAN", "True for an unexpressed participant (dst is NULL).",
          nullable=False),
        C("ord", "INTEGER", "Position in the upstream list.", nullable=False),
        *EDGE_COLS,
    ), ("src", "ord")),

    Table("frame_arg", "edge",
          "Semantic-frame argument of a predicate (usually a verb), from MACULA's frame "
          "column. A0 = agent/causer, A1 = patient/theme, A2 / AA2 = further arguments.", (
        C("src", "VARCHAR", "Predicate token.", ref="token", label="FRAME_ARG", nullable=False),
        C("dst", "VARCHAR", "Argument token; NULL when implicit.", ref="token",
          label="FRAME_ARG"),
        C("arg_role", "VARCHAR", "A0 | A1 | A2 | AA2.", MC, nullable=False, enum=True),
        C("implicit", "BOOLEAN", "True for an unexpressed participant (dst is NULL).",
          nullable=False),
        C("ord", "INTEGER", "Position in the upstream frame.", nullable=False),
        *EDGE_COLS,
    ), ("src", "ord")),

    Table("dominance", "index",
          "Transitive closure of the tree: every word group and every token it dominates. "
          "Turns tree questions into plain joins.", (
        C("wg_id", "VARCHAR", "Dominating word group.", ref="wg", label="DOMINATES",
          nullable=False),
        C("token_id", "VARCHAR", "Dominated token.", ref="token", label="DOMINATES",
          nullable=False),
        C("dist", "INTEGER", "Levels between them (1 = parent).", nullable=False),
    ), ("wg_id", "token_id")),
)

BY_NAME: dict[str, Table] = {t.name: t for t in TABLES}


def ddl(table: Table) -> str:
    cols = ",\n  ".join(
        f'"{c.name}" {c.type}' + ("" if c.nullable else " NOT NULL") for c in table.columns)
    pk = f",\n  PRIMARY KEY ({', '.join(table.pk)})" if table.kind == "node" else ""
    return f'CREATE TABLE "{table.name}" (\n  {cols}{pk}\n)'


def fk_edges() -> list[tuple[Table, Column]]:
    """Every foreign-key relation, as (table, column)."""
    return [(t, c) for t in TABLES for c in t.refs if t.kind == "node"]


def edge_view_sql() -> str:
    """``edge(src, dst, label, tier, src_table, dst_table)``: every relation in one view.

    Foreign keys are upstream data by construction; edge tables carry their
    own tier. Implicit participants (NULL dst) are left out -- a view of
    connections has no edge to nowhere.
    """
    parts = []
    for t, c in fk_edges():
        parts.append(f"SELECT id AS src, \"{c.name}\" AS dst, '{c.label}' AS label, "
                     f"'data' AS tier, '{t.name}' AS src_table, '{c.ref}' AS dst_table "
                     f"FROM \"{t.name}\" WHERE \"{c.name}\" IS NOT NULL")
    for t in TABLES:
        if t.kind == "edge":
            dst = t.column("dst")
            parts.append(f"SELECT src, dst, '{dst.label}' AS label, tier, "
                         f"'token' AS src_table, '{dst.ref}' AS dst_table "
                         f"FROM \"{t.name}\" WHERE dst IS NOT NULL")
    return "CREATE VIEW edge AS\n" + "\nUNION ALL\n".join(parts)


def components() -> set[str]:
    return {c.component for t in TABLES for c in t.columns}
