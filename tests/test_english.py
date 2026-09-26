"""gbg.english: each normalisation step pinned, in the order it must run.

Every test breaks exactly one step: if the steps were reordered or one were
dropped, exactly the named test fails.
"""

import pytest

from gbg import english
from gbg.english import gloss_terms, query_terms


def test_no_gloss_is_none_not_empty():
    # NULL (no gloss: mostly articles) and "only stopwords" are different facts.
    assert gloss_terms(None) == (None, False)
    assert gloss_terms("the") == ([], False)


def test_lowercase_runs_before_the_irregular_table():
    assert gloss_terms("Knew") == (["know"], False)


def test_bracketed_insertions_are_dropped_with_their_content():
    # "[how]" is the translator's addition, not the Greek word's meaning.
    assert gloss_terms("you do know [how]") == (["know"], False)
    assert gloss_terms("[the] knowledge") == (["knowledg"], False)


def test_split_phrase_mark_is_a_space():
    assert gloss_terms("made ~ known") == (["make", "know"], False)


def test_hyphens_split_words():
    assert gloss_terms("heart-knowing") == (["heart", "know"], False)


def test_irregular_forms_map_before_stemming():
    # The stemmer alone leaves these untouched; that is why the table exists.
    assert english._STEMMER.stemWord("hidden") == "hidden"
    assert gloss_terms("hidden") == (["hide"], False)
    assert gloss_terms("foreknew") == gloss_terms("foreknown") == (["foreknow"], False)


def test_regular_inflection_is_stemmed():
    assert {tuple(gloss_terms(g)[0]) for g in ("know", "knows", "knowing")} == {("know",)}
    assert gloss_terms("appointed") == gloss_terms("appoint")


def test_leading_negator_negates_instead_of_becoming_a_term():
    assert gloss_terms("not know") == (["know"], True)
    assert gloss_terms("without knowing") == (["know"], True)
    # a stopword ahead of the negator does not stop it counting
    assert gloss_terms("do not know") == (["know"], True)


def test_negator_after_the_content_does_not_negate_it():
    assert gloss_terms("know not") == (["know"], False)


def test_stopwords_are_dropped_and_terms_are_distinct_in_order():
    assert gloss_terms("who knows the heart") == (["know", "heart"], False)
    assert gloss_terms("know and knew") == (["know"], False)


def test_curly_apostrophe_is_an_apostrophe():
    assert gloss_terms("God’s") == gloss_terms("God's") == (["god"], False)


def test_query_terms_meet_the_stored_terms():
    # What a person types must land on what the build stored.
    for typed, gloss in [("knew", "known"), ("hide", "hidden"), ("reveal", "revealed")]:
        assert query_terms(typed) == gloss_terms(gloss)[0]


def test_query_of_only_stopwords_is_empty():
    assert query_terms("the, of, not") == []


@pytest.mark.parametrize("form,base", sorted(english.IRREGULAR.items()))
def test_irregular_table_is_one_step(form, base):
    # A chain (a -> b -> c) would need a loop; the table must map straight to a base.
    assert base not in english.IRREGULAR, f"{form} -> {base} -> {english.IRREGULAR[base]}"
