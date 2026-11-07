from pathlib import Path
import unittest, importlib.util, json, tempfile

MODULE = Path(__file__).with_name('corpus_collect.py')

class CollectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if MODULE.exists():
            spec = importlib.util.spec_from_file_location('corpus_collect', MODULE)
            cls.collect = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.collect)
        else:
            cls.collect = None

    def test_body_bounds_exclude_download_license(self):
        self.assertIsNotNone(self.collect, 'Collector implementation is missing')
        text = 'header\n*** START OF THE PROJECT GUTENBERG EBOOK EXAMPLE ***\n\nActual author text.\n\n*** END OF THE PROJECT GUTENBERG EBOOK EXAMPLE ***\nlicense'
        start, end = self.collect.body_bounds(text)
        self.assertEqual(text[start:end].strip(), 'Actual author text.')
        with self.assertRaisesRegex(ValueError, 'markers'):
            self.collect.body_bounds('unmarked text')

    def test_excerpt_offsets_round_trip_without_changing_spelling(self):
        self.assertIsNotNone(self.collect, 'Collector implementation is missing')
        text = '\n\n'.join(' '.join(f'paragraph{p}word{i}' for i in range(100)) + '.' for p in range(40))
        excerpts = self.collect.select_excerpts(text, 0, len(text), count=3, minimum=180, maximum=300)
        self.assertEqual(len(excerpts), 3)
        for excerpt in excerpts:
            self.assertEqual(excerpt['text'], self.collect.normalize_excerpt(text[excerpt['start']:excerpt['end']]))
            self.assertGreaterEqual(len(excerpt['text'].split()), 180)
            self.assertLessEqual(len(excerpt['text'].split()), 300)
        self.assertTrue(all(a['end'] <= b['start'] for a,b in zip(excerpts,excerpts[1:])))

    def test_split_audit_rejects_same_author_across_splits(self):
        self.assertIsNotNone(self.collect, 'Collector implementation is missing')
        rows = [{'source_id':'one','author_id':'same','document_id':'one','source_group_id':'one','split':'train','text':'first'}, {'source_id':'two','author_id':'same','document_id':'two','source_group_id':'two','split':'test','text':'second'}]
        with self.assertRaisesRegex(ValueError, 'author_id'):
            self.collect.audit_groups(rows)

    def test_reconstruction_rejects_tampered_hash_and_excerpt(self):
        self.assertIsNotNone(self.collect, 'Collector implementation is missing')
        source = {'raw_sha256':'bad','raw_path':'unused'}
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            self.collect.verify_raw(source, b'content')
        with self.assertRaisesRegex(ValueError, 'excerpt'):
            self.collect.verify_excerpt('original spelling', {'start':0,'end':8,'text':'modified'})

    def test_catalog_death_evidence_must_be_in_contributor_row(self):
        self.assertTrue(hasattr(self.collect, 'catalog_contributors'), 'Contributor evidence parser is missing')
        page = '<tr><th>Author</th><td>Austen, Jane, 1775-1817</td></tr><tr><th>Editor</th><td>Example, Editor, 1800-1897</td></tr><p>Unrelated year1920</p>'
        people = self.collect.catalog_contributors(page)
        self.assertEqual(people, [{'role':'Author','name_dates':'Austen, Jane, 1775-1817','death_year':1817}, {'role':'Editor','name_dates':'Example, Editor, 1800-1897','death_year':1897}])

    def test_generation_verification_rejects_prompt_and_model_digest_tampering(self):
        self.assertTrue(hasattr(self.collect, 'verify_generation'), 'Generation audit implementation is missing')
        source = {'gutenberg_id':1342,'author_id':'jane-austen','language':'en','genre':'fiction','split':'train','topic':'An unexpected visit.'}
        contract = {'generation_options':{'seed':42}}
        request = {'model':'llama3.2:3b','prompt':self.collect.generation_prompt(source),'stream':False,'think':False,'options':{'seed':42}}
        digest = 'a' * 64
        log = {'model_digest':digest,'request':request,'request_sha256':self.collect.sha256(__import__('json').dumps(request,ensure_ascii=False,sort_keys=True).encode()),'response':{'done':True,'response':'An actual recorded output.'},'raw_response_field_sha256':self.collect.sha256(b'An actual recorded output.')}
        row = {'author_id':'commission-pg1342','document_id':'generation-pg1342','source_group_id':'pg1342','split':'train','language':'en','genre':'fiction','label':'ai','model':'llama3.2:3b','text':'An actual recorded output.','text_sha256':self.collect.sha256(b'An actual recorded output.')}
        self.collect.verify_generation(row,log,source,contract,digest)
        log['model_digest'] = 'b' * 64
        with self.assertRaisesRegex(ValueError, 'digest'):
            self.collect.verify_generation(row,log,source,contract,digest)
        log['model_digest'] = digest
        log['request']['prompt'] = 'Different unrecorded prompt'
        with self.assertRaisesRegex(ValueError, 'request'):
            self.collect.verify_generation(row,log,source,contract,digest)

    def test_frozen_real_corpus_reconstructs_and_retains_held_out_source_families(self):
        result = self.collect.verify()
        self.assertEqual((result['source_count'], result['human_count'], result['ai_count']), (12,36,24))
        rows = self.collect.read_rows(self.collect.PILOT/'corpus.jsonl')
        self.assertEqual({row['model'] for row in rows if row['label']=='ai'}, {'llama3.2:3b','qwen3.5:4b'})
        groups = {}
        for row in rows:
            groups.setdefault(row['source_group_id'], []).append(row)
        self.assertEqual(len(groups), 12)
        for group, family in groups.items():
            self.assertEqual(len(family), 5)
            self.assertEqual(len({row['split'] for row in family}), 1)
            self.assertEqual([row['label'] for row in family].count('human'), 3)
            for row in family:
                if row['label']=='ai':
                    self.assertEqual(row['author_id'], 'commission-'+group)
                    self.assertEqual(row['document_id'], 'generation-'+group)

    def test_manifest_verification_rejects_changed_source_bytes(self):
        actual_root = self.collect.ROOT
        actual_pilot = self.collect.PILOT
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pilot = root/'data'/'pilot'
            pilot.mkdir(parents=True)
            contract = b'{}'
            (pilot/'contract.json').write_bytes(contract)
            (pilot/'policy').write_bytes(b'policy')
            (pilot/'raw').write_bytes(b'changed source')
            manifest = {'contract_sha256':self.collect.sha256(contract),'rights_policy':{'path':'data/pilot/policy','sha256':self.collect.sha256(b'policy')},'additional_rights_evidence':[], 'sources':[{'raw_path':'data/pilot/raw','raw_sha256':self.collect.sha256(b'original source')}]}
            (pilot/'manifest.json').write_text(json.dumps(manifest),encoding='utf8')
            try:
                self.collect.ROOT, self.collect.PILOT = root,pilot
                with self.assertRaisesRegex(ValueError, 'Raw SHA256 mismatch'):
                    self.collect.verify()
            finally:
                self.collect.ROOT, self.collect.PILOT = actual_root,actual_pilot

if __name__ == '__main__':
    unittest.main()
