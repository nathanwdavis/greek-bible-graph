-- name: lemma_by_book
-- description: How often a lemma occurs in each book (books where it is absent are omitted).
-- description: For the edition-wide total, `gbg resolve lemma:<lemma>`.
-- param: lemma lemma -- the dictionary form, e.g. ἀγάπη
-- cites: book
SELECT b.id AS book_id, b.name, count(*) AS n
FROM token t JOIN book b ON b.id = t.book_id
WHERE t.lemma = $lemma
GROUP BY b.id, b.name, b.ord
ORDER BY b.ord
