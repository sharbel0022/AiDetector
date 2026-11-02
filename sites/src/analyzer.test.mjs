import test from 'node:test';
import assert from 'node:assert/strict';
import { analyzeText, wordCount, MAX_CHARS } from './analyzer.mjs';
const longText = 'Jag tog bussen till biblioteket. Där läste jag en bok om nätverk och skrev några egna anteckningar. Sedan provade jag ett annat exempel hemma och upptäckte ett fel som jag behövde rätta. '.repeat(5);
test('empty input abstains with no score', () => { const r=analyzeText(''); assert.equal(r.styleIndex,null); assert.equal(r.status,'insufficient'); });
test('short input never receives an authorship probability', () => { const r=analyzeText('Det är viktigt att notera att detta är ett test.'); assert.equal(r.styleIndex,null); assert.equal(r.authorship,'undetermined'); assert.equal('probability' in r,false); });
test('supports Swedish unicode words', () => assert.equal(wordCount('Åsa äter blåbär, 2026.'),4));
test('analysis is deterministic and bounded', () => {const a=analyzeText(longText);assert.deepEqual(a,analyzeText(longText));assert.ok(a.styleIndex>=0&&a.styleIndex<=100);assert.equal(a.method,'style-heuristics-v3');});
test('sentence ranges exactly refer to original text', () => {const s='Hej världen!\n\nDetta är nästa mening. 🙂';for(const x of analyzeText(s).sentences) assert.equal(s.slice(x.start,x.end),x.text);});
test('marker detection handles Swedish and English', () => {assert.ok(analyzeText('Sammanfattningsvis är det viktigt. Moreover, this matters.').markers.length>=2);});
test('markers are not matched inside other words',()=>assert.equal(analyzeText('moreoverly sammanfattningsvisare').markers.length,0));
test('no HTML is generated from hostile input',()=>{const r=analyzeText('<script>alert(1)</script> '+longText);assert.equal(r.authorship,'undetermined');assert.equal('html' in r,false);});
test('minimum 80 words required',()=>{assert.equal(analyzeText('ord '.repeat(79)).styleIndex,null);assert.notEqual(analyzeText(longText).styleIndex,null);});
test('oversized input is rejected rather than silently truncated',()=>assert.throws(()=>analyzeText('a'.repeat(MAX_CHARS+1)),RangeError));
test('non-string input rejected',()=>assert.throws(()=>analyzeText(null),TypeError));
test('abbreviations and decimals do not create extra sentences',()=>assert.equal(analyzeText('Dr. Smith mätte 3.14 meter. Det fungerade.').sentences.length,2));
test('closing quotation marks remain in the sentence and allow the next boundary',()=>{
  const text='She said, “The meeting is over.” We left the room.';
  const r=analyzeText(text,'en');assert.equal(r.sentenceCount,2);assert.equal(r.sentences[0].text,'She said, “The meeting is over.”');
  for(const s of r.sentences)assert.equal(text.slice(s.start,s.end),s.text);
});
test('common English abbreviation examples do not end a sentence',()=>{
  assert.equal(analyzeText('We brought fruit, e.g. apples and pears. They were fresh.','en').sentenceCount,2);
});
test('Latin script alone does not establish Swedish or English support',()=>{
  const r=analyzeText('Le texte de cette histoire est une description des villes et des personnes qui habitent dans le pays. '.repeat(7),'sv');
  assert.equal(r.styleIndex,null);assert.equal(r.languageAssessment.status,'uncertain');assert.equal(r.authorship,'undetermined');
});
test('wrong requested language abstains with an explicit reason',()=>{
  const r=analyzeText('The children were in the garden and they could see the trees from the house. It was a bright day but there were clouds over the hills. '.repeat(4),'sv');
  assert.equal(r.status,'language_mismatch');assert.equal(r.languageAssessment.detected,'en');assert.equal(r.styleIndex,null);
});
test('non-Latin and unsupported requested languages abstain',()=>{
  assert.equal(analyzeText('这是一个测试。'.repeat(90),'sv').status,'unsupported');
  assert.equal(analyzeText(longText,'de').status,'unsupported');
});
test('too little sentence structure cannot produce an index',()=>{
  const r=analyzeText('jag och du är i en bok som vi har läst '.repeat(12),'sv');
  assert.equal(r.status,'insufficient_structure');assert.equal(r.styleIndex,null);assert.ok(r.abstentionReasons.includes('too_few_sentences'));
});
test('every evidence highlight refers to the exact original Unicode source',()=>{
  const text='🙂 Café: Sammanfattningsvis är det viktigt att notera saken.\r\n'+longText;
  const r=analyzeText(text);
  assert.ok(r.evidence.length>1);
  for(const e of r.evidence){assert.equal(text.slice(e.start,e.end),e.text);assert.ok(e.end>e.start);assert.ok(e.explanation);}
  assert.ok(r.evidence.some(e=>e.feature==='repetition'));
  for(const signal of r.signals)for(const id of signal.evidenceIds)assert.ok(r.evidence.some(e=>e.id===id));
});
test('phrase boundaries include numbers and combining marks',()=>{
  assert.equal(analyzeText('in conclusion2 moreover1 sammanfattningsviså moreover\u0301').markers.length,0);
});
test('repetition includes phrase counts and is not labelled authorship evidence',()=>{
  const r=analyzeText(longText);
  assert.ok(r.features.repeatedNgrams.length>0);
  assert.ok(r.features.repeatedNgrams.every(n=>n.occurrences.length>=2&&n.words>=4));
  assert.equal(r.uncertainty.probabilityAvailable,false);assert.equal(r.uncertainty.authorship,'unvalidated');
  assert.equal('probability' in r,false);assert.equal('confidence' in r,false);
});
test('the 80-word gate includes its boundary when language and structure are supported',()=>{
  const text=Array.from({length:4},(_,s)=>['the','and','with',...Array.from({length:17},(_,i)=>`word${s}x${i}`)].join(' ')+'.').join(' ');
  assert.equal(wordCount(text),80);assert.notEqual(analyzeText(text,'en').styleIndex,null);
  assert.equal(analyzeText(text.replace('word3x16',''),'en').styleIndex,null);
});
test('lexical measurement and sentence CV have known values on controlled text',()=>{
  const sentence='the and with were they their our from for which';
  const r=analyzeText(Array(8).fill(sentence+'.').join(' '),'en');
  assert.ok(Math.abs(r.features.mattr-.2)<1e-12);assert.equal(r.features.sentenceLengthCV,0);assert.equal(r.features.repeatedNgramCoverage,1);
  assert.equal(r.signals.find(s=>s.key==='uniformity').value,1);
});
test('ngram repetition cannot be manufactured by crossing sentence boundaries',()=>{
  const r=analyzeText('the and with were. A quiet day. Were a quiet day. The and with.','en');
  assert.equal(r.features.repeatedNgrams.length,0);assert.equal(r.features.repeatedNgramCoverage,0);
});
