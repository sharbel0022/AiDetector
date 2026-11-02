import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { analyzeText, wordCount, MAX_CHARS } from './analyzer.mjs';
import { validateBase, validateRewriteInput, normalizeRewriteResult, sourceHighlights, createRequestGate, parseProtectedTerms, normalizeHealthResponse, normalizeProviderStatus, apiErrorMessage } from './ui-state.mjs';
import './style.css';

const SAMPLE = `Det är viktigt att notera att en text kan vara tydlig utan att alla meningar ser likadana ut. Ibland räcker en kort mening. Andra gånger behövs mer utrymme för att förklara ett resonemang och visa hur olika delar hänger ihop.

När jag läser en text vill jag förstå vad författaren faktiskt menar. Konkreta exempel hjälper, men de ska inte läggas till om de saknar stöd i originalet. Detsamma gäller siffror, namn och källor. En omskrivning ska förbättra språket, inte förändra innehållet.

Sammanfattningsvis handlar bra redigering om att göra budskapet lättare att följa. Det betyder inte att alla texter ska låta likadant. En personlig berättelse får gärna ha ett annat tempo än en teknisk rapport, och skribentens egen röst ska fortfarande finnas kvar.`;
const ENGLISH_SAMPLE = `It is important to note that a clear text does not need every sentence to follow the same pattern. Sometimes a short sentence helps. At other times, a longer explanation gives the reader enough context to understand how the different ideas fit together.

When I read a text, I want to know what the writer means. Concrete examples can help, but an editor should not add them without support from the original. The same applies to numbers, names and sources. Editing should improve the language while preserving what the writer actually said.

In summary, good editing makes an argument easier to follow. It does not mean every piece should sound the same. A personal story can have a different rhythm from a technical report, and the writer should still recognise their own voice.`;
const TONES = [
  ['natural', 'Naturlig', 'Ledigt och följsamt'],
  ['simple', 'Enklare', 'Vanliga ord och tydliga meningar'],
  ['professional', 'Professionell', 'Sakligt och välstrukturerat'],
  ['academic', 'Akademisk', 'Formellt, med nyanserna kvar'],
  ['concise', 'Kortare', 'Färre ord, samma kärna'],
  ['detailed', 'Utförligare', 'Utveckla det som redan finns'],
];
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
function Icon({ name, size = 18 }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={PATHS[name] || PATHS.analyze}/></svg>;
}

async function apiRequest(base, token, path, options = {}) {
  let response;
  try {
    response = await fetch(base + path, { ...options, cache: 'no-store', headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers } });
  } catch (error) {
    if (options.signal?.aborted) throw error;
    throw new Error('Servern kunde inte nås. Kontrollera anslutningen och backend-adressen under Inställningar.');
  }
  let data;
  try { data = await response.json(); }
  catch { throw new Error('Backend svarade inte med JSON. Kontrollera API-adressen under Inställningar.'); }
  if (!response.ok) throw new Error(apiErrorMessage(data, response.status));
  return data;
}

function App() {
  const [mode, setMode] = useState('analyze');
  const [text, setText] = useState('');
  const [language, setLanguage] = useState('sv');
  const [tone, setTone] = useState('natural');
  const [protectedDraft, setProtectedDraft] = useState('');
  const [analysis, setAnalysis] = useState(null);
  const [result, setResult] = useState(null);
  const [originalSnapshot, setOriginalSnapshot] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [showDiff, setShowDiff] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsError, setSettingsError] = useState('');
  const [base, setBase] = useState('');
  const [baseDraft, setBaseDraft] = useState('');
  const [token, setToken] = useState('');
  const [tokenDraft, setTokenDraft] = useState('');
  const [connection, setConnection] = useState(null);
  const [connectionError, setConnectionError] = useState('');
  const [provider, setProvider] = useState(null);
  const [connectionAttempt, setConnectionAttempt] = useState(0);
  const inputRef = useRef(null);
  const fileRef = useRef(null);
  const dialogRef = useRef(null);
  const settingsButton = useRef(null);
  const settingsReturnFocus = useRef(null);
  const resultHeading = useRef(null);
  const gate = useRef(null);
  if (!gate.current) gate.current = createRequestGate();
  const revision = useRef(0);
  const words = wordCount(text);

  function invalidate() {
    revision.current++;
    gate.current.cancel();
    setBusy(false);
    setResult(null);
    setAnalysis(null);
    setError('');
    setNotice('');
    setShowDiff(false);
  }
  function changeText(next) { invalidate(); setText(next); }
  function loadText(next) { changeText(next); setOriginalSnapshot(null); setProtectedDraft(''); }
  function openSettings(event) {
    settingsReturnFocus.current = event.currentTarget;
    setBaseDraft(base);
    setTokenDraft(token);
    setSettingsError('');
    setSettingsOpen(true);
  }

  useEffect(() => {
    let mounted = true;
    const healthController = new AbortController();
    const providerController = new AbortController();
    const healthTimeout = setTimeout(() => healthController.abort(), 6000);
    const providerTimeout = setTimeout(() => providerController.abort(), 25000);
    setConnection(null);
    setConnectionError('');
    setProvider(null);
    apiRequest(base, token, '/api/health', { signal: healthController.signal })
      .then(data => { const normalized = normalizeHealthResponse(data); if (mounted) setConnection(normalized); })
      .catch(error => {
        if (mounted) {
          setConnection(false);
          setConnectionError(healthController.signal.aborted ? 'Kontrollen av backend tog för lång tid. Kontrollera backend och försök igen.' : error.message);
        }
      })
      .finally(() => clearTimeout(healthTimeout));
    apiRequest(base, token, '/api/provider-status', { signal: providerController.signal })
      .then(data => { const normalized = normalizeProviderStatus(data); if (mounted) setProvider(normalized); })
      .catch(error => {
        if (mounted) setProvider({ ready: false, verified: false, error: true, message: providerController.signal.aborted ? 'Kontrollen tog för lång tid. Modellen kan fortfarande starta. Försök kontrollera igen.' : error.message });
      })
      .finally(() => clearTimeout(providerTimeout));
    return () => {
      mounted = false;
      healthController.abort();
      providerController.abort();
      clearTimeout(healthTimeout);
      clearTimeout(providerTimeout);
    };
  }, [base, token, connectionAttempt]);
  useEffect(() => () => gate.current.cancel(), []);
  useEffect(() => {
    if (settingsOpen) dialogRef.current?.showModal();
    else dialogRef.current?.close();
  }, [settingsOpen]);
  useEffect(() => {
    if (analysis || result) resultHeading.current?.focus({ preventScroll: true });
  }, [analysis, result]);

  function switchMode(next) { if (next !== mode) { invalidate(); setMode(next); } }
  async function run() {
    if (busy) return;
    setError('');
    setNotice('');
    if (!text.trim()) { setError('Skriv eller klistra in en text först.'); inputRef.current?.focus(); return; }
    if (mode === 'analyze') {
      try {
        setAnalysis({ ...analyzeText(text, language), sourceText: text });
        setNotice('Analysen är klar. Stilindex beskriver språkmönster; författarskap kan inte avgöras.');
      } catch (error) { setError(error.message); }
      return;
    }
    const validationError = validateRewriteInput(text);
    if (validationError) { setError(validationError); inputRef.current?.focus(); return; }
    let protectedTerms;
    try { protectedTerms = parseProtectedTerms(protectedDraft, text); }
    catch (error) { setError(error.message); return; }
    const source = text;
    const controller = gate.current.begin();
    const timeout = setTimeout(() => {
      if (!gate.current.isCurrent(controller)) return;
      gate.current.cancel();
      setBusy(false);
      setError('Omskrivningen tog för lång tid. Originalet finns kvar. Försök igen när modellen är tillgänglig.');
      setNotice('');
    }, 135000);
    setBusy(true);
    setResult(null);
    setShowDiff(false);
    setNotice('Omskrivningen pågår. Du kan avbryta; originalet finns kvar.');
    try {
      const data = await apiRequest(base, token, '/api/rewrite', { method: 'POST', body: JSON.stringify({ text: source, tone, language, ...(protectedTerms.length ? { protected_terms: protectedTerms } : {}) }), signal: controller.signal });
      if (!gate.current.isCurrent(controller)) return;
      setResult(normalizeRewriteResult(data, source));
      setOriginalSnapshot(source);
      setNotice('Omskrivningen är klar. Jämför versionerna och granska betydelsen innan du använder texten.');
    } catch (error) {
      if (gate.current.isCurrent(controller)) { setError(error.message); setNotice(''); }
    } finally {
      clearTimeout(timeout);
      if (gate.current.isCurrent(controller)) setBusy(false);
    }
  }
  function cancel() {
    invalidate();
    setNotice('Omskrivningen avbröts i webbläsaren. Servern kan fortfarande slutföra modellens anrop. Originalet finns kvar.');
    inputRef.current?.focus();
  }
  async function importFile(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (!/\.txt$/i.test(file.name) || file.size > 60000) { setError('Välj en .txt-fil på högst 60 kB.'); return; }
    invalidate();
    const id = revision.current;
    try {
      const content = await file.text();
      if (id !== revision.current) return;
      if (content.length > MAX_CHARS) { setError(`Filen innehåller fler än ${MAX_CHARS.toLocaleString('sv-SE')} tecken. Dela upp den innan du importerar.`); return; }
      loadText(content);
      setNotice('Textfilen är inläst.');
      inputRef.current?.focus();
    } catch { if (id === revision.current) setError('Filen kunde inte läsas. Försök med en UTF-8-kodad textfil.'); }
  }
  async function copy() {
    const currentResult = result;
    const id = revision.current;
    try {
      await navigator.clipboard.writeText(currentResult.text);
      if (id === revision.current) setNotice('Texten är kopierad.');
    } catch {
      if (id === revision.current) setError('Kopiering blockerades. Markera texten och kopiera manuellt.');
    }
  }
  function download() {
    const url = URL.createObjectURL(new Blob([result.text], { type: 'text/plain;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'textlab-omskriven.txt';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setNotice('Textfilen har exporterats.');
  }
  function useResult() {
    changeText(result.text);
    setNotice('Den nya versionen finns i redigeraren. Du kan återställa originalet.');
    inputRef.current?.focus();
  }
  function restoreOriginal() {
    changeText(originalSnapshot);
    setNotice('Originalet från den senaste omskrivningen är återställt.');
    inputRef.current?.focus();
  }
  function saveSettings(event) {
    event.preventDefault();
    try {
      const next = validateBase(baseDraft);
      invalidate();
      setBase(next);
      setToken(tokenDraft.trim());
      setConnectionAttempt(attempt => attempt + 1);
      setSettingsOpen(false);
    } catch (error) { setSettingsError(error.message); }
  }

  const modelVerified = provider?.ready === true && provider?.verified === true;
  const connectionLabel = provider === null ? 'Kontrollerar AI-anslutningen…' : modelVerified ? 'Modellanslutningen är verifierad' : 'Modellanslutningen är inte verifierad';

  return <div className="app">
    <a className="skip-link" href="#workspace">Hoppa till textverktyget</a>
    <header className="header">
      <a href="./" className="brand"><span className="brand-icon" aria-hidden="true">t<span>l</span></span>textlab<span className="sr-only"> startsida</span><span className="version" aria-hidden="true">STUDIO / 03</span></a>
      <div className="header-actions"><span className="local-chip"><i/>Analys i din webbläsare</span><button className="icon-button settings" ref={settingsButton} onClick={openSettings} aria-label="Inställningar"><Icon name="settings"/><span>Inställningar</span></button></div>
    </header>
    <main>
      <section className="intro"><div><p className="eyebrow">ETT LUGNARE SÄTT ATT ARBETA MED TEXT</p><h1>Din text. <em>Din röst.</em></h1><p className="lead">Förstå textens mönster. Förbättra språket.<br className="desktop-break"/> Låt innehållet fortsätta vara ditt.</p></div><div className="intro-note"><span className="small-symbol">Aa<span>↗</span></span><p>Svenska & engelska<br/><strong>Analys med förklaringar.</strong></p></div></section>
      <div id="workspace" tabIndex={-1} className="workspace-start">
        <nav className="workspace-tabs" aria-label="Verktyg"><div className="segmented"><button aria-pressed={mode === 'analyze'} onClick={() => switchMode('analyze')} className={mode === 'analyze' ? 'selected' : ''}><Icon name="analyze"/>AI-detektor<span className="tag">STILANALYS</span></button><button aria-pressed={mode === 'rewrite'} onClick={() => switchMode('rewrite')} className={mode === 'rewrite' ? 'selected' : ''}><Icon name="edit"/>AI-humanizer</button></div><span className="workspace-hint">{mode === 'analyze' ? 'Ingen text skickas till en server.' : 'Texten skickas till din konfigurerade AI-backend.'}</span></nav>
        <div className="workspace">
          <section className="editor panel" aria-labelledby="editor-title">
            <div className="panel-heading"><div><span className="step">01</span><h2 id="editor-title">Din originaltext</h2></div><label className="language"><span className="sr-only">Textens språk</span><select aria-label="Textens språk" value={language} onChange={event => { invalidate(); setLanguage(event.target.value); }}><option value="sv">Svenska</option><option value="en">English</option></select></label></div>
            <textarea ref={inputRef} className="source-editor" aria-label="Din originaltext" aria-describedby="editor-count editor-help" placeholder={'Börja med dina ord.\n\nKlistra in en text eller importera en textfil…'} value={text} maxLength={MAX_CHARS} onChange={event => changeText(event.target.value)} onKeyDown={event => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); run(); } }} spellCheck lang={language}/>
            <div className="editor-meta"><span id="editor-count">{words.toLocaleString('sv-SE')} ord <span className="dot">·</span> {text.length.toLocaleString('sv-SE')} / {MAX_CHARS.toLocaleString('sv-SE')} tecken</span><button className="text-button" onClick={() => loadText('')} disabled={!text}>Rensa</button></div>
            <p id="editor-help" className={mode === 'rewrite' && text.length > 8000 ? 'editor-help limit-warning' : 'editor-help'}>{mode === 'analyze' ? 'Välj textens språk. Stilindex kräver minst 80 ord och flera meningar.' : 'Omskrivning: 10–8 000 tecken. Språkvalet anger den nya versionens språk.'}</p>
            {originalSnapshot !== null ? <div className="restore-row"><button className="text-button" onClick={restoreOriginal} disabled={text === originalSnapshot} title="Återställ texten från den senaste omskrivningen">Återställ original</button><span>Originalet från senaste omskrivningen finns i sidans minne.</span></div> : null}
            {mode === 'rewrite' ? <>
              <fieldset className="tone"><legend>Välj omskrivningsläge</legend>{TONES.map(([value, label, description]) => <label key={value} className={tone === value ? 'chosen' : ''}><input type="radio" name="tone" value={value} checked={tone === value} onChange={() => { invalidate(); setTone(value); }}/><span>{label}</span><small aria-hidden="true">{description}</small></label>)}</fieldset>
              <details className="protected-options"><summary>Behåll exakta textdelar <span>Valfritt</span></summary><label htmlFor="protected-terms">Textdelar att behålla exakt</label><textarea id="protected-terms" rows={3} value={protectedDraft} onChange={event => { invalidate(); setProtectedDraft(event.target.value); }} placeholder={'Projekt Atlas\nEtt viktigt namn'} aria-describedby="protected-help"/><p id="protected-help">En textdel per rad, högst 40. Skriv exakt som i originalet, inklusive stora bokstäver. Siffror, citat, länkar och referenser kontrolleras automatiskt.</p></details>
            </> : null}
            <div className="editor-bottom"><div className="import-actions"><input ref={fileRef} type="file" accept=".txt,text/plain" className="sr-only" tabIndex={-1} aria-label="Importera textfil" onChange={importFile}/><button className="text-button" onClick={() => fileRef.current?.click()}><Icon name="upload" size={16}/>Importera .txt</button><button className="text-button" onClick={() => loadText(language === 'en' ? ENGLISH_SAMPLE : SAMPLE)}>Prova ett exempel</button></div><button className="primary" onClick={run} disabled={busy} aria-keyshortcuts="Control+Enter Meta+Enter" title="Ctrl+Enter eller ⌘+Enter">{busy ? <><span className="spinner"/>Bearbetar…</> : <>{mode === 'analyze' ? 'Analysera text' : 'Skriv om med AI'}<Icon name="arrow"/></>}</button></div>
            {busy ? <div className="cancel-row"><span>Originalet finns kvar medan du väntar.</span><button className="text-button cancel" onClick={cancel}>Avbryt</button></div> : null}
          </section>
          <section className="results panel" aria-labelledby="result-title" aria-busy={busy}>
            <div className="panel-heading"><div><span className="step">02</span><h2 id="result-title" tabIndex={-1} ref={resultHeading}>{mode === 'analyze' ? 'Insikter, inte gissningar' : 'Din omskrivna text'}</h2></div><span className="live-tag">{mode === 'analyze' ? 'LOKAL ANALYS' : 'AI-BACKEND'}</span></div>
            {mode === 'analyze' ? analysis ? <Analysis result={analysis}/> : <div className="empty"><div className="illustration"><span/><span/><span/><span/><span/><i><Icon name="analyze" size={25}/></i></div><h3>Varje text har ett mönster.</h3><p>Se hur meningslängd, ordvariation och<br/>återkommande formuleringar samspelar.</p><div className="empty-tags"><span>Meningsrytm</span><span>Ordvariation</span><span>Språkmönster</span></div><small>Minst 80 ord och flera meningar för ett stilindex.<br/>Stilanalys kan inte avgöra om AI har skrivit texten.</small></div> : result ? <div className="rewrite-result">
              <div className="result-tools"><label className="diff-toggle"><input type="checkbox" checked={showDiff} onChange={event => setShowDiff(event.target.checked)}/>Visa ändringar</label><div><button className="icon-button" onClick={copy} aria-label="Kopiera omskriven text" title="Kopiera omskriven text"><Icon name="copy"/></button><button className="icon-button" onClick={download} aria-label="Ladda ner omskriven text" title="Ladda ner omskriven text"><Icon name="download"/></button></div></div>
              {showDiff ? <p className="diff-legend"><span><ins>Tillagt</ins></span><span><del>Borttaget</del></span><span>Originalet finns kvar i redigeraren.</span></p> : null}
              <div className="output" tabIndex={0} role="region" aria-label={showDiff ? 'Ändringar jämfört med originalet' : 'Omskriven text'} lang={language}>{showDiff ? result.diff.map((part, index) => part.kind === 'insert' ? <ins key={index}>{part.text}</ins> : part.kind === 'delete' ? <del key={index}>{part.text}</del> : <React.Fragment key={index}>{part.text}</React.Fragment>) : result.text}</div>
              <div className="version-actions"><button className="secondary" onClick={useResult}>Använd som original<Icon name="arrow" size={16}/></button><span>{wordCount(result.text).toLocaleString('sv-SE')} ord i den nya versionen</span></div>
              <p className="protected"><Icon name="check"/>{result.protected_count} skyddade textdelar kontrollerade</p><p className="result-warning">{result.warning}</p><div className="model-label">{result.provider || 'AI'}{result.model ? ` / ${result.model}` : ''}</div>
            </div> : busy ? <div className="empty processing"><span className="processing-icon"><Icon name="edit" size={32}/></span><h3>En ny version tar form.</h3><p>Modellen bearbetar texten.<br/>Det kan ta ett par minuter vid lokal körning.</p><small>Du kan fortsätta redigera för att avbryta den här omskrivningen. Originalet finns kvar.</small></div> : <div className="empty"><div className="rewrite-symbol"><Icon name="edit" size={38}/></div><h3>Tydligare. Inte någon annans.</h3><p>Välj ett av sex lägen och jämför versionerna.<br/>Kontrollera alltid betydelse, namn och fakta.</p><div className="model-status"><i className={modelVerified ? 'ready' : ''}/>{connectionLabel}</div>{connection?.provider ? <p className="provider-name">{connection.provider}{connection.model ? ` · ${connection.model}` : ''}</p> : null}<small role={connectionError || provider?.error ? 'alert' : undefined}>{connectionError || provider?.message || (connection === false ? 'Backend kunde inte nås. Stilanalysen fungerar utan backend.' : 'Stilanalysen fungerar även utan backend.')}</small><div className="connection-actions"><button className="text-button" onClick={openSettings}>Anslut AI-backend</button><button className="text-button" disabled={provider === null} onClick={() => setConnectionAttempt(attempt => attempt + 1)}>Kontrollera igen</button></div></div>}
          </section>
        </div>
      </div>
      {error ? <div className="error" role="alert"><strong>Något behöver ses över.</strong> {error}</div> : null}
      <div className="notice" role="status" aria-live="polite" aria-atomic="true">{notice}</div>
      <section className="trust-row"><div><Icon name="shield"/><p><strong>Du behåller kontrollen</strong>Texter sparas inte av TextLab. AI-omskrivning skickar text till den valda leverantören.</p></div><div><Icon name="analyze"/><p><strong>Inga falska garantier</strong>Stilanalys kan inte fastställa författarskap. En omskrivning garanterar inte att andra detektorer påverkas.</p></div></section>
    </main>
    <footer><span>textlab <span className="footer-slash">/</span> Studio för genomtänkt text</span><span>V3.0 <span className="footer-slash">/</span> Ingen spårning. Ingen texthistorik.</span></footer>
    <dialog ref={dialogRef} className="settings-dialog" onCancel={() => setSettingsOpen(false)} onClose={() => { setSettingsOpen(false); (settingsReturnFocus.current || settingsButton.current)?.focus(); }} aria-labelledby="settings-title"><form onSubmit={saveSettings}><div className="dialog-heading"><h2 id="settings-title">AI-anslutning</h2><button type="button" className="icon-button" aria-label="Stäng inställningar" onClick={() => setSettingsOpen(false)}><Icon name="close"/></button></div><p>Stilanalys körs lokalt. AI-omskrivning kräver en betrodd backend med Ollama eller OpenAI.</p><label htmlFor="api-base">Backend-adress</label><input id="api-base" type="text" placeholder="Tomt = samma server som webbplatsen" autoComplete="url" value={baseDraft} onChange={event => { setBaseDraft(event.target.value); setSettingsError(''); }} aria-describedby="api-base-help"/><small id="api-base-help">Ange HTTPS-adressen till din egen server. Ingen API-nyckel ska finnas i den här adressen.</small><label htmlFor="api-token">TextLab-åtkomstkod</label><input id="api-token" type="password" autoComplete="off" value={tokenDraft} onChange={event => setTokenDraft(event.target.value)} placeholder="Åtkomstkod från din backend" aria-describedby="api-token-help"/><small id="api-token-help">Inte en OpenAI-nyckel. Koden används endast i minnet och försvinner när sidan laddas om.</small><div className="privacy-box">OpenAI-nycklar hör hemma på servern. Leverantörens egna lagringsregler kan gälla även när TextLab inte sparar texten.</div>{settingsError ? <p className="dialog-error" role="alert">{settingsError}</p> : null}<button className="primary" type="submit">Anslut<Icon name="arrow"/></button></form></dialog>
  </div>;
}

function Analysis({ result }) {
  const evidence = result.evidence || result.markers.map(marker => ({ ...marker, explanation: 'En standardformulering som också används av människor.' }));
  const sourceParts = sourceHighlights(result.sourceText, evidence);
  const index = result.styleIndex;
  const abstained = index === null || index === undefined;
  const reasons = result.uncertainty?.reasons || (result.status === 'insufficient' ? ['Texten behöver minst 80 ord för ett stilindex.'] : result.status === 'unsupported' ? ['Språket stöds inte av stilmodellen.'] : []);
  return <div className="analysis-result">
    <div className="score-row"><div><div className="eyebrow">FÖRKLARBART STILINDEX</div><div className="score" aria-label={abstained ? 'Inget stilindex' : `Stilindex ${index} av 100`}>{abstained ? '—' : index}{!abstained ? <span>/100</span> : null}</div></div><p>{abstained ? 'Inget tillförlitligt stilindex för den här texten.' : 'Beskriver språkmönster i just den här texten.'}<small>Författarskap: kan inte avgöras.</small></p></div>
    {!abstained ? <><div className="score-track" aria-hidden="true"><span style={{ width: `${index}%` }}/></div><p className="index-explanation">Ett högre index betyder fler av de uppmätta stilmönstren. Det är inte en AI-sannolikhet eller ett kvalitetsbetyg.</p></> : null}
    {abstained && reasons.length ? <div className="uncertainty"><strong>{abstained ? 'Därför avstår analysen från ett index' : 'Så ska resultatet tolkas'}</strong><ul>{reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul>{result.status === 'insufficient' ? <p>{Math.max(0, 80 - result.wordCount)} ord kvar till 80.</p> : null}</div> : null}
    <div className="metrics"><div><strong>{result.sentenceCount}</strong><span>Meningar</span></div><div><strong>{result.averageLength}</strong><span>Ord / mening</span></div><div><strong>{result.lexicalDiversity}%</strong><span>Ordvariation</span></div></div>
    <div className="signal-list">{result.signals.map(signal => <details key={signal.key}><summary><span>{signal.label}</span><div className="signal-track" aria-hidden="true"><span style={{ width: `${Math.round(signal.value * 100)}%` }}/></div><span className="expand" aria-hidden="true">+</span></summary><p>{signal.detail}</p></details>)}</div>
    <details className="evidence"><summary>Se formuleringar i sitt sammanhang <span>{evidence.length} träffar</span></summary><div><p className="evidence-help">Markeringarna visar var de språkliga signalerna finns. Samma uttryck kan förekomma i människors texter.</p><div className="evidence-source" lang={result.languageAssessment?.requested || 'sv'}>{sourceParts.map((part, index) => part.marked ? <mark key={index} title={part.explanations.join(' ')}>{part.text}</mark> : <React.Fragment key={index}>{part.text}</React.Fragment>)}</div>{evidence.length ? <details className="evidence-explanations"><summary>Förklaringar till markeringarna</summary><ol>{evidence.map((item, index) => <li key={item.id || index}><q>{item.text || result.sourceText.slice(item.start, item.end)}</q> — {item.explanation}</li>)}</ol></details> : <p>Inga formuleringar att markera. Andra stilvärden kan fortfarande beskrivas ovan.</p>}</div></details>
    <div className="analysis-warning"><Icon name="shield" size={17}/><p>Inte en AI-sannolikhet. Träffsäkerheten är inte validerad mot ett oberoende märkt material. Använd inte detta som bevis för fusk eller som grund för beslut om en person.</p></div>
  </div>;
}

createRoot(document.getElementById('root')).render(<App/>);
