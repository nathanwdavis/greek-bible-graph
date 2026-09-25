-- name: verses_split_across_sentences
-- description: Verses whose words belong to more than one sentence: the evidence that
-- description: verse and sentence are independent hierarchies.
-- param: scope passage optional -- limit to a passage
-- cites: verse
SELECT v.id AS verse_id, v.text, count(DISTINCT t.sentence_id) AS n_sentences
FROM verse v
JOIN token t ON t.verse_id = v.id
WHERE t.ord BETWEEN $scope_first AND $scope_last
GROUP BY v.id, v.text, v.ord
HAVING count(DISTINCT t.sentence_id) > 1
ORDER BY v.ord
