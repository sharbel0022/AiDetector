"""Python counterpart of sites/src/analyzer.mjs; all offsets are UTF-16 units.

This module describes style. It does not classify authorship or load the offline
research models. Keep changes paired with the browser-oracle contract tests.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import math
import re
import unicodedata

MAX_CHARS = 12000
METHOD = 'style-heuristics-v3'
MIN_WORDS = 80
MIN_SENTENCES = 4
MARKERS = (
    'det är viktigt att notera', 'sammanfattningsvis', 'avslutningsvis',
    'det är värt att nämna', 'i dagens digitala värld', 'it is important to note',
    'in conclusion', 'furthermore', 'moreover', 'delve into', 'in summary',
)
LANGUAGE_WORDS = {
    'sv': frozenset('och det att som är på för med jag du vi han hon den ett inte till av om har hade var kan ska men eller när från också finns där här sin sitt denna detta dessa genom mellan mycket sedan blev blir hur varför vilka vad behöver några skulle kunde'.split()),
    'en': frozenset('the and that is are was were with for from this these those they their there have has had not but or when which what who would could should will can into about been being because through between some each more than then she he we you our your its'.split()),
}
# ECMAScript WhiteSpace + LineTerminator; Python str.isspace() differs for U+0085
# and U+001C–001F, and omits U+FEFF.
_SPACE = frozenset('\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff')
_ABBREVIATION = re.compile(r'(?:\b(?:dr|mr|mrs|ms|prof|etc|e\.g|i\.e|vs|bl\.a|t\.ex))\.$', re.I | re.ASCII)
# Unicode Script=Latin ranges (Unicode 17.0, ECMAScript property escape). A name
# check is insufficient: modifier letters and Roman numerals also use this script.
_LATIN = (
    (65, 90), (97, 122), (170, 170), (186, 186), (192, 214), (216, 246),
    (248, 696), (736, 740), (7424, 7461), (7468, 7516), (7522, 7525),
    (7531, 7543), (7545, 7614), (7680, 7935), (8305, 8305), (8319, 8319),
    (8336, 8348), (8490, 8491), (8498, 8498), (8526, 8526), (8544, 8584),
    (11360, 11391), (42786, 42887), (42891, 42972), (42993, 43007),
    (43824, 43866), (43868, 43876), (43878, 43881), (64256, 64262),
    (65313, 65338), (65345, 65370), (67456, 67461), (67463, 67504),
    (67506, 67514), (122624, 122654), (122661, 122666),
)


def _normalize(text):
    return unicodedata.normalize('NFKC', text).lower()


def _category(char):
    return unicodedata.category(char)[0]


def _words(text, offsets):
    """Implement /[LN][LNM]*(?:[’'-][LN][LNM]*)*/gu without ASCII shortcuts."""
    result = []
    i = 0
    while i < len(text):
        if _category(text[i]) not in 'LN':
            i += 1
            continue
        start = i
        i += 1
        while i < len(text):
            if _category(text[i]) in 'LNM':
                i += 1
            elif text[i] in "’'-" and i + 1 < len(text) and _category(text[i + 1]) in 'LN':
                i += 2
            else:
                break
        value = text[start:i]
        result.append({'text': value, 'key': _normalize(value), 'start': offsets[start], 'end': offsets[i], 'index': len(result)})
    return result


def _sentences(text, offsets, tokens):
    result = []
    start = 0

    def add(end):
        nonlocal start
        while start < end and text[start] in _SPACE:
            start += 1
        last = end
        while last > start and text[last - 1] in _SPACE:
            last -= 1
        if last > start and any(t['start'] >= offsets[start] and t['end'] <= offsets[last] for t in tokens):
            result.append({'start': offsets[start], 'end': offsets[last], 'text': text[start:last]})
        start = end

    i = 0
    while i < len(text):
        end = i + 1
        if text[i] in '.!?':
            while end < len(text) and text[end] in ('"', "'", '”', '’', '»', ')', ']', '}'):
                end += 1
        punctuation = text[i] in '.!?' and (end == len(text) or text[end] in _SPACE)
        abbreviation = _ABBREVIATION.search(text[start:i + 1])
        if punctuation and not abbreviation:
            add(end)
            i = end - 1
        elif text[i] == '\n':
            add(i + 1)
        i += 1
    add(len(text))
    return result


def _language(text, tokens, requested):
    letters = sum(_category(c) == 'L' for c in text)
    latin = sum(any(a <= ord(c) <= b for a, b in _LATIN) for c in text)
    matched = {lang: sum(t['key'] in lexicon for t in tokens) for lang, lexicon in LANGUAGE_WORDS.items()}
    result = {'requested': requested, 'detected': None, 'status': 'uncertain', 'matchedWords': matched, 'reason': 'För få tydliga svenska eller engelska språkmarkörer. Språkbedömningen är en försiktig ordregel och kan avstå även för rätt språk.'}
    if requested not in ('sv', 'en') or (letters and latin / letters < 0.8):
        return {**result, 'status': 'unsupported', 'reason': 'Analysen stöder endast svenska och engelska. Texten eller det valda språket ligger utanför stödet.'}
    candidate = 'sv' if matched['sv'] > matched['en'] else 'en'
    other = 'en' if candidate == 'sv' else 'sv'
    distinct = {t['key'] for t in tokens if t['key'] in LANGUAGE_WORDS[candidate]}
    strong = matched[candidate] >= 6 and len(distinct) >= 3 and matched[candidate] / max(1, len(tokens)) >= 0.08
    dominant = matched[candidate] >= max(1, matched[other]) * 1.8
    if not strong or not dominant:
        return result
    supported = candidate == requested
    reason = 'Vanliga funktionsord ger stöd för det valda språket. Detta är ingen validerad språkmodell.' if supported else f"Textens språkmarkörer liknar {'svenska' if candidate == 'sv' else 'engelska'}, men ett annat språk har valts. Välj textens språk och analysera igen."
    return {**result, 'detected': candidate, 'status': 'supported' if supported else 'mismatch', 'reason': reason}


def _repeated_phrases(tokens, sentence_tokens):
    candidates = []
    repeated_positions = set()
    for size in range(12, 3, -1):
        groups = {}
        for group in sentence_tokens:
            for i in range(len(group) - size + 1):
                portion = group[i:i + size]
                key = ' '.join(t['key'] for t in portion)
                groups.setdefault(key, []).append({'start': portion[0]['start'], 'end': portion[-1]['end'], 'tokenStart': portion[0]['index'], 'tokenEnd': portion[-1]['index'] + 1})
        for key, occurrences in groups.items():
            nonoverlapping = []
            for occurrence in occurrences:
                if not nonoverlapping or occurrence['start'] >= nonoverlapping[-1]['end']:
                    nonoverlapping.append(occurrence)
            if len(nonoverlapping) < 2:
                continue
            if size == 4:
                for occurrence in nonoverlapping:
                    repeated_positions.update(range(occurrence['tokenStart'], occurrence['tokenEnd']))
            candidates.append({'key': key, 'words': size, 'occurrences': nonoverlapping})
    selected = []
    occupied = set()
    for candidate in candidates:
        occurrences = [o for o in candidate['occurrences'] if occupied.isdisjoint(range(o['tokenStart'], o['tokenEnd']))]
        if len(occurrences) < 2:
            continue
        selected.append({'phrase': candidate['key'], 'words': candidate['words'], 'count': len(occurrences), 'occurrences': [{'start': o['start'], 'end': o['end']} for o in occurrences[:30]]})
        for occurrence in occurrences:
            occupied.update(range(occurrence['tokenStart'], occurrence['tokenEnd']))
        if len(selected) >= 20:
            break
    return {'groups': selected, 'coverage': len(repeated_positions) / max(1, len(tokens))}


def _round(value):
    return math.floor(value + 0.5)


def _fixed(value, digits):
    # Number.toFixed rounds the exact binary float, with positive ties upward.
    return format(Decimal.from_float(float(value)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP), f'.{digits}f')


def _clamp(value):
    return max(0, min(1, value))


def analyze_text(text: str, language: str = 'sv') -> dict:
    """Return local descriptive signals, never authorship likelihood.

    The synchronous, bounded function can be run via asyncio.to_thread by the API.
    The browser remains the default local execution path. Input and all evidence
    indices follow JavaScript UTF-16 conventions, including astral characters.
    """
    if not isinstance(text, str):
        raise TypeError('Text must be a string')
    offsets = [0]
    for char in text:
        offsets.append(offsets[-1] + (2 if ord(char) > 0xffff else 1))
    if offsets[-1] > MAX_CHARS:
        raise ValueError(f'Maximum {MAX_CHARS} characters')
    tokens = _words(text, offsets)
    spans = _sentences(text, offsets, tokens)
    sentence_tokens = [[t for t in tokens if t['start'] >= s['start'] and t['end'] <= s['end']] for s in spans]
    lengths = [len(group) for group in sentence_tokens]
    mean = len(tokens) / len(lengths) if lengths else 0
    cv = math.sqrt(sum((length - mean) ** 2 for length in lengths) / len(lengths)) / mean if mean else 0
    markers = []
    for phrase in MARKERS:
        for match in re.finditer(re.escape(phrase), text, re.I):
            start, end = match.span()
            # Python IGNORECASE additionally matches dotted/dotless I. The fixed
            # phrase lexicon needs Unicode simple-fold behavior like JS /iu.
            if match.group().casefold() != phrase.casefold():
                continue
            if (start and _category(text[start - 1]) in 'LNM') or (end < len(text) and _category(text[end]) in 'LNM'):
                continue
            markers.append({'text': match.group(), 'start': offsets[start], 'end': offsets[end]})
    markers.sort(key=lambda marker: marker['start'])
    window = min(50, len(tokens))
    diversity = 0
    if window:
        for i in range(len(tokens) - window + 1):
            diversity += len({t['key'] for t in tokens[i:i + window]}) / window
        diversity /= len(tokens) - window + 1
    openings = {}
    for group in sentence_tokens:
        if len(group) >= 2:
            key = ' '.join(t['key'] for t in group[:2])
            openings.setdefault(key, []).append({'start': group[0]['start'], 'end': group[1]['end']})
    repeated_openings = [group for group in openings.values() if len(group) > 1]
    repeated = sum(len(group) - 1 for group in repeated_openings)
    ngrams = _repeated_phrases(tokens, sentence_tokens)
    evidence = []
    position = {offset: i for i, offset in enumerate(offsets)}

    def add_evidence(feature, span, explanation):
        evidence.append({'feature': feature, **span, 'text': text[position[span['start']]:position[span['end']]], 'explanation': explanation})

    for marker in markers:
        add_evidence('phrases', marker, 'Standardformulering i ordlistan. Både människor och språkmodeller använder den; träffen visar inte ursprung.')
    for group in repeated_openings:
        for occurrence in group[:30]:
            add_evidence('openings', occurrence, f'Samma två första ord återkommer i {len(group)} meningar. Det kan bero på struktur eller stilval.')
    for group in ngrams['groups']:
        for occurrence in group['occurrences']:
            add_evidence('repetition', occurrence, f"En följd om {group['words']} ord förekommer {group['count']} gånger. Citat, instruktioner och ämnet kan förklara upprepningen.")
    evidence.sort(key=lambda item: (item['start'], item['end'], item['feature']))
    for index, item in enumerate(evidence):
        item['id'] = f'e{index + 1}'
    signals = [
        {'key': 'uniformity', 'label': 'Jämna meningslängder', 'value': _clamp(1 - cv / 0.65), 'detail': f'Variationskoefficient {_fixed(cv, 2)} över {len(lengths)} meningar. Jämn längd kan vara ett medvetet stilval. Detta är ett mått för hela texten, utan enskild ordträff.'},
        {'key': 'openings', 'label': 'Återkommande inledningar', 'value': _clamp(repeated / max(1, len(lengths)) * 2), 'detail': f'{repeated} återkommande tvåordsinledningar efter den första förekomsten. Upprepning säger inte vem som skrev texten.'},
        {'key': 'phrases', 'label': 'Standardformuleringar', 'value': _clamp(len(markers) / max(1, len(tokens)) * 100), 'detail': f'{len(markers)} träffar i en liten fast ordlista. Ordlistan är inte ett validerat kännetecken för AI.'},
        {'key': 'vocabulary', 'label': 'Begränsad ordvariation', 'value': _clamp((0.8 - diversity) / 0.4), 'detail': f'MATTR: {_round(diversity * 100)} % unika ord i glidande fönster om {window} ord. Ämne, böjningsformer och genre påverkar måttet; ingen enskild ordträff.'},
        {'key': 'repetition', 'label': 'Upprepade ordsekvenser', 'value': _clamp(ngrams['coverage']), 'detail': f"{_round(ngrams['coverage'] * 100)} % av orden ingår i återkommande fyrordssekvenser inom meningar. Exemplen visar längre följder upp till tolv ord. Upprepning kan vara avsiktlig."},
    ]
    for signal in signals:
        signal['evidenceIds'] = [item['id'] for item in evidence if item['feature'] == signal['key']]
    language_assessment = _language(text, tokens, language)
    abstentions = []
    if len(tokens) < MIN_WORDS:
        abstentions.append('too_short')
    if len(lengths) < MIN_SENTENCES:
        abstentions.append('too_few_sentences')
    language_status = language_assessment['status']
    if language_status != 'supported':
        abstentions.append({'unsupported': 'unsupported_language', 'mismatch': 'language_mismatch', 'uncertain': 'language_uncertain'}[language_status])
    status = ('unsupported' if language_status == 'unsupported' else 'insufficient' if len(tokens) < MIN_WORDS else 'language_mismatch' if language_status == 'mismatch' else 'language_uncertain' if language_status == 'uncertain' else 'insufficient_structure' if len(lengths) < MIN_SENTENCES else 'analyzed')
    messages = {'too_short': 'Minst 80 ord behövs för ett stilindex.', 'too_few_sentences': 'Minst fyra meningar med ord behövs för att jämföra meningsrytm.', **{key: language_assessment['reason'] for key in ('unsupported_language', 'language_mismatch', 'language_uncertain')}}
    return {
        'method': METHOD, 'authorship': 'undetermined', 'benchmarkStatus': 'not_evaluated', 'status': status,
        'styleIndex': None if abstentions else _round(sum(signal['value'] for signal in signals) * 20),
        'wordCount': len(tokens), 'charCount': offsets[-1], 'sentenceCount': len(spans),
        'averageLength': float(_fixed(mean, 1)), 'variation': float(_fixed(cv, 2)), 'lexicalDiversity': _round(diversity * 100),
        'languageAssessment': language_assessment, 'abstentionReasons': abstentions,
        'uncertainty': {'authorship': 'unvalidated', 'probabilityAvailable': False, 'reasons': [messages[reason] for reason in abstentions] + ['Författarskap kan inte avgöras. Metoden har inte validerats på ett oberoende märkt material.']},
        'features': {'sentenceLengthCV': cv, 'mattr': diversity, 'mattrWindow': window, 'repeatedOpeningCount': repeated, 'repeatedNgramCoverage': ngrams['coverage'], 'repeatedNgrams': ngrams['groups']},
        'markers': markers, 'evidence': evidence, 'signals': signals,
        'sentences': [{**span, 'marked': any(e['start'] < span['end'] and e['end'] > span['start'] for e in evidence), 'words': lengths[index]} for index, span in enumerate(spans)],
        'limitations': [
            'Stilindex är ett oviktat medelvärde av fem beskrivande signaler, inte en sannolikhet att texten är AI-skriven.',
            'Signalernas skalor och språkregler är manuella och inte statistiskt validerade. Citat, genre, översättning och redigering påverkar dem.',
            'Träffsäkerhet har inte validerats på ett oberoende märkt material. Enskilda markeringar är exempel på stil, inte bevis på ursprung.',
            'Använd inte resultatet som bevis för fusk eller som grund för beslut om en person.',
        ],
    }
