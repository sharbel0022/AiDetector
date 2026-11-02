import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { analyzeText, wordCount, MAX_CHARS } from './analyzer.mjs';
import './style.css';

const SAMPLE = `Det är viktigt att notera att en text kan vara tydlig utan att alla meningar ser likadana ut. Ibland räcker en kort mening. Andra gånger behövs mer utrymme för att förklara ett resonemang och visa hur olika delar hänger ihop.

När jag läser en text vill jag förstå vad författaren faktiskt menar. Konkreta exempel hjälper, men de ska inte läggas till om de saknar stöd i originalet. Detsamma gäller siffror, namn och källor. En omskrivning ska förbättra språket, inte förändra innehållet.

Sammanfattningsvis handlar bra redigering om att göra budskapet lättare att följa. Det betyder inte att alla texter ska låta likadant. En personlig berättelse får gärna ha ett annat tempo än en teknisk rapport, och skribentens egen röst ska fortfarande finnas kvar.`;

const PATHS = {
  analyze: 'M4 18V12M10 18V6M16 18V10M22 18V3',
  edit: 'm15 5 4 4M4 20l4-1L20 7a3 3 0 0 0-4-4L4 15v5Z',
  settings: 'M4 7h16M4 17h16M8 4v6M16 14v6',
  arrow: 'M5 12h14m-5-5 5 5-5 5',
  upload: 'M12 16V3m-4 4 4-4 4 4M4 16v5h16v-5',
  copy: 'M9 9h11v12H9zM5 16H3V3h11v2',
  download: 'M12 3v13m-4-4 4 4 4-4M4 17v4h16v-4',
  check: 'm5 12 4 4L19 6',
  shield: 'M12 3 3 7v5c0 5 9 10 9 10s9-5 9-10V7l-9-4Zm-4 9 3 3 5-5',
  close: 'm6 6 12 12M6 18 18 6',
};
function Icon({ name, size = 18 }) { return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={PATHS[name] || PATHS.analyze}/></svg>; }

function validateBase(value) {
  if (!value.trim()) return '';
  const url = new URL(value.trim());
  if (url.username || url.password || url.search || url.hash || url.pathname !== '/') throw new Error('Ange bara serverns ursprung, till exempel https://api.example.se.');
  if (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['localhost','127.0.0.1','[::1]'].includes(url.hostname))) throw new Error('Använd HTTPS. HTTP tillåts endast till localhost.');
  return url.origin;
}

function App() {
  const [mode,setMode] = useState('analyze');
  const [text,setText] = useState('');
  const [language,setLanguage] = useState('sv');
  const [tone,setTone] = useState('natural');
  const [analysis,setAnalysis] = useState(null);
  const [result,setResult] = useState(null);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState('');
  const [notice,setNotice] = useState('');
  const [showDiff,setShowDiff] = useState(false);
  const [settingsOpen,setSettingsOpen] = useState(false);
  const [base,setBase] = useState('');
  const [baseDraft,setBaseDraft] = useState('');
  const [token,setToken] = useState('');
  const [tokenDraft,setTokenDraft] = useState('');
  const [connection,setConnection] = useState(null);
  const [provider,setProvider] = useState(null);
  const inputRef = useRef(null);
  const fileRef = useRef(null);
  const dialogRef = useRef(null);
  const settingsButton = useRef(null);
  const active = useRef(null);
  const revision = useRef(0);
  const words = wordCount(text);

  function invalidate() {
    revision.current++;
    active.current?.abort();
    setBusy(false); setResult(null); setAnalysis(null); setError(''); setNotice(''); setShowDiff(false);
  }
  function changeText(next) { invalidate(); setText(next); }

  async function request(path, options = {}, apiBase = base, apiToken = token) {
    const response = await fetch(apiBase + path, { ...options, cache:'no-store', headers:{ 'Content-Type':'application/json', ...(apiToken ? { Authorization:`Bearer ${apiToken}` } : {}), ...options.headers } });
    let data;
    try { data = await response.json(); } catch { throw new Error('Backend svarade inte med JSON. Kontrollera API-adressen under Inställningar.'); }
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Begäran misslyckades (${response.status}).`);
    return data;
  }

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(),6000);
    setConnection(null); setProvider(null);
    request('/api/health',{signal:controller.signal}).then(data => {
      if (controller.signal.aborted) return;
      setConnection(data);
      return request('/api/provider-status',{signal:controller.signal}).then(status => {
        if (!controller.signal.aborted) setProvider(status);
      }).catch(() => {
        if (!controller.signal.aborted) setProvider({ready:false,message:'Ange serverns åtkomstkod för att kontrollera AI-anslutningen.'});
      });
    }).catch(() => { if (!controller.signal.aborted) setConnection(false); }).finally(() => clearTimeout(timer));
    return () => { controller.abort(); clearTimeout(timer); };
  },[base,token]);
  useEffect(() => () => active.current?.abort(),[]);
  useEffect(() => {
    if (settingsOpen) dialogRef.current?.showModal();
    else dialogRef.current?.close();
  },[settingsOpen]);

  function switchMode(next) { if(next !== mode) {invalidate();setMode(next);} }
  async function run() {
    setError('');setNotice('');
    if (!text.trim()) {setError('Skriv eller klistra in en text först.');inputRef.current?.focus();return;}
    if (mode === 'analyze') {
      try {setAnalysis(analyzeText(text,language));} catch (e) {setError(e.message);}
      return;
    }
    if (text.trim().length<10 || text.length>8000) {setError('AI-omskrivning kräver 10–8 000 tecken.');return;}
    const id=++revision.current;
    const controller = new AbortController();
    active.current=controller;
    const timeout=setTimeout(() => controller.abort('timeout'),135000);
    setBusy(true);setResult(null);
    try {
      const data=await request('/api/rewrite',{method:'POST',body:JSON.stringify({text,tone,language}),signal:controller.signal});
      if(id===revision.current) {setResult(data);setNotice('Omskrivningen är klar. Granska texten innan du använder den.');}
    } catch (e) {
      if(id===revision.current) setError(controller.signal.aborted ? 'Omskrivningen avbröts eller tog för lång tid. Originalet finns kvar.' : e.message);
    } finally {
      clearTimeout(timeout);
      if(id===revision.current) {setBusy(false);active.current=null;}
    }
  }
  async function importFile(event) {
    const file=event.target.files?.[0]; event.target.value='';
    if(!file) return;
    if(!/\.txt$/i.test(file.name)||file.size>60000) {setError('Välj en .txt-fil på högst 60 kB.');return;}
    const id=revision.current;
    try {
      const content=await file.text();
      if (id!==revision.current) return;
      if(content.length>MAX_CHARS) {setError(`Filen innehåller fler än ${MAX_CHARS.toLocaleString('sv-SE')} tecken.`);return;}
      changeText(content);
    } catch {setError('Filen kunde inte läsas.');}
  }
  async function copy() {
    try {await navigator.clipboard.writeText(result.text);setNotice('Texten är kopierad.');} catch {setError('Kopiering blockerades. Markera texten och kopiera manuellt.');}
  }
  function download() {
    const url=URL.createObjectURL(new Blob([result.text],{type:'text/plain;charset=utf-8'}));
    const a=document.createElement('a');a.href=url;a.download='textlab-omskriven.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function saveSettings(event) {
    event.preventDefault();
    try {const next=validateBase(baseDraft);invalidate();setBase(next);setToken(tokenDraft.trim());setSettingsOpen(false);}
    catch(e) {setError(e.message);}
  }

  return <div className="app">
    <header className="header">
      <a href="./" className="brand" aria-label="TextLab startsida"><span className="brand-icon">t<span>l</span></span>textlab<span className="version">STUDIO / 02</span></a>
      <div className="header-actions"><span className="local-chip"><i/>Analys i din webbläsare</span><button className="icon-button settings" ref={settingsButton} onClick={()=>{setBaseDraft(base);setTokenDraft(token);setError('');setSettingsOpen(true);}}><Icon name="settings"/><span>Inställningar</span></button></div>
    </header>
    <main>
      <section className="intro"><div><p className="eyebrow">ETT LUGNARE SÄTT ATT ARBETA MED TEXT</p><h1>Din text. <em>Din röst.</em></h1><p className="lead">Förstå textens mönster. Förbättra språket.<br className="desktop-break"/> Låt innehållet fortsätta vara ditt.</p></div><div className="intro-note"><span className="small-symbol">Aa<span>↗</span></span><p>Svenska & engelska<br/><strong>Analys med förklaringar.</strong></p></div></section>
      <nav className="workspace-tabs" aria-label="Verktyg"><div className="segmented"><button aria-pressed={mode==='analyze'} onClick={()=>switchMode('analyze')} className={mode==='analyze'?'selected':''}><Icon name="analyze"/>AI-detektor<span className="tag">STILANALYS</span></button><button aria-pressed={mode==='rewrite'} onClick={()=>switchMode('rewrite')} className={mode==='rewrite'?'selected':''}><Icon name="edit"/>AI-humanizer</button></div><span className="workspace-hint">{mode==='analyze'?'Ingen text skickas till en server.':'Texten skickas till din konfigurerade AI-backend.'}</span></nav>
      <div className="workspace">
        <section className="editor panel" aria-labelledby="editor-title">
          <div className="panel-heading"><div><span className="step">01</span><h2 id="editor-title">Din originaltext</h2></div><label className="language"><span className="sr-only">Textens språk</span><select aria-label="Textens språk" value={language} onChange={e=>{invalidate();setLanguage(e.target.value);}}><option value="sv">Svenska</option><option value="en">English</option></select></label></div>
          <textarea ref={inputRef} aria-label="Din originaltext" placeholder={"Börja med dina ord.\n\nKlistra in en text eller importera en textfil…"} value={text} maxLength={MAX_CHARS} onChange={e=>changeText(e.target.value)} spellCheck lang={language}/>
          <div className="editor-meta"><span>{words.toLocaleString('sv-SE')} ord <span className="dot">·</span> {text.length.toLocaleString('sv-SE')} / 12 000 tecken</span><button className="text-button" onClick={()=>changeText('')} disabled={!text}>Rensa</button></div>
          {mode==='rewrite' && <fieldset className="tone"><legend>Hur ska texten kännas?</legend>{[['natural','Naturlig'],['simple','Enklare'],['professional','Professionell']].map(([value,label])=><label key={value} className={tone===value?'chosen':''}><input type="radio" name="tone" value={value} checked={tone===value} onChange={()=>{invalidate();setTone(value);}}/>{label}</label>)}</fieldset>}
          <div className="editor-bottom"><div className="import-actions"><input ref={fileRef} type="file" accept=".txt,text/plain" className="sr-only" tabIndex={-1} onChange={importFile}/><button className="text-button" onClick={()=>fileRef.current?.click()}><Icon name="upload" size={16}/>Importera .txt</button><button className="text-button" onClick={()=>changeText(SAMPLE)}>Prova ett exempel</button></div><button className="primary" onClick={run} disabled={busy}>{busy?<><span className="spinner"/>Bearbetar…</>:<>{mode==='analyze'?'Analysera text':'Skriv om med AI'}<Icon name="arrow"/></>}</button></div>
          {busy&&<button className="text-button cancel" onClick={()=>{invalidate();setNotice('Omskrivningen avbröts i webbläsaren. Servern kan fortfarande slutföra modellens anrop.');}}>Avbryt</button>}
        </section>
        <section className="results panel" aria-labelledby="result-title" aria-busy={busy}>
          <div className="panel-heading"><div><span className="step">02</span><h2 id="result-title">{mode==='analyze'?'Insikter, inte gissningar':'Din omskrivna text'}</h2></div><span className="live-tag">{mode==='analyze'?'LOKAL ANALYS':'AI-BACKEND'}</span></div>
          {mode==='analyze' ? analysis ? <Analysis result={analysis}/> : <div className="empty"><div className="illustration"><span/><span/><span/><span/><span/><i><Icon name="analyze" size={25}/></i></div><h3>Varje text har ett mönster.</h3><p>Se hur meningslängd, ordvariation och<br/>återkommande formuleringar samspelar.</p><div className="empty-tags"><span>Meningsrytm</span><span>Ordvariation</span><span>Språkmönster</span></div><small>Minst 80 ord för ett stilindex.<br/>Det här är inte ett bevis på AI-ursprung.</small></div> : result ? <div className="rewrite-result"><div className="result-tools"><label className="diff-toggle"><input type="checkbox" checked={showDiff} onChange={e=>setShowDiff(e.target.checked)}/>Visa ändringar</label><div><button className="icon-button" onClick={copy} aria-label="Kopiera omskriven text"><Icon name="copy"/></button><button className="icon-button" onClick={download} aria-label="Ladda ner omskriven text"><Icon name="download"/></button></div></div><div className="output" tabIndex={0}>{showDiff?result.diff.map((part,i)=>part.kind==='insert'?<ins key={i}>{part.text}</ins>:part.kind==='delete'?<del key={i}>{part.text}</del>:<React.Fragment key={i}>{part.text}</React.Fragment>):result.text}</div><p className="protected"><Icon name="check"/>{result.protected_count} skyddade textdelar kontrollerade</p><p className="result-warning">{result.warning}</p><div className="model-label">{result.provider} / {result.model}</div></div> : <div className="empty"><div className="rewrite-symbol"><Icon name="edit" size={38}/></div><h3>Tydligare. Inte någon annans.</h3><p>En språkmodell bearbetar hela texten<br/>med originalets innehåll som utgångspunkt.</p><div className="model-status"><i className={provider?.ready?'ready':''}/>{connection?.provider?`${connection.provider} · ${connection.model}`:'Ingen AI-backend ansluten'}</div><small>{provider?.message || 'Starta backend eller ange dess adress under Inställningar. Stilanalysen fungerar utan backend.'}</small></div>}
        </section>
      </div>
      {error&&<div className="error" role="alert"><strong>Något behöver ses över.</strong> {error}</div>}
      <div className="notice" role="status" aria-live="polite">{notice}</div>
      <section className="trust-row"><div><Icon name="shield"/><p><strong>Du behåller kontrollen</strong>Texter sparas inte av TextLab. AI-omskrivning skickar text till den valda leverantören.</p></div><div><Icon name="analyze"/><p><strong>Inga falska garantier</strong>Stilanalys kan inte fastställa författarskap. Granska alltid en omskriven texts betydelse.</p></div></section>
    </main>
    <footer><span>textlab <span className="footer-slash">/</span> Studio för genomtänkt text</span><span>V2.0 <span className="footer-slash">/</span> Ingen spårning. Ingen texthistorik.</span></footer>
    <dialog ref={dialogRef} className="settings-dialog" onCancel={()=>setSettingsOpen(false)} onClose={()=>{setSettingsOpen(false);settingsButton.current?.focus();}} aria-labelledby="settings-title"><form onSubmit={saveSettings}><div className="dialog-heading"><h2 id="settings-title">AI-anslutning</h2><button type="button" className="icon-button" aria-label="Stäng inställningar" onClick={()=>setSettingsOpen(false)}><Icon name="close"/></button></div><p>Stilanalys körs lokalt. AI-omskrivning kräver en betrodd backend med Ollama eller OpenAI.</p><label htmlFor="api-base">Backend-adress</label><input id="api-base" type="text" placeholder="Tomt = samma server som webbplatsen" value={baseDraft} onChange={e=>setBaseDraft(e.target.value)}/><small>Ange HTTPS-adressen till din egen server. Ingen API-nyckel ska finnas i den här adressen.</small><label htmlFor="api-token">TextLab-åtkomstkod</label><input id="api-token" type="password" autoComplete="off" value={tokenDraft} onChange={e=>setTokenDraft(e.target.value)} placeholder="TEXTLAB_TOKEN från din backend"/><small>Inte en OpenAI-nyckel. Koden används endast i minnet och försvinner när sidan laddas om.</small><div className="privacy-box">OpenAI-nycklar sparas endast i serverns miljövariabler. Leverantörens egna lagringsregler kan gälla även när TextLab inte sparar texten.</div>{error&&<p className="dialog-error" role="alert">{error}</p>}<button className="primary" type="submit">Anslut<Icon name="arrow"/></button></form></dialog>
  </div>;
}

function Analysis({result:r}) {
  return <div className="analysis-result"><div className="score-row"><div><div className="eyebrow">FÖRKLARBART STILINDEX</div><div className="score">{r.styleIndex??'—'}{r.styleIndex!==null&&<span>/100</span>}</div></div><p>{r.status==='insufficient'?'Lite mer text behövs.':r.status==='unsupported'?'Språket stöds inte av stilmodellen.':'Språkliga signaler — inte sannolikheten för AI.'}<small>{r.status==='insufficient'?`${Math.max(0,80-r.wordCount)} ord kvar till 80.`:'Författarskap: kan inte avgöras.'}</small></p></div>
    <div className="score-track"><span style={{width:`${r.styleIndex??0}%`}}/></div>
    <div className="metrics"><div><strong>{r.sentenceCount}</strong><span>Meningar</span></div><div><strong>{r.averageLength}</strong><span>Ord / mening</span></div><div><strong>{r.lexicalDiversity}%</strong><span>Ordvariation</span></div></div>
    <div className="signal-list">{r.signals.map(s=><details key={s.key}><summary><span>{s.label}</span><div className="signal-track"><span style={{width:`${Math.round(s.value*100)}%`}}/></div><span className="expand">+</span></summary><p>{s.detail}</p></details>)}</div>
    <details className="evidence"><summary>Se formuleringar i sitt sammanhang <span>{r.markers.length} träffar</span></summary><div>{r.sentences.map((s,i)=><p key={i} className={s.marked?'marked':''}>{s.text}</p>)}</div></details>
    <div className="analysis-warning"><Icon name="shield" size={17}/><p>Inte en AI-sannolikhet. Träffsäkerheten är inte validerad mot ett oberoende märkt material. Använd inte detta som bevis för fusk.</p></div>
  </div>;
}

createRoot(document.getElementById('root')).render(<App/>);
