import pytest
from pydantic import ValidationError

from ai.contracts import DetectRequest, ModelText, RewriteRequest


@pytest.mark.parametrize('contract,limit', [(DetectRequest, 12000), (RewriteRequest, 8000), (ModelText, 16000)])
def test_text_bounds_match_browser_utf16_length(contract, limit):
    assert contract(text='😀' * (limit // 2)).text == '😀' * (limit // 2)
    with pytest.raises(ValidationError):
        contract(text='😀' * (limit // 2) + 'a')


@pytest.mark.parametrize('contract', [DetectRequest, RewriteRequest, ModelText])
def test_invalid_unicode_surrogates_cannot_reach_json_serialization(contract):
    with pytest.raises(ValidationError):
        contract(text='Invalid \ud800 input value')


def test_explicit_terms_have_the_same_unicode_bounds_as_the_ui():
    with pytest.raises(ValidationError):
        RewriteRequest(text='😀' * 100, protected_terms=['😀' * 81])


def test_rewrite_minimum_also_matches_browser_utf16_units():
    assert RewriteRequest(text='😀' * 5).text == '😀' * 5
    with pytest.raises(ValidationError):
        RewriteRequest(text='😀' * 4)
