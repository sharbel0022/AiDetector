"""Explicit release policy for independent document/segment/calibration evidence.

These conservative requirements are release criteria, not empirical claims about
the shipped pilot. A JSON boolean cannot substitute for the evidence checks.
"""
from __future__ import annotations

import math

from .linear import digest, finite

POLICY_VERSION = 'textlab-v5-evidence-policy-1'
POLICY = {
    'minimumPerClass': 200, 'minimumPerLanguageClass': 100,
    'minimumFamiliesPerClass': 20, 'minimumLanguageFamiliesPerClass': 10,
    'maximumHumanFprUpper95': .05, 'minimumAiRecallLower95': .70,
    'minimumCoverage': .70, 'minimumSegmentPrecisionLower95': .90,
    'maximumCalibrationECE': .05, 'maximumCalibrationBrier': .20,
    'minimumCalibrationFitPerClass': 100,
}


def _finite_le(value, maximum):
    return finite(value) and 0 <= value <= maximum


def _finite_ge(value, minimum):
    return finite(value) and value >= minimum


def _count(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _probability(value):
    return finite(value) and 0 <= value <= 1


def _interval(value):
    return isinstance(value, list) and len(value) == 2 and all(_probability(item) for item in value) and value[0] <= value[1]


def _wilson(successes, count):
    if not count:
        return None
    z = 1.959963984540054
    proportion = successes/count
    denominator = 1 + z*z/count
    centre = (proportion + z*z/(2*count))/denominator
    width = z*math.sqrt(proportion*(1-proportion)/count + z*z/(4*count*count))/denominator
    return [max(0., centre-width), min(1., centre+width)]


def _valid_metric_counts(metrics):
    counts, families = metrics.get('classCounts', {}), metrics.get('familiesByLabel', {})
    if any(not _count(counts.get(label)) or not _count(families.get(label)) or families[label] > counts[label] for label in ('human', 'ai')):
        return False
    confusion = metrics.get('confusion', {})
    if any(not _count(confusion.get(key)) for key in ('tp', 'fp', 'tn', 'fn')):
        return False
    tp, fp, tn, fn = (confusion[key] for key in ('tp', 'fp', 'tn', 'fn'))
    if fp+tn > counts['human'] or tp+fn > counts['ai']:
        return False
    if any(not _count(metrics.get(key)) for key in ('total', 'assessed', 'binaryAssessed')):
        return False
    if metrics['total'] < sum(counts.values()) or metrics['assessed'] > metrics['total'] or metrics['binaryAssessed'] != tp+fp+tn+fn:
        return False
    if not _probability(metrics.get('coverage')) or metrics['coverage'] != metrics['assessed']/max(1, metrics['total']):
        return False
    expected = {'falsePositiveRate': _wilson(fp, fp+tn), 'recallAssessed': _wilson(tp, tp+fn), 'precision': _wilson(tp, tp+fp)}
    for key, value in expected.items():
        supplied = metrics.get('intervals95', {}).get(key)
        if not value or not _interval(supplied) or any(abs(left-right) > 1e-10 for left, right in zip(value, supplied, strict=True)):
            return False
    for key in ('falsePositiveRate', 'falseNegativeRate', 'recallAssessed', 'recallAllAI', 'precision', 'accuracyAssessed', 'f1', 'auroc'):
        if metrics.get(key) is not None and not _probability(metrics[key]):
            return False
    return True


def _classification_reasons(artifact, level):
    evidence = artifact.get('evidence', {}).get(level, {})
    reasons = []
    if evidence.get('evidenceUse') != 'fresh-independent-holdout':
        reasons.append('fresh_independent_' + level + '_test_missing')
    if evidence.get('testFrozenBeforeEvaluation') is not True:
        reasons.append('frozen_test_provenance_missing')
    audit = evidence.get('lineageAudit', {})
    if audit.get('passed') is not True or audit.get('independentSplits') is not True:
        reasons.append('independent_lineage_audit_missing')
    model = artifact.get('documentModel' if level == 'document' else 'segmentModel')
    if not model or evidence.get('modelSha256') != digest(model):
        reasons.append('model_evidence_binding_missing')
    thresholds = artifact.get('documentThresholds' if level == 'document' else 'segmentThresholds') or {}
    low, high = thresholds.get('humanMax'), thresholds.get('aiMin')
    if (not finite(low) or not finite(high) or low >= high or
            thresholds.get('selectionSplit') != 'validation' or
            evidence.get('thresholdsSha256') != digest(thresholds)):
        reasons.append('independently_selected_thresholds_missing')
    overall = evidence.get('metrics', {})
    for name, metrics in [('overall', overall), *[(lang, evidence.get('byLanguage', {}).get(lang, {})) for lang in ('sv', 'en')]]:
        minimum = POLICY['minimumPerClass'] if name == 'overall' else POLICY['minimumPerLanguageClass']
        family_minimum = POLICY['minimumFamiliesPerClass'] if name == 'overall' else POLICY['minimumLanguageFamiliesPerClass']
        counts = metrics.get('classCounts', {})
        families = metrics.get('familiesByLabel', {})
        if not _valid_metric_counts(metrics):
            reasons.append(name + '_invalid_metric_counts_or_intervals')
        if any(not _count(counts.get(label)) or counts[label] < minimum for label in ('human', 'ai')):
            reasons.append(name + '_sample_size_insufficient')
        if any(not _count(families.get(label)) or families[label] < family_minimum or
               (_count(counts.get(label)) and families[label] > counts[label]) for label in ('human', 'ai')):
            reasons.append(name + '_source_family_count_insufficient')
        intervals = metrics.get('intervals95', {})
        fpr, recall = intervals.get('falsePositiveRate'), intervals.get('recallAssessed')
        if not _interval(fpr) or not _finite_le(fpr[1], POLICY['maximumHumanFprUpper95']):
            reasons.append(name + '_human_false_positive_bound_not_met')
        if not _interval(recall) or not _finite_ge(recall[0], POLICY['minimumAiRecallLower95']):
            reasons.append(name + '_ai_recall_bound_not_met')
        if not _probability(metrics.get('coverage')) or not _finite_ge(metrics.get('coverage'), POLICY['minimumCoverage']):
            reasons.append(name + '_coverage_insufficient')
        if level == 'segment':
            precision = intervals.get('precision')
            if not _interval(precision) or not _finite_ge(precision[0], POLICY['minimumSegmentPrecisionLower95']):
                reasons.append(name + '_segment_precision_bound_not_met')
    if audit.get('bindingSha256') != digest({key: value for key, value in evidence.items() if key != 'lineageAudit'}):
        reasons.append('evidence_integrity_binding_missing')
    return sorted(set(reasons))


def _calibration_reasons(artifact, level, classification_passed):
    evidence = artifact.get('evidence', {}).get(level, {})
    fitted = artifact.get('documentCalibration' if level == 'document' else 'segmentCalibration')
    reasons = [] if classification_passed else [level + '_classification_unvalidated']
    if not isinstance(fitted, dict) or fitted.get('method') != 'platt' or not finite(fitted.get('slope')) or fitted.get('slope', 0) <= 0 or not finite(fitted.get('intercept')):
        reasons.append('independent_' + level + '_calibration_missing')
    else:
        if evidence.get('calibrationSha256') != digest(fitted):
            reasons.append('calibration_evidence_binding_missing')
        fitting = fitted.get('fitting', {})
        if fitting.get('split') != 'calibration' or any(not _count(fitting.get('classCounts', {}).get(label)) or fitting['classCounts'][label] < POLICY['minimumCalibrationFitPerClass'] for label in ('human', 'ai')):
            reasons.append('calibration_fitting_sample_insufficient')
    for name, metrics in [('overall', evidence.get('metrics', {})), *[(lang, evidence.get('byLanguage', {}).get(lang, {})) for lang in ('sv', 'en')]]:
        calibration = metrics.get('calibration', {})
        if not _finite_le(calibration.get('ece10'), POLICY['maximumCalibrationECE']) or not _finite_le(calibration.get('brier'), POLICY['maximumCalibrationBrier']):
            reasons.append(name + '_calibration_error_not_validated')
    return sorted(set(reasons))


def gate_results(artifact):
    gates = {}
    for level, calibration_key in (('document', 'calibration'), ('segment', 'segmentCalibration')):
        try:
            reasons = _classification_reasons(artifact, level)
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            reasons = ['invalid_' + level + '_evidence']
        gates[level] = {'passed': not reasons, 'reasons': reasons}
        try:
            calibration_reasons = _calibration_reasons(artifact, level, not reasons)
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            calibration_reasons = ['invalid_' + level + '_calibration_evidence']
        gates[calibration_key] = {'passed': not calibration_reasons, 'reasons': calibration_reasons}
    return gates
