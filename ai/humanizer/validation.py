"""Exact anchors and conservative surface checks; not semantic verification."""
from collections import Counter
import re
import secrets
from ai.humanizer.meaning import QUANTITY_PATTERN, changed_risk_categories

class PreservationError(ValueError):
    pass

NUMBER = re.compile(r'\d+(?:[ ,.:/\-]\d+)*(?:\s?%)?')
FACT_PATTERN = (
    r'https?://[^\s<>\]"”]+(?<![.,;!?])'
    r'|"[^"\n]+"|“[^”\n]+”|”[^”\n]+”'
    r"|(?<!\w)'[^'\n]+'(?!\w)|‘[^’\n]+’"
    r'|\[[^\]\n]{1,160}\]'
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
    mapping: dict[str, str] = {}
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
