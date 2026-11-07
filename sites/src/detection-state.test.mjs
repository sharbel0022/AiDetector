import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeDetectionResult, segmentParts, prepareLocalAnalysis, buildAnalysisReport, analysisReportText } from './detection-state.mjs';
import { normalizeUsage, normalizeUsageTotals } from './ui-state.mjs';
import { wordCount } from './analyzer.mjs';

const SOURCE = '🙂 Hej världen.\nThe text is here.';
function fixture() {
  return { detector:{modelVersion:'test-only-v5',category:'mixed',documentProbability:0.72,aiMarkedPercent:100 / 3,documentValidated:true,calibrationValidated:true,segmentValidated:true,segmentCalibrationValidated:false,status:'analyzed',reasons:['Testfixture, inte modellbevis.'],analyzedWords:wordCount(SOURCE),flaggedWords:2,excludedWords:0,totalSegments:2,flaggedSegments:1,calibrationStatus:'validated'},segments:[{id:'s1',start:0,end:15,text:SOURCE.slice(0,15),wordCount:wordCount(SOURCE.slice(0,15)),eligible:true,category:'ai_like',probability:0.87,reason:'Segmentmodellens bedömning.'},{id:'s2',start:16,end:SOURCE.length,text:SOURCE.slice(16),wordCount:wordCount(SOURCE.slice(16)),eligible:true,category:'human_like',probability:0.1,reason:'Segmentmodellens bedömning.'}] };
}
test('confidence, share and segment probability have independent evidence gates', () => {
  const raw=fixture();
  const valid=normalizeDetectionResult(raw,SOURCE);
  assert.equal(valid.detector.documentProbability,0.72);
  assert.equal(valid.detector.aiMarkedPercent,100 / 3);
  assert.equal(valid.segments[0].probability,null);
  for (const field of ['documentValidated','calibrationValidated']) {
    assert.equal(normalizeDetectionResult({...raw,detector:{...raw.detector,[field]:false}},SOURCE).detector.documentProbability,null);
  }
  const blocked=normalizeDetectionResult({...raw,detector:{...raw.detector,documentValidated:false,calibrationValidated:false,segmentValidated:false}},SOURCE);
  assert.equal(blocked.detector.category,'uncertain');
  assert.equal(blocked.detector.aiMarkedPercent,null);
  assert.equal(blocked.segments[0].category,'unassessed');
  assert.equal(blocked.detector.flaggedWords,0);
  assert.equal(blocked.detector.analyzedWords,6);
  assert.equal(normalizeDetectionResult({...raw,detector:{...raw.detector,segmentCalibrationValidated:true}},SOURCE).segments[0].probability,0.87);
});
test('Unicode source intervals preserve every character and reject source disagreement', () => {
  const raw=fixture(), normalized=normalizeDetectionResult(raw,SOURCE);
  assert.equal(segmentParts(SOURCE,normalized.segments).map(part=>part.text).join(''),SOURCE);
  for (const patch of [{start:1},{end:SOURCE.length + 1},{text:'invented'},{id:'s2'},{end:1}]) {
    assert.throws(()=>normalizeDetectionResult({...raw,segments:[{...raw.segments[0],...patch},raw.segments[1]]},SOURCE));
  }
  assert.throws(()=>normalizeDetectionResult({...raw,segments:[raw.segments[1],raw.segments[0]]},SOURCE));
});
test('malformed metadata, enum values, flags and inconsistent wordweighted shares fail closed', () => {
  for (const patch of [{category:'definitely AI'},{documentValidated:'true'},{segmentCalibrationValidated:1},{documentProbability:82},{aiMarkedPercent:64},{analyzedWords:0},{flaggedWords:7},{flaggedSegments:2},{totalSegments:1},{reasons:[{}]},{modelVersion:{}},{calibrationStatus:[]}]) {
    const raw=fixture();
    assert.throws(()=>normalizeDetectionResult({...raw,detector:{...raw.detector,...patch}},SOURCE));
  }
  for (const patch of [{wordCount:3},{category:'mixed'},{probability:NaN},{reason:{}}]) {
    const raw=fixture();assert.throws(()=>normalizeDetectionResult({...raw,segments:[{...raw.segments[0],...patch},raw.segments[1]]},SOURCE));
  }
});
test('report contains definitions, exact source and only sanitized metrics', () => {
  const raw=fixture(); raw.detector.documentValidated=false;raw.detector.segmentValidated=false;raw.detector.api_key='must-not-export';
  const analysis=normalizeDetectionResult(raw,SOURCE), report=buildAnalysisReport(analysis);
  assert.equal(report.sourceText,SOURCE);
  assert.equal(report.detector.documentProbability,null);
  assert.equal(report.detector.aiMarkedPercent,null);
  assert.equal(JSON.stringify(report).includes('must-not-export'),false);
  const plain=analysisReportText(analysis);
  assert.ok(plain.includes(SOURCE));assert.match(plain,/Ej tillgängligt/);assert.match(plain,/inte bevis/);
});
test('automatic language identifies supported text, manual mismatch warns and short text abstains', () => {
  const english='The text is clear and the reader can understand what the writer means. It is a useful example of the way we use language.';
  assert.equal(prepareLocalAnalysis(english,'auto').languageAssessment.effective,'en');
  assert.equal(prepareLocalAnalysis(english,'sv').languageAssessment.status,'mismatch');
  assert.equal(prepareLocalAnalysis('Hej','auto').languageAssessment.effective,null);
});
test('provider usage preserves missing counters and distinguishes unknown from free', () => {
  assert.equal(normalizeUsage(undefined),null);
  const raw={provider:'mock',model:'fixture',recorded_at:'2026-11-07T10:00:00Z',latency_ms:52,input_tokens:100,output_tokens:20,total_tokens:120,cached_input_tokens:null,cost:{currency:'USD',estimated_amount:0.005,status:'estimated',pricing_version:'fixture'}};
  assert.equal(normalizeUsage(raw).cost.estimated_amount,0.005);
  assert.equal(normalizeUsage({...raw,input_tokens:null,output_tokens:null,total_tokens:null,cost:{...raw.cost,status:'unknown',estimated_amount:null}}).total_tokens,null);
  for(const patch of [{input_tokens:'100'},{total_tokens:999},{cost:{...raw.cost,status:'unknown'}},{cost:{...raw.cost,estimated_amount:-1}},{cost:{...raw.cost,currency:'SEK'}}]) assert.throws(()=>normalizeUsage({...raw,...patch}));
});
test('aggregate usage preserves partial totals and rejects malformed counters', () => {
  const reply={period:{start:'2026-11-07T00:00:00Z',end:'2026-11-08T00:00:00Z'},requests:2,input_tokens:100,output_tokens:20,total_tokens:120,cached_input_tokens:null,unreported_counters:{input_tokens:1,output_tokens:1,total_tokens:1,cached_input_tokens:2},estimated_cost:{currency:'USD',amount:0.005,unknown_requests:1,not_applicable_requests:0}};
  const totals=normalizeUsageTotals(reply);
  assert.equal(totals.total_tokens,120);assert.equal(totals.unreported_counters.total_tokens,1);assert.equal(totals.cached_input_tokens,null);
  assert.equal(totals.estimated_cost.unknown_requests,1);
  for(const patch of [{total_tokens:'120'},{period:{}},{estimated_cost:{...reply.estimated_cost,amount:Infinity}},{unreported_counters:{...reply.unreported_counters,total_tokens:-1}}]) assert.throws(()=>normalizeUsageTotals({...reply,...patch}));
});

test('legacy usage stays explicitly incomplete without inventing missing counters or actual usage from reservations', () => {
  const reply={period:{start:'2026-11-07T00:00:00Z',end:'2026-11-08T00:00:00Z'},requests:1,input_tokens:100,output_tokens:20,total_tokens:120,cached_input_tokens:0,unreported_counters:{input_tokens:0,output_tokens:0,total_tokens:0,cached_input_tokens:0},estimated_cost:{currency:'USD',amount:0.005,unknown_requests:0,not_applicable_requests:0},legacy_usage_unavailable:true,reservations:{legacy_reserved_tokens:5000}};
  const totals=normalizeUsageTotals(reply);
  assert.equal(totals.legacy_usage_unavailable,true);
  assert.equal(totals.total_tokens,120);
  assert.equal(totals.estimated_cost.amount,0.005);
  assert.equal(totals.unreported_counters.total_tokens,0);
  assert.equal(totals.estimated_cost.unknown_requests,0);
  assert.equal(normalizeUsageTotals({...reply,legacy_usage_unavailable:undefined}).legacy_usage_unavailable,false);
  for (const value of [null,'true',1,{},[]]) assert.throws(()=>normalizeUsageTotals({...reply,legacy_usage_unavailable:value}));
  const unknown=normalizeUsageTotals({...reply,input_tokens:null,output_tokens:null,total_tokens:null,estimated_cost:{...reply.estimated_cost,amount:null}});
  assert.equal(unknown.total_tokens,null);
  assert.equal(unknown.estimated_cost.amount,null);
});

test('coordinated count/share changes cannot inflate source-derived coverage or flagged share', () => {
  const raw=fixture();
  raw.segments[0].wordCount=4;
  raw.segments[1].wordCount=2;
  raw.detector.flaggedWords=4;
  raw.detector.aiMarkedPercent=200 / 3;
  assert.throws(()=>normalizeDetectionResult(raw,SOURCE));
  const omitted=fixture();
  omitted.segments.shift();
  Object.assign(omitted.detector,{category:'human_like',analyzedWords:4,flaggedWords:0,excludedWords:2,totalSegments:1,flaggedSegments:0,aiMarkedPercent:0});
  assert.throws(()=>normalizeDetectionResult(omitted,SOURCE));
  const wrongEligibility=fixture();wrongEligibility.segments[0].eligible=false;
  assert.throws(()=>normalizeDetectionResult(wrongEligibility,SOURCE));
  const wrongTotal=fixture();wrongTotal.detector.excludedWords=1;
  assert.throws(()=>normalizeDetectionResult(wrongTotal,SOURCE));
});

test('mixed classification requires independently validated opposing segment outcomes', () => {
  const noSegments=fixture();noSegments.detector.segmentValidated=false;
  assert.equal(normalizeDetectionResult(noSegments,SOURCE).detector.category,'uncertain');
  const oneClass=fixture();oneClass.segments[1].category='uncertain';
  assert.equal(normalizeDetectionResult(oneClass,SOURCE).detector.category,'uncertain');
  const segmentOnly=fixture();segmentOnly.detector.documentValidated=false;
  assert.equal(normalizeDetectionResult(segmentOnly,SOURCE).detector.category,'mixed');
});

test('coverage verifies combining marks, apostrophes, hyphens, numbers and Unicode boundaries', () => {
  const text='🙂 A\u030asa skriver O’Connor och e-post 12,5.\nThe reader follows the text.';
  const split=text.indexOf('\n');
  const raw=fixture();
  raw.segments=[{...raw.segments[0],start:0,end:split,text:text.slice(0,split),wordCount:wordCount(text.slice(0,split))},{...raw.segments[1],start:split+1,end:text.length,text:text.slice(split+1),wordCount:wordCount(text.slice(split+1))}];
  raw.detector.analyzedWords=wordCount(text);raw.detector.flaggedWords=raw.segments[0].wordCount;raw.detector.aiMarkedPercent=100*raw.detector.flaggedWords/raw.detector.analyzedWords;
  const result=normalizeDetectionResult(raw,text);
  assert.equal(result.detector.analyzedWords,wordCount(text));
  assert.equal(segmentParts(text,result.segments).map(part=>part.text).join(''),text);
});
