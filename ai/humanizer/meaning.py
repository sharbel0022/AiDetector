"""Conservative surface checks, never a claim of semantic equivalence.

These catch selected deletions/additions, timeline direction and movement between
matching surface clauses, plus supported number/unit expressions. They do not
parse semantic scope, resolve actor relations, entailment, arbitrary synonym
strength, implicit negation or added facts. Safe rewrites can be rejected when
they express the same meaning with an unrecognized form.
"""
from collections import Counter
import re


SCALAR = r'\d+(?:[ ,.:/\-]\d+)*'
UNIT = r'(?:°[CF]|(?:k|M|G)?Wh|(?:m|µ|μ)?mol|(?:m|c|k|µ|μ)?(?:g|l|L|m|s)|kr|SEK|EUR|USD|%)'
QUANTITY_PATTERN = rf'(?<!\w){SCALAR}\s?{UNIT}(?:[/·]{UNIT})?(?!\w)'
QUANTITIES = re.compile(QUANTITY_PATTERN)
# Post-restore checks deliberately do not alter protection or the provider
# payload. Capture attached operators even when the following unit is unknown.
# Worded ratios ("per kg") and arbitrary mathematical semantics are not parsed.
UNIT_SUFFIX = r'(?:\s*[/·^*]\s*(?:[A-Za-zµμ°%0-9_+−\-²³]+)?|[²³])*'
QUANTITY_BASE = re.compile(rf'(?<!\w){SCALAR}\s?{UNIT}(?=$|[^\w]|[²³])')
SUFFIX = re.compile(UNIT_SUFFIX)
UNSIGNED_SCALAR = r'\d+(?:[ ,.:/]\d+)*'
SIGNED_SCALAR = rf'(?:[+\-−]\s*)?{UNSIGNED_SCALAR}'
SIGNED_EXPRESSIONS = re.compile(
    rf'(?<!\w){SIGNED_SCALAR}(?:\s*[–—-]\s*{SIGNED_SCALAR})*'
    rf'(?:\s?{UNIT}(?=$|[^\w]|[²³]){UNIT_SUFFIX})?')
QUOTED_OR_REFERENCE = re.compile(
    r'https?://[^\s<>]+|"[^"\n]*"|“[^”\n]*”|”[^”\n]*”'
    r"|(?<!\w)'[^'\n]+'(?!\w)|‘[^’\n]*’|\[[^\]\n]*\]")

# "can"/"kan" are a separate conservative modality guard: deleting either can
# lose ability or possibility. "since" remains excluded because reason/time
# cannot be distinguished here. Exact dates, names and quotations are ignored.
MARKERS = {
    'negation': r"\b(?:not|no|never|without|cannot|neither|nor|inte|ej|aldrig|utan|ingen|inget|inga|varken)\b|n['’]t\b",
    'uncertainty': r'\b(?:may|might|could|possibly|perhaps|possible|potential(?:ly)?|uncertain|preliminary|seems?|appears?|suggests?|suggested|indicates?|indicated|möjligen|kanske|eventuellt|möjlig[at]?|potentiell[at]?|osäker(?:t|a)?|preliminär(?:t|a)?|verkar|förefaller|tyder\s+på)\b',
    'modality': r'\b(?:can|kan|kunde|kunna)\b',
    'likelihood_high': r'\b(?:likely|probably|probable|troligen|sannolik(?:t|a)?)\b',
    'likelihood_low': r'\b(?:unlikely|improbable|osannolik(?:t|a)?)\b',
    'obligation': r'\b(?:must|required\s+to|obliged\s+to|has\s+to|have\s+to|had\s+to|måste|skyldig\s+att)\b',
    'causation': r'\b(?:therefore|thus|consequently|as\s+a\s+result|result(?:s|ed|ing)?\s+in|led\s+to|lead(?:s|ing)?\s+to|caus(?:e|es|ed|ing)|because|due\s+to|därför|eftersom|på\s+grund\s+av|orsak(?:ar|ade|at|as)|till\s+följd|resulter(?:ar|ade)\s+i|vilket\s+(?:ledde|resulterade))\b',
    'timeline_before': r'\b(?:before|earlier|previously|prior\s+to|före|innan|tidigare)\b',
    'timeline_after': r'\b(?:after|later|subsequently|afterwards|thereafter|efter|senare|därefter|efteråt)\b',
    'timeline_during': r'\b(?:during|simultaneously|samtidigt)\b',
    'timeline_until': r'\b(?:until|tills|fram\s+till)\b',
    'timeline_current': r'\b(?:currently|now|för\s+närvarande|nu)\b',
}
COMPILED_MARKERS = {key: re.compile(pattern, re.I) for key, pattern in MARKERS.items()}


def _editable_surface(text: str, exact_values=()) -> str:
    for value in sorted(set(exact_values), key=len, reverse=True):
        text = text.replace(value, ' ')
    return QUOTED_OR_REFERENCE.sub(' ', text)


def marker_counts(text: str, exact_values=()) -> dict[str, int]:
    text = _editable_surface(text, exact_values)
    return {key: len(pattern.findall(text)) for key, pattern in COMPILED_MARKERS.items()}


def changed_risk_categories(original: str, output: str, exact_values=()) -> list[str]:
    before, after = marker_counts(original, exact_values), marker_counts(output, exact_values)
    changed = [key for key in before if before[key] != after[key]]
    # Compare only alignable surface clauses. This catches moving a negation
    # between otherwise similarly punctuated claims, without claiming a parse.
    def scopes(text):
        return [marker_counts(part) for part in re.split(r'[.!?;]+|\n+', _editable_surface(text, exact_values)) if part.strip()]
    old_scopes, new_scopes = scopes(original), scopes(output)
    if len(old_scopes) == len(new_scopes) and len(old_scopes) > 1 and old_scopes != new_scopes:
        changed.append('marker_scope')
    def quantities(text):
        return Counter(text[match.start():SUFFIX.match(text, match.end()).end()]
                       for match in QUANTITY_BASE.finditer(text))
    if quantities(original) != quantities(output):
        changed.append('quantity_units')
    if Counter(SIGNED_EXPRESSIONS.findall(original)) != Counter(SIGNED_EXPRESSIONS.findall(output)):
        changed.append('numeric_signs_or_ranges')
    return changed
