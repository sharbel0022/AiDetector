import { analyzeText, wordCount, MAX_CHARS } from './analyzer.mjs';

export const CATEGORY_LABELS = Object.freeze({
  ai_like: 'AI-liknande', human_like: 'Mänskligt-liknande', mixed: 'Blandad eller varierande text',
  uncertain: 'Osäkert resultat', insufficient: 'Otillräckligt underlag', unassessed: 'Ej bedömt',
});
export const REPORT_LIMITATION = 'Modellens bedömning är inte bevis för författarskap. AI-markerad textandel är inte en verifierad andel AI-skriven text. Granska original, sammanhang och metodens begränsningar.';
const INVALID = 'Serverns detektorresultat har ett ogiltigt format. Inga AI-värden visas. Originalet finns kvar.';
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
function fail() { throw new Error(INVALID); }
function string(value, max = 2000) { if (typeof value !== 'string' || value.length > max) fail(); return value; }
function integer(value, max) { if (!Number.isSafeInteger(value) || value < 0 || value > max) fail(); return value; }
function flag(data, key) { if (data[key] === undefined) return false; if (typeof data[key] !== 'boolean') fail(); return data[key]; }
function probability(value, max = 1) { if (value == null) return null; if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > max) fail(); return value; }
function boundary(text, offset) {
  const before = text.charCodeAt(offset - 1), after = text.charCodeAt(offset);
  return !(before >= 0xD800 && before <= 0xDBFF && after >= 0xDC00 && after <= 0xDFFF);
}

function explainReason(reason) {
  const direct = {
    model_unavailable:'Detektormodellen är inte tillgänglig. Stilanalysen fungerar fortfarande.',
    too_short:'Dokumentbedömningen behöver minst 80 ord.',
    too_few_sentences:'Dokumentbedömningen behöver minst fyra meningar med ord.',
    unsupported_language:'Textens språk ligger utanför stödet för svenska och engelska.',
    language_mismatch:'Textens språk och det manuella språkvalet verkar skilja sig åt.',
    language_uncertain:'Textens språk kan inte identifieras med tillräckligt stöd.',
    document_not_eligible:'Texten har inte tillräckligt underlag för dokumentklassificering.',
    independently_selected_thresholds_missing:'Beslutsgränserna saknar verifierad oberoende validering.',
  };
  if (direct[reason]) return direct[reason];
  if (/fresh_independent_.*_test_missing/.test(reason)) return 'Modellen saknar ett nytt, oberoende och tillräckligt valideringstest.';
  if (/provenance|lineage|binding/.test(reason)) return 'Testunderlagets ursprung, oberoende eller koppling till modellen är inte fullt verifierat.';
  if (/sample_size_insufficient|fitting_sample_insufficient/.test(reason)) return 'Det oberoende testmaterialet är för litet för en säker slutsats.';
  if (/source_family_count_insufficient/.test(reason)) return 'Testmaterialet innehåller för få oberoende källfamiljer.';
  if (/human_false_positive_bound_not_met/.test(reason)) return 'Tillräckligt låg risk för felaktig AI-markering av mänsklig text har inte verifierats.';
  if (/ai_recall_bound_not_met/.test(reason)) return 'Förmågan att identifiera AI-text är inte tillräckligt verifierad.';
  if (/segment_precision_bound_not_met/.test(reason)) return 'Segmentmarkeringarnas precision är inte tillräckligt verifierad.';
  if (/coverage_insufficient/.test(reason)) return 'För få texter i testmaterialet kunde bedömas.';
  if (/calibration/.test(reason)) return 'Sannolikhetskalibreringen saknar tillräcklig oberoende validering.';
  if (/invalid_|classification_unvalidated/.test(reason)) return 'Valideringsunderlaget är ofullständigt eller uppfyller inte metodens krav.';
  return /^[a-z][a-z0-9_]+$/.test(reason) ? 'Ytterligare begränsningar finns i modellens valideringsunderlag.' : reason;
}

// Reuses the unchanged V4 lexical guard. It can abstain; it is not a validated language model.
export function prepareLocalAnalysis(text, requested = 'auto') {
  if (!['auto', 'sv', 'en'].includes(requested) || typeof text !== 'string' || text.length > MAX_CHARS) fail();
  const initial = analyzeText(text, requested === 'auto' ? 'sv' : requested);
  const detected = initial.languageAssessment?.detected ?? null;
  const effective = requested === 'auto' ? detected : requested;
  const style = requested === 'auto' && detected === 'en' ? analyzeText(text, 'en') : initial;
  return { ...style, sourceText: text, languageAssessment: { ...style.languageAssessment, requested, selected: requested, effective, detected } };
}

// Only accepted fields enter UI or exports. Unknown metadata and unvalidated scores are discarded.
export function normalizeDetectionResult(data, sourceText, requested = 'auto') {
  if (typeof sourceText !== 'string' || sourceText.length > MAX_CHARS) fail();
  if (!record(data) || !record(data.detector) || !Array.isArray(data.segments) || data.segments.length > sourceText.length + 1) fail();
  const raw = data.detector;
  const documentValidated = flag(raw, 'documentValidated');
  const calibrationValidated = flag(raw, 'calibrationValidated');
  const segmentValidated = flag(raw, 'segmentValidated');
  const segmentCalibrationValidated = flag(raw, 'segmentCalibrationValidated');
  if (!['ai_like', 'human_like', 'mixed', 'uncertain', 'insufficient'].includes(raw.category)) fail();
  const rawProbability = probability(raw.documentProbability);
  const rawShare = probability(raw.aiMarkedPercent, 100);
  if (!Array.isArray(raw.reasons) || raw.reasons.length > 100) fail();
  const reasonCodes = raw.reasons.map(reason => string(reason));
  const reasons = [...new Set(reasonCodes.map(explainReason))];
  let end = 0;
  const ids = new Set();
  const segments = data.segments.map((item, index) => {
    if (!record(item)) fail();
    const id = string(item.id, 160);
    if (!id || ids.has(id)) fail();
    ids.add(id);
    const start = integer(item.start, sourceText.length);
    const nextEnd = integer(item.end, sourceText.length);
    if (start < end || nextEnd <= start || !boundary(sourceText, start) || !boundary(sourceText, nextEnd)) fail();
    if (wordCount(sourceText.slice(end, start)) !== 0) fail();
    if (string(item.text, MAX_CHARS) !== sourceText.slice(start, nextEnd)) fail();
    if (!['ai_like', 'human_like', 'uncertain', 'unassessed'].includes(item.category)) fail();
    if (typeof item.eligible !== 'boolean') fail();
    const sourceWordCount = wordCount(item.text);
    if (integer(item.wordCount, sourceText.length) !== sourceWordCount) fail();
    if (segmentValidated && item.eligible !== (item.category !== 'unassessed')) fail();
    const rawSegmentProbability = probability(item.probability);
    end = nextEnd;
    return {
      id, index, start, end: nextEnd, text: item.text,
      wordCount: sourceWordCount, eligible: item.eligible,
      category: segmentValidated ? item.category : 'unassessed',
      probability: item.eligible && segmentValidated && segmentCalibrationValidated ? rawSegmentProbability : null,
      reason: string(item.reason),
    };
  });
  if (wordCount(sourceText.slice(end)) !== 0) fail();
  const counts = Object.fromEntries(['analyzedWords', 'flaggedWords', 'excludedWords', 'totalSegments', 'flaggedSegments'].map(key => [key, integer(raw[key], sourceText.length)]));
  if (counts.totalSegments !== segments.length || counts.flaggedSegments > counts.totalSegments || counts.flaggedWords > counts.analyzedWords) fail();
  const totalWords = wordCount(sourceText);
  if (counts.analyzedWords + counts.excludedWords !== totalWords || segments.reduce((sum, segment) => sum + segment.wordCount, 0) !== totalWords || segments.filter(segment => segment.eligible).reduce((sum, segment) => sum + segment.wordCount, 0) !== counts.analyzedWords) fail();
  if (segmentValidated) {
    const assessed = segments.filter(segment => segment.category !== 'unassessed');
    const flagged = segments.filter(segment => segment.category === 'ai_like');
    if (assessed.reduce((sum, segment) => sum + segment.wordCount, 0) !== counts.analyzedWords || flagged.reduce((sum, segment) => sum + segment.wordCount, 0) !== counts.flaggedWords || flagged.length !== counts.flaggedSegments) fail();
    if (rawShare !== null && (!counts.analyzedWords || Math.abs(rawShare - counts.flaggedWords / counts.analyzedWords * 100) > 0.11)) fail();
  }
  const mixedSupported = segmentValidated && segments.some(segment => segment.category === 'ai_like') && segments.some(segment => segment.category === 'human_like');
  const detector = {
    modelVersion: raw.modelVersion === null ? null : string(raw.modelVersion, 256),
    category: raw.category === 'mixed' ? mixedSupported ? 'mixed' : 'uncertain' : documentValidated || raw.category === 'insufficient' ? raw.category : 'uncertain',
    documentProbability: documentValidated && calibrationValidated ? rawProbability : null,
    aiMarkedPercent: segmentValidated ? rawShare : null,
    documentValidated, calibrationValidated, segmentValidated, segmentCalibrationValidated,
    status: string(raw.status, 128), reasons, reasonCodes,
    calibrationStatus: string(raw.calibrationStatus, 256),
    ...counts,
    ...(segmentValidated ? {} : { flaggedWords: 0, flaggedSegments: 0 }),
  };
  const local = prepareLocalAnalysis(sourceText, requested);
  if (data.languageAssessment !== undefined) {
    const value = data.languageAssessment;
    if (!record(value) || !['supported', 'mismatch', 'uncertain', 'unsupported'].includes(value.status) || (value.detected !== null && !['sv', 'en'].includes(value.detected))) fail();
    local.languageAssessment = {
      ...local.languageAssessment, status: value.status, detected: value.detected,
      effective: requested === 'auto' ? value.detected : requested,
      reason: string(value.reason),
    };
  }
  return { ...local, detector, segments, analyzedAt: new Date().toISOString() };
}

export function segmentParts(sourceText, segments) {
  const parts = [];
  let cursor = 0;
  for (const segment of segments) {
    if (cursor < segment.start) parts.push({ text: sourceText.slice(cursor, segment.start), segment: null });
    parts.push({ text: sourceText.slice(segment.start, segment.end), segment });
    cursor = segment.end;
  }
  if (cursor < sourceText.length) parts.push({ text: sourceText.slice(cursor), segment: null });
  return parts;
}

export function buildAnalysisReport(analysis) {
  return {
    format: 'textlab-report-v5', createdAt: analysis.analyzedAt,
    sourceText: analysis.sourceText, language: analysis.languageAssessment,
    definitions: {
      documentProbability: 'Kalibrerad uppskattad sannolikhet för AI-klassen; inte andel av texten.',
      aiMarkedPercent: 'AI-markerade analyserbara ord / samtliga analyserbara ord × 100. Inte verifierat AI-författarskap.',
      offsets: 'Halvöppna UTF-16-intervall [start, end) i den oförändrade originaltexten.',
      styleIndex: 'Förklarande stilindex 0–100, inte AI-sannolikhet.',
    },
    detector: analysis.detector,
    segments: analysis.segments,
    style: { styleIndex: analysis.styleIndex, status: analysis.status, wordCount: analysis.wordCount, sentenceCount: analysis.sentenceCount, signals: analysis.signals },
    limitation: REPORT_LIMITATION,
  };
}

export function analysisReportText(analysis) {
  const { detector, segments } = analysis;
  const number = value => value === null ? 'Ej tillgängligt' : `${value.toLocaleString('sv-SE', { maximumFractionDigits: 1 })} %`;
  return [
    'TEXTLAB V5 — ANALYSRAPPORT', analysis.analyzedAt,
    `Modell: ${detector.modelVersion || 'Ej tillgänglig'}`, `Dokumentbedömning: ${CATEGORY_LABELS[detector.category]}`,
    `Modellens uppskattade sannolikhet för AI-klassen: ${number(detector.documentProbability === null ? null : detector.documentProbability * 100)}`,
    `Uppskattad andel AI-markerad text: ${number(detector.aiMarkedPercent)}`,
    `Analyserbara ord: ${detector.analyzedWords}; AI-markerade ord: ${detector.flaggedWords}; exkluderade ord: ${detector.excludedWords}`,
    `Markerade segment: ${detector.flaggedSegments} av ${detector.totalSegments}`,
    `Dokumentvalidering: ${detector.documentValidated ? 'verifierad' : 'ej verifierad'}; kalibrering: ${detector.calibrationValidated ? 'verifierad' : 'ej verifierad'}; segmentvalidering: ${detector.segmentValidated ? 'verifierad' : 'ej verifierad'}; segmentkalibrering: ${detector.segmentCalibrationValidated ? 'verifierad' : 'ej verifierad'}`,
    'Dokumentsannolikhet är inte andel text. Textandel = AI-markerade analyserbara ord / samtliga analyserbara ord × 100.',
    `Stilindex: ${analysis.styleIndex ?? 'Ej tillgängligt'} (inte AI-sannolikhet)`,
    ...detector.reasons, REPORT_LIMITATION, '', 'ORIGINALTEXT', analysis.sourceText, '', 'SEGMENT',
    ...segments.map((segment, index) => `${index + 1}. ${CATEGORY_LABELS[segment.category]} · ${segment.wordCount} ord · UTF-16 [${segment.start}, ${segment.end})\n${segment.text}\n${segment.reason}`),
  ].join('\n');
}
