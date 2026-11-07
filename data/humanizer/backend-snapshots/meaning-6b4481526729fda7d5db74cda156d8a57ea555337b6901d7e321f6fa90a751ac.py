"""Conservative surface checks, never a claim of semantic equivalence.

These catch selected deletions/additions of meaning-bearing markers and supported
number/unit expressions. They do not resolve scope, actor relations, entailment,
synonym strength, implicit negation, or arbitrary added facts. Safe rewrites can
be rejected when they express the same meaning with an unrecognized form.
"""
from collections import Counter
import re


SCALAR = r'\d+(?:[ ,.:/\-]\d+)*'
UNIT = r'(?:°[CF]|(?:k|M|G)?Wh|(?:m|µ|μ)?mol|(?:m|c|k|µ|μ)?(?:g|l|L|m|s)|kr|SEK|EUR|USD|%)'
QUANTITY_PATTERN = rf'(?<!\w){SCALAR}\s?{UNIT}(?:[/·]{UNIT})?(?!\w)'
QUANTITIES = re.compile(QUANTITY_PATTERN)
QUOTED_OR_REFERENCE = re.compile(
    r'https?://[^\s<>]+|"[^"\n]*"|“[^”\n]*”|”[^”\n]*”'
    r"|(?<!\w)'[^'\n]+'(?!\w)|‘[^’\n]*’|\[[^\]\n]*\]")

# Categories intentionally do not include ambiguous words such as Swedish
# "kan" (ability or possibility), English "since" (time or reason), or "May"
# as an unprotected month name. Dates/names/quotes are ignored via exact anchors.
MARKERS = {
    'negation': r"\b(?:not|no|never|without|cannot|neither|nor|inte|ej|aldrig|utan|ingen|inget|inga|varken)\b|n['’]t\b",
    'uncertainty': r'\b(?:may|might|could|possibly|perhaps|possible|potential|uncertain|preliminary|möjligen|kanske|eventuellt|möjlig[at]?|potentiell[at]?|osäker(?:t|a)?|preliminär(?:t|a)?)\b',
    'obligation': r'\b(?:must|required\s+to|obliged\s+to|has\s+to|have\s+to|had\s+to|måste|skyldig\s+att)\b',
    'causation': r'\b(?:therefore|thus|consequently|as\s+a\s+result|resulting\s+in|led\s+to|caused|because|därför|orsakade|till\s+följd|vilket\s+(?:ledde|resulterade))\b',
}
COMPILED_MARKERS = {key: re.compile(pattern, re.I) for key, pattern in MARKERS.items()}


def marker_counts(text: str, exact_values=()) -> dict[str, int]:
    for value in sorted(set(exact_values), key=len, reverse=True):
        text = text.replace(value, ' ')
    text = QUOTED_OR_REFERENCE.sub(' ', text)
    return {key: len(pattern.findall(text)) for key, pattern in COMPILED_MARKERS.items()}


def changed_risk_categories(original: str, output: str, exact_values=()) -> list[str]:
    before, after = marker_counts(original, exact_values), marker_counts(output, exact_values)
    changed = [key for key in before if before[key] != after[key]]
    if Counter(QUANTITIES.findall(original)) != Counter(QUANTITIES.findall(output)):
        changed.append('quantity_units')
    return changed
