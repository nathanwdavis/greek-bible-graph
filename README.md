# greek-bible-graph

Open Greek interlinear Bible data -- the SBL Greek New Testament with MACULA
Greek's morphology, glosses, syntax trees and coreference -- built into a
deterministic, queryable corpus graph (DuckDB + Parquet), with a Claude Code
skill for asking it questions in plain English.

Sibling of [auto-zettel-skill](https://github.com/nathanwdavis/auto-zettel-skill):
that repo's notes will cite this graph's verse and token ids.

**Status:** prototype, NT only. The LXX is designed (see `docs/DESIGN.md`) but
not built.
