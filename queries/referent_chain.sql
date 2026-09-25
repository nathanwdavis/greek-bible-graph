-- name: referent_chain
-- description: Follow a word's referent (its first refers_to target) step by step to
-- description: the word it ultimately refers to. Guarded against cycles, which exist.
-- description: A word can have several referents; this follows the first at each
-- description: step -- list the rest with SELECT * FROM refers_to WHERE src = '<id>'.
-- param: token token -- the referring word, e.g. sblgnt:n57001012003 or "PHM 1:12!3"
-- cites: token
WITH RECURSIVE chain(step, id, path) AS (
    SELECT 0, $token, [$token]
    UNION ALL
    SELECT c.step + 1, r.dst, list_append(c.path, r.dst)
    FROM chain c
    JOIN refers_to r ON r.src = c.id AND r.ord = 1
    WHERE r.dst IS NOT NULL
      AND NOT list_contains(c.path, r.dst)
      AND c.step < 50
)
SELECT c.step, t.id, t.ref, t.surface, t.lemma, t.gloss
FROM chain c JOIN token t ON t.id = c.id
ORDER BY c.step
