"""V5 local detector and exact source segments, preserving all V4 style fields."""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

from . import features
from .evidence import gate_results
from .linear import MAX_MODEL_BYTES, calibrated_probability, digest, margin, validate_model

SCHEMA = 'textlab-v5-detector-1'
DEFAULT_MODEL = Path(__file__).resolve().parents[2] / 'models' / 'v5' / 'detector.json'
MIN_SEGMENT_WORDS = 12


def _reject_constant(_value):
    raise ValueError('Nonfinite JSON number')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


@lru_cache(maxsize=4)
def _load_cached(path, modified, size, inode):
    del modified, size, inode
    with open(path, 'rb') as stream:
        raw = stream.read(MAX_MODEL_BYTES + 1)
    if len(raw) > MAX_MODEL_BYTES:
        raise ValueError('Model exceeds size limit')
    artifact = json.loads(raw, parse_constant=_reject_constant, object_pairs_hook=_unique_object)
    if not isinstance(artifact, dict) or artifact.get('schemaVersion') != SCHEMA:
        raise ValueError('Unsupported detector artifact')
    if not isinstance(artifact.get('modelVersion'), str) or not 1 <= len(artifact['modelVersion']) <= 120:
        raise ValueError('Invalid model version')
    validate_model(artifact.get('documentModel'))
    if artifact.get('segmentModel') is not None:
        validate_model(artifact['segmentModel'])
    if artifact.get('artifactSha256') != digest({key: value for key, value in artifact.items() if key != 'artifactSha256'}):
        raise ValueError('Detector artifact integrity check failed')
    return artifact, gate_results(artifact)


def load_artifact(path=None):
    selected = Path(path) if path is not None else DEFAULT_MODEL
    stat = selected.stat()
    if not 0 < stat.st_size <= MAX_MODEL_BYTES:
        raise ValueError('Invalid model file size')
    return _load_cached(str(selected.resolve()), stat.st_mtime_ns, stat.st_size, stat.st_ino)


def _language_and_style(text, requested):
    if requested not in ('auto', 'sv', 'en'):
        raise ValueError('Language must be auto, sv, or en')
    # Reuse the frozen rule, selecting its detected language for auto mode. No
    # behavior inside features.py changes, including its JS parity contract.
    initial = features.analyze_text(text, 'en' if requested == 'auto' else requested)
    detected = initial['languageAssessment']['detected']
    if requested == 'auto' and detected == 'sv':
        initial = features.analyze_text(text, 'sv')
    assessment = initial['languageAssessment']
    assessment.update({'requested': requested,
                       'selected': detected if requested == 'auto' else requested,
                       'effective': detected if assessment['status'] == 'supported' else None,
                       'method': 'function-word-and-script-v1', 'confidence': None})
    return initial


def _category(score, thresholds):
    if score >= thresholds['aiMin']:
        return 'ai_like'
    if score <= thresholds['humanMax']:
        return 'human_like'
    return 'uncertain'


def analyze_v5(text: str, language: str = 'auto', model_path=None) -> dict:
    """Return V4 style information and separately gated V5 inference.

    The loader caches at most four stat-keyed trusted local artifacts. Request
    text stays local; malformed/missing models leave descriptive style usable.
    """
    result = _language_and_style(text, language)
    artifact, gates, available = None, gate_results({}), False
    try:
        artifact, gates = load_artifact(model_path)
        available = True
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        pass
    supported = result['languageAssessment']['status'] == 'supported'
    document_eligible = supported and result['wordCount'] >= 80 and result['sentenceCount'] >= 4
    document_score = margin(artifact['documentModel'], text) if available and document_eligible else None
    if document_score is None:
        document_eligible = False
    segment_model = artifact.get('segmentModel') if available else None
    segments, analyzed_words, flagged_words, flagged_segments = [], 0, 0, 0
    for index, sentence in enumerate(result['sentences']):
        word_count = sentence['words']
        language_ok = supported
        if language_ok:
            offsets = [0]
            for char in sentence['text']:
                offsets.append(offsets[-1] + (2 if ord(char) > 0xffff else 1))
            tokens = features._words(sentence['text'], offsets)
            assessment = features._language(sentence['text'], tokens, result['languageAssessment']['effective'])
            language_ok = assessment['status'] == 'supported'
        eligible = available and language_ok and word_count >= MIN_SEGMENT_WORDS
        score = None
        if eligible and available:
            # An unvalidated document model can establish vocabulary coverage
            # for diagnostics, but cannot classify or calibrate a segment.
            score = margin(segment_model or artifact['documentModel'], sentence['text'])
            eligible = score is not None
        category, probability = 'unassessed', None
        if not language_ok:
            reason = 'Språket kan inte bedömas säkert för detta segment.'
        elif word_count < MIN_SEGMENT_WORDS:
            reason = 'Segmentet innehåller färre än 12 ord.'
        elif not available:
            reason = 'Detektormodellen är inte tillgänglig.'
        elif score is None:
            reason = 'Segmentet saknar ord- eller teckenföljder som modellen känner igen.'
        elif not gates['segment']['passed']:
            reason = 'Segmentklassningen saknar oberoende validering; stilträffar visar inte ursprung.'
        else:
            category = _category(score, artifact['segmentThresholds'])
            reason = {'ai_like': 'Segmentets egen modellpoäng passerar den validerade AI-tröskeln.',
                      'human_like': 'Segmentets egen modellpoäng ligger under den validerade mänsklig-tröskeln.',
                      'uncertain': 'Segmentets egen modellpoäng ligger mellan de validerade trösklarna.'}[category]
            if gates['segmentCalibration']['passed']:
                probability = calibrated_probability(artifact['segmentCalibration'], score)
        if eligible:
            analyzed_words += word_count
        if category == 'ai_like':
            flagged_words += word_count
            flagged_segments += 1
        segments.append({'id': f's{index+1}', 'start': sentence['start'], 'end': sentence['end'],
                         'text': sentence['text'], 'wordCount': word_count, 'category': category,
                         'probability': probability, 'reason': reason, 'eligible': eligible})
    category = 'uncertain' if document_eligible else 'insufficient'
    probability = None
    if document_eligible and gates['document']['passed']:
        category = _category(document_score, artifact['documentThresholds'])
        if gates['calibration']['passed']:
            probability = calibrated_probability(artifact['documentCalibration'], document_score)
    share = 100 * flagged_words / analyzed_words if gates['segment']['passed'] and analyzed_words else None
    if gates['segment']['passed'] and {'ai_like', 'human_like'} <= {segment['category'] for segment in segments}:
        # Mixed is an inference from independently validated local decisions;
        # it neither changes nor substitutes for the document probability.
        category = 'mixed'
    reasons = list(gates['document']['reasons'])
    if not available:
        reasons = ['model_unavailable']
    elif not document_eligible:
        reasons = result['abstentionReasons'] + ['document_not_eligible'] + reasons
    status = 'model_unavailable' if not available else 'abstained' if not document_eligible else 'available' if gates['document']['passed'] else 'unverified'
    result.update({'detector': {
        'version': 'textlab-v5', 'modelVersion': artifact['modelVersion'] if available else None,
        'category': category, 'documentProbability': probability, 'aiMarkedPercent': share,
        'documentValidated': gates['document']['passed'], 'calibrationValidated': gates['calibration']['passed'],
        'segmentValidated': gates['segment']['passed'], 'segmentCalibrationValidated': gates['segmentCalibration']['passed'],
        'status': status, 'reasons': reasons, 'analyzedWords': analyzed_words,
        'flaggedWords': flagged_words, 'excludedWords': result['wordCount']-analyzed_words,
        'totalSegments': len(segments), 'flaggedSegments': flagged_segments,
        'calibrationStatus': 'validated' if gates['calibration']['passed'] else 'unavailable',
        'gates': gates, 'scoreSemantics': 'calibrated_class_probability' if probability is not None else 'unavailable',
    }, 'segments': segments})
    return result
