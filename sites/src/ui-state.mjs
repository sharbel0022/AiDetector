export function validateBase(value) {
  if (!value.trim()) return '';
  let url;
  try { url = new URL(value.trim()); }
  catch { throw new Error('Ange en giltig serveradress, till exempel https://api.example.se.'); }
  if (url.username || url.password || url.search || url.hash || url.pathname !== '/') throw new Error('Ange bara serverns ursprung, till exempel https://api.example.se.');
  if (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname))) throw new Error('Använd HTTPS. HTTP tillåts endast till localhost.');
  return url.origin;
}

export function validateRewriteInput(text, maxChars = 8000) {
  return text.trim().length < 10 || text.length > maxChars ? `AI-omskrivning kräver 10–${maxChars.toLocaleString('sv-SE').replace(/\u00a0/g, ' ')} tecken. Korta eller dela upp texten vid behov.` : '';
}

export function normalizeRewriteResult(data, original) {
  if (!data || typeof data.text !== 'string' || !data.text.trim() || data.text.length > 16000 || !Number.isSafeInteger(data.protected_count) || data.protected_count < 0 || data.protected_count > original.length) throw new Error('Servern returnerade ingen giltig omskrivning. Originalet finns kvar.');
  const diff = data.diff;
  if (!Array.isArray(diff) || diff.length > 50000 || diff.some(part => !part || !['equal', 'insert', 'delete'].includes(part.kind) || typeof part.text !== 'string') || diff.filter(part => part.kind !== 'insert').map(part => part.text).join('') !== original || diff.filter(part => part.kind !== 'delete').map(part => part.text).join('') !== data.text) throw new Error('Serverns jämförelse stämmer inte med originalet. Originalet finns kvar.');
  const unchanged = data.text === original;
  if (data.unchanged !== undefined && metadataBoolean(data, 'unchanged') !== unchanged) throw new Error(METADATA_ERROR);
  return {
    text: data.text,
    diff: diff.map(part => ({kind:part.kind,text:part.text})),
    protected_count: data.protected_count,
    original,
    unchanged,
    explanation: metadataString(data, 'explanation', 2000, unchanged ? 'Servern gav ingen förklaring till att texten lämnades oförändrad. Granska texten innan du använder den.' : ''),
    provider: metadataString(data, 'provider', 128, 'AI'),
    model: metadataString(data, 'model', 256, ''),
    warning: metadataString(data, 'warning', 2000, 'Granska betydelse, namn och fakta. Semantisk likvärdighet är inte verifierad.'),
  };
}

// Merge overlapping half-open UTF-16 intervals; React renders every fragment as literal text.
export function sourceHighlights(text, evidence = []) {
  const ranges = evidence.filter(item => Number.isInteger(item.start) && Number.isInteger(item.end) && item.start >= 0 && item.end > item.start && item.end <= text.length).sort((a, b) => a.start - b.start);
  const merged = [];
  for (const item of ranges) {
    const previous = merged.at(-1);
    const explanation = typeof item.explanation === 'string' ? item.explanation : '';
    if (previous && item.start < previous.end) {
      previous.end = Math.max(previous.end, item.end);
      if (explanation && !previous.explanations.includes(explanation)) previous.explanations.push(explanation);
    } else merged.push({ start:item.start, end:item.end, explanations:explanation ? [explanation] : [] });
  }
  const parts = [];
  let cursor = 0;
  for (const range of merged) {
    if (cursor < range.start) parts.push({ text:text.slice(cursor, range.start), marked:false, explanations:[] });
    parts.push({ text:text.slice(range.start, range.end), marked:true, explanations:range.explanations });
    cursor = range.end;
  }
  if (cursor < text.length) parts.push({ text:text.slice(cursor), marked:false, explanations:[] });
  return parts;
}

export function createRequestGate() {
  let current = null;
  return {
    begin() { current?.abort(); current = new AbortController(); return current; },
    cancel() { current?.abort(); current = null; },
    isCurrent(request) { return current === request && !request.signal.aborted; },
  };
}

export function parseProtectedTerms(draft, text) {
  const terms = [...new Set(draft.split(/\r?\n/u).map(term => term.trim()).filter(Boolean))];
  if (terms.length > 40) throw new Error('Ange högst 40 textdelar att behålla exakt.');
  for (const term of terms) {
    if (term.length > 160) throw new Error('Varje skyddad textdel får vara högst 160 tecken.');
    if (!text.includes(term)) throw new Error(`Den skyddade textdelen ”${term}” finns inte exakt så i originalet.`);
  }
  return terms;
}

const METADATA_ERROR = 'Serverns metadata har ett ogiltigt format. Kontrollera backend och försök igen. Originalet finns kvar.';
function assertRecord(data) {
  if (!data || typeof data !== 'object' || Array.isArray(data)) throw new Error(METADATA_ERROR);
}
function metadataString(data, key, limit, fallback) {
  const value = data[key];
  if (value === undefined) return fallback;
  if (typeof value !== 'string' || value.length > limit) throw new Error(METADATA_ERROR);
  return value.trim() || fallback;
}
function metadataBoolean(data, key) {
  const value = data[key];
  if (value === undefined) return false;
  if (typeof value !== 'boolean') throw new Error(METADATA_ERROR);
  return value;
}

// API data is reduced to explicitly validated fields before it enters React state.
export function normalizeHealthResponse(data) {
  assertRecord(data);
  const maxInputChars = data.max_input_chars === undefined ? 8000 : data.max_input_chars;
  if (!Number.isInteger(maxInputChars) || maxInputChars < 10 || maxInputChars > 8000) throw new Error(METADATA_ERROR);
  return {provider:metadataString(data,'provider',128,''),model:metadataString(data,'model',256,''),max_input_chars:maxInputChars};
}
export function normalizeProviderStatus(data) {
  assertRecord(data);
  return {
    ready:metadataBoolean(data,'ready'),
    verified:metadataBoolean(data,'verified'),
    message:metadataString(data,'message',2000,'Anslutningen är inte verifierad. Kontrollera backend och försök igen.'),
  };
}
export function apiErrorMessage(data, status) {
  return typeof data?.detail === 'string' && data.detail.trim() && data.detail.length <= 2000 ? data.detail.trim() : `Begäran misslyckades (${status}). Kontrollera backend och texten och försök igen.`;
}
