# Notice: data sources and attribution

The **code** in this repository is MIT-licensed (see `LICENSE`). The **data**
it builds from, and therefore every built artifact (`build/`, Parquet files,
the DuckDB database, query results), is licensed by its owners as below.
Built artifacts are adaptations: the text is NFC-normalised, fields are
renamed and restructured into node and edge tables, and non-open fields are
removed.

## MACULA Greek Linguistic Datasets -- CC BY 4.0

MACULA Greek Linguistic Datasets, available at https://github.com/Clear-Bible/macula-greek/
© 2022-2024 Biblica, Inc., licensed under CC BY 4.0. Pinned by commit in
`sources.lock.json`. MACULA licenses by component; this build uses:

| Component | Fields used | License | Attribution |
|---|---|---|---|
| SBLGNT text | surface text, `after`, `normalized` | CC BY 4.0 | SBL Greek New Testament (SBLGNT), copyright 2010 by the Society of Biblical Literature and Logos Bible Software, https://github.com/LogosBible/SBLGNT |
| Clear (MACULA) | ids, morphology, lemmas, Strong's, syntax trees, roles, semantic frames, participant referents | CC BY 4.0 | MACULA Greek Linguistic Datasets, available at https://github.com/Clear-Bible/macula-greek/ |
| Berean Interlinear | `gloss` | Public domain | Berean Interlinear Bible glosses, placed in the public domain on 2023-04-30, https://interlinearbible.com/ |
| Cherith Glosses | `english` (and the search terms derived from it) | CC BY 4.0 | Cherith Glosses for the Greek New Testament, by Andi Wu, Copyright (C) 2023 by Cherith Analytics |
| Clear synonyms | Strong's-to-Strong's semantic proximity (`lemma_proximity`) | CC BY 4.0 | MACULA Greek Linguistic Datasets (Clear synonyms: Strong's-to-Strong's semantic proximity, sources/Clear/synonyms), available at https://github.com/Clear-Bible/macula-greek/ |

**Excluded:** MACULA's Louw-Nida semantic domains (`domain`, `ln`) come from
the United Bible Societies MARBLE project and are "used with permission", not
under an open license. They are removed at parse time and from the test
fixtures, and no built artifact contains them.

## Topical indexes -- CC BY

| Source | What | License | Attribution |
|---|---|---|---|
| Nave's Topical Bible | topics, subtopics and the verses they cite (`naves_topic`, `naves_topic_verse`) | CC BY 4.0 | Nave's Topical Bible (Orville J. Nave, 1896), as structured data in BibleData by Brady Stephenson, https://github.com/BradyStephenson/bible-data (CC BY 4.0) |
| OpenBible.info topics | topics and the verses readers voted for (`openbible_topic`, `openbible_topic_verse`) | CC BY | Topical Bible data from OpenBible.info, https://www.openbible.info/topics (CC BY) |

Nave's 1896 text is in the public domain; the structured CSV is licensed CC BY 4.0
by its repository, which does not say how it was digitised. The OpenBible data is
regenerated weekly without version history, so a dated snapshot is committed under
`vendor/openbible/` and pinned by sha256.

The fixture under `tests/fixtures/macula/` is a subset of the above (Philemon,
2 John, 3 John) with the excluded fields removed; see
`tests/fixtures/ATTRIBUTION.md`.
