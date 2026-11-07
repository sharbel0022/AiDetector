"""Deterministic UI contracts. These fixtures provide no detector-quality evidence."""
import re
import unicodedata


def utf16_length(text):
    return len(text.encode('utf-16-le')) // 2


def source_word_count(text):
    """Same Unicode L/N/M and internal apostrophe/hyphen rule as analyzer.mjs."""
    index, count = 0, 0
    category = lambda char: unicodedata.category(char)[0]
    while index < len(text):
        if category(text[index]) not in 'LN':
            index += 1
            continue
        count += 1
        index += 1
        while index < len(text) and category(text[index]) in 'LNM':
            index += 1
        while index + 1 < len(text) and text[index] in "’'-" and category(text[index + 1]) in 'LN':
            index += 2
            while index < len(text) and category(text[index]) in 'LNM':
                index += 1
    return count


def detection_fixture(text, *, verified=False, raw_unvalidated_scores=False):
    segments = []
    categories = ['ai_like', 'human_like', 'uncertain', 'unassessed']
    for match in re.finditer(r'[^\n]+', text):
        raw = match.group()
        value = raw.strip()
        if not value:
            continue
        index = len(segments)
        start = match.start() + len(raw) - len(raw.lstrip())
        end = start + len(value)
        # Match runtime span edges: preserve paragraph whitespace as source
        # gaps, outside the interactive segment buttons.
        segments.append({
            'id': f'fixture-{index + 1}',
            'start': utf16_length(text[:start]),
            'end': utf16_length(text[:end]),
            'text': value,
            'wordCount': source_word_count(value),
            'eligible': not verified or categories[index % len(categories)] != 'unassessed',
            'category': categories[index % len(categories)] if verified else 'unassessed',
            'probability': 0.87 if verified or raw_unvalidated_scores else None,
            'reason': 'Kontrollerad UI-fixture. Ingen uppmätt modellkvalitet.' if verified else 'Segmentmetoden är inte validerad. Segmentet lämnas utan bedömning.',
        })
    assessed = [item for item in segments if item['category'] != 'unassessed']
    analyzed = sum(item['wordCount'] for item in assessed) if verified else sum(item['wordCount'] for item in segments)
    flagged = [item for item in segments if item['category'] == 'ai_like']
    flagged_words = sum(item['wordCount'] for item in flagged)
    return {
        'detector': {
            'modelVersion': 'UI-fixture-only-v5',
            'category': 'mixed' if verified else 'insufficient' if analyzed < 20 else 'uncertain',
            'documentProbability': 0.72 if verified else 0.98 if raw_unvalidated_scores else None,
            'aiMarkedPercent': round(flagged_words / analyzed * 100, 2) if verified and analyzed else 99 if raw_unvalidated_scores else None,
            'documentValidated': verified, 'calibrationValidated': verified,
            'segmentValidated': verified, 'segmentCalibrationValidated': False,
            'status': 'analyzed' if verified else 'unvalidated',
            'reasons': ['Endast UI-fixture; detta verifierar inga detektionsresultat.'],
            'analyzedWords': analyzed, 'flaggedWords': flagged_words,
            'excludedWords': sum(item['wordCount'] for item in segments) - analyzed,
            'totalSegments': len(segments), 'flaggedSegments': len(flagged),
            'calibrationStatus': 'fixture-only' if verified else 'not_validated',
        },
        'segments': segments,
    }


USAGE_FIXTURE = {
    'provider': 'mock', 'model': 'test-only', 'recorded_at': '2026-11-07T12:00:00Z',
    'latency_ms': 120, 'input_tokens': 100, 'output_tokens': 25,
    'total_tokens': 125, 'cached_input_tokens': None,
    'cost': {'currency': 'USD', 'estimated_amount': 0.001, 'pricing_version': 'ui-fixture-only', 'status': 'estimated'},
}

USAGE_TOTALS_FIXTURE = {
    'period': {'start': '2026-11-07T00:00:00Z', 'end': '2026-11-08T00:00:00Z', 'timezone': 'UTC'},
    'requests': 2, 'input_tokens': 100, 'output_tokens': 25, 'total_tokens': 125, 'cached_input_tokens': None,
    'unreported_counters': {'input_tokens': 1, 'output_tokens': 1, 'total_tokens': 1, 'cached_input_tokens': 2},
    'estimated_cost': {'currency': 'USD', 'amount': 0.001, 'unknown_requests': 1, 'not_applicable_requests': 0},
}
