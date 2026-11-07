import fs from 'node:fs';
import { createHash } from 'node:crypto';
import { pathToFileURL } from 'node:url';
import { analyzeText, METHOD, MAX_CHARS } from '../sites/src/analyzer.mjs';

const LABELS = ['human', 'ai', 'ai-edited'];
const SPLITS = ['train', 'validation', 'test'];
const SCHEMA_VERSION = 'textlab-benchmark-v3';
const MAX_RECORDS = 2000;
const NEAR_DUPLICATE_THRESHOLD = 0.8;
const ratio = (a, b) => b ? a / b : null;
const hash = value => createHash('sha256').update(value).digest('hex');
const calibration = { available: false, reason: 'No independently calibrated authorship probabilities exist. Style indices cannot be used for Brier score, ECE or probability claims.' };
const countBy = (rows, key) => Object.fromEntries([...new Set(rows.map(key))].sort().map(value => [value, rows.filter(row => key(row) === value).length]));
const requireString = (value, name) => { if (typeof value !== 'string' || !value.trim()) throw new Error(`Missing or invalid ${name}`); };

function wilson(successes, n) {
  if (!n) return null;
  const z = 1.959963984540054, p = successes / n, denominator = 1 + z * z / n;
  const center = (p + z * z / (2 * n)) / denominator;
  const margin = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator;
  return { lower: Math.max(0, center - margin), upper: Math.min(1, center + margin), n, method: 'Wilson observation-level; does not adjust for grouped samples' };
}

function auc(rows) {
  const sorted = rows.filter(row => row.score !== null && row.label !== 'ai-edited').sort((a, b) => a.score - b.score);
  const positiveCount = sorted.filter(row => row.label === 'ai').length;
  const negativeCount = sorted.length - positiveCount;
  if (!positiveCount || !negativeCount) return null;
  let rankSum = 0;
  for (let i = 0; i < sorted.length;) {
    let end = i + 1;
    while (end < sorted.length && sorted[end].score === sorted[i].score) end++;
    const meanRank = (i + 1 + end) / 2;
    rankSum += sorted.slice(i, end).filter(row => row.label === 'ai').length * meanRank;
    i = end;
  }
  return (rankSum - positiveCount * (positiveCount + 1) / 2) / (positiveCount * negativeCount);
}

/** Diagnostic binary metrics for a fixed STYLE threshold. Not an authorship classifier. */
export function summarize(rows, threshold = 65) {
  if (!Number.isFinite(threshold) || threshold < 0 || threshold > 100) throw new Error('Threshold must be 0–100');
  const confusion = { tp: 0, fp: 0, tn: 0, fn: 0 };
  const abstentionsByLabel = Object.fromEntries(LABELS.map(label => [label, 0]));
  let abstained = 0, totalAI = 0, binaryAssessed = 0;
  const edited = { total: 0, assessed: 0, flagged: 0 };
  for (const row of rows) {
    if (!LABELS.includes(row.label)) throw new Error('Each label must be human, ai or ai-edited');
    if (row.label === 'ai') totalAI++;
    if (row.label === 'ai-edited') edited.total++;
    if (row.score === null) { abstained++; abstentionsByLabel[row.label]++; continue; }
    if (!Number.isFinite(row.score) || row.score < 0 || row.score > 100) throw new Error('Invalid style index');
    const positive = row.score >= threshold;
    if (row.label === 'ai-edited') { edited.assessed++; if (positive) edited.flagged++; continue; }
    binaryAssessed++;
    confusion[row.label === 'ai' ? (positive ? 'tp' : 'fn') : (positive ? 'fp' : 'tn')]++;
  }
  const { tp, fp, tn, fn } = confusion, assessed = rows.length - abstained;
  return {
    total: rows.length, assessed, binaryAssessed, abstained, abstentionsByLabel, threshold,
    coverage: ratio(assessed, rows.length), confusion,
    accuracyAssessed: ratio(tp + tn, binaryAssessed), precision: ratio(tp, tp + fp), recallAssessed: ratio(tp, tp + fn),
    recallAllAI: ratio(tp, totalAI), falsePositiveRate: ratio(fp, fp + tn), falseNegativeRate: ratio(fn, tp + fn),
    f1: ratio(2 * tp, 2 * tp + fp + fn), auroc: auc(rows),
    aiEdited: { ...edited, abstained: edited.total - edited.assessed, coverage: ratio(edited.assessed, edited.total), flagRateAssessed: ratio(edited.flagged, edited.assessed) },
    intervals95: { accuracyAssessed: wilson(tp + tn, binaryAssessed), precision: wilson(tp, tp + fp), recallAssessed: wilson(tp, tp + fn), falsePositiveRate: wilson(fp, fp + tn), falseNegativeRate: wilson(fn, tp + fn), coverage: wilson(assessed, rows.length) },
    calibration,
    evidenceWarning: binaryAssessed < 100 ? 'Fewer than 100 assessed binary examples in this slice; no reliability or generalization claim is supported.' : 'Metrics are conditional on this corpus and threshold. Group dependence, provenance and distribution shifts require separate review.',
  };
}

const normalizedTokens = text => text.normalize('NFKC').toLowerCase().match(/[\p{L}\p{N}][\p{L}\p{M}\p{N}]*/gu) || [];
function shingles(tokens) {
  const result = new Set(), size = Math.min(5, tokens.length);
  if (!size) return result;
  for (let i = 0; i <= tokens.length - size; i++) result.add(tokens.slice(i, i + size).join(' '));
  return result;
}

function auditLeakage(records) {
  for (const field of ['author_id', 'document_id', 'source_group_id']) {
    const seen = new Map();
    for (const row of records) {
      if (seen.has(row[field]) && seen.get(row[field]) !== row.split) throw new Error(`Split leakage in ${field}: ${row[field]}`);
      seen.set(row[field], row.split);
    }
  }
  // Union source ids and references, including shared external parents and reference chains.
  const parents = new Map();
  const find = id => { if (!parents.has(id)) parents.set(id, id); if (parents.get(id) !== id) parents.set(id, find(parents.get(id))); return parents.get(id); };
  for (const row of records) {
    find(row.source_id);
    if (row.related_source_id) parents.set(find(row.source_id), find(row.related_source_id));
  }
  const components = new Map();
  for (const row of records) {
    const parent = find(row.source_id);
    if (components.has(parent) && components.get(parent) !== row.split) throw new Error(`Split leakage in related_source_id: ${row.source_id}`);
    components.set(parent, row.split);
  }
  const byId = new Map(records.map(row => [row.source_id, row]));
  const editRoot = row => {
    const seen = new Set();
    let current = row;
    while (current?.label === 'ai-edited') {
      if (seen.has(current.source_id)) return null;
      seen.add(current.source_id);
      const parent = byId.get(current.related_source_id);
      if (!parent || parent.split !== row.split || parent.source_group_id !== row.source_group_id) return null;
      current = parent;
    }
    return current?.label === 'human' ? current.source_id : null;
  };
  const roots = records.map(editRoot);
  const isDocumentedEditPair = (a, b) => records[a].split === records[b].split
    && records[a].source_group_id === records[b].source_group_id
    && (records[a].label === 'ai-edited' || records[b].label === 'ai-edited')
    && roots[a] !== null && roots[a] === roots[b];
  const exact = new Map(), indexed = new Map(), sets = [], relatedEditExamples = [], recorded = new Set();
  let nearDuplicateComparisons = 0, relatedEditPairs = 0, relatedExactPairs = 0, relatedNearPairs = 0;
  const recordDependency = (a, b, kind) => {
    const pair = `${a}:${b}`;
    if (recorded.has(pair)) return;
    recorded.add(pair);
    relatedEditPairs++;
    if (kind === 'exact') relatedExactPairs++; else relatedNearPairs++;
    if (relatedEditExamples.length < 1000) relatedEditExamples.push({ originalRoot: roots[a], first: records[a].source_id, second: records[b].source_id, kind, sourceGroup: records[a].source_group_id, split: records[a].split });
  };
  for (let i = 0; i < records.length; i++) {
    const row = records[i], tokens = normalizedTokens(row.text), key = tokens.join(' ');
    if (!tokens.length) throw new Error(`No lexical text in ${row.source_id}`);
    for (const previous of exact.get(key) || []) {
      if (!isDocumentedEditPair(previous, i)) throw new Error(`Exact duplicate: ${records[previous].source_id} and ${row.source_id}; duplicates cannot count as independent examples`);
      recordDependency(previous, i, 'exact');
    }
    if (!exact.has(key)) exact.set(key, []);
    exact.get(key).push(i);
    const set = shingles(tokens), intersections = new Map();
    // An inverted index checks only pairs sharing a shingle; all Jaccard >=0.8 pairs must share one.
    for (const shingle of set) for (const previous of indexed.get(shingle) || []) intersections.set(previous, (intersections.get(previous) || 0) + 1);
    for (const [previous, intersection] of intersections) {
      nearDuplicateComparisons++;
      const similarity = intersection / (set.size + sets[previous].size - intersection);
      if (similarity >= NEAR_DUPLICATE_THRESHOLD) {
        if (!isDocumentedEditPair(previous, i)) throw new Error(`Near-duplicate: ${records[previous].source_id} and ${row.source_id}; five-token shingle Jaccard=${similarity.toFixed(3)}`);
        recordDependency(previous, i, 'near');
      }
    }
    for (const shingle of set) { if (!indexed.has(shingle)) indexed.set(shingle, []); indexed.get(shingle).push(i); }
    sets.push(set);
  }
  return { passed: true, groupingFields: ['author_id', 'document_id', 'source_group_id', 'related_source_id'], exactDuplicates: 0, nearDuplicates: 0, nearDuplicateComparisons, relatedEditPairs, relatedExactPairs, relatedNearPairs, relatedEditExamples, relatedExamplesTruncated: relatedEditPairs > relatedEditExamples.length, shingleWords: 5, jaccardThreshold: NEAR_DUPLICATE_THRESHOLD, note: 'Duplicate counts exclude explicitly documented human/AI-edited pairs with a shared human ancestor in the same split/source family. Related pairs are dependent observations, never independent examples. Token overlap cannot establish semantic independence; source-family audit and grouped uncertainty are still required.' };
}

/** Validates metadata assertions; it cannot verify external rights or labels itself. */
export function validateDataset(records, { fixture = false } = {}) {
  if (!Array.isArray(records) || !records.length) throw new Error('Dataset is empty');
  if (records.length > MAX_RECORDS) throw new Error(`Dataset exceeds ${MAX_RECORDS} records`);
  const ids = new Set();
  for (const [index, row] of records.entries()) {
    const prefix = `record ${index + 1}`;
    if (!row || typeof row !== 'object') throw new Error(`Invalid ${prefix}`);
    for (const field of ['source_id', 'author_id', 'document_id', 'source_group_id', 'genre', 'split', 'language']) requireString(row[field], `${field} in ${prefix}`);
    if (ids.has(row.source_id)) throw new Error(`Duplicate source_id: ${row.source_id}`);
    ids.add(row.source_id);
    if (!SPLITS.includes(row.split)) throw new Error(`Invalid split in ${prefix}`);
    if (!LABELS.includes(row.label)) throw new Error(`Invalid label in ${prefix}`);
    if (!/^[a-z]{2,3}(?:-[A-Za-z0-9]+)*$/.test(row.language)) throw new Error(`Invalid language in ${prefix}`);
    if (typeof row.text !== 'string' || !row.text.trim() || row.text.length > MAX_CHARS) throw new Error(`Text must contain 1–${MAX_CHARS} characters in ${prefix}`);
    if (row.related_source_id !== undefined) requireString(row.related_source_id, `related_source_id in ${prefix}`);
    if (row.label !== 'human') requireString(row.model, `model in ${prefix}`);
    if (row.label === 'human' && row.model !== null && row.model !== undefined) throw new Error(`Human model must be null in ${prefix}; AI-assisted texts belong in ai-edited`);
    const provenance = row.provenance;
    if (!provenance || typeof provenance !== 'object') throw new Error(`Missing provenance in ${prefix}`);
    if (fixture && provenance.kind !== 'synthetic-fixture') throw new Error('Cannot mix independent data with fixture mode');
    if (!fixture && provenance.kind !== 'independent') throw new Error('Synthetic fixture data requires explicit --fixture mode; independent provenance is required otherwise');
    requireString(provenance.source, `provenance.source in ${prefix}`);
    if (provenance.rights?.status !== 'verified' || !['owned', 'license', 'public-domain'].includes(provenance.rights?.basis)) throw new Error(`Unverified or missing provenance.rights in ${prefix}`);
    requireString(provenance.rights.evidence, `provenance.rights.evidence in ${prefix}`);
    if (provenance.rights.basis === 'license') requireString(provenance.rights.license, `provenance.rights.license in ${prefix}`);
    const methods = fixture ? ['fixture-assignment'] : row.label === 'human' ? ['self-authored', 'verified-source'] : row.label === 'ai' ? ['generation-log'] : ['edit-log'];
    if (!methods.includes(provenance.label?.method)) throw new Error(`provenance.label.method must be ${methods.join(' or ')} in ${prefix}`);
    requireString(provenance.label.evidence, `provenance.label.evidence in ${prefix}`);
  }
  const leakage = auditLeakage(records);
  return { counts: { total: records.length, bySplit: countBy(records, row => row.split), byLabel: countBy(records, row => row.label), byLanguage: countBy(records, row => row.language), groups: Object.fromEntries(['author_id', 'document_id', 'source_group_id'].map(field => [field, new Set(records.map(row => row[field])).size])) }, leakage };
}

export function selectThreshold(rows) {
  if (!rows.length || rows.some(row => row.split !== 'validation')) throw new Error('Threshold selection requires only the validation split');
  const binary = rows.filter(row => row.score !== null && ['human', 'ai'].includes(row.label));
  if (!binary.some(row => row.label === 'human') || !binary.some(row => row.label === 'ai')) throw new Error('Threshold selection needs assessed human and ai validation examples');
  let best = null;
  for (let threshold = 0; threshold <= 100; threshold++) {
    const metrics = summarize(rows, threshold);
    if (!best || metrics.f1 > best.f1 || (metrics.f1 === best.f1 && metrics.falsePositiveRate < best.falsePositiveRate) || (metrics.f1 === best.f1 && metrics.falsePositiveRate === best.falsePositiveRate && threshold > best.threshold)) best = { threshold, f1: metrics.f1, falsePositiveRate: metrics.falsePositiveRate };
  }
  return { ...best, selectionSplit: 'validation', objective: 'f1', tieBreak: 'lowest false-positive rate, then highest threshold', assessedBinaryCount: binary.length, warning: 'Exploratory style-threshold selection, not a trained or calibrated authorship classifier. A single validation split can overfit.' };
}

export function evaluateDataset(records, { threshold = 65, fixture = false, tuneOnValidation = false } = {}) {
  const dataset = validateDataset(records, { fixture });
  if (!records.some(row => row.split === 'test')) throw new Error('Dataset has no test split; training or validation records cannot stand in for a held-out test');
  const scored = records.map(row => {
    const result = analyzeText(row.text, row.language);
    return { source_id: row.source_id, split: row.split, label: row.label, language: row.language, genre: row.genre, model: row.model || '(human)', score: result.styleIndex, words: result.wordCount, status: result.status, abstentionReasons: result.abstentionReasons };
  });
  const selection = tuneOnValidation ? selectThreshold(scored.filter(row => row.split === 'validation')) : { threshold, selectionSplit: 'predeclared', warning: 'Default 65 is an arbitrary descriptive style threshold, not a validated operating point. Predeclare a threshold before examining test outcomes.' };
  threshold = selection.threshold;
  const test = scored.filter(row => row.split === 'test');
  const slices = key => Object.fromEntries([...new Set(test.map(key))].sort().map(value => [value, summarize(test.filter(row => key(row) === value), threshold)]));
  return {
    schemaVersion: SCHEMA_VERSION, method: METHOD,
    mode: fixture ? 'synthetic-fixture' : 'independent-data-required', qualityEvidence: false,
    provenanceStatus: fixture ? 'synthetic_not_quality_evidence' : 'asserted_not_independently_audited',
    notice: fixture ? 'SYNTHETIC ENGINEERING FIXTURES ONLY. Labels are deliberately assigned and do not represent measured authorship detection quality.' : 'Diagnostic evaluation of a descriptive style threshold. Provenance fields are assertions requiring independent review. This report contains no trained-model classification or calibrated AI probability; the offline experimental baseline has separate reports.',
    dataset, selection, overall: summarize(test, threshold),
    byLanguage: slices(row => row.language), byGenre: slices(row => row.genre),
    byLength: slices(row => row.words < 80 ? 'short' : row.words < 300 ? 'medium' : 'long'), byModel: slices(row => row.model),
    abstentionReasons: countBy(test.flatMap(row => row.abstentionReasons), reason => reason),
    predictions: test, calibration,
    reproducibility: { datasetSha256: hash(JSON.stringify(records)), method: METHOD, evaluatedSplit: 'test', threshold, tuneOnValidation, nearDuplicateThreshold: NEAR_DUPLICATE_THRESHOLD, recordsOrdered: true, runtime: process.version },
    limitations: ['Accuracy, precision, recall, F1, FPR and FNR are diagnostic threshold metrics among assessed human/ai examples. ai-edited is separate.', 'Coverage includes all labels; recallAllAI also includes abstained ai examples in its denominator. AUROC excludes abstentions and ai-edited.', 'Wilson intervals assume independent observations; repeated authors and source families can make them too narrow. Grouped resampling is required for inferential claims.', 'Split and duplicate checks cannot detect every translated, paraphrased, related, contaminated or mislabeled text.', 'The real historical pilot and offline learned baseline have separate scope/limitations; neither validates this style threshold for general authorship detection. Do not interpret engineering fixture metrics as detector quality.'],
  };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const args = process.argv.slice(2), file = args.shift();
    if (!file) throw new Error('Usage: npm run evaluate -- dataset.jsonl [threshold] [--fixture] [--select-threshold]');
    const fixture = args.includes('--fixture'), tuneOnValidation = args.includes('--select-threshold');
    const positional = args.filter(arg => !arg.startsWith('--'));
    if (args.some(arg => arg.startsWith('--') && !['--fixture', '--select-threshold'].includes(arg)) || positional.length > 1) throw new Error('Unknown benchmark arguments');
    if (tuneOnValidation && positional.length) throw new Error('Choose a fixed threshold OR --select-threshold, not both');
    if (fs.statSync(file).size > 10_000_000) throw new Error('Dataset exceeds 10 MB');
    const content = fs.readFileSync(file, 'utf8');
    const records = content.split(/\r?\n/).filter(line => line.trim()).map((line, index) => {
      try { return JSON.parse(line); } catch { throw new Error(`Invalid JSON on non-empty line ${index + 1}`); }
    });
    const report = evaluateDataset(records, { threshold: positional.length ? Number(positional[0]) : 65, fixture, tuneOnValidation });
    report.reproducibility.fileSha256 = hash(content);
    report.reproducibility.analyzerSha256 = hash(fs.readFileSync(new URL('../sites/src/analyzer.mjs', import.meta.url)));
    report.reproducibility.evaluatorSha256 = hash(fs.readFileSync(new URL('./evaluate.mjs', import.meta.url)));
    console.log(JSON.stringify(report, null, 2));
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
