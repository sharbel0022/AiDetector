import test from 'node:test';
import assert from 'node:assert/strict';
import { summarize } from './evaluate.mjs';
test('confusion matrix and coverage are measured without hiding abstentions',()=>{
  const r=summarize([{label:'ai',score:90},{label:'human',score:10},{label:'human',score:80},{label:'ai',score:20},{label:'ai',score:null}]);
  assert.deepEqual(r.confusion,{tp:1,fp:1,tn:1,fn:1});assert.equal(r.coverage,.8);assert.equal(r.precision,.5);assert.equal(r.falsePositiveRate,.5);assert.equal(r.recallAllAI,1/3);
});
test('empty benchmark reports unknown metrics, not perfect accuracy',()=>{const r=summarize([]);assert.equal(r.accuracyAssessed,null);assert.equal(r.precision,null);});
test('invalid labels rejected',()=>assert.throws(()=>summarize([{label:'guess',score:10}])));
test('invalid scores rejected',()=>assert.throws(()=>summarize([{label:'ai',score:NaN}])));
