-- name: verse_topics
-- description: Which topics of the two topical indexes cite the given verses -- what human
-- description: indexers thought a passage is about. OpenBible rows carry a vote score.
-- param: verses verses -- references or verse ids separated by ;, e.g. "Heb 4:13"
-- cites: verse
SELECT e.dst AS verse_id, 'naves' AS source, t.id AS topic_id, t.path AS topic,
       NULL::INTEGER AS votes
FROM naves_topic_verse e JOIN naves_topic t ON t.id = e.src
WHERE list_contains($verses, e.dst)
UNION ALL
SELECT e.dst, 'openbible', t.id, t.title, e.votes
FROM openbible_topic_verse e JOIN openbible_topic t ON t.id = e.src
WHERE list_contains($verses, e.dst)
ORDER BY verse_id, source, votes DESC NULLS LAST, topic_id
