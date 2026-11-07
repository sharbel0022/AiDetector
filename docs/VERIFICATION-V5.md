# TextLab V5 — verifiering

Datum: 7 november 2026. Utgångspunkt: `ab16164c7baef1863cbdbd0a6b52f4fa0fc1e237`.
Arbetsbranch: `feature/textlab-v5`. Denna rapport skiljer tekniska tester,
återanvända diagnostikdata och verkliga generativa modellkörningar.

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
Docker-binary och daemon saknas i den lokala körmiljön. Browser- och containerprov
måste därför redovisas från kandidatens faktiska GitHub Actions-körning när den
har körts, inte från äldre CI.

## Säkerhet och beroenden

De aktuella beroendegranskningarna gav noll kända sårbarheter: npm, 23 Python-
runtimeberoenden och sju ML-beroenden. Npm:s miljövarning om `http-proxy` sparas
separat från audit-JSON. Detta är en datumbunden beroendekontroll, inte ett pentest.

Gitleaks 8.30.1 användes efter att den befintliga officiella distributionsfilens
SHA-256 verifierats mot CI:s fastställda checksumma. Baslinjens 11 commits,
cirka 14,8 MB, gav inga fynd. Slutkandidatens ändringar ska även skannas före push.

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

Den fullständiga integrationskörningen efter implementationen gav **417
godkända Python-tester** och **81 godkända JavaScript-tester**. Regressionerna
omfattar bland annat separata evidensgrindar, Unicode-intervall, ordandelar,
förfalskade räknare, källfamiljsläckage, språkval, providerfel, actual usage,
parallella budgetreservationer, användarisolering och äldre kvotdata.

En separat träningskörning reproducerade både modell- och utvärderingsfil byte
för byte. Maximal skillnad mellan scikit-learn och JSON-inferens var cirka
`4,55e-15`. Produktionsbygget passerade; två byggen av samma källversion gav
samma filhashar. Inga dependency-versioner ändrades för V5.

Alla **247 tidigare spårade data-, modell- och evidensfiler** jämfördes mot
baslinjens Git-objekt och var oförändrade byte för byte. V4:s tidigare
kvalitetsbedömning finns även bevarad i [QUALITY-SCORECARD-V4.md](QUALITY-SCORECARD-V4.md).

Browser-, axe- och containerresultat ska redovisas från den nya branchens
GitHub Actions. En genomförd lokal build eller kompilering av browser-testkoden
räknas inte som ett godkänt webbläsarprov. Oberoende kodgranskning och CI-status
kompletteras i denna rapport efter kandidatkontrollen.

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
