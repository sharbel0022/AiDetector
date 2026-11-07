"""Explicit preservation must survive overlapping automatic and manual spans."""
import pytest

from ai.humanizer.validation import PreservationError, protect_text, restore_text


def test_explicit_phrase_overlapping_name_cannot_be_partially_edited():
    original = 'Alice Smith works here.'
    protected, mapping = protect_text(original, ['Smith works'])
    candidate = protected.replace('works', 'rests')
    # If "works" remains editable, a supposedly exact phrase can disappear.
    try:
        output = restore_text(candidate, mapping, original)
    except PreservationError:
        return
    assert 'Smith works' in output


@pytest.mark.parametrize('original,terms', [
    ('Alice Smith works here.', ['Smith works']),
    ('Alice Smith works here.', ['Alice Smith', 'Smith works', 'works here']),
    ('We quote "exact words" today.', ['words" today']),
    ('The code is ababa.', ['aba', 'bab']),
    ('Åsa Öberg arbetar här.', ['Öberg arbetar']),
])
def test_overlapping_terms_roundtrip_and_are_fully_opaque(original, terms):
    protected, mapping = protect_text(original, terms)
    assert restore_text(protected, mapping, original) == original
    for term in terms:
        assert any(term in value for value in mapping.values())


def test_adjacent_nonoverlapping_facts_do_not_hide_editable_surroundings():
    original = 'Alice Smith works with Bob Jones.'
    protected, mapping = protect_text(original, ['Alice Smith'])
    assert ' works with ' in protected
    assert set(mapping.values()) == {'Alice Smith', 'Bob Jones'}


def test_explicit_phrase_must_be_preserved_in_each_occurrence():
    original = 'Alice Smith works here. Smith works remotely.'
    protected, mapping = protect_text(original, ['Smith works'])
    assert 'works' not in protected
    token = next(key for key, value in mapping.items() if value == 'Smith works')
    with pytest.raises(PreservationError):
        restore_text(protected.replace(token, ''), mapping, original)
