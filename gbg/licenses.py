"""Which licenses count as open, in one place, pinned by a test.

The project rule is "open only": anything a user of the built graph may
redistribute, commercially or not, with attribution at most. Share-alike
(CC BY-SA) is deliberately NOT here yet: it is open, but it would bind every
derived artifact to the same license, and that is a decision for a person,
not a default (docs/DESIGN.md, open questions).

The check is applied per *field*, not per source, because MACULA licenses by
component: its SBLGNT text and Clear's annotations are CC BY 4.0, the Berean
glosses are public domain -- and its Louw-Nida columns come from UBS MARBLE
"used with permission". A per-source check would pass that data straight
through under MACULA's headline CC BY.
"""

from __future__ import annotations

#: SPDX ids (LicenseRef- for the one SPDX has no id for).
OPEN_LICENSES: frozenset[str] = frozenset({
    "CC-BY-4.0",
    "CC0-1.0",
    "LicenseRef-PublicDomain",
})


def is_open(license_id: str | None) -> bool:
    return license_id in OPEN_LICENSES
