export const MAX_CHARS = 12000;
const WORD = /[\p{L}\p{N}]+(?:[’'-][\p{L}\p{N}]+)*/gu;
const MARKERS = ['det är viktigt att notera', 'sammanfattningsvis', 'avslutningsvis', 'det är värt att nämna', 'i dagens digitala värld', 'it is important to note', 'in conclusion', 'furthermore', 'moreover', 'delve into', 'in summary'];
const words = text => text.match(WORD) || [];
export const wordCount = text => words(text).length;

function sentences(text) {
  const result = [];
  let start = 0;
  const add = end => {
    while (start < end && /\s/u.test(text[start])) start++;
    let last = end;
    while (last > start && /\s/u.test(text[last - 1])) last--;
    if (last > start) result.push({ start, end: last, text: text.slice(start, last) });
    start = end;
  };
  for (let i = 0; i < text.length; i++) {
    const punctuation = /[.!?]/.test(text[i]) && (i + 1 === text.length || /\s/.test(text[i + 1]));
    const abbreviation = /(?:\b(?:dr|mr|mrs|ms|prof|etc|bl\.a|t\.ex))\.$/i.test(text.slice(start, i + 1));
    if ((punctuation && !abbreviation) || text[i] === '\n') add(i + 1);
  }
  add(text.length);
  return result;
}

export function analyzeText(text, language = 'sv') {
  if (typeof text !== 'string') throw new TypeError('Text must be a string');
  if (text.length > MAX_CHARS) throw new RangeError(`Maximum ${MAX_CHARS} characters`);
  const tokens = words(text).map(w => w.toLocaleLowerCase(language));
  const spans = sentences(text);
  const lens = spans.map(s => wordCount(s.text)).filter(Boolean);
  const mean = lens.length ? tokens.length / lens.length : 0;
  const cv = mean ? Math.sqrt(lens.reduce((n, v) => n + (v - mean) ** 2, 0) / lens.length) / mean : 0;
  const markers = [];
  for (const phrase of MARKERS) {
    const pattern = new RegExp(`(?<![\\p{L}])${phrase}(?![\\p{L}])`, 'giu');
    for (const match of text.matchAll(pattern)) markers.push({ text: match[0], start: match.index, end: match.index + match[0].length });
  }
  markers.sort((a,b) => a.start-b.start);
  // A moving window reduces (but does not eliminate) lexical-diversity length bias.
  const window = Math.min(50, tokens.length);
  let diversity = 0;
  if (window) {
    for (let i = 0; i <= tokens.length - window; i++) diversity += new Set(tokens.slice(i, i + window)).size / window;
    diversity /= tokens.length - window + 1;
  }
  const openings = new Map();
  for (const span of spans) {
    const key = words(span.text).slice(0,2).join(' ').toLocaleLowerCase(language);
    if (key) openings.set(key, (openings.get(key) || 0) + 1);
  }
  const repeated = [...openings.values()].reduce((n,v) => n + Math.max(0,v-1),0);
  const letters = text.match(/\p{L}/gu) || [];
  const latin = text.match(/\p{Script=Latin}/gu) || [];
  const supported = !letters.length || latin.length / letters.length > 0.8;
  const enough = tokens.length >= 80;
  const signals = [
    { key: 'uniformity', label: 'Jämna meningslängder', value: Math.max(0, 1 - cv / 0.65), detail: `Variationskoefficient ${cv.toFixed(2)}. Jämn längd kan också vara ett medvetet stilval.` },
    { key: 'openings', label: 'Återkommande inledningar', value: Math.min(1, repeated / Math.max(1, spans.length) * 2), detail: `${repeated} återkommande meningsinledningar. Upprepning säger inte vem som skrev texten.` },
    { key: 'phrases', label: 'Standardformuleringar', value: Math.min(1, markers.length / Math.max(1, tokens.length) * 100), detail: `${markers.length} träffar. Formuleringarna används även av människor.` },
    { key: 'vocabulary', label: 'Begränsad ordvariation', value: Math.max(0, Math.min(1,(0.8-diversity)/0.4)), detail: `Ordvariation i fönster om ${window} ord: ${Math.round(diversity*100)} %. Ämne och genre påverkar måttet.` },
  ];
  return {
    method: 'style-heuristics-v2', authorship: 'undetermined', benchmarkStatus: 'not_evaluated',
    status: !supported ? 'unsupported' : enough ? 'analyzed' : 'insufficient',
    styleIndex: enough && supported ? Math.round(signals.reduce((n,s) => n+s.value,0)*25) : null,
    wordCount: tokens.length, charCount: text.length, sentenceCount: spans.length,
    averageLength: Number(mean.toFixed(1)), variation: Number(cv.toFixed(2)), lexicalDiversity: Math.round(diversity*100),
    markers, signals,
    sentences: spans.map(s => ({ ...s, marked: markers.some(m => m.start >= s.start && m.end <= s.end), words: wordCount(s.text) })),
    limitations: ['Stilindex är inte en sannolikhet att texten är AI-skriven.', 'Träffsäkerhet har inte validerats på ett oberoende märkt material.', 'Använd inte resultatet som bevis för fusk eller som grund för beslut om en person.'],
  };
}
