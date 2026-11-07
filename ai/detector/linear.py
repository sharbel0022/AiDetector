"""Bounded, dependency-free inference for exported word/character TF-IDF models.

Only numerical JSON is supported. This module never imports sklearn, unpickles
objects, evaluates code, or exposes a logistic margin as a probability.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
import re

MAX_FEATURES = 30_000
MAX_MODEL_BYTES = 8_000_000


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def finite(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def validate_model(model):
    if not isinstance(model, dict) or model.get('kind') != 'tfidf_logistic':
        raise ValueError('Unsupported numerical model')
    blocks = model.get('blocks')
    if not isinstance(blocks, list) or not 1 <= len(blocks) <= 2:
        raise ValueError('Model must contain one or two feature blocks')
    total = 0
    seen = set()
    for block in blocks:
        if not isinstance(block, dict):
            raise ValueError('Invalid feature block')
        analyzer = block.get('analyzer')
        expected = [3, 5] if analyzer == 'char' else [1, 2]
        if analyzer not in ('char', 'word') or analyzer in seen or block.get('ngramRange') != expected:
            raise ValueError('Unsupported feature configuration')
        seen.add(analyzer)
        vocabulary, idf = block.get('vocabulary'), block.get('idf')
        if not isinstance(vocabulary, dict) or not 1 <= len(vocabulary) <= MAX_FEATURES:
            raise ValueError('Invalid vocabulary size')
        indices = list(vocabulary.values())
        if any(not isinstance(i, int) or isinstance(i, bool) for i in indices) or sorted(indices) != list(range(len(indices))):
            raise ValueError('Vocabulary indices must be unique and contiguous')
        if any(not isinstance(term, str) or not term or len(term) > 12000 or
               (analyzer == 'char' and not 3 <= len(term) <= 5) for term in vocabulary):
            raise ValueError('Invalid vocabulary term')
        if not isinstance(idf, list) or len(idf) != len(vocabulary) or any(not finite(x) or not 0 < x < 1e6 for x in idf):
            raise ValueError('Invalid IDF weights')
        total += len(vocabulary)
    coefficients = model.get('coefficients')
    if total > MAX_FEATURES or not isinstance(coefficients, list) or len(coefficients) != total:
        raise ValueError('Invalid coefficient dimensions')
    if any(not finite(x) or abs(x) > 1e6 for x in coefficients) or not finite(model.get('intercept')) or abs(model['intercept']) > 1e6:
        raise ValueError('Invalid numerical weights')
    if model.get('normalization') != 'block-l2-then-global-l2':
        raise ValueError('Unsupported normalization')
    return model


def _counts(block, text):
    value = text.lower()
    if block['analyzer'] == 'char':
        # Exactly sklearn's char analyzer normalization, including Unicode space.
        value = re.sub(r'\s\s+', ' ', value)
        return Counter(value[i:i+n] for n in range(3, 6) for i in range(max(0, len(value)-n+1)))
    tokens = re.findall(r'(?u)\b\w\w+\b', value)
    return Counter(tokens + [' '.join(tokens[i:i+2]) for i in range(len(tokens)-1)])


def margin(model, text):
    """Return the linear score, or None for an out-of-vocabulary document.

    Callers validate the model once at load time. These scores are for offline
    diagnostic/calibration machinery; public responses do not include them.
    """
    offset, active_blocks, dots = 0, 0, []
    for block in model['blocks']:
        vocabulary = block['vocabulary']
        values = {vocabulary[t]: (1 + math.log(count)) * block['idf'][vocabulary[t]]
                  for t, count in _counts(block, text).items() if t in vocabulary}
        norm = math.sqrt(math.fsum(x*x for x in values.values()))
        if norm:
            active_blocks += 1
            dots.append(math.fsum(value * model['coefficients'][offset+i] for i, value in values.items()) / norm)
        offset += len(vocabulary)
    if not active_blocks:
        return None
    return model['intercept'] + math.fsum(dots) / math.sqrt(active_blocks)


def calibrated_probability(calibration, score):
    if not isinstance(calibration, dict) or calibration.get('method') != 'platt':
        raise ValueError('Missing fitted calibration')
    slope, intercept = calibration.get('slope'), calibration.get('intercept')
    if not finite(slope) or slope <= 0 or not finite(intercept) or not finite(score):
        raise ValueError('Invalid fitted calibration')
    value = slope * score + intercept
    if value >= 0:
        return 1 / (1 + math.exp(-value))
    exponential = math.exp(value)
    return exponential / (1 + exponential)
