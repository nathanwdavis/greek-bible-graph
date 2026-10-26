-- name: topics_matching
-- description: Topics in the two human topical indexes whose title matches a pattern
-- description: (case-insensitive regex): Nave's Topical Bible (1896; editorial, nested -- search
-- description: the full path, GOD > KNOWLEDGE OF) and OpenBible.info (readers' votes; flat,
-- description: broad, noisy). n_verses counts verses of this edition. Feed topic ids to
-- description: topic_verses. These find passages about a subject whatever their wording.
-- param: pattern text -- a regex, e.g. "knowledge of|omnisci"
-- cites: verse
SELECT id AS topic_id, 'naves' AS source, path AS topic, n_verses
FROM naves_topic WHERE regexp_matches(path, $pattern, 'i')
UNION ALL
SELECT id, 'openbible', title, n_verses
FROM openbible_topic WHERE regexp_matches(title, $pattern, 'i')
ORDER BY n_verses DESC, topic
