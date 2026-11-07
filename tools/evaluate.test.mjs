import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { summarize } from './evaluate.mjs';
import * as evaluator from './evaluate.mjs';
test('confusion matrix and coverage are measured without hiding abstentions',()=>{
  const r=summarize([{label:'ai',score:90},{label:'human',score:10},{label:'human',score:80},{label:'ai',score:20},{label:'ai',score:null}]);
  assert.deepEqual(r.confusion,{tp:1,fp:1,tn:1,fn:1});assert.equal(r.coverage,.8);assert.equal(r.precision,.5);assert.equal(r.falsePositiveRate,.5);assert.equal(r.recallAllAI,1/3);
});
test('empty benchmark reports unknown metrics, not perfect accuracy',()=>{const r=summarize([]);assert.equal(r.accuracyAssessed,null);assert.equal(r.precision,null);});
test('invalid labels rejected',()=>assert.throws(()=>summarize([{label:'guess',score:10}])));
test('invalid scores rejected',()=>assert.throws(()=>summarize([{label:'ai',score:NaN}])));
test('false negative rate and tie-aware AUROC use only assessed binary labels',()=>{
  const r=summarize([{label:'ai',score:90},{label:'ai',score:50},{label:'human',score:50},{label:'human',score:10},{label:'ai',score:null}]);
  assert.equal(r.falseNegativeRate,.5);assert.equal(r.auroc,.875);assert.equal(r.binaryAssessed,4);assert.equal(r.calibration.available,false);
  assert.ok(r.intervals95.falsePositiveRate.upper>0);assert.equal(r.abstentionsByLabel.ai,1);
});
test('AI-edited examples are reported separately from binary authorship metrics',()=>{
  const r=summarize([{label:'ai-edited',score:90},{label:'ai-edited',score:null},{label:'human',score:10},{label:'ai',score:90}]);
  assert.deepEqual(r.confusion,{tp:1,fp:0,tn:1,fn:0});assert.equal(r.aiEdited.total,2);assert.equal(r.aiEdited.flagRateAssessed,1);assert.equal(r.binaryAssessed,2);assert.equal(r.accuracyAssessed,1);
});
test('single-class and entirely abstained AUC remain unknown',()=>{
  assert.equal(summarize([{label:'ai',score:90}]).auroc,null);assert.equal(summarize([{label:'human',score:null}]).falseNegativeRate,null);
});

// These records are in-memory validation fixtures, never independent quality evidence.
function record(id,overrides={}){
  const label=overrides.label||'human';
  return {source_id:`id-${id}`,text:`unique${id} example${id} document${id} sample${id}.`,label,language:'en',genre:'essay',split:'test',author_id:`author-${id}`,document_id:`doc-${id}`,source_group_id:`family-${id}`,model:label==='human'?null:'fixture-model',provenance:{kind:'independent',source:`test-memory:${id}`,rights:{status:'verified',basis:'owned',evidence:'In-memory unit fixture only'},label:{method:label==='human'?'self-authored':label==='ai'?'generation-log':'edit-log',evidence:'Unit fixture assigned labels'}},...overrides};
}
test('dataset gate requires all provenance and grouping fields',()=>{
  assert.equal(typeof evaluator.validateDataset,'function');
  for(const field of ['author_id','document_id','source_group_id','genre','split','provenance']){
    const row=record('missing');delete row[field];assert.throws(()=>evaluator.validateDataset([row]),new RegExp(field));
  }
});
test('rights and label evidence are required rather than inferred',()=>{
  assert.equal(typeof evaluator.validateDataset,'function');
  const row=record('rights');row.provenance.rights.status='unknown';assert.throws(()=>evaluator.validateDataset([row]),/rights/);
  row.provenance.rights.status='verified';delete row.provenance.label.evidence;assert.throws(()=>evaluator.validateDataset([row]),/label/);
});
test('edited and generated records require model and production provenance',()=>{
  assert.equal(typeof evaluator.validateDataset,'function');
  assert.throws(()=>evaluator.validateDataset([record('ai',{label:'ai',model:null})]),/model/);
  const row=record('edited',{label:'ai-edited'});row.provenance.label.method='self-authored';assert.throws(()=>evaluator.validateDataset([row]),/edit-log/);
});
test('synthetic fixtures require explicit mode and cannot be mixed with independent data',()=>{
  assert.equal(typeof evaluator.validateDataset,'function');
  const row=record('fixture');row.provenance.kind='synthetic-fixture';row.provenance.label.method='fixture-assignment';
  assert.throws(()=>evaluator.validateDataset([row]),/fixture/);
  assert.equal(evaluator.validateDataset([row],{fixture:true}).counts.total,1);
  assert.throws(()=>evaluator.validateDataset([row,record('independent')],{fixture:true}),/mix|independent/);
});
test('duplicate ids and unknown labels are rejected before scoring',()=>{
  assert.equal(typeof evaluator.validateDataset,'function');
  assert.throws(()=>evaluator.validateDataset([record('same'),record('same')]),/source_id/);
  assert.throws(()=>evaluator.validateDataset([record('label',{label:'robot'})]),/label/);
});
test('all author, document and source-family crossings fail the split audit',()=>{
  assert.equal(typeof evaluator.validateDataset,'function');
  for(const field of ['author_id','document_id','source_group_id']){
    const train=record('train',{split:'train'}),testRow=record('test');testRow[field]=train[field];
    assert.throws(()=>evaluator.validateDataset([train,testRow]),new RegExp(field));
  }
});
test('related-source chains cannot cross train, validation and test',()=>{
  assert.equal(typeof evaluator.validateDataset,'function');
  const first=record('first',{split:'train'}),second=record('second',{split:'validation',related_source_id:first.source_id}),third=record('third',{related_source_id:second.source_id});
  assert.throws(()=>evaluator.validateDataset([first,second,third]),/related_source/);
});
test('exact duplicates normalize punctuation, case, Unicode and whitespace',()=>{
  assert.equal(typeof evaluator.validateDataset,'function');
  const first=record('one',{split:'train',text:'Café has a little house.'}),second=record('two',{text:'  CAFE\u0301 has A little house! '});
  assert.throws(()=>evaluator.validateDataset([first,second]),/duplicate/);
});
test('near duplicates with small edits cannot cross splits',()=>{
  assert.equal(typeof evaluator.validateDataset,'function');
  const text=Array.from({length:100},(_,i)=>`token${i}`).join(' ');
  assert.throws(()=>evaluator.validateDataset([record('base',{split:'train',text}),record('changed',{text:text.replace('token50','replacement')})]),/near.duplicate/i);
});
test('same-split duplication is explicitly counted and cannot pass as independent examples',()=>{
  assert.equal(typeof evaluator.validateDataset,'function');
  const a=record('a'),b=record('b',{text:a.text});
  assert.throws(()=>evaluator.validateDataset([a,b]),/duplicate/);
});
test('evaluation separates test metrics, split counts, slices and fixture status reproducibly',()=>{
  assert.equal(typeof evaluator.evaluateDataset,'function');
  const rows=[record('train',{split:'train'}),record('test',{label:'ai'}),record('edited',{label:'ai-edited',genre:'email',language:'sv'})];
  const r=evaluator.evaluateDataset(rows,{threshold:65});
  assert.equal(r.overall.total,2);assert.equal(r.dataset.counts.bySplit.train,1);assert.equal(r.dataset.counts.byLabel['ai-edited'],1);
  assert.equal(r.byGenre.email.total,1);assert.equal(r.byLength.short.total,2);assert.equal(r.byModel['fixture-model'].total,2);
  assert.equal(r.qualityEvidence,false);assert.equal(r.provenanceStatus,'asserted_not_independently_audited');
  assert.equal(r.reproducibility.datasetSha256.length,64);assert.deepEqual(r,evaluator.evaluateDataset(rows,{threshold:65}));
  assert.equal(r.calibration.available,false);assert.ok(r.overall.abstained>0);
});
test('unavailable test split fails instead of evaluating the training rows',()=>{
  assert.equal(typeof evaluator.evaluateDataset,'function');
  assert.throws(()=>evaluator.evaluateDataset([record('train',{split:'train'})]),/test split/);
});
test('threshold selection uses validation only and freezes it for the test run',()=>{
  assert.equal(typeof evaluator.selectThreshold,'function');
  assert.throws(()=>evaluator.selectThreshold([{label:'ai',score:90,split:'test'}]),/validation/);
  const selected=evaluator.selectThreshold([{label:'ai',score:90,split:'validation'},{label:'human',score:10,split:'validation'}]);
  assert.equal(selected.selectionSplit,'validation');assert.equal(selected.objective,'f1');assert.ok(selected.threshold>10&&selected.threshold<=90);
});
test('checked-in fixture runs reproducibly and cannot masquerade as an independent benchmark',()=>{
  const file=new URL('./fixtures/detector.synthetic.jsonl',import.meta.url);
  assert.ok(fs.existsSync(file));
  const records=fs.readFileSync(file,'utf8').trim().split(/\r?\n/).map(line=>JSON.parse(line));
  assert.ok(records.every(row=>row.provenance.kind==='synthetic-fixture'));
  assert.throws(()=>evaluator.evaluateDataset(records),/fixture/);
  const run=()=>spawnSync(process.execPath,[fileURLToPath(new URL('./evaluate.mjs',import.meta.url)),fileURLToPath(file),'--fixture'],{encoding:'utf8'});
  const first=run(),second=run();assert.equal(first.status,0,first.stderr);assert.equal(first.stdout,second.stdout);
  const report=JSON.parse(first.stdout);assert.equal(report.qualityEvidence,false);assert.equal(report.mode,'synthetic-fixture');assert.ok(report.overall.total>=6);assert.equal(report.reproducibility.fileSha256.length,64);assert.equal(report.dataset.leakage.passed,true);
  const selected=spawnSync(process.execPath,[fileURLToPath(new URL('./evaluate.mjs',import.meta.url)),fileURLToPath(file),'--fixture','--select-threshold'],{encoding:'utf8'});
  assert.equal(selected.status,0,selected.stderr);assert.equal(JSON.parse(selected.stdout).selection.selectionSplit,'validation');
});
test('invalid threshold is rejected even if every example abstains',()=>{
  assert.throws(()=>evaluator.evaluateDataset([record('threshold')],{threshold:NaN}),/Threshold/);
});

test('documented human and AI-edited near-duplicates stay in one dependent family',()=>{
  const text=Array.from({length:100},(_,i)=>`token${i}`).join(' ');
  const human=record('paired-human',{text});
  const edited=record('paired-edit',{label:'ai-edited',text:text.replace('token50','replacement'),related_source_id:human.source_id,source_group_id:human.source_group_id});
  const report=evaluator.validateDataset([human,edited]);
  assert.equal(report.leakage.relatedEditPairs,1);
  assert.equal(report.leakage.relatedEditExamples[0].kind,'near');
  assert.equal(report.counts.groups.source_group_id,1);
  assert.match(report.leakage.note,/dependent|independent/i);
});

test('unchanged documented AI edits remain visible instead of being discarded for perfect-looking coverage',()=>{
  const human=record('unchanged-human');
  const edited=record('unchanged-edit',{label:'ai-edited',text:human.text,related_source_id:human.source_id,source_group_id:human.source_group_id});
  const report=evaluator.validateDataset([human,edited]);
  assert.equal(report.leakage.relatedEditPairs,1);
  assert.equal(report.leakage.relatedEditExamples[0].kind,'exact');
});

test('two documented revisions share their original dependency without inflating independent groups',()=>{
  const human=record('original');
  const first=record('revision1',{label:'ai-edited',text:human.text,related_source_id:human.source_id,source_group_id:human.source_group_id});
  const second=record('revision2',{label:'ai-edited',text:human.text,related_source_id:first.source_id,source_group_id:human.source_group_id});
  const report=evaluator.validateDataset([human,first,second]);
  assert.equal(report.leakage.relatedEditPairs,3);
  assert.equal(report.counts.groups.source_group_id,1);
});

test('claiming an edit alone cannot bypass family, ancestry or split leakage checks',()=>{
  const human=record('guard-original');
  for(const overrides of [{related_source_id:'missing'},{source_group_id:'other-family'},{label:'ai'},{split:'train'}]){
    const edited=record('guard-edit',{label:'ai-edited',text:human.text,related_source_id:human.source_id,source_group_id:human.source_group_id,...overrides});
    assert.throws(()=>evaluator.validateDataset([human,edited]),/duplicate|leakage/);
  }
  const generated=record('generated',{label:'ai',text:human.text});
  const edited=record('edit-of-ai',{label:'ai-edited',text:human.text,source_group_id:generated.source_group_id,related_source_id:generated.source_id});
  assert.throws(()=>evaluator.validateDataset([generated,edited]),/duplicate/);
});
