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
| Cherith Glosses | `english` | CC BY 4.0 | Cherith Glosses for the Greek New Testament, by Andi Wu, Copyright (C) 2023 by Cherith Analytics |

**Excluded:** MACULA's Louw-Nida semantic domains (`domain`, `ln`) come from
the United Bible Societies MARBLE project and are "used with permission", not
under an open license. They are removed at parse time and from the test
fixtures, and no built artifact contains them.

The fixture under `tests/fixtures/macula/` is a subset of the above (Philemon,
2 John, 3 John) with the excluded fields removed; see
`tests/fixtures/ATTRIBUTION.md`.
