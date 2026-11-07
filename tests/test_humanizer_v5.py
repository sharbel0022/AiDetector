"""Bounded regressions for meaning-bearing surface changes, not semantic proof."""
import pytest

from ai.humanizer.meaning import changed_risk_categories
from ai.humanizer.validation import PreservationError, protect_text, restore_text


@pytest.mark.parametrize(('source', 'candidate', 'risk'), [
    ('The pilot started before the inspection.', 'The pilot started after the inspection.', 'timeline_before'),
    ('Försöket började innan granskningen.', 'Försöket började efter granskningen.', 'timeline_before'),
    ('The team previously supported the proposal.', 'The team currently supported the proposal.', 'timeline_before'),
    ('The test will continue until approval.', 'The test will continue after approval.', 'timeline_until'),
    ('The treatment can reduce pain.', 'The treatment reduces pain.', 'modality'),
    ('Behandlingen kan minska smärtan.', 'Behandlingen minskar smärtan.', 'modality'),
    ('It is unlikely that the plan helps.', 'It is likely that the plan helps.', 'likelihood_low'),
    ('The observations suggest a benefit.', 'The observations prove a benefit.', 'uncertainty'),
    ('The variables were associated.', 'The variables cause the change.', 'causation'),
    ('Observationerna följdes åt.', 'Observationerna orsakar förändringen.', 'causation'),
    ('The team did not approve it. The group signed it.', 'The team approved it. The group did not sign it.', 'marker_scope'),
    ('Teamet godkände inte utkastet; gruppen skrev under.', 'Teamet godkände utkastet; gruppen skrev inte under.', 'marker_scope'),
])
def test_new_bounded_risk_checks_reject_demonstrated_meaning_changes(source, candidate, risk):
    assert risk in changed_risk_categories(source, candidate)
    with pytest.raises(PreservationError):
        restore_text(candidate, {}, source)


@pytest.mark.parametrize('source', [
    'Alice informed Bob about the decision.',
    'Alice recorded 12 mg. Bob recorded 15 mg.',
    'Maria arrived on 2 May 2025 before Johan arrived on 3 May 2025.',
])
def test_reordering_same_exact_anchors_cannot_swap_actor_quantity_or_dates(source):
    protected, mapping = protect_text(source)
    keys = list(mapping)
    assert len(keys) >= 2
    candidate = protected.replace(keys[0], 'SWAP').replace(keys[1], keys[0]).replace('SWAP', keys[1])
    with pytest.raises(PreservationError):
        restore_text(candidate, mapping, source)


def test_negation_cannot_move_between_actors_when_sentence_count_changes():
    source = 'Alice did not approve it. Bob signed it.'
    protected, mapping = protect_text(source)
    candidate = protected.replace('did not approve it.', 'approved it and').replace('signed it', 'did not sign it')
    with pytest.raises(PreservationError):
        restore_text(candidate, mapping, source)


def test_parenthetical_author_year_reference_is_an_exact_anchor():
    source = 'The evidence remains preliminary (Smith et al., 2024, p. 12).'
    protected, mapping = protect_text(source)
    assert '(Smith et al., 2024, p. 12)' in mapping.values()
    assert restore_text(protected, mapping, source) == source


@pytest.mark.parametrize(('source', 'candidate'), [
    ('The test began before the review.', 'The test started prior to the review.'),
    ('Försöket började innan granskningen.', 'Försöket startade före granskningen.'),
    ('The observations suggest a benefit.', 'The observations indicate a benefit.'),
    ('The treatment may reduce pain.', 'The treatment might ease pain.'),
    ('It is probably helpful.', 'It is likely helpful.'),
    ('The group did not approve it. The team signed it.', "The group didn't approve it. The team signed it."),
])
def test_recognized_safe_local_edits_remain_possible(source, candidate):
    assert restore_text(candidate, {}, source) == candidate


def test_unchanged_quoted_risk_words_do_not_block_surrounding_edits():
    source = 'Alice recorded "before after may not" and saved [Before, 2024].'
    protected, mapping = protect_text(source)
    candidate = protected.replace('recorded', 'noted').replace('saved', 'retained')
    assert restore_text(candidate, mapping, source) == source.replace('recorded', 'noted').replace('saved', 'retained')


def test_original_anchor_offsets_survive_identical_substrings_in_editable_words():
    source = 'wordMay may improve. May reviewed the result.'
    protected, mapping = protect_text(source)
    assert restore_text(protected, mapping, source) == source
