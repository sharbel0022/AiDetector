import json
import pytest
from tools import paired_edits as edits


def source(identifier='h1', family='book1', language='en'):
    return {'source_id':identifier,'source_group_id':family,'document_id':family,'author_id':'human-'+family,'language':language,'genre':'fiction','split':'test','label':'human','text':'Alice did not know whether the old road was safe.','provenance':{'rights':{'basis':'public-domain'}}}


def test_pair_selection_is_fixed_before_generation_and_keeps_one_source_per_family():
    rows=[source('h2'),source('h1'),source('h3','book2')]
    selected=edits.select_sources(rows)
    assert [row['source_id'] for row in selected]==['h1','h3']
    assert selected==edits.select_sources(list(reversed(rows)))
    with pytest.raises(ValueError,match='human'):
        edits.select_sources([dict(rows[0],label='ai')])


def log_for(original, output):
    return {'original_sha256':edits.digest(original['text']),'model':'test-local-model','model_digest':'sha-fixture','request':edits.make_request(original,'test-local-model'),'response':{'model':'test-local-model','done':True,'done_reason':'stop','message':{'content':json.dumps({'text':output})}}}


def test_unchanged_actual_edit_stays_ai_edited_and_in_the_original_family():
    original=source()
    row=edits.edited_record(original,log_for(original,original['text']),'data/pilot-edits/logs/test.json')
    assert row['label']=='ai-edited' and row['related_source_id']==original['source_id']
    assert row['source_group_id']==original['source_group_id'] and row['split']==original['split']
    assert row['author_id']!=original['author_id']
    assert row['edit_changed'] is False
    assert row['provenance']['label']['method']=='edit-log'


def test_recorded_edit_cannot_silently_change_source_or_accept_truncation():
    original=source()
    log=log_for(original,'Alice was unsure whether the old road was safe.')
    assert edits.edited_record(original,log,'log.json')['text'].startswith('Alice')
    log['original_sha256']='wrong'
    with pytest.raises(ValueError,match='source'):
        edits.edited_record(original,log,'log.json')
    log=log_for(original,'truncated')
    log['response']['done_reason']='length'
    with pytest.raises(ValueError,match='incomplete'):
        edits.edited_record(original,log,'log.json')


def test_edit_prompt_is_bounded_untrusted_data_and_uses_frozen_options():
    original=source()
    request=edits.make_request(original,'model')
    body=json.loads(request['messages'][-1]['content'])
    assert body=={'language':'en','text':original['text']}
    assert request['think'] is False and request['options']['seed']==20261102
    assert request['format']['additionalProperties'] is False


def test_cached_edit_cannot_swap_the_predeclared_model_or_installed_digest():
    original=source()
    log=log_for(original,original['text'])
    with pytest.raises(ValueError,match='model'):
        edits.edited_record(original,log,'log.json',expected_model='different-model',expected_digest='sha-fixture')
    with pytest.raises(ValueError,match='digest'):
        edits.edited_record(original,log,'log.json',expected_model='test-local-model',expected_digest='different-digest')
    assert edits.edited_record(original,log,'log.json',expected_model='test-local-model',expected_digest='sha-fixture')['model']=='test-local-model'
    log['response']['model']='different-model'
    with pytest.raises(ValueError,match='response model'):
        edits.edited_record(original,log,'log.json',expected_model='test-local-model',expected_digest='sha-fixture')


def test_frozen_manifest_cannot_be_rewritten_after_an_edit_log_changes(tmp_path):
    path=tmp_path/'manifest.json'
    edits.freeze_json(path,{'logSha256':'original'})
    before=path.read_bytes()
    edits.freeze_json(path,{'logSha256':'original'})
    assert path.read_bytes()==before
    with pytest.raises(ValueError,match='Frozen'):
        edits.freeze_json(path,{'logSha256':'changed'})
    assert path.read_bytes()==before
