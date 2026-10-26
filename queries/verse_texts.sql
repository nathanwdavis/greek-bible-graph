-- name: verse_texts
-- description: The Greek and a word-by-word English line (Cherith; · where a word has no gloss)
-- description: for a batch of verses, in canonical order -- for reading candidates and writing
-- description: an analysis without opening the database directly.
-- param: verses verses -- references or verse ids separated by ;, e.g. "Heb 4:13; Rom 11:33-34"
-- cites: verse
SELECT v.id, b.sbl || ' ' || v.chapter || ':' || v.verse AS ref, v.text AS greek,
       (SELECT string_agg(coalesce(t.english, '·'), ' ' ORDER BY t.ord)
        FROM token t WHERE t.verse_id = v.id) AS english
FROM verse v
JOIN book b ON b.id = v.book_id
WHERE list_contains($verses, v.id)
ORDER BY v.ord
