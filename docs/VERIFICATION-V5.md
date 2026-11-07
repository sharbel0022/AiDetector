# TextLab V5 — verifiering

Datum: 7 november 2026. Utgångspunkt: `ab16164c7baef1863cbdbd0a6b52f4fa0fc1e237`.
Arbetsbranch: `feature/textlab-v5`. Denna rapport skiljer tekniska tester,
återanvända diagnostikdata och verkliga generativa modellkörningar.

**Verifierad kodkandidat:** `d92b824c9055f4628511a1df955bc15bb1e01681`.
[GitHub Actions 42379391802](https://github.com/sharbel0022/AiDetector/actions/runs/42379391802)
passerade alla steg. Rårapporter, skärmbilder och kontrollerade filhashar finns i
[V5-evidensen](evidence/v5/README.md). Dokumentations- och utskriftsjusteringar
efter denna mätpunkt verifieras även av sin egen körning på
[PR #3](https://github.com/sharbel0022/AiDetector/pull/3).

## Baslinje före V5

Den oförändrade V4-koden på senaste main gav **309 godkända Python-tester** och
**70 godkända JavaScript-tester**. Python rapporterade en befintlig upstream-varning
om Starlette TestClient/httpx. V4:s tidigare CI- och modellresultat finns kvar i
[V4-rapporten](VERIFICATION-V4.md); de räknas inte som nya V5-resultat.

## Körmiljö och verklig modellåtkomst

Python 3.12.14 och de befintliga låsta beroendena användes. Ingen OpenAI-nyckel,
vald OpenAI-modell eller kompatibel provider var konfigurerad i miljön, och ingen
`.env` fanns i denna eller den befintliga checkouten av samma repository.
Port 11434 svarade med connection refused och någon Ollama-binary hittades inte.
**Nya verkliga OpenAI-/Ollama-genereringar: 0.** Provider-mockar verifierar
integration och säkerhet, aldrig modellkvalitet.

En lokal Uvicorn-server kunde startas. Playwright saknade sin nedladdade
Chromium-binary; system-Chromium avbröts av `socket() failed: Operation not permitted`
vid processuppstart. Den separata molnwebbläsaren kunde inte nå denna lokala server.
Docker-binary och daemon saknas i den lokala körmiljön. Browser-, axe- och
containerproven kördes därför i kandidatens faktiska GitHub Actions. Dessa
resultat kommer från V5-koden och inte från äldre CI.

## Säkerhet och beroenden

De aktuella beroendegranskningarna gav noll kända sårbarheter: npm, 23 Python-
runtimeberoenden och sju ML-beroenden. Npm:s miljövarning om `http-proxy` sparas
separat från audit-JSON. Detta är en datumbunden beroendekontroll, inte ett pentest.

Gitleaks 8.30.1 användes efter att den befintliga officiella distributionsfilens
SHA-256 verifierats mot CI:s fastställda checksumma. Baslinjens 11 commits,
cirka 14,8 MB, gav inga fynd. Ändringsdiffarna skannades före publicering och
den aktuella branchens tillgängliga Git-historik skannades i CI, utan fynd.
CI-actions är pinnade till commit-SHA och checkout behåller inga credentials.

## Data och modellbevis

[24 blandade regressioner](../data/v5-mixed-regression/README.md) har byggts av
oförändrade, tidigare arkiverade föräldratexter. De omfattar 12 svenska och 12
engelska dokument från de 12 befintliga källfamiljerna. De tillför **noll nya
oberoende källfamiljer**. Sju regressionstester verifierar källhashar, exakta
UTF-16-intervall, ordandelar, partitioner, reproduktion och att gamla körningar
inte skrivs över. Sammanfogade dokument är inga oberoende kvalitetsdata.

Den [externa datasetgranskningen](DATASET-REVIEW-V5.md) redovisar vilka källor som
undersökts och varför inget sådant material har importerats som en godkänd
produktionskorpus. Originalet till användarens tidigare 572-ords-/47-meningsfall
saknas och har inte återskapats från en skärmbild.

Aktuella detektorresultat, kalibreringsstatus, språk-/genresnitt och
produktionsgrindar dokumenteras i [modellutvärderingen](MODEL_EVALUATION.md).

## Lokal integrationsverifiering

Den fullständiga integrationskörningen efter kodgranskningen gav **482
godkända Python-tester** och **84 godkända JavaScript-tester**. Regressionerna
omfattar bland annat separata evidensgrindar, Unicode-intervall, ordandelar,
förfalskade räknare, källfamiljsläckage, språkval, providerfel, actual usage,
parallella budgetreservationer, användarisolering och äldre kvotdata.

En separat träningskörning reproducerade modellen byte för byte i samma miljö.
Utvärderingsrapporten uppdaterades med hash för de skärpta evidenskontrollerna;
modellvikter, data och mätvärden är oförändrade. Maximal skillnad mellan scikit-learn och JSON-inferens var cirka
`4,55e-15`. Produktionsbygget passerade; två byggen av samma källversion gav
samma filhashar. Inga dependency-versioner ändrades för V5.

Alla **247 tidigare spårade data-, modell- och evidensfiler** jämfördes mot
baslinjens Git-objekt och var oförändrade byte för byte. V4:s tidigare
kvalitetsbedömning finns även bevarad i [QUALITY-SCORECARD-V4.md](QUALITY-SCORECARD-V4.md).

### Browser, tillgänglighet och container

Den byggda frontenden kördes i Chromium mot den riktiga FastAPI-detektorn.
Testet kontrollerade modellversion, exakta originalintervall, stängda grindar
och uteblivna procentsiffror. **17 browsergrupper** passerade, liksom den
separata UI-körningen för sex redigeringslägen, tangentbord, diff, export,
återställning, avbrott, felaktig metadata och fokusåtergång. Färgade
detektorresultat och generativa svar i övriga UI-scenarier är märkta fixtures.

Automatiska axe-kontroller omfattade **11 vyer** vid 1440, 390 och 320 px:
**0 rapporterade överträdelser**. Två resultatvyer innehåller kvarvarande
inkonklusiva kontrastkontroller eftersom axe inte kunde fastställa bakgrunden.
Separat skärmbildsgranskning hittade ingen oavsiktlig överlappning; de berörda
deklarerade färgparen ger kontrastförhållanden mellan 7,15:1 och 10,03:1.
Det ersätter inte en kontroll av alla interaktionstillstånd eller en manuell
skärmläsargranskning. Detaljerna bevaras i `accessibility.json` och
`visual-review.json`. Ingen horisontell overflow eller okontrollerat JavaScriptfel
observerades i de körda mobilscenarierna.

Docker-imagen byggdes och kördes som **UID 10001 med två workers**. Provet
verifierade frontend och säkerhetsheaders, 401 utan autentisering för provider,
detektor och usage, faktisk inferens med den paketerade modellen och en
textfri användarvy. Tolv samtidiga anrop för en annan testanvändare gav exakt
**2 HTTP 200 och 10 HTTP 429**, delat över workers. Ingen verklig generativ
leverantör användes av containertestet.

### Granskningsfynd och första CI-körningen

Separata agentgranskningar identifierade motsägelsefulla kalibreringsräknare som kunde
passera valideringen samt en förbrukningsvy som kunde se aktuell ut efter ett
avbrutet modellanrop. Nya regressioner reproducerade problemen före rättning.
Kalibreringsgrinden kontrollerar nu positiva observationsantal, heltaliga
AI-observationer, överensstämmelse med facit, ECE och Wilson-intervall. UI bevarar
en tydlig osäkerhetsmarkering efter avbrott och erbjuder manuell uppdatering.
En hämtad totalsumma påstår inte att ett visst avbrutet anrop har slutförts.

[Första PR-körningen](https://github.com/sharbel0022/AiDetector/actions/runs/42377205003)
passerade 417 Python- och 81 JavaScript-tester samt beroende- och
hemlighetskontroller, men stoppades av en bytejämförelse mellan träningsmiljöer.
Den nedladdade CI-artefakten hade en största numerisk skillnad på
`1,1102230246251565e-16`; klassutfall, räknare och grindbeslut var identiska.
Den rättade reproduktionskontrollen kräver fortfarande exakta strukturer,
datakällor, typer, heltal och beslut, men accepterar ändliga flyttal inom absolut
plus relativ tolerans `1e-12`. Varje artefakts härledda hashvärden verifieras
separat. CI tränar dessutom två gånger i samma miljö och kräver byteidentitet
mellan dessa körningar. Modellvikterna ändrades inte för att dölja skillnaden.

Nästa CI-körning passerade browserfunktionerna men fann knappnamn som saknade
delar av den synliga texten. Knapparna använder nu sina synliga namn, och
grupproller ger övriga etiketter korrekt semantik. Inga axe-regler stängdes av.
Kodgranskningens omfattning, åtgärder och begränsningar finns i
[granskningsprotokollet](evidence/v5/REVIEW.md).

## Humanizer: historisk återspelning

Samtliga sex lägen har skärpta instruktioner. Nya regelkontroller täcker utvalda
tidsrelationer, modalitet, sannolikhetsstyrka, negation mellan jämförbara satser,
ordningen mellan skyddade namn/tal/datum och betydelsemarkörer mellan ankare.
Parentetiska författar-/årreferenser skyddas. Kontrollerna är avsiktligt begränsade
och kan både missa betydelsefel och avvisa en legitim omskrivning.

De sparade V3-körningarna återspelades mot aktuell validator. **Inga nya
genereringar gjordes** och nya promptar har därför inte testats live.

| Historisk modell | Sparade fall | Accepterades då | Klarar rapportens begränsade innehållskontroller bland då accepterade | Stoppas nu vid återspelning, utöver dåvarande API |
|---|---:|---:|---:|---:|
| llama3.2:3b | 24 | 20 | 12 | 1 |
| qwen3.5:4b | 24 | 19 | 18 | 3 |
| qwen3.5:9b | 24 | 23 | 22 | 1 |

De fem ytterligare stoppen är regelutfall, inte fem oberoende bevisade
betydelsefel. Två av dem passerade rapportens äldre begränsade innehållskontroller.
Några sparade utdata är oförändrade original; ett godkänt schema eller bevarade
siffror är inte ett mått på stilförbättring. `review_required` förblir true och
`semantic_equivalence_verified` false. Blindad redaktionell bedömning av nya
svenska/engelska körningar i alla sex lägen återstår.

## Faktisk usage och budgettester

Provideradaptrarna bevarar verkliga input-, output-, totaltoken, cachetoken när
sådana finns, modell-ID och tidpunkt. Okända räknare förblir null; en total
summerad från två leverantörsräknare märks som härledd. Pristabellen har exakta
modell-ID:n, version och officiell källa. Okända modeller och kompatibla
tredjepartsservrar får inga gissade priser.

Tester verifierar person-/globalbudget, samtidighet över delad SQLite,
idempotent avstämning, felaktigt men potentiellt debiterbart modellsvar,
avbrutna anrop, processförlust, UTC-dygn, användarisolering och äldre V4-kvoter.
USD-gränser kräver en absolut beständig databas. Tidigare okänd kostnad får
inte räknas som noll när gränsen aktiveras. Gränssnittet märker delvis kända
totalsummor och förbrukning från äldre versioner som ofullständiga.
Ett avbrutet anrop markeras som potentiellt ofullständigt även efter nya
hämtningar; ett browserprov visar en fördröjd debitering, manuell uppdatering
och isolering mellan olika åtkomstkoder.

## Prestanda och dess gränser

Lokala mätningar gjordes på Python 3.12.14, Node 24.22.1 och den aktuella
delade exekveringsmiljön. Resultaten är teknikdiagnostik, inte en produktions-SLA.
För en 12 000-teckens svensk text gav faktisk V5-inferens genom ASGI:

| Mätning | Utfall |
|---|---:|
| Första observerade anropet, inklusive import/modelladdning | cirka 293 ms |
| Uppvärmd median, 20 anrop | cirka 206 ms |
| Uppvärmd p95, 20 anrop | cirka 241 ms |
| Åtta samtidiga analyser, p95 | cirka 1 395 ms; samtliga HTTP 200 |

Hela benchmarkprocessens RSS ökade från cirka 51 till 78 MB. Detta inkluderar
Python, ramverk, modellcache och tidigare tester; det är inte isolerad
allokering per anrop. Humanizerns samtidighetsprov använde en uttrycklig HTTP-mock:
två accepterade och sex begränsade av åtta samtidiga begäranden. Den tiden är
inte verklig generativ modellprestanda. OpenAI-/Ollama-kallstart har inte mätts.

Den arkiverade CI-mätningen på Python 3.12.16 och en runner med fyra logiska
CPU:er gav första faktiska detektoranropet **161 ms**, uppvärmd median
**122 ms** och p95 **131 ms** för 20 anrop med 12 000 tecken. Åtta samtidiga
analyser gav p95 **844 ms**, samtliga HTTP 200. Benchmarkprocessens RSS gick
från cirka **62,5 till 79,5 MB**; detta är total process-RSS, inte minne per anrop.
Skillnaden mot lokala tider visar varför värdena måste knytas till körmiljön.

Frontendens gzipstorlek var **91 360 byte JavaScript och 7 430 byte CSS**, under
de oförändrade gränserna 100 000/10 000 byte. Den separata lokala stilanalysen
gav vid 12 000 tecken p95 **8,89 ms för svenska och 5,88 ms för engelska**
(100 körningar per språk). Dessa tider är inte den ML-baserade serveranalysen.
