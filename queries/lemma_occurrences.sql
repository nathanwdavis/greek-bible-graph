-- name: lemma_occurrences
-- description: Every occurrence of a lemma (dictionary form), in text order, with
-- description: its morphology and gloss. Lemma matching is exact (accents matter).
-- param: lemma lemma -- the dictionary form, e.g. θεός
-- param: scope passage optional -- limit to a passage, e.g. "Phlm" or "Rom 1-8"
-- cites: token
SELECT t.id, t.ref, t.surface, t.lemma, t.morph, t.gloss, t.verse_id
FROM token t
WHERE t.lemma = $lemma
  AND t.ord BETWEEN $scope_first AND $scope_last
ORDER BY t.ord
