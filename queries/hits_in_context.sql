-- name: hits_in_context
-- description: Turn hit words (any query's token ids) into readable passages: one row per
-- description: sentence containing a hit, with the verses it spans (citable), the Greek, and a
-- description: word-by-word English line (Cherith; · where a word has no gloss). Sentences
-- description: are for reading only -- cite verse or token ids, never the sentence. A sentence
-- description: can be long (Eph 1:3-14 is one); widen or narrow with gbg ref.
-- param: tokens tokens -- token ids or MACULA refs, comma-separated, e.g. a predicate_id column
-- cites: verse
SELECT f.verse_id AS first_verse, l.verse_id AS last_verse,
       list_sort(list_distinct(list(h.id))) AS hits,
       list_sort(list_distinct(list(h.verse_id))) AS hit_verses,
       s.text AS greek,
       (SELECT string_agg(coalesce(t.english, '·'), ' ' ORDER BY t.ord)
        FROM token t WHERE t.sentence_id = s.id) AS english
FROM token h
JOIN sentence s ON s.id = h.sentence_id
JOIN token f ON f.id = s.first_token
JOIN token l ON l.id = s.last_token
WHERE list_contains($tokens, h.id)
GROUP BY s.id, s.ord, s.text, f.verse_id, l.verse_id
ORDER BY s.ord
