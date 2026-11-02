"""Collect an untouched pre-2018 Wikipedia human-origin diagnostic; never train.

The human label is a pre-LLM collaborative-publication inference. It does not
verify every contributor, exclude bots, or establish a population human label.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlencode

import requests

if __package__:
    from . import model_evaluate as evaluation
else:
    import model_evaluate as evaluation

ROOT = Path(__file__).resolve().parents[1]
CUTOFF = '2018-01-01T00:00:00Z'
TOPICS = [('photosynthesis', 'Photosynthesis', 'Fotosyntes'), ('bridge', 'Bridge', 'Bro'),
          ('library', 'Library', 'Bibliotek'), ('volcano', 'Volcano', 'Vulkan'),
          ('telephone', 'Telephone', 'Telefon'), ('bicycle', 'Bicycle', 'Cykel')]
PROTOCOL = {'revisionCutoffUtc': CUTOFF, 'topics': TOPICS, 'languages': ['en', 'sv'],
            'passagesPerArticleMaximum': 2, 'minimumWords': 180, 'maximumWords': 300,
            'selection': 'first two disjoint consecutive whole-paragraph runs of 180–300 words, greedily extending to at least180; skip paragraphs longer than300',
            'grouping': 'both languages of each topic share one source_group_id; all Wikipedia contributors share an author_id',
            'label': 'human is a pre-LLM collaborative-publication inference; bots/templates and copied material are not excluded by timestamp',
            'model': 'models/experimental/pilot-v1-audited/model.json', 'styleThreshold': 65,
            'use': 'external human-only false-positive/coverage diagnostic; no accuracy, recall, calibration or training claim',
            'noTuning': True}
UA = 'TextLabResearch/0.1 (historical revision audit)'
LICENSE_URL = 'https://creativecommons.org/licenses/by-sa/4.0/'
TERMS_URL = 'https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8', newline='\n')


def words(text):
    return len(re.findall(r"[^\W_]+(?:[’'-][^\W_]+)*", text, flags=re.UNICODE))


class ProseParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.paragraph = None
        self.paragraphs = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = set(attributes.get('class', '').split())
        ignored = tag in {'table', 'script', 'style', 'figure', 'figcaption', 'math', 'blockquote'} or bool(classes & {
            'reference', 'references', 'reflist', 'hatnote', 'navbox', 'vertical-navbox', 'metadata', 'toc', 'thumb', 'mw-editsection', 'mwe-math-element'})
        ignored = ignored or any(skip for _, skip in self.stack)
        if tag not in {'br', 'hr', 'img', 'input', 'meta', 'link', 'wbr', 'source'}:
            self.stack.append((tag, ignored))
        if tag == 'p' and not ignored:
            self.paragraph = []
        if tag == 'br' and self.paragraph is not None and not ignored:
            self.paragraph.append(' ')

    def handle_endtag(self, tag):
        if tag == 'p' and self.paragraph is not None:
            text = re.sub(r'\s+', ' ', ''.join(self.paragraph)).strip()
            if text:
                self.paragraphs.append(text)
            self.paragraph = None
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if self.paragraph is not None and not any(skip for _, skip in self.stack):
            self.paragraph.append(data)


def extract_paragraphs(html):
    parser = ProseParser()
    parser.feed(html)
    parser.close()
    return parser.paragraphs


def choose_passages(paragraphs):
    source = '\n\n'.join(paragraphs)
    starts, offset = [], 0
    for paragraph in paragraphs:
        starts.append(offset)
        offset += len(paragraph) + 2
    passages, index = [], 0
    while index < len(paragraphs) and len(passages) < 2:
        if words(paragraphs[index]) > 300:
            index += 1
            continue
        end = index + 1
        count = words(paragraphs[index])
        while count < 180 and end < len(paragraphs) and count + words(paragraphs[end]) <= 300:
            count += words(paragraphs[end])
            end += 1
        if 180 <= count <= 300:
            start_offset = starts[index]
            end_offset = starts[end - 1] + len(paragraphs[end - 1])
            passages.append({'text': source[start_offset:end_offset], 'start': start_offset, 'end': end_offset, 'words': count,
                             'paragraphStart': index, 'paragraphEndExclusive': end})
            index = end
        else:
            index += 1
    return passages


def checked_revision(data):
    try:
        page = next(iter(data['query']['pages'].values()))
        revision = page['revisions'][0]
        if not isinstance(page['pageid'], int) or not isinstance(revision['revid'], int):
            raise ValueError('Missing page/revision identity')
        if revision['timestamp'] > CUTOFF:
            raise ValueError('Revision is later than cutoff')
        return {'pageid': page['pageid'], 'title': page['title'], **revision}
    except (KeyError, IndexError, StopIteration, TypeError) as error:
        raise ValueError('Invalid revision API response') from error


def verify_excerpt(record, source):
    if digest(source.encode('utf-8')) != record['source_text_sha256']:
        raise ValueError('Source text hash mismatch')
    if source[record['excerpt_start']:record['excerpt_end']] != record['text']:
        raise ValueError('Excerpt offsets/text mismatch')


def fetch(url, destination):
    # Wikimedia throttled the initial parallel attempt. A single sequential
    # worker and spacing between requests keep the bounded retry polite.
    time.sleep(1.25)
    response = requests.get(url, headers={'User-Agent': UA}, timeout=25)
    destination.write_bytes(response.content)
    meta = {'url': url, 'status': response.status_code, 'contentType': response.headers.get('Content-Type'),
            'sha256': digest(response.content), 'file': destination.name, 'retrievedAtUtc': datetime.now(timezone.utc).isoformat()}
    save_json(destination.with_suffix(destination.suffix + '.meta.json'), meta)
    response.raise_for_status()
    return response


def article(output, language, topic, title):
    stem = f'{language}-{topic}'
    endpoint = f'https://{language}.wikipedia.org/w/api.php'
    revision_url = endpoint + '?' + urlencode({'action': 'query', 'format': 'json', 'prop': 'revisions', 'titles': title,
                                              'rvprop': 'ids|timestamp|user', 'rvstart': CUTOFF, 'rvdir': 'older', 'rvlimit': 1})
    metadata = fetch(revision_url, output / 'raw' / f'{stem}.revision.json').json()
    revision = checked_revision(metadata)
    parse_url = endpoint + '?' + urlencode({'action': 'parse', 'format': 'json', 'oldid': revision['revid'], 'prop': 'text|revid|displaytitle|categories'})
    parsed = fetch(parse_url, output / 'raw' / f'{stem}.parse.json').json()['parse']
    if parsed['revid'] != revision['revid']:
        raise ValueError('Rendered revision does not match frozen metadata')
    paragraphs = extract_paragraphs(parsed['text']['*'])
    source = '\n\n'.join(paragraphs)
    source_path = output / 'sources' / f'{stem}.txt'
    source_path.write_text(source, encoding='utf-8', newline='\n')
    passages = choose_passages(paragraphs)
    permanent = f'https://{language}.wikipedia.org/w/index.php?oldid={revision["revid"]}'
    history = f'https://{language}.wikipedia.org/w/index.php?title={title}&action=history'
    base = {'language': language, 'topic': topic, 'title': revision['title'], 'revision': revision, 'revisionUrl': permanent, 'historyUrl': history,
            'sourceFile': source_path.relative_to(output).as_posix(), 'sourceTextSha256': digest(source.encode()),
            'revisionApiFile': f'raw/{stem}.revision.json', 'parseApiFile': f'raw/{stem}.parse.json',
            'categories': parsed.get('categories', []), 'passageCount': len(passages)}
    rows = []
    for index, passage in enumerate(passages):
        row = {'source_id': f'wikipedia-{language}-{revision["revid"]}-p{index + 1}', 'text': passage['text'], 'label': 'human',
               'split': 'test', 'language': language, 'genre': 'encyclopedia', 'model': None,
               'author_id': 'wikipedia-collaborative-contributors', 'document_id': f'wikipedia-{language}-{revision["pageid"]}',
               'source_group_id': f'wikipedia-topic-{topic}', 'related_source_id': f'wikipedia-topic-{topic}',
               'source_text_file': base['sourceFile'], 'source_text_sha256': base['sourceTextSha256'],
               'excerpt_start': passage['start'], 'excerpt_end': passage['end'],
               'paragraph_start': passage['paragraphStart'], 'paragraph_end_exclusive': passage['paragraphEndExclusive'],
               'revision_id': revision['revid'], 'revision_timestamp': revision['timestamp'],
               'provenance': {'kind': 'independent', 'source': permanent,
                              'rights': {'status': 'verified', 'basis': 'license', 'license': 'CC-BY-SA-4.0',
                                         'evidence': f'Wikimedia rightsinfo snapshot raw/{language}.rights.json; {TERMS_URL} section7. Attribution: Wikipedia contributors, {revision["title"]}, {permanent}; contributor history {history}; {LICENSE_URL}. HTML stripped, citations/navigation removed, whitespace normalized; corpus extraction licensed CC-BY-SA-4.0.'},
                              'label': {'method': 'verified-source',
                                        'evidence': f'Official revision metadata raw/{stem}.revision.json timestamps revision {revision["revid"]} at {revision["timestamp"]}, before public modern LLMs. Human-origin is collaborative-publication inference, not verification of each word; bots, templates, copying and contributor identity are not excluded.'}}}
        verify_excerpt(row, source)
        rows.append(row)
    return base, rows


def collect(output):
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'manifest.json').exists() or (output / 'corpus.jsonl').exists():
        raise ValueError('Frozen modern-human corpus already exists')
    (output / 'raw').mkdir(exist_ok=True)
    (output / 'sources').mkdir(exist_ok=True)
    save_json(output / 'protocol.json', {'declaredAtUtc': datetime.now(timezone.utc).isoformat(), 'declaredBeforeModelScoring': True, **PROTOCOL})
    for language in ('en', 'sv'):
        response = fetch(f'https://{language}.wikipedia.org/w/api.php?' + urlencode({'action': 'query', 'format': 'json', 'meta': 'siteinfo', 'siprop': 'rightsinfo'}), output / 'raw' / f'{language}.rights.json')
        rights = response.json()['query']['rightsinfo']
        if 'creativecommons.org/licenses/by-sa/' not in rights.get('url', ''):
            raise ValueError('Explicit Wikimedia CC-BY-SA license declaration unavailable')
    jobs = [(language, topic, en if language == 'en' else sv) for topic, en, sv in TOPICS for language in ('en', 'sv')]
    def run(job):
        try:
            source, rows = article(output, *job)
            return {'source': source, 'rows': rows}
        except (ValueError, KeyError, OSError, requests.RequestException) as error:
            return {'unavailable': {'language': job[0], 'topic': job[1], 'title': job[2], 'reason': str(error)}}
    with ThreadPoolExecutor(max_workers=1) as executor:
        results = list(executor.map(run, jobs))
    rows = [row for result in results for row in result.get('rows', [])]
    if not rows:
        save_json(output / 'unavailable.json', results)
        raise ValueError('No verifiable pre-cutoff passages could be collected')
    audit = evaluation.audit_records(rows)
    corpus = ''.join(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n' for row in rows)
    (output / 'corpus.jsonl').write_text(corpus, encoding='utf-8', newline='\n')
    manifest = {'schemaVersion': 'textlab-modern-human-holdout-v1', 'frozenBeforeModelScoring': True,
                'corpusSha256': digest(corpus.encode()), 'records': len(rows), 'protocol': PROTOCOL,
                'sources': [result['source'] for result in results if 'source' in result],
                'unavailable': [result['unavailable'] for result in results if 'unavailable' in result],
                'audit': audit['dataset'], 'collectorSha256': digest(Path(__file__).read_bytes()),
                'modelFileSha256BeforeScoring': digest((ROOT / PROTOCOL['model']).read_bytes()),
                'sourceAuditGap': 'Revision date establishes historical publication, not human identity or absence of bots/templates/copied material. No complete contributor/history/talk-page copyright audit. Excerpts are a convenience sample and paired topics may share translated prose.'}
    save_json(output / 'manifest.json', manifest)
    return manifest


def evaluate(output):
    if (output / 'report.json').exists():
        raise ValueError('Frozen external diagnostic already exists; no rescoring/retuning')
    manifest_path = output / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    corpus = (output / 'corpus.jsonl').read_bytes()
    model_bytes = (ROOT / PROTOCOL['model']).read_bytes()
    if digest(corpus) != manifest['corpusSha256'] or digest(model_bytes) != manifest['modelFileSha256BeforeScoring']:
        raise ValueError('Frozen corpus/model hash changed')
    records = evaluation.load_records(output / 'corpus.jsonl')
    for row in records:
        if row['split'] != 'test' or row['label'] != 'human':
            raise ValueError('External diagnostic must contain only test human rows')
        verify_excerpt(row, (output / row['source_text_file']).read_text(encoding='utf-8'))
    audit = evaluation.audit_records(records)
    model = evaluation.validate_artifact(json.loads(model_bytes))
    evaluation.assert_unseen_test(model, records)
    scored = evaluation.score_records(records, audit['analyses'], model)
    style = [{**row, 'score': analysis['styleScore']} for row, analysis in zip(scored, audit['analyses'], strict=True)]
    report = {'status': 'external-human-only-robustness-diagnostic', 'noTuning': True, 'modelSha256': digest(model_bytes),
              'datasetSha256': digest(corpus), 'preScoringManifestSha256': digest(manifest_path.read_bytes()),
              'trained': evaluation.heldout_report(scored, model['selection']['threshold']),
              'frozenStyleComparator': evaluation.heldout_report(style, 65),
              'calibration': evaluation.CALIBRATION, 'sourceAuditGap': manifest['sourceAuditGap'],
              'notice': 'Human-only diagnostic measures false flags/coverage on pre-2018 collaborative Wikipedia prose. No AI recall, accuracy, F1, AUROC, calibrated probability or production-quality claim is supported. Author identity/bot absence is not proven.'}
    # Binary authorship quality cannot be inferred from a human-only diagnostic.
    def remove_quality_metrics(value):
        if isinstance(value, dict):
            for key in ('accuracyAssessed', 'precision', 'recallAssessed', 'recallAllAI', 'falseNegativeRate', 'f1', 'auroc'):
                if key in value:
                    value[key] = None
            if isinstance(value.get('intervals95'), dict):
                for key in ('accuracyAssessed', 'recallAssessed'):
                    value['intervals95'][key] = None
            for child in value.values():
                remove_quality_metrics(child)
        elif isinstance(value, list):
            for child in value:
                remove_quality_metrics(child)
    remove_quality_metrics(report)
    save_json(output / 'report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['collect', 'evaluate'])
    parser.add_argument('--output', default='data/modern-human')
    args = parser.parse_args()
    try:
        result = collect(Path(args.output)) if args.action == 'collect' else evaluate(Path(args.output))
        print(json.dumps({'action': args.action, 'records': result.get('records'), 'trained': result.get('trained', {}).get('overall'), 'unavailable': result.get('unavailable', [])}, ensure_ascii=False, indent=2))
    except (ValueError, OSError, requests.RequestException) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
