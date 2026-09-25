-- name: shared_lemma_trigrams
-- description: Sequences of three lemmas (within one sentence) that occur in both
-- description: passages: a cheap, exact signal of shared wording. One hash join --
-- description: the replacement for all-pairs similarity, and the seed of the LXX
-- description: intertext candidates (docs/DESIGN.md).
-- param: a passage -- first passage, e.g. "2 John"
-- param: b passage -- second passage, e.g. "3 John"
-- cites: token
WITH tri AS (
    SELECT id, ord, lemma AS l1,
           lead(lemma, 1) OVER w AS l2,
           lead(lemma, 2) OVER w AS l3
    FROM token
    WINDOW w AS (PARTITION BY sentence_id ORDER BY ord)
),
a AS (SELECT * FROM tri WHERE l3 IS NOT NULL AND ord BETWEEN $a_first AND $a_last),
b AS (SELECT * FROM tri WHERE l3 IS NOT NULL AND ord BETWEEN $b_first AND $b_last)
SELECT a.l1 || ' ' || a.l2 || ' ' || a.l3 AS trigram,
       min(a.id) AS first_in_a, min(b.id) AS first_in_b,
       count(DISTINCT a.id) AS n_a, count(DISTINCT b.id) AS n_b
FROM a JOIN b ON a.l1 = b.l1 AND a.l2 = b.l2 AND a.l3 = b.l3
GROUP BY 1
ORDER BY first_in_a
