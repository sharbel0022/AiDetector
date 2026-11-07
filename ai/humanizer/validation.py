"""Exact anchors and conservative surface checks; not semantic verification."""
from collections import Counter
import re
import secrets
from ai.humanizer.meaning import QUANTITY_PATTERN, changed_risk_categories, marker_counts

class PreservationError(ValueError):
    pass


class ProtectedValues(dict):
    """Dictionary-compatible anchors with their original offsets, kept in memory."""
    def __init__(self, spans):
        super().__init__()
        self.spans = tuple(spans)

NUMBER = re.compile(r'\d+(?:[ ,.:/\-]\d+)*(?:\s?%)?')
FACT_PATTERN = (
    r'https?://[^\s<>\]"”]+(?<![.,;!?])'
    r'|"[^"\n]+"|“[^”\n]+”|”[^”\n]+”'
    r"|(?<!\w)'[^'\n]+'(?!\w)|‘[^’\n]+’"
    r'|\[[^\]\n]{1,160}\]'
    r'|\([A-ZÅÄÖÉÜ][^()\n]{0,120}?\b(?:19|20)\d{2}[a-z]?[^()\n]{0,40}\)'
    r'|\d+(?:[ ,.:/\-]\d+)*(?:\s?%)?'
)
FACTS = re.compile(FACT_PATTERN)
MONTHS = r'(?:January|February|March|April|May|June|July|August|September|October|November|December|januari|februari|mars|april|maj|juni|juli|augusti|september|oktober|november|december)'
DATE = rf'\b\d{{1,2}}\s+(?i:{MONTHS})\s+\d{{4}}\b|\b(?i:{MONTHS})\s+\d{{1,2}},?\s+\d{{4}}\b'
NAME_WORD = r'[A-ZÅÄÖÉÜÀ-Þ][a-zåäöéüà-ÿ]+(?:[-\x27][A-ZÅÄÖÉÜÀ-Þ]?[a-zåäöéüà-ÿ]+)*'
NAMES = rf'\b{NAME_WORD}(?:\s+(?:(?:van|von|de|del|af)\s+)?{NAME_WORD})*\b|\b[A-ZÅÄÖ]{{2,}}\b'
# Capitalization is only a conservative name heuristic. Protecting an occasional
# ordinary noun is preferable to silently changing a name; explicit terms cover
# lowercase/non-Latin names and ambiguous common words.
COMMON_STARTERS = set('A An And As At But By For From He Her His How I If In It Its My No On Or Our She So That The Their Them There These They This Those To We What When Where Which Who Why With You Your De Den Det Dessa Detta Din Ditt Du En Ett Er Era För Från Han Hans Har Hon Hennes Hur I Inte Jag Läs Man Med Men Min Mitt Ni Nu När Om Och På Rapporten Som Så Till Vad Var Vi Vår Våra Även Är'.split())
SENTENCE_STARTERS = set('More Further Finally However Therefore Team Report Reports Research Results Study Goal Aim Teamet Mer Syfte Syftet Studien Resultatet Resultaten Information Forskningen'.split())
PROTECTED = re.compile(rf'{DATE}|{QUANTITY_PATTERN}|{FACT_PATTERN}|{NAMES}')
TOKEN = re.compile(r'__TL_[a-f0-9]{16}_\d+__')

def protect_text(text: str, protected_terms: list[str] | None = None) -> tuple[str, dict[str,str]]:
    if '__TL_' in text:
        raise PreservationError('Reserved token in input')
    terms = protected_terms or []
    if any(term not in text for term in terms):
        raise PreservationError('Protected term absent')
    spans: list[tuple[int, int]] = []
    for match in PROTECTED.finditer(text):
        value = match.group(0)
        prefix = text[:match.start()]
        sentence_start = not prefix.strip() or re.search(r'(?:[.!?]|\n)\s*$', prefix)
        if (value in COMMON_STARTERS or (value in SENTENCE_STARTERS and sentence_start)) and value not in terms:
            continue
        spans.append(match.span())
    # Explicit spans are collected independently, including overlapping matches.
    # A regex alternation alone would let an earlier name/quote swallow the
    # beginning of an explicit term, leaving its remaining words editable.
    for term in terms:
        for match in re.finditer(r'(?=(' + re.escape(term) + r'))', text):
            spans.append((match.start(1), match.end(1)))
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start < merged[-1][1]:
            previous_start, previous_end = merged[-1]
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))
    mapping: dict[str, str] = ProtectedValues(merged)
    nonce = secrets.token_hex(8)
    parts: list[str] = []
    cursor = 0
    for start, end in merged:
        key = f'__TL_{nonce}_{len(mapping)}__'
        mapping[key] = text[start:end]
        parts.extend((text[cursor:start], key))
        cursor = end
    parts.append(text[cursor:])
    return ''.join(parts), mapping

def restore_text(output: str, mapping: dict[str,str], original: str) -> str:
    if not output.strip() or len(output) > 16000:
        raise PreservationError('Empty or oversized output')
    if Counter(TOKEN.findall(output)) != Counter(mapping.keys()):
        raise PreservationError('Protected values changed')
    if TOKEN.findall(output) != list(mapping):
        raise PreservationError('Protected actor, quantity or reference order changed')
    if mapping:
        # Reconstruct the editable intervals from the ordered exact spans. The
        # generated counterpart must keep risk markers within those intervals;
        # a matching document-wide count does not suffice when actors swap scope.
        cursor, source_parts = 0, []
        spans = getattr(mapping, 'spans', None)
        for index, value in enumerate(mapping.values()):
            # Explicit offsets avoid confusing a later name with an identical
            # substring inside an earlier editable word. Plain dictionaries from
            # older internal callers retain the sequential fallback.
            start, end = spans[index] if spans is not None else (original.find(value, cursor), None)
            end = start + len(value) if end is None else end
            if start < cursor or original[start:end] != value:
                raise PreservationError('Invalid protected value mapping')
            source_parts.append(original[cursor:start])
            cursor = end
        source_parts.append(original[cursor:])
        if [marker_counts(part) for part in source_parts] != [marker_counts(part) for part in TOKEN.split(output)]:
            raise PreservationError('Meaning-bearing markers moved between protected values')
    for key,value in mapping.items():
        output=output.replace(key,value)
    if '__TL_' in output:
        raise PreservationError('Unknown reserved marker')
    if Counter(NUMBER.findall(output)) != Counter(NUMBER.findall(original)):
        raise PreservationError('Numbers changed')
    if Counter(FACTS.findall(output)) != Counter(FACTS.findall(original)):
        raise PreservationError('Protected facts added or changed')
    if any(output.count(value) != original.count(value) for value in set(mapping.values())):
        raise PreservationError('Protected values missing, changed or duplicated')
    if changed_risk_categories(original, output, mapping.values()):
        raise PreservationError('Meaning-bearing surface markers changed')
    return output.strip()
