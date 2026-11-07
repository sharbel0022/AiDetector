import test from 'node:test';
import assert from 'node:assert/strict';
import * as uiState from './ui-state.mjs';
import { validateBase, validateRewriteInput, normalizeRewriteResult, sourceHighlights, createRequestGate, parseProtectedTerms, normalizeHealthResponse, normalizeProviderStatus, apiErrorMessage } from './ui-state.mjs';

test('API origin validation allows secure origins and loopback without leaking credentials', () => {
  assert.equal(validateBase(' https://api.example.se/ '), 'https://api.example.se');
  assert.equal(validateBase('http://localhost:8767'), 'http://localhost:8767');
  for (const value of ['http://example.se', 'https://user:secret@example.se', 'https://example.se/api', 'https://example.se/?key=secret', 'invalid']) assert.throws(() => validateBase(value));
});

test('rewrite validation reports the actionable character limit', () => {
  assert.match(validateRewriteInput('kort'), /10/);
  assert.match(validateRewriteInput('a'.repeat(8001)), /8 000/);
  assert.equal(validateRewriteInput('Tio tecken räcker.'), '');
});

test('rewrite validation enforces the configured server limit at its exact boundary', () => {
  assert.equal(validateRewriteInput('a'.repeat(4000),4000),'');
  assert.match(validateRewriteInput('a'.repeat(4001),4000),/4 000/);
  assert.equal(validateRewriteInput('a'.repeat(10),10),'');
  assert.match(validateRewriteInput('a'.repeat(11),10),/10/);
  assert.match(validateRewriteInput('a'.repeat(9),4000),/10/);
  assert.equal(validateRewriteInput('a'.repeat(8000)),'');
});

test('a mismatched diff is rejected instead of showing changes for a different original', () => {
  const reply = {text:'Ny text.', diff:[{kind:'delete',text:'Fel text.'},{kind:'insert',text:'Ny text.'}], protected_count:0};
  assert.throws(() => normalizeRewriteResult(reply,'Min text.'), /jämförelse/);
  assert.throws(() => normalizeRewriteResult({...reply,text:''},'Fel text.'));
  const valid = normalizeRewriteResult({...reply,diff:[{kind:'delete',text:'Min text.'},{kind:'insert',text:'Ny text.'}]},'Min text.');
  assert.equal(valid.text,'Ny text.');
  assert.equal(valid.original,'Min text.');
});

test('overlapping source evidence merges without losing literal text or UTF-16 offsets', () => {
  const text='🙂 Hej världen!';
  assert.deepEqual(sourceHighlights(text,[{start:3,end:6,id:'a',explanation:'Ord'},{start:5,end:14,id:'b',explanation:'Fras'}]), [
    {text:'🙂 ',marked:false,explanations:[]}, {text:'Hej världen',marked:true,explanations:['Ord','Fras']}, {text:'!',marked:false,explanations:[]}
  ]);
  assert.deepEqual(sourceHighlights('<img>',[{start:-1,end:99},{start:2,end:2}]),[{text:'<img>',marked:false,explanations:[]}]);
});

test('superseded and cancelled requests cannot publish even when a fetch ignores abort', () => {
  const gate=createRequestGate();
  const first=gate.begin();
  const second=gate.begin();
  assert.equal(first.signal.aborted,true);
  assert.equal(gate.isCurrent(first),false);
  assert.equal(gate.isCurrent(second),true);
  gate.cancel();
  assert.equal(second.signal.aborted,true);
  assert.equal(gate.isCurrent(second),false);
});

test('usage reads after cancellation retain uncertainty before and after a delayed charge appears', () => {
  assert.equal(typeof uiState.usageStateReducer, 'function', 'usage snapshots need cancellation state');
  const scope = JSON.stringify(['https://api.example.se', 'token-a']);
  let state = uiState.usageStateReducer({}, {type:'received', scope, totals:{requests:2,total_tokens:125}, at:'2026-11-07T12:00:00Z'});
  state = uiState.usageStateReducer(state, {type:'uncertain', scope});
  state = uiState.usageStateReducer(state, {type:'loading', scope});
  assert.equal(state[scope].uncertain, true);
  assert.equal(state[scope].totals.requests, 2);
  state = uiState.usageStateReducer(state, {type:'received', scope, totals:{requests:2,total_tokens:125}, at:'2026-11-07T12:00:01Z'});
  assert.equal(state[scope].uncertain, true, 'an early read cannot confirm server settlement');
  state = uiState.usageStateReducer(state, {type:'received', scope, totals:{requests:3,total_tokens:250}, at:'2026-11-07T12:00:05Z'});
  assert.equal(state[scope].totals.total_tokens, 250);
  assert.equal(state[scope].refreshedAt, '2026-11-07T12:00:05Z');
  assert.equal(state[scope].refreshing, false);
  assert.equal(state[scope].uncertain, true, 'aggregate counters cannot identify completion of a particular request');
});

test('usage uncertainty and snapshots stay scoped to their backend and access code', () => {
  assert.equal(typeof uiState.usageStateReducer, 'function');
  const scopes = [JSON.stringify(['https://one.example.se', 'token-a']), JSON.stringify(['https://two.example.se', 'token-a']), JSON.stringify(['https://one.example.se', 'token-b'])];
  let state = uiState.usageStateReducer({}, {type:'uncertain', scope:scopes[0]});
  for (const scope of scopes.slice(1)) state = uiState.usageStateReducer(state, {type:'received', scope, totals:{requests:0,total_tokens:null}, at:'2026-11-07T12:00:00Z'});
  assert.equal(state[scopes[0]].uncertain, true);
  for (const scope of scopes.slice(1)) assert.equal(state[scope].uncertain, false);
  state = uiState.usageStateReducer(state, {type:'received', scope:scopes[0], totals:{requests:3,total_tokens:250}, at:'2026-11-07T12:00:05Z'});
  assert.equal(state[scopes[0]].uncertain, true);
  assert.equal(state[scopes[1]].totals.requests, 0);
  assert.equal(state[scopes[2]].totals.requests, 0);
});

test('a failed usage refresh keeps the last snapshot and cancellation warning until retry', () => {
  assert.equal(typeof uiState.usageStateReducer, 'function');
  const scope = JSON.stringify(['', '']);
  let state = uiState.usageStateReducer({}, {type:'received', scope, totals:{requests:2,total_tokens:125}, at:'2026-11-07T12:00:00Z'});
  state = uiState.usageStateReducer(state, {type:'uncertain', scope});
  state = uiState.usageStateReducer(state, {type:'loading', scope});
  state = uiState.usageStateReducer(state, {type:'failed', scope});
  assert.equal(state[scope].unavailable, true);
  assert.equal(state[scope].refreshing, false);
  assert.equal(state[scope].totals.requests, 2);
  assert.equal(state[scope].refreshedAt, '2026-11-07T12:00:00Z');
  assert.equal(state[scope].uncertain, true);
  state = uiState.usageStateReducer(state, {type:'loading', scope});
  assert.equal(state[scope].refreshing, true);
  assert.equal(state[scope].unavailable, false);
  assert.equal(state[scope].uncertain, true);
});

test('explicit protected terms require exact source matches and reject silent truncation', () => {
  assert.deepEqual(parseProtectedTerms('Åsa\nProjekt Atlas\nÅsa','Åsa leder Projekt Atlas.'),['Åsa','Projekt Atlas']);
  assert.throws(()=>parseProtectedTerms('atlas','Projekt Atlas.'),/atlas/);
  assert.throws(()=>parseProtectedTerms('a'.repeat(161),'a'.repeat(161)),/160/);
  assert.throws(()=>parseProtectedTerms(Array.from({length:41},(_,i)=>`ord${i}`).join('\n'),Array.from({length:41},(_,i)=>`ord${i}`).join(' ')),/40/);
});


test('valid rewrite text and diff cannot publish malformed rendered metadata', () => {
  const reply = {text:'Ny text.', diff:[{kind:'delete',text:'Min text.'},{kind:'insert',text:'Ny text.'}], protected_count:0};
  for (const field of ['provider','model','warning']) {
    for (const value of [null, {}, [], 17, true, 'x'.repeat(100000)]) {
      assert.throws(() => normalizeRewriteResult({...reply,[field]:value},'Min text.'), /metadata/);
    }
  }
  const result=normalizeRewriteResult(reply,'Min text.');
  assert.equal(typeof result.provider,'string');
  assert.equal(typeof result.model,'string');
  assert.equal(typeof result.warning,'string');
  assert.equal('unexpected' in normalizeRewriteResult({...reply,unexpected:{bad:true}},'Min text.'),false);
});

test('health metadata is bounded and cannot inject React children', () => {
  for (const field of ['provider','model']) {
    for (const value of [null,{},[],42,false,'x'.repeat(100000)]) assert.throws(() => normalizeHealthResponse({provider:'ollama',model:'test',[field]:value}), /metadata/);
  }
  assert.deepEqual(normalizeHealthResponse({provider:'ollama',model:'test',untrusted:{bad:true}}),{provider:'ollama',model:'test',max_input_chars:8000});
  assert.throws(() => normalizeHealthResponse(null));
});

test('health input limits default safely and accept only integers from 10 to 8000', () => {
  assert.equal(normalizeHealthResponse({}).max_input_chars,8000);
  for(const limit of [10,4000,8000]) {
    assert.equal(normalizeHealthResponse({max_input_chars:limit}).max_input_chars,limit);
  }
  for(const limit of [null,{},[],false,true,'4000',0,9,8001,10.5,NaN,Infinity]) {
    assert.throws(()=>normalizeHealthResponse({max_input_chars:limit}),/metadata/);
  }
});

test('provider status validates actual booleans and bounded message text', () => {
  for (const value of [null,{},[],42,false,'x'.repeat(100000)]) assert.throws(() => normalizeProviderStatus({ready:false,verified:false,message:value}), /metadata/);
  for (const field of ['ready','verified']) assert.throws(() => normalizeProviderStatus({ready:false,verified:false,[field]:'true'}), /metadata/);
  assert.deepEqual(normalizeProviderStatus({ready:true,verified:true,message:'Modellen svarade.',untrusted:{bad:true}}),{ready:true,verified:true,message:'Modellen svarade.'});
  assert.throws(() => normalizeProviderStatus([]));
});

test('malformed or oversized API error details use an actionable bounded fallback', () => {
  assert.equal(apiErrorMessage({detail:'Modellen är inte tillgänglig.'},503),'Modellen är inte tillgänglig.');
  for(const detail of [{bad:true},[], 'x'.repeat(100000),'']) {
    const message=apiErrorMessage({detail},503);
    assert.ok(message.length<300);
    assert.match(message,/503/);
    assert.match(message,/försök igen/);
  }
});


test('protected-value counts are safe integers bounded by the submitted text', () => {
  const reply={text:'Ny text.',diff:[{kind:'delete',text:'Min text.'},{kind:'insert',text:'Ny text.'}],protected_count:0};
  for(const count of [-1,0.5,Infinity,Number.MAX_SAFE_INTEGER,100000]) assert.throws(()=>normalizeRewriteResult({...reply,protected_count:count},'Min text.'));
});

test('unchanged results retain the original and a bounded explanation without implying a new version', () => {
  const original='Min text.';
  const reply={text:original,diff:[{kind:'equal',text:original}],protected_count:0,unchanged:true,explanation:'  Texten lämnades oförändrad eftersom skyddade värden inte kunde bevaras.  '};
  const result=normalizeRewriteResult(reply,original);
  assert.equal(result.unchanged,true);
  assert.equal(result.text,original);
  assert.equal(result.explanation,'Texten lämnades oförändrad eftersom skyddade värden inte kunde bevaras.');
  assert.match(result.warning,/Semantisk likvärdighet är inte verifierad/);
});

test('older replies derive unchanged status from exact text and use an honest explanation fallback', () => {
  const original='Min text.';
  const unchanged={text:original,diff:[{kind:'equal',text:original}],protected_count:0};
  for(const explanation of [undefined,'','   ']) {
    const result=normalizeRewriteResult({...unchanged,explanation},original);
    assert.equal(result.unchanged,true);
    assert.match(result.explanation,/ingen förklaring/);
  }
  const changed=normalizeRewriteResult({text:'Ny text.',diff:[{kind:'delete',text:original},{kind:'insert',text:'Ny text.'}],protected_count:0},original);
  assert.equal(changed.unchanged,false);
  assert.equal(changed.explanation,'');
});

test('unchanged metadata must be boolean and agree with the returned text', () => {
  const original='Min text.';
  const unchanged={text:original,diff:[{kind:'equal',text:original}],protected_count:0};
  for(const value of [null,{},[],0,1,'true','false',false]) {
    assert.throws(()=>normalizeRewriteResult({...unchanged,unchanged:value},original),/metadata/);
  }
  const changed={text:'Ny text.',diff:[{kind:'delete',text:original},{kind:'insert',text:'Ny text.'}],protected_count:0};
  assert.throws(()=>normalizeRewriteResult({...changed,unchanged:true},original),/metadata/);
  assert.equal(normalizeRewriteResult({...changed,unchanged:false},original).unchanged,false);
});

test('explanations reject malformed or oversized metadata before it reaches React', () => {
  const original='Min text.';
  const reply={text:original,diff:[{kind:'equal',text:original}],protected_count:0,unchanged:true};
  for(const value of [null,{},[],17,true,'x'.repeat(2001)]) {
    assert.throws(()=>normalizeRewriteResult({...reply,explanation:value},original),/metadata/);
  }
  assert.equal(normalizeRewriteResult({...reply,explanation:'x'.repeat(2000)},original).explanation.length,2000);
});
