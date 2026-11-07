import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { wordCount, MAX_CHARS } from './analyzer.mjs';
import { validateBase, validateRewriteInput, normalizeRewriteResult, sourceHighlights, createRequestGate, parseProtectedTerms, normalizeHealthResponse, normalizeProviderStatus, normalizeUsageTotals, apiErrorMessage } from './ui-state.mjs';
import { prepareLocalAnalysis, normalizeDetectionResult, segmentParts, CATEGORY_LABELS, buildAnalysisReport, analysisReportText, REPORT_LIMITATION } from './detection-state.mjs';
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
  const [language, setLanguage] = useState('auto');
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
  const [usageTotals, setUsageTotals] = useState(null);
  const [usageError, setUsageError] = useState(false);
  const [usageRefresh, setUsageRefresh] = useState(0);
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
  const rewriteMaxChars = connection?.max_input_chars ?? 8000;
  const editorMaxChars = mode === 'rewrite' ? rewriteMaxChars : MAX_CHARS;
  const localPreview = useMemo(() => prepareLocalAnalysis(text, language), [text, language]);
  const languageInfo = localPreview.languageAssessment;

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
    if (mode !== 'rewrite') return;
    let active = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    setUsageTotals(null); setUsageError(false);
    apiRequest(base, token, '/api/usage', { signal:controller.signal })
      .then(data => { const normalized=normalizeUsageTotals(data); if (active) setUsageTotals(normalized); })
      .catch(() => { if (active) setUsageError(true); })
      .finally(() => clearTimeout(timeout));
    return () => { active=false; controller.abort(); clearTimeout(timeout); };
  }, [mode, base, token, connectionAttempt, usageRefresh]);
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
      const source = text;
      const controller = gate.current.begin();
      const timeout = setTimeout(() => {
        if (!gate.current.isCurrent(controller)) return;
        gate.current.cancel();
        setBusy(false);
        setAnalysis(localPreview);
        setError('AI-analysen tog för lång tid. Stilanalysen visas lokalt. Försök igen när servern är tillgänglig.');
        setNotice('');
      }, 45000);
      setBusy(true);
      setAnalysis(null);
      setNotice('Texten analyseras på din TextLab-server. Du kan avbryta när som helst.');
      try {
        const data = await apiRequest(base, token, '/api/detect', { method:'POST', body:JSON.stringify({ text:source, language }), signal:controller.signal });
        if (!gate.current.isCurrent(controller)) return;
        const normalized = normalizeDetectionResult(data, source, language);
        setAnalysis(normalized);
        setNotice('Textanalysen är klar. Läs bedömning, osäkerhet och textens sammanhang tillsammans.');
      } catch (error) {
        if (gate.current.isCurrent(controller)) { setAnalysis(localPreview); setError(error.message); setNotice('Stilanalysen finns tillgänglig lokalt. Inget AI-resultat visas.'); }
      } finally {
        clearTimeout(timeout);
        if (gate.current.isCurrent(controller)) setBusy(false);
      }
      return;
    }
    const validationError = validateRewriteInput(text, rewriteMaxChars);
    if (validationError) { setError(validationError); inputRef.current?.focus(); return; }
    const rewriteLanguage = language === 'auto' ? languageInfo.effective : language;
    if (!rewriteLanguage) { setError('Språket kunde inte identifieras säkert. Välj Svenska eller English före omskrivningen.'); return; }
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
      const data = await apiRequest(base, token, '/api/rewrite', { method: 'POST', body: JSON.stringify({ text: source, tone, language:rewriteLanguage, ...(protectedTerms.length ? { protected_terms: protectedTerms } : {}) }), signal: controller.signal });
      if (!gate.current.isCurrent(controller)) return;
      const normalized = normalizeRewriteResult(data, source);
      setResult(normalized);
      setOriginalSnapshot(source);
      setNotice(normalized.unchanged ? 'Originalet är oförändrat. Läs förklaringen och granska texten innan du använder den.' : 'Omskrivningen är klar. Jämför versionerna och granska betydelsen innan du använder texten.');
    } catch (error) {
      if (gate.current.isCurrent(controller)) { setError(error.message); setNotice(''); }
    } finally {
      clearTimeout(timeout);
      if (gate.current.isCurrent(controller)) { setBusy(false); setUsageRefresh(value => value + 1); }
    }
  }
  function cancel() {
    invalidate();
    setNotice('Begäran avbröts i webbläsaren. Servern kan fortfarande slutföra anropet. Originalet finns kvar.');
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
    saveFile(result.text, 'textlab-omskriven.txt', 'text/plain;charset=utf-8');
    setNotice('Textfilen har exporterats.');
  }
  function saveFile(content, name, type) {
    const url = URL.createObjectURL(new Blob([content], { type }));
    const link = document.createElement('a');
    link.href = url;
    link.download = name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function exportAnalysis(format) {
    if (!analysis?.detector) return;
    const json = format === 'json';
    saveFile(json ? JSON.stringify(buildAnalysisReport(analysis), null, 2) : analysisReportText(analysis), `textlab-analys.${format}`, json ? 'application/json;charset=utf-8' : 'text/plain;charset=utf-8');
    setNotice(`Analysrapporten har exporterats som ${format.toUpperCase()}. Rapporten innehåller originaltexten.`);
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
      <a href="./" className="brand"><span className="brand-icon" aria-hidden="true">t<span>l</span></span>textlab<span className="sr-only"> startsida</span><span className="version" aria-hidden="true">STUDIO / 05</span></a>
      <div className="header-actions"><span className="local-chip"><i/>Svenska & English</span><button className="icon-button settings" ref={settingsButton} onClick={openSettings} aria-label="Inställningar"><Icon name="settings"/><span>Inställningar</span></button></div>
    </header>
    <main>
      <section className="intro"><div><p className="eyebrow">TEXTANALYS MED UTRYMME FÖR NYANSER</p><h1>Din text. <em>Din röst.</em></h1><p className="lead">Se mönstren. Förstå bedömningen.<br className="desktop-break"/> Skriv tydligare, med innehållet kvar.</p></div><div className="intro-note"><span className="small-symbol">Aa<span>↗</span></span><p>Från helhet till mening.<br/><strong>Varje bedömning i sitt sammanhang.</strong></p></div></section>
      <div id="workspace" tabIndex={-1} className="workspace-start">
        <nav className="workspace-tabs" aria-label="Verktyg"><div className="segmented"><button aria-label="AI-detektor" aria-pressed={mode === 'analyze'} onClick={() => switchMode('analyze')} className={mode === 'analyze' ? 'selected' : ''}><Icon name="analyze"/>AI-detektor<span className="tag" aria-hidden="true">V5</span></button><button aria-pressed={mode === 'rewrite'} onClick={() => switchMode('rewrite')} className={mode === 'rewrite' ? 'selected' : ''}><Icon name="edit"/>AI-humanizer</button></div><span className="workspace-hint">{mode === 'analyze' ? 'AI-analys på din TextLab-server · stilanalys lokalt' : 'Omskrivning med din konfigurerade AI-leverantör'}</span></nav>
        <div className="workspace">
          <section className="editor panel" aria-labelledby="editor-title">
            <div className="panel-heading"><div><span className="step">01</span><h2 id="editor-title">Din originaltext</h2></div><label className="language"><span className="sr-only">Textens språk</span><select aria-label="Textens språk" value={language} onChange={event => { invalidate(); setLanguage(event.target.value); }}><option value="auto">Auto · språk</option><option value="sv">Svenska</option><option value="en">English</option></select></label></div>
            <textarea ref={inputRef} className="source-editor" aria-label="Din originaltext" aria-describedby="editor-count editor-help language-feedback" placeholder={'Börja med dina ord.\n\nKlistra in en text eller importera en textfil…'} value={text} maxLength={editorMaxChars} onChange={event => changeText(event.target.value)} onKeyDown={event => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); run(); } }} spellCheck lang={languageInfo.effective || undefined}/>
            <div className="editor-meta"><span id="editor-count">{words.toLocaleString('sv-SE')} ord <span className="dot">·</span> {text.length.toLocaleString('sv-SE')} / {editorMaxChars.toLocaleString('sv-SE')} tecken</span><button className="text-button" onClick={() => loadText('')} disabled={!text}>Rensa</button></div>
            <p id="editor-help" className={mode === 'rewrite' && text.length > rewriteMaxChars ? 'editor-help limit-warning' : 'editor-help'}>{mode === 'analyze' ? 'Mer sammanhang ger bättre underlag. Korta och osäkra segment kan lämnas utan bedömning.' : `Omskrivning: 10–${rewriteMaxChars.toLocaleString('sv-SE')} tecken. Språkvalet anger den nya versionens språk.`}</p>
            <div id="language-feedback" className={`language-feedback ${text && ['mismatch','unsupported','uncertain'].includes(languageInfo.status) ? 'language-warning' : ''}`} aria-live="polite">{!text ? 'Språk identifieras försiktigt från svenska och engelska ord. Du kan välja själv.' : languageInfo.status === 'mismatch' ? `Texten verkar vara på ${languageInfo.detected === 'en' ? 'engelska' : 'svenska'}, men ${language === 'sv' ? 'svenska' : 'engelska'} är valt. Kontrollera språkvalet.` : languageInfo.status === 'unsupported' ? 'Textens språk verkar ligga utanför stödet för svenska och engelska.' : !languageInfo.detected ? 'Språket är osäkert. Välj Svenska eller English om du vet vilket språk texten har.' : `${language === 'auto' ? 'Identifierat språk' : 'Språkval'}: ${languageInfo.detected === 'sv' ? 'svenska' : 'engelska'}. Språkbedömningen kan ha fel.`}</div>
            {originalSnapshot !== null ? <div className="restore-row"><button className="text-button" onClick={restoreOriginal} disabled={text === originalSnapshot} title="Återställ texten från den senaste omskrivningen">Återställ original</button><span>Originalet från senaste omskrivningen finns i sidans minne.</span></div> : null}
            {mode === 'rewrite' ? <>
              <fieldset className="tone"><legend>Välj omskrivningsläge</legend>{TONES.map(([value, label, description]) => <label key={value} className={tone === value ? 'chosen' : ''}><input type="radio" name="tone" value={value} checked={tone === value} onChange={() => { invalidate(); setTone(value); }}/><span>{label}</span><small aria-hidden="true">{description}</small></label>)}</fieldset>
              <details className="protected-options"><summary>Behåll exakta textdelar <span>Valfritt</span></summary><label htmlFor="protected-terms">Textdelar att behålla exakt</label><textarea id="protected-terms" rows={3} value={protectedDraft} onChange={event => { invalidate(); setProtectedDraft(event.target.value); }} placeholder={'Projekt Atlas\nEtt viktigt namn'} aria-describedby="protected-help"/><p id="protected-help">En textdel per rad, högst 40. Skriv exakt som i originalet, inklusive stora bokstäver. Siffror, citat, länkar och referenser kontrolleras automatiskt.</p></details>
            </> : null}
            <div className="editor-bottom"><div className="import-actions"><input ref={fileRef} type="file" accept=".txt,text/plain" className="sr-only" tabIndex={-1} aria-label="Importera textfil" onChange={importFile}/><button className="text-button" onClick={() => fileRef.current?.click()}><Icon name="upload" size={16}/>Importera .txt</button><button className="text-button" onClick={() => loadText(language === 'en' ? ENGLISH_SAMPLE : SAMPLE)}>Prova ett exempel</button></div><button className="primary" onClick={run} disabled={busy} aria-keyshortcuts="Control+Enter Meta+Enter" title="Ctrl+Enter eller ⌘+Enter">{busy ? <><span className="spinner"/>Bearbetar…</> : <>{mode === 'analyze' ? 'Analysera text' : 'Skriv om med AI'}<Icon name="arrow"/></>}</button></div>
            {busy ? <div className="cancel-row"><span>Originalet finns kvar medan du väntar.</span><button className="text-button cancel" onClick={cancel}>Avbryt</button></div> : null}
          </section>
          <section className="results panel" aria-labelledby="result-title" aria-busy={busy}>
            <div className="panel-heading"><div><span className="step">02</span><h2 id="result-title" tabIndex={-1} ref={resultHeading}>{mode === 'analyze' ? analysis ? 'Textanalys slutförd' : 'Din analys' : result?.unchanged ? 'Originalet är oförändrat' : 'Din omskrivna text'}</h2></div><span className="live-tag">{mode === 'analyze' ? 'DOKUMENT & SEGMENT' : 'AI-REDIGERING'}</span></div>
            {mode === 'analyze' ? analysis ? <><DetectorSummary analysis={analysis}/><details className="style-details"><summary>Förklarande stilanalys <span>Körs lokalt</span></summary><Analysis result={analysis}/></details></> : <div className={`empty ${busy ? 'processing' : ''}`}><div className="illustration"><span/><span/><span/><span/><span/><i><Icon name="analyze" size={25}/></i></div><h3>{busy ? 'Läser textens mönster…' : 'Helheten först. Nyanserna sedan.'}</h3><p>{busy ? 'Dokument och segment analyseras. Resultatet visas när kontrollen är klar.' : 'En samlad bedömning, tydlig osäkerhet och plats att granska varje del av texten.'}</p><div className="empty-tags"><span>Dokument</span><span>Segment</span><span>Förklaringar</span></div><small>AI-procent visas bara när motsvarande metod är validerad. En bedömning fastställer aldrig författarskap.</small>{!busy ? <button className="text-button local-analysis" disabled={!text.trim()} onClick={() => { invalidate(); setAnalysis(localPreview); setNotice('Stilanalysen kördes lokalt. Ingen text skickades till servern.'); }}>Visa bara stilanalys</button> : null}</div> : result ? <div className="rewrite-result">
              <div className="result-tools"><label className="diff-toggle"><input type="checkbox" checked={showDiff} onChange={event => setShowDiff(event.target.checked)}/>Visa ändringar</label><div><button className="icon-button" onClick={copy} aria-label={result.unchanged ? 'Kopiera originaltext' : 'Kopiera omskriven text'} title={result.unchanged ? 'Kopiera originaltext' : 'Kopiera omskriven text'}><Icon name="copy"/></button><button className="icon-button" onClick={download} aria-label={result.unchanged ? 'Ladda ner originaltext' : 'Ladda ner omskriven text'} title={result.unchanged ? 'Ladda ner originaltext' : 'Ladda ner omskriven text'}><Icon name="download"/></button></div></div>
              {result.unchanged ? <p className="result-warning">{result.explanation}</p> : null}
              {showDiff ? <p className="diff-legend"><span><ins>Tillagt</ins></span><span><del>Borttaget</del></span><span>Originalet finns kvar i redigeraren.</span></p> : null}
              <details className="original-comparison"><summary>Originalet för jämförelse</summary><div className="original-snapshot" lang={languageInfo.effective || undefined}>{result.original}</div></details>
              <div className="output" tabIndex={0} role="region" aria-label={showDiff ? 'Ändringar jämfört med originalet' : result.unchanged ? 'Oförändrad originaltext' : 'Omskriven text'} lang={languageInfo.effective || undefined}>{showDiff ? result.diff.map((part, index) => part.kind === 'insert' ? <ins key={index}>{part.text}</ins> : part.kind === 'delete' ? <del key={index}>{part.text}</del> : <React.Fragment key={index}>{part.text}</React.Fragment>) : result.text}</div>
              <div className="version-actions"><button className="secondary" onClick={useResult} disabled={result.unchanged}>Använd som original<Icon name="arrow" size={16}/></button><span>{wordCount(result.text).toLocaleString('sv-SE')} ord i {result.unchanged ? 'originalet' : 'den nya versionen'}</span></div>
              <p className="protected"><Icon name="check"/>{result.protected_count} skyddade textdelar kontrollerade</p><p className="result-warning">{result.warning}</p><div className="model-label">{result.provider || 'AI'}{result.model ? ` / ${result.model}` : ''}</div><UsageDetails usage={result.usage}/>
            </div> : busy ? <div className="empty processing"><span className="processing-icon"><Icon name="edit" size={32}/></span><h3>En ny version tar form.</h3><p>Modellen bearbetar texten.<br/>Det kan ta ett par minuter vid lokal körning.</p><small>Du kan fortsätta redigera för att avbryta den här omskrivningen. Originalet finns kvar.</small></div> : <div className="empty"><div className="rewrite-symbol"><Icon name="edit" size={38}/></div><h3>Tydligare. Inte någon annans.</h3><p>Välj ett av sex lägen och jämför versionerna.<br/>Kontrollera alltid betydelse, namn och fakta.</p><div className="model-status"><i className={modelVerified ? 'ready' : ''}/>{connectionLabel}</div>{connection?.provider ? <p className="provider-name">{connection.provider}{connection.model ? ` · ${connection.model}` : ''}</p> : null}<small role={connectionError || provider?.error ? 'alert' : undefined}>{connectionError || provider?.message || (connection === false ? 'Backend kunde inte nås. Stilanalysen fungerar utan backend.' : 'Stilanalysen fungerar även utan backend.')}</small><div className="connection-actions"><button className="text-button" onClick={openSettings}>Anslut AI-backend</button><button className="text-button" disabled={provider === null} onClick={() => setConnectionAttempt(attempt => attempt + 1)}>Kontrollera igen</button></div></div>}
            {mode === 'rewrite' ? <UsageTotals totals={usageTotals} unavailable={usageError}/> : null}
          </section>
        </div>
      </div>
      {error ? <div className="error" role="alert"><strong>Något behöver ses över.</strong> {error}</div> : null}
      <div className="notice" role="status" aria-live="polite" aria-atomic="true">{notice}</div>
      {mode === 'analyze' && analysis?.detector ? <SegmentReview key={analysis.analyzedAt} analysis={analysis} onExport={exportAnalysis}/> : null}
      <section className="trust-row"><div><Icon name="shield"/><p><strong>Du behåller kontrollen</strong>Stilanalysen körs lokalt. AI-analys skickar texten till din TextLab-server. Omskrivning skickar den vidare till din valda AI-leverantör.</p></div><div><Icon name="analyze"/><p><strong>Bedömning med begränsningar</strong>Resultatet är inte bevis för författarskap. Granska texten i sitt sammanhang och kontrollera betydelsen efter en omskrivning.</p></div></section>
    </main>
    <footer><span>textlab <span className="footer-slash">/</span> Studio för genomtänkt text</span><span>V5.0 <span className="footer-slash">/</span> Läs. Förstå. Förfina.</span></footer>
    <dialog ref={dialogRef} className="settings-dialog" onCancel={() => setSettingsOpen(false)} onClose={() => { setSettingsOpen(false); (settingsReturnFocus.current || settingsButton.current)?.focus(); }} aria-labelledby="settings-title"><form onSubmit={saveSettings}><div className="dialog-heading"><h2 id="settings-title">AI-anslutning</h2><button type="button" className="icon-button" aria-label="Stäng inställningar" onClick={() => setSettingsOpen(false)}><Icon name="close"/></button></div><p>Stilanalys körs lokalt. AI-detektering använder din TextLab-server. Omskrivning använder serverns konfigurerade Ollama- eller OpenAI-modell.</p><label htmlFor="api-base">Backend-adress</label><input id="api-base" type="text" placeholder="Tomt = samma server som webbplatsen" autoComplete="url" value={baseDraft} onChange={event => { setBaseDraft(event.target.value); setSettingsError(''); }} aria-describedby="api-base-help"/><small id="api-base-help">Ange HTTPS-adressen till din egen server. Ingen API-nyckel ska finnas i den här adressen.</small><label htmlFor="api-token">TextLab-åtkomstkod</label><input id="api-token" type="password" autoComplete="off" value={tokenDraft} onChange={event => setTokenDraft(event.target.value)} placeholder="Åtkomstkod från din backend" aria-describedby="api-token-help"/><small id="api-token-help">Inte en OpenAI-nyckel. Koden används endast i minnet och försvinner när sidan laddas om.</small><div className="privacy-box">OpenAI-nycklar hör hemma på servern. Leverantörens egna lagringsregler kan gälla även när TextLab inte sparar texten.</div>{settingsError ? <p className="dialog-error" role="alert">{settingsError}</p> : null}<button className="primary" type="submit">Anslut<Icon name="arrow"/></button></form></dialog>
  </div>;
}

function DetectorSummary({ analysis }) {
  const detector = analysis.detector;
  if (!detector) return <div className="detector-summary local-only"><span className="result-kicker">LOKAL STILANALYS</span><h3>Textens stil går att granska.</h3><p>Inget AI-resultat är tillgängligt. Öppna stilanalysen nedan för språkmönster och förklaringar.</p><p className="result-caveat">Stilindex kan inte användas som AI-sannolikhet eller som bevis för författarskap.</p></div>;
  const percent = value => `${value.toLocaleString('sv-SE', { maximumFractionDigits: 1 })} %`;
  return <div className="detector-summary">
    <div className="assessment-head"><span className="result-kicker">DOKUMENTBEDÖMNING</span><span className={`assessment-badge ${detector.category}`}>{CATEGORY_LABELS[detector.category]}</span></div>
    {!detector.documentValidated && !detector.segmentValidated ? <p className="unvalidated-message">Stilanalys tillgänglig. AI-procent kan ännu inte beräknas tillförlitligt.</p> : null}
    <div className="metric-cards">
      <div className="metric-card"><h3>Dokumentkonfidens</h3><strong className="document-probability">{detector.documentProbability === null ? '—' : percent(detector.documentProbability * 100)}</strong><p>{detector.documentProbability === null ? 'Ingen verifierad sannolikhet är tillgänglig för den här texten.' : 'Modellens uppskattade sannolikhet för AI-klassen.'}</p><span>Gäller dokumentet, inte textandelen.</span></div>
      <div className="metric-card"><h3>AI-markerad text</h3><strong className="ai-marked-share">{detector.aiMarkedPercent === null ? '—' : percent(detector.aiMarkedPercent)}</strong><p>{detector.aiMarkedPercent === null ? 'Ingen validerad textandel är tillgänglig för den här texten.' : 'Uppskattad andel AI-markerade analyserbara ord.'}</p><span>En modelluppskattning av markerad text.</span></div>
    </div>
    <dl className="coverage-grid"><div><dt>Analyserbara ord</dt><dd>{detector.analyzedWords.toLocaleString('sv-SE')}</dd></div><div><dt>Exkluderade ord</dt><dd>{detector.excludedWords.toLocaleString('sv-SE')}</dd></div><div><dt>AI-markerade segment</dt><dd>{detector.segmentValidated ? `${detector.flaggedSegments} / ${detector.totalSegments}` : 'Ej bedömt'}</dd></div></dl>
    <p className="coverage-note">Analyserbara ord har tillräckligt underlag för modellen. Det betyder inte att klassificeringen är validerad.</p>
    <div className="uncertainty detector-uncertainty"><strong>Osäkerhet & underlag</strong>{detector.reasons.length ? <ul>{detector.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul> : <p>Läs dokumentet och segmenten tillsammans. Resultatet fastställer inte vem som skrev texten.</p>}</div>
    <div className="detector-model"><span>Modell</span><strong>{detector.modelVersion || 'Ej angiven'}</strong><span>Dokumentkalibrering: {detector.calibrationValidated ? 'verifierad' : 'ej verifierad'}</span></div>
  </div>;
}

function SegmentReview({ analysis, onExport }) {
  const { detector, segments, sourceText } = analysis;
  const [selectedId, setSelectedId] = useState(segments[0]?.id ?? null);
  const selected = segments.find(segment => segment.id === selectedId);
  const parts = segmentParts(sourceText, segments);
  const relatedStyle = selected ? (analysis.evidence || []).filter(item => item.start < selected.end && item.end > selected.start) : [];
  function selectSegment(segment, scroll = false) {
    setSelectedId(segment.id);
    if (scroll) document.getElementById(`source-segment-${segment.index}`)?.scrollIntoView({ block:'center', behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  }
  function printReport() {
    const details = [...document.querySelectorAll('.method-details, .style-details')];
    const prior = details.map(item => item.open);
    details.forEach(item => { item.open = true; });
    window.print();
    details.forEach((item, index) => { item.open = prior[index]; });
  }
  return <section className="source-review panel" aria-labelledby="source-title">
    <div className="panel-heading source-heading"><div><span className="step">03</span><h2 id="source-title">Texten i sitt sammanhang</h2></div><span className="live-tag">{segments.length} SEGMENT</span></div>
    <div className="source-intro"><p>Hela originalet, i samma ordning. Välj ett segment för att läsa bedömning och begränsningar.</p><div className="segment-legend" aria-label="Segmentmarkeringar">{['ai_like','human_like','uncertain','unassessed'].map(category => <span className={category} key={category}><i aria-hidden="true"/>{CATEGORY_LABELS[category]}</span>)}</div></div>
    <div className="document-layout">
      <div className="annotated-source" aria-label="Originaltext med segmentmarkeringar" lang={analysis.languageAssessment.effective || undefined}>{parts.map((part, index) => part.segment ? <button key={index} id={`source-segment-${part.segment.index}`} className={`source-segment ${part.segment.category} ${selectedId === part.segment.id ? 'active' : ''}`} onClick={() => selectSegment(part.segment)} aria-pressed={selectedId === part.segment.id} aria-controls="segment-detail" aria-label={`Segment ${part.segment.index + 1}: ${CATEGORY_LABELS[part.segment.category]}, ${part.segment.wordCount} ord. ${part.text}`} title={`${CATEGORY_LABELS[part.segment.category]} · ${part.segment.wordCount} ord`}>{part.text}</button> : <React.Fragment key={index}>{part.text}</React.Fragment>)}</div>
      <aside className="segment-sidebar" aria-label="Segmentdetaljer">
        <div id="segment-detail" className="segment-detail" aria-live="polite" aria-atomic="true">{selected ? <><p className="eyebrow">SEGMENT {selected.index + 1} AV {segments.length}</p><h3 className={selected.category}>{CATEGORY_LABELS[selected.category]}</h3><dl><div><dt>Längd</dt><dd>{selected.wordCount} ord</dd></div><div><dt>Kalibrerad sannolikhet</dt><dd>{selected.probability === null ? 'Ej tillgängligt' : `${(selected.probability * 100).toLocaleString('sv-SE', { maximumFractionDigits:1 })} % för AI-klassen`}</dd></div></dl><p>{selected.reason}</p><h4>Språkliga observationer</h4>{relatedStyle.length ? <ul>{relatedStyle.slice(0,5).map((item, index) => <li key={index}>{item.explanation}</li>)}</ul> : <p>Inga lokala stilmarkeringar i detta segment.</p>}<p className="segment-limit">Stilmarkeringar beskriver språkbruk. En segmentbedömning är inte bevis för hur meningen skapades.</p></> : <p>Inga segment kunde bedömas. Hela originaltexten visas fortfarande.</p>}</div>
        {segments.length ? <details className="segment-navigation"><summary>Segmentöversikt <span>{segments.length}</span></summary><ol>{segments.map(segment => <li key={segment.id}><button onClick={() => selectSegment(segment, true)} aria-label={`Gå till segment ${segment.index + 1}: ${CATEGORY_LABELS[segment.category]}`} className={segment.category}><span>{segment.index + 1}</span><span>{CATEGORY_LABELS[segment.category]}</span><small>{segment.wordCount} ord</small></button></li>)}</ol></details> : null}
      </aside>
    </div>
    <details className="method-details"><summary>Analysmetod & begränsningar</summary><div><dl className="method-grid"><div><dt>Modellversion</dt><dd>{detector.modelVersion || 'Ej angiven'}</dd></div><div><dt>Dokumentvalidering</dt><dd>{detector.documentValidated ? 'Verifierad' : 'Ej verifierad'}</dd></div><div><dt>Dokumentkalibrering</dt><dd>{detector.calibrationValidated ? 'Verifierad' : 'Ej verifierad'} · {detector.calibrationStatus}</dd></div><div><dt>Segmentvalidering</dt><dd>{detector.segmentValidated ? 'Verifierad' : 'Ej verifierad'}</dd></div><div><dt>Segmentkalibrering</dt><dd>{detector.segmentCalibrationValidated ? 'Verifierad' : 'Ej verifierad'}</dd></div><div><dt>Analyserad</dt><dd><time dateTime={analysis.analyzedAt}>{new Date(analysis.analyzedAt).toLocaleString('sv-SE')}</time></dd></div></dl><p><strong>Dokumentkonfidens</strong> är modellens kalibrerade uppskattning av AI-klassen för hela dokumentet. <strong>AI-markerad textandel</strong> räknas som AI-markerade analyserbara ord / samtliga analyserbara ord × 100. Exkluderade ord ingår inte i nämnaren.</p><p>Segmenten överlappar inte. Positionerna pekar på originaltextens UTF-16-intervall. Ej bedömt kan betyda för kort text, osäkert språk, saknad modell eller saknad validering. Stilanalysen är en separat lokal regelanalys.</p><p>{REPORT_LIMITATION}</p></div></details>
    <div className="print-segment-list"><h3>Samtliga segmentbedömningar</h3><ol>{segments.map(segment => <li key={segment.id}><strong>{CATEGORY_LABELS[segment.category]} · {segment.wordCount} ord · UTF-16 [{segment.start}, {segment.end})</strong><p>{segment.reason}</p></li>)}</ol><p>{REPORT_LIMITATION}</p></div>
    <div className="report-actions"><p><strong>Ta med analysen</strong><span>Rapporten innehåller originaltext, resultat och begränsningar.</span></p><div><button className="secondary" onClick={() => onExport('txt')}><Icon name="download" size={16}/>Rapport TXT</button><button className="secondary" onClick={() => onExport('json')}><Icon name="download" size={16}/>Rapport JSON</button><button className="secondary" onClick={printReport}>Skriv ut / PDF</button></div></div>
  </section>;
}

function UsageDetails({ usage }) {
  const count = value => value == null ? 'Ej tillgängligt' : value.toLocaleString('sv-SE');
  const cost = !usage || usage.cost.status === 'unknown' ? 'Ej tillgänglig' : usage.cost.status === 'not_applicable' ? 'Ej tillämplig för denna provider' : usage.cost.estimated_amount === null ? 'Ej tillgänglig' : `${usage.cost.estimated_amount.toLocaleString('sv-SE', { minimumFractionDigits: 2, maximumFractionDigits: 6 })} USD (uppskattad)`;
  return <details className="usage-details"><summary>Förbrukning & kostnad <span>{usage?.total_tokens == null ? 'Usage saknas' : `${count(usage.total_tokens)} tokens`}</span></summary><dl className="usage-grid"><div><dt>Input-tokens</dt><dd>{count(usage?.input_tokens)}</dd></div><div><dt>Output-tokens</dt><dd>{count(usage?.output_tokens)}</dd></div><div><dt>Totala tokens</dt><dd>{count(usage?.total_tokens)}</dd></div><div><dt>Uppskattad kostnad</dt><dd>{cost}</dd></div></dl>{usage ? <p className="usage-meta">{usage.model}{usage.recorded_at ? ` · ${new Date(usage.recorded_at).toLocaleString('sv-SE')}` : ''}{usage.cost.pricing_version ? ` · Prisversion ${usage.cost.pricing_version}` : ''}</p> : null}<p>Tokens visas när leverantören rapporterar dem. Okända priser och saknad usage ersätts inte med uppskattade tokenantal.</p></details>;
}

function UsageTotals({ totals, unavailable }) {
  const tokensIncomplete = totals && (totals.unreported_counters.total_tokens > 0 || totals.legacy_usage_unavailable);
  const costIncomplete = totals && (totals.estimated_cost.unknown_requests > 0 || totals.legacy_usage_unavailable);
  return <details className="aggregate-usage"><summary>Dagens samlade förbrukning <span>UTC</span></summary>{totals ? <>
    <p>{totals.requests.toLocaleString('sv-SE')} registrerade modellanrop under perioden {new Date(totals.period.start).toLocaleDateString('sv-SE', { timeZone:'UTC' })}.</p>
    <dl className="usage-grid"><div><dt>Rapporterade tokens</dt><dd>{totals.total_tokens === null ? 'Ej tillgängligt' : totals.total_tokens.toLocaleString('sv-SE')}{tokensIncomplete ? ' · ofullständig summa' : ''}</dd></div><div><dt>Uppskattad kostnad</dt><dd>{totals.estimated_cost.amount === null ? 'Ej tillgänglig' : `${totals.estimated_cost.amount.toLocaleString('sv-SE', { minimumFractionDigits:2, maximumFractionDigits:6 })} USD`}{costIncomplete ? ' · ofullständig summa' : ''}</dd></div></dl>
    {totals.legacy_usage_unavailable ? <p>Förbrukning från äldre anrop är inte tillgänglig. Token- och kostnadssummorna omfattar endast rapporterade uppgifter och är därför ofullständiga.</p> : null}
    {totals.unreported_counters.total_tokens ? <p>Tokenantal saknas för {totals.unreported_counters.total_tokens} anrop. Saknade värden räknas inte som noll.</p> : null}
    {totals.estimated_cost.unknown_requests ? <p>Kostnaden är okänd för {totals.estimated_cost.unknown_requests} anrop.</p> : null}
    {totals.estimated_cost.not_applicable_requests ? <p>Tokenpris är inte tillämpligt för {totals.estimated_cost.not_applicable_requests} anrop.</p> : null}
    <p>Även genereringar som avvisats av kvalitetskontrollen kan ha använt tokens. Originaltext och omskrivningar ingår inte i förbrukningsloggen.</p>
  </> : <p>{unavailable ? 'Samlad förbrukning är inte tillgänglig just nu. Kontrollera anslutningen och åtkomstkoden.' : 'Hämtar samlad förbrukning…'}</p>}</details>;
}

function Analysis({ result }) {
  const evidence = result.evidence || result.markers.map(marker => ({ ...marker, explanation: 'En standardformulering som också används av människor.' }));
  const sourceParts = sourceHighlights(result.sourceText, evidence);
  const sourceLanguage = [result.languageAssessment?.effective, result.languageAssessment?.detected].find(value => ['sv', 'en'].includes(value));
  const index = result.styleIndex;
  const abstained = index === null || index === undefined;
  const reasons = result.uncertainty?.reasons || (result.status === 'insufficient' ? ['Texten behöver minst 80 ord för ett stilindex.'] : result.status === 'unsupported' ? ['Språket stöds inte av stilmodellen.'] : []);
  return <div className="analysis-result">
    <div className="score-row"><div><div className="eyebrow">FÖRKLARBART STILINDEX</div><div className="score" aria-label={abstained ? 'Inget stilindex' : `Stilindex ${index} av 100`}>{abstained ? '—' : index}{!abstained ? <span>/100</span> : null}</div></div><p>{abstained ? 'Inget tillförlitligt stilindex för den här texten.' : 'Beskriver språkmönster i just den här texten.'}<small>Författarskap: kan inte avgöras.</small></p></div>
    {!abstained ? <><div className="score-track" aria-hidden="true"><span style={{ width: `${index}%` }}/></div><p className="index-explanation">Ett högre index betyder fler av de uppmätta stilmönstren. Det är inte en AI-sannolikhet eller ett kvalitetsbetyg.</p></> : null}
    {abstained && reasons.length ? <div className="uncertainty"><strong>{abstained ? 'Därför avstår analysen från ett index' : 'Så ska resultatet tolkas'}</strong><ul>{reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul>{result.status === 'insufficient' ? <p>{Math.max(0, 80 - result.wordCount)} ord kvar till 80.</p> : null}</div> : null}
    <div className="metrics"><div><strong>{result.sentenceCount}</strong><span>Meningar</span></div><div><strong>{result.averageLength}</strong><span>Ord / mening</span></div><div><strong>{result.lexicalDiversity}%</strong><span>Ordvariation</span></div></div>
    <div className="signal-list">{result.signals.map(signal => <details key={signal.key}><summary><span>{signal.label}</span><div className="signal-track" aria-hidden="true"><span style={{ width: `${Math.round(signal.value * 100)}%` }}/></div><span className="expand" aria-hidden="true">+</span></summary><p>{signal.detail}</p></details>)}</div>
    <details className="evidence"><summary>Se formuleringar i sitt sammanhang <span>{evidence.length} träffar</span></summary><div><p className="evidence-help">Markeringarna visar var de språkliga signalerna finns. Samma uttryck kan förekomma i människors texter.</p><div className="evidence-source" lang={sourceLanguage}>{sourceParts.map((part, index) => part.marked ? <mark key={index} title={part.explanations.join(' ')}>{part.text}</mark> : <React.Fragment key={index}>{part.text}</React.Fragment>)}</div>{evidence.length ? <details className="evidence-explanations"><summary>Förklaringar till markeringarna</summary><ol>{evidence.map((item, index) => <li key={item.id || index}><q>{item.text || result.sourceText.slice(item.start, item.end)}</q> — {item.explanation}</li>)}</ol></details> : <p>Inga formuleringar att markera. Andra stilvärden kan fortfarande beskrivas ovan.</p>}</div></details>
    <div className="analysis-warning"><Icon name="shield" size={17}/><p>Inte en AI-sannolikhet. Träffsäkerheten är inte validerad mot ett oberoende märkt material. Använd inte detta som bevis för fusk eller som grund för beslut om en person.</p></div>
  </div>;
}

createRoot(document.getElementById('root')).render(<App/>);
