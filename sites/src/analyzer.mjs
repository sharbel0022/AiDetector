export const MAX_CHARS = 12000;
export const METHOD = 'style-heuristics-v3';
export const MIN_WORDS = 80;
export const MIN_SENTENCES = 4;
const WORD = /[\p{L}\p{N}][\p{L}\p{N}\p{M}]*(?:[’'-][\p{L}\p{N}][\p{L}\p{N}\p{M}]*)*/gu;
const MARKERS = ['det är viktigt att notera', 'sammanfattningsvis', 'avslutningsvis', 'det är värt att nämna', 'i dagens digitala värld', 'it is important to note', 'in conclusion', 'furthermore', 'moreover', 'delve into', 'in summary'];
const LANGUAGE_WORDS = {
  sv: new Set('och det att som är på för med jag du vi han hon den ett inte till av om har hade var kan ska men eller när från också finns där här sin sitt denna detta dessa genom mellan mycket sedan blev blir hur varför vilka vad behöver några skulle kunde'.split(' ')),
  en: new Set('the and that is are was were with for from this these those they their there have has had not but or when which what who would could should will can into about been being because through between some each more than then she he we you our your its'.split(' ')),
};
const normalize = text => text.normalize('NFKC').toLowerCase();
const words = text => [...text.matchAll(WORD)].map(m => ({ text: m[0], key: normalize(m[0]), start: m.index, end: m.index + m[0].length }));
export const wordCount = text => words(text).length;
const clamp = value => Math.max(0, Math.min(1, value));

function sentences(text) {
  const result = [];
  let start = 0;
  const add = end => {
    while (start < end && /\s/u.test(text[start])) start++;
    let last = end;
    while (last > start && /\s/u.test(text[last - 1])) last--;
    if (last > start && wordCount(text.slice(start, last))) result.push({ start, end: last, text: text.slice(start, last) });
    start = end;
  };
  for (let i = 0; i < text.length; i++) {
    let end = i + 1;
    if (/[.!?]/.test(text[i])) while (end < text.length && /["'”’»)\]}]/.test(text[end])) end++;
    const punctuation = /[.!?]/.test(text[i]) && (end === text.length || /\s/.test(text[end]));
    const abbreviation = /(?:\b(?:dr|mr|mrs|ms|prof|etc|e\.g|i\.e|vs|bl\.a|t\.ex))\.$/i.test(text.slice(start, i + 1));
    if (punctuation && !abbreviation) { add(end); i = end - 1; }
    else if (text[i] === '\n') add(i + 1);
  }
  add(text.length);
  return result;
}

// A conservative lexical guard, not a language-identification model. Latin script alone is insufficient.
function assessLanguage(text, tokens, requested) {
  const letters = text.match(/\p{L}/gu) || [];
  const latin = text.match(/\p{Script=Latin}/gu) || [];
  const matchedWords = Object.fromEntries(Object.entries(LANGUAGE_WORDS).map(([language, lexicon]) => [language, tokens.filter(t => lexicon.has(t.key)).length]));
  const result = { requested, detected: null, status: 'uncertain', matchedWords, reason: 'För få tydliga svenska eller engelska språkmarkörer. Språkbedömningen är en försiktig ordregel och kan avstå även för rätt språk.' };
  if (!['sv', 'en'].includes(requested) || (letters.length && latin.length / letters.length < 0.8)) return { ...result, status: 'unsupported', reason: 'Analysen stöder endast svenska och engelska. Texten eller det valda språket ligger utanför stödet.' };
  const candidate = matchedWords.sv > matchedWords.en ? 'sv' : 'en';
  const other = candidate === 'sv' ? 'en' : 'sv';
  const distinct = new Set(tokens.filter(t => LANGUAGE_WORDS[candidate].has(t.key)).map(t => t.key)).size;
  const strong = matchedWords[candidate] >= 6 && distinct >= 3 && matchedWords[candidate] / Math.max(1, tokens.length) >= 0.08;
  const dominant = matchedWords[candidate] >= Math.max(1, matchedWords[other]) * 1.8;
  if (!strong || !dominant) return result;
  return { ...result, detected: candidate, status: candidate === requested ? 'supported' : 'mismatch', reason: candidate === requested ? 'Vanliga funktionsord ger stöd för det valda språket. Detta är ingen validerad språkmodell.' : `Textens språkmarkörer liknar ${candidate === 'sv' ? 'svenska' : 'engelska'}, men ett annat språk har valts. Välj textens språk och analysera igen.` };
}

function repeatedPhrases(tokens, sentenceTokens) {
  const candidates = [];
  const repeatedTokenPositions = new Set();
  for (let size = 12; size >= 4; size--) {
    const groups = new Map();
    for (const group of sentenceTokens) {
      for (let i = 0; i <= group.length - size; i++) {
        const slice = group.slice(i, i + size);
        const key = slice.map(t => t.key).join(' ');
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push({ start: slice[0].start, end: slice.at(-1).end, tokenStart: slice[0].index, tokenEnd: slice.at(-1).index + 1 });
      }
    }
    for (const [key, occurrences] of groups) {
      const nonoverlapping = [];
      for (const occurrence of occurrences) if (!nonoverlapping.length || occurrence.start >= nonoverlapping.at(-1).end) nonoverlapping.push(occurrence);
      if (nonoverlapping.length < 2) continue;
      if (size === 4) for (const occurrence of nonoverlapping) for (let i = occurrence.tokenStart; i < occurrence.tokenEnd; i++) repeatedTokenPositions.add(i);
      candidates.push({ key, words: size, occurrences: nonoverlapping });
    }
  }
  // Show maximal non-overlapping examples; coverage uses every repeated four-word sequence.
  const selected = [];
  const occupied = new Set();
  for (const candidate of candidates) {
    const occurrences = candidate.occurrences.filter(o => {
      for (let i = o.tokenStart; i < o.tokenEnd; i++) if (occupied.has(i)) return false;
      return true;
    });
    if (occurrences.length < 2) continue;
    selected.push({ phrase: candidate.key, words: candidate.words, count: occurrences.length, occurrences: occurrences.slice(0, 30).map(({ start, end }) => ({ start, end })) });
    for (const o of occurrences) for (let i = o.tokenStart; i < o.tokenEnd; i++) occupied.add(i);
    if (selected.length >= 20) break;
  }
  return { groups: selected, coverage: repeatedTokenPositions.size / Math.max(1, tokens.length) };
}

export function analyzeText(text, language = 'sv') {
  if (typeof text !== 'string') throw new TypeError('Text must be a string');
  if (text.length > MAX_CHARS) throw new RangeError(`Maximum ${MAX_CHARS} characters`);
  const tokens = words(text).map((t, index) => ({ ...t, index }));
  const spans = sentences(text);
  const sentenceTokens = spans.map(s => tokens.filter(t => t.start >= s.start && t.end <= s.end));
  const lens = sentenceTokens.map(t => t.length);
  const mean = lens.length ? tokens.length / lens.length : 0;
  const cv = mean ? Math.sqrt(lens.reduce((n, v) => n + (v - mean) ** 2, 0) / lens.length) / mean : 0;
  const markers = [];
  for (const phrase of MARKERS) {
    const pattern = new RegExp(`(?<![\\p{L}\\p{M}\\p{N}])${phrase}(?![\\p{L}\\p{M}\\p{N}])`, 'giu');
    for (const match of text.matchAll(pattern)) markers.push({ text: match[0], start: match.index, end: match.index + match[0].length });
  }
  markers.sort((a, b) => a.start - b.start);
  // MATTR with fixed 50-word windows reduces, but does not eliminate, sample-length and genre effects.
  const window = Math.min(50, tokens.length);
  let diversity = 0;
  if (window) {
    for (let i = 0; i <= tokens.length - window; i++) diversity += new Set(tokens.slice(i, i + window).map(t => t.key)).size / window;
    diversity /= tokens.length - window + 1;
  }
  const openings = new Map();
  for (const group of sentenceTokens) {
    if (group.length < 2) continue;
    const key = group.slice(0, 2).map(t => t.key).join(' ');
    if (!openings.has(key)) openings.set(key, []);
    openings.get(key).push({ start: group[0].start, end: group[1].end });
  }
  const repeatedOpenings = [...openings.values()].filter(group => group.length > 1);
  const repeated = repeatedOpenings.reduce((n, group) => n + group.length - 1, 0);
  const ngrams = repeatedPhrases(tokens, sentenceTokens);
  const evidence = [];
  const addEvidence = (feature, span, explanation) => evidence.push({ feature, ...span, text: text.slice(span.start, span.end), explanation });
  for (const marker of markers) addEvidence('phrases', marker, 'Standardformulering i ordlistan. Både människor och språkmodeller använder den; träffen visar inte ursprung.');
  for (const group of repeatedOpenings) for (const occurrence of group.slice(0, 30)) addEvidence('openings', occurrence, `Samma två första ord återkommer i ${group.length} meningar. Det kan bero på struktur eller stilval.`);
  for (const group of ngrams.groups) for (const occurrence of group.occurrences) addEvidence('repetition', occurrence, `En följd om ${group.words} ord förekommer ${group.count} gånger. Citat, instruktioner och ämnet kan förklara upprepningen.`);
  evidence.sort((a, b) => a.start - b.start || a.end - b.end || a.feature.localeCompare(b.feature));
  evidence.forEach((item, index) => { item.id = `e${index + 1}`; });
  const signals = [
    { key: 'uniformity', label: 'Jämna meningslängder', value: clamp(1 - cv / 0.65), detail: `Variationskoefficient ${cv.toFixed(2)} över ${lens.length} meningar. Jämn längd kan vara ett medvetet stilval. Detta är ett mått för hela texten, utan enskild ordträff.` },
    { key: 'openings', label: 'Återkommande inledningar', value: clamp(repeated / Math.max(1, lens.length) * 2), detail: `${repeated} återkommande tvåordsinledningar efter den första förekomsten. Upprepning säger inte vem som skrev texten.` },
    { key: 'phrases', label: 'Standardformuleringar', value: clamp(markers.length / Math.max(1, tokens.length) * 100), detail: `${markers.length} träffar i en liten fast ordlista. Ordlistan är inte ett validerat kännetecken för AI.` },
    { key: 'vocabulary', label: 'Begränsad ordvariation', value: clamp((0.8 - diversity) / 0.4), detail: `MATTR: ${Math.round(diversity * 100)} % unika ord i glidande fönster om ${window} ord. Ämne, böjningsformer och genre påverkar måttet; ingen enskild ordträff.` },
    { key: 'repetition', label: 'Upprepade ordsekvenser', value: clamp(ngrams.coverage), detail: `${Math.round(ngrams.coverage * 100)} % av orden ingår i återkommande fyrordssekvenser inom meningar. Exemplen visar längre följder upp till tolv ord. Upprepning kan vara avsiktlig.` },
  ].map(signal => ({ ...signal, evidenceIds: evidence.filter(e => e.feature === signal.key).map(e => e.id) }));
  const languageAssessment = assessLanguage(text, tokens, language);
  const abstentionReasons = [];
  if (tokens.length < MIN_WORDS) abstentionReasons.push('too_short');
  if (lens.length < MIN_SENTENCES) abstentionReasons.push('too_few_sentences');
  if (languageAssessment.status !== 'supported') abstentionReasons.push({ unsupported: 'unsupported_language', mismatch: 'language_mismatch', uncertain: 'language_uncertain' }[languageAssessment.status]);
  const status = languageAssessment.status === 'unsupported' ? 'unsupported' : tokens.length < MIN_WORDS ? 'insufficient' : languageAssessment.status === 'mismatch' ? 'language_mismatch' : languageAssessment.status === 'uncertain' ? 'language_uncertain' : lens.length < MIN_SENTENCES ? 'insufficient_structure' : 'analyzed';
  const messages = { too_short: 'Minst 80 ord behövs för ett stilindex.', too_few_sentences: 'Minst fyra meningar med ord behövs för att jämföra meningsrytm.', unsupported_language: languageAssessment.reason, language_mismatch: languageAssessment.reason, language_uncertain: languageAssessment.reason };
  return {
    method: METHOD, authorship: 'undetermined', benchmarkStatus: 'not_evaluated', status,
    styleIndex: abstentionReasons.length ? null : Math.round(signals.reduce((n, s) => n + s.value, 0) * 20),
    wordCount: tokens.length, charCount: text.length, sentenceCount: spans.length,
    averageLength: Number(mean.toFixed(1)), variation: Number(cv.toFixed(2)), lexicalDiversity: Math.round(diversity * 100),
    languageAssessment, abstentionReasons,
    uncertainty: { authorship: 'unvalidated', probabilityAvailable: false, reasons: [...abstentionReasons.map(reason => messages[reason]), 'Författarskap kan inte avgöras. Metoden har inte validerats på ett oberoende märkt material.'] },
    features: { sentenceLengthCV: cv, mattr: diversity, mattrWindow: window, repeatedOpeningCount: repeated, repeatedNgramCoverage: ngrams.coverage, repeatedNgrams: ngrams.groups },
    markers, evidence, signals,
    sentences: spans.map((s, index) => ({ ...s, marked: evidence.some(e => e.start < s.end && e.end > s.start), words: lens[index] })),
    limitations: ['Stilindex är ett oviktat medelvärde av fem beskrivande signaler, inte en sannolikhet att texten är AI-skriven.', 'Signalernas skalor och språkregler är manuella och inte statistiskt validerade. Citat, genre, översättning och redigering påverkar dem.', 'Träffsäkerhet har inte validerats på ett oberoende märkt material. Enskilda markeringar är exempel på stil, inte bevis på ursprung.', 'Använd inte resultatet som bevis för fusk eller som grund för beslut om en person.'],
  };
}
