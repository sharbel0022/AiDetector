# Verifiering — TextLab v3, evidensiteration 2

Datum: 2026-11-02. Branch `codex/textlab-v3`, befintlig PR #1 mot `main`, utan merge. Utgångspunkt för iterationen: `78d4f70fc6bd188b0ff7e5b541f56f84759f2544`. [Första leveransens verifiering](VERIFICATION-INITIAL.md) och dess rårapporter är bevarade; nedan gäller det fortsatta arbetet.

## Genomförda förbättringar

- Riktiga sv/en-pilotdata, käll-/villkorsgranskning, fullständiga råkällor, utdragspositioner, SHA-256 och verkliga lokala genereringsloggar. Tekniska fixtures hålls separata.
- Tränad men **offline och experimentell** char3–5 TF-IDF/logistisk baslinje, fryst konfiguration och författar-/källgrupperade splitar. Webbläsarprodukten använder fortfarande beskrivande stilindex; ingen AI-sannolikhet införs.
- Fristående utvärdering avvisar överlapp mot både träning och tröskelval: source/document/author/group-ID och normaliserade textfingeravtryck. Legacyartefakten godtas inte som bevis för fristående heldout-utvärdering.
- Dokumenterade original/AI-redigeringar i samma split/familj kan behållas som beroende par; orelaterade kopior och splitläckage avvisas fortfarande.
- Humanizern skyddar kända tal/enhetspar atomiskt och kontrollerar utvalda negationer, förbehåll, skyldighets-/orsaksmarkörer samt tecken/intervall/enhetssuffix. Detta är begränsade ytkontroller och kan avvisa säkra omskrivningar.
- Gemensam request-builder gör kvotreservationen utifrån faktiskt HTTPX-serialiserat JSON, inklusive schema, modeinstruktion och escapning, plus protokollmarginal/maxoutput.
- Auditverktyget avvisar siffer-/enhetsprefix och vägrar skriva över befintlig körning innan provideranslutning. Cachade parloggar binds till planerad modell, responsmodell och fryst digest.

## Automatiska kontroller på slutkoden

| Kontroll | Faktiskt resultat |
|---|---|
| `npm test` | **64 godkända, 0 misslyckade, 0 överhoppade** |
| `python -m pytest -q --basetemp=artifacts/pytest-round2-complete` | **210 godkända, 0 misslyckade**, 1 befintlig Starlette/TestClient/httpx-deprecationvarning |
| `tools/browser_checks.py` | Alla 10 kontroller godkända |
| `sites/src/ui_checks.py` | Godkänd: sex lägen, språk, termer, tangentbord, diff/kopia/export, återställning, avbrott, metadatafel och 320 px |
| `tools/accessibility_checks.py` | **0 axe-överträdelser i 11 vyer**; ingen fullständig manuell skärmläsargranskning |
| `npm run build` | Lyckat produktionsbygge; reproducerbarhet kontrolleras även med två byggen i CI |
| Container | Bygge lyckades; UID10001, två workers, auth401 och gemensam rategräns: 2 accepterade/10 avvisade |
| Dataintegritet | Historiska råbyte/utdrag, fryst korpus, moderna revisioner, modeller, snapshots och 72 replay-requesthashar verifierade |
| Fristående ML-replay | Historiska 20 testresultat och moderna 8 resultat reproducerade; ingen träning eller tröskeljustering på test |
| Audits | `npm audit` och `pip-audit` för ML-låset utan kända fynd vid körningen; Gitleaks på staged data/kod utan fynd |

Git-attribut bevarar råa databyte och CRLF där de ingår i frysta SHA-256. Kod som hashas använder LF-checkout. En regression visade att automatisk CRLF-normalisering skulle ändra korpushashen; det är rättat och testat. Extern källarkivering stilformateras inte om för att få grön diffkontroll. Genererade data/experiment är märkta för att kunna fällas ihop i GitHub-review.

Full testmiljö med låst NumPy/SciPy kräver Python 3.12+. Lokalt: Python 3.13.15 och Node 22.16.0 på Windows 11 build 26300, i7-14700K / 28 logiska trådar, cirka 32 GiB RAM och RTX 5070 / 12 227 MiB. Ollama 0.40.13. Container/CI använder Linux/Python 3.12. Standardtempkatalogen gav Windows-rättighetsfel; slutkörningen använder en avgränsad, ignorerad basetemp. Det är ett miljöproblem, inte dolda misslyckade tester.

## Detektor: verkliga pilotresultat och verklig generaliseringsbrist

[Historisk korpus](PILOT_CORPUS.md): 36 mänskliga utdrag från12 böcker/författare och24 verkliga genereringar från två modeller. Train30/validation10/test20, med6/2/4 oberoende historiska källfamiljer. Metadata för AI-kommissioner tillskrivs inte historiska författare. Rättigheter och historiskt mänskligt ursprung är källunderbyggda påståenden med uttryckliga editions-/transkriptionsluckor, inte en universell juridisk eller forensisk garanti.

Frysta hyperparametrar och lågt observerat validerings-FPR-mål valdes före test. Den historiska testmängden gav **TP8, FP0, TN12, FN0; F1/AUROC1,0**. Detta är endast ett litet pilotresultat. Med0/12 mänskliga fel är Wilson-övregränsen24,25%; fyra källfamiljer där ingen familj som har mänskliga fel ger en övregräns48,99% för det annorlunda familjeestimandet. Det validerar inte låg populations-FPR. Stilindexets godtyckliga fasta tröskel65 missade8/8AI i samma pilot, trots att dess ranking-AUROC också var1,0.

Förregistrerade modellholdout-diagnoser missade1/4AI från den helt utelämnade Qwen-modellen i ena riktningen. Kalibrering, sannolikheter och bred genre-/längd-/modellgeneraliserbarhet är inte verifierade.

[Extern modern kontroll](MODERN_HUMAN_HOLDOUT.md): åtta sv/en-utdrag från fyra Wikipedia-revisioner från2017, grupperade som två gemensamma ämnesfamiljer. Den oförändrade modellen flaggade **2/8 mänskligt ursprungsmärkta utdrag (25% observerad FPR)**, 1/4 svenska och1/4 engelska, utan avståenden. Wilsonintervallet på utdragsnivå är7,15–59,07%, och beroendet mellan utdrag gör populationsslutsatser ännu svagare. Båda ämnesfamiljerna innehöll minst en flaggning. AI-recall/F1/AUROC kan inte uppskattas från denna human-only kontroll.

Åtta ytterligare planerade artiklar returnerade HTTP 429 i två begränsade försök; ingen källa byttes efter modellresultat. Licens/revision/attribution är arkiverade. För-LLM-publicering bevisar inte enskilda författaridentiteter eller frånvaro av bottar/importerat material. Ingen ny prompt, feature, vikt eller tröskel valdes för att få den moderna kontrollen att se bättre ut. Modellen är därför fortfarande avstängd i produkten.

[Experimentell metod och resultat](EXPERIMENTAL_DETECTOR.md), [auditerad modell](../models/experimental/pilot-v1-audited/model.json), [metadata-korrigering](../models/experimental/pilot-v1-audited/audit-correction.json). Originalmodellen `pilot-v1` och den första moderna rapporten är byte-identiskt bevarade. De auditerade vikterna, konfigurationen, tröskeln och samtliga20testmarginaler är exakt lika; rättningen gäller källisolering/proveniens och ändrar inte utfall.

Tolv extra [AI-redigeringar](../data/pilot-edits/README.md) är verkliga loggade interventioner, 6permodell. Fyra finns i testsplit och ingen av dem flaggas av den frysta binära modellen. Blandade texter räknas inte som binära AI-falsknegativ. De ursprungliga12mänskliga testutdragen återanvänds som par och är ingen ny oberoende humanvalidering.

## Humanizer: faktisk jämförelse och kvarstående svagheter

Två utvecklings- och två reserverade jämförelsekällor på svenska/engelska kördes i alla sex lägen. Baseline hade redan körts även för de reserverade källorna före utveckling. Kandidatval använde utvecklingsutdata; detta är författade, frysta jämförelsefall, **inte en blind eller orörd extern kvalitetsmängd**. Varje cell är en observation vid temperatur0,3 och slumpmässiga skyddsmarkörer. Skillnader är beskrivande utfall, inte en kausal statistisk kvalitetsökning.

Korrigerad efterbedömning av exakt samma sparade utdata, utan ny inferens:

| Körning/modell | Fall | API accepterade | Accepterade + begränsade kontroller | Därav även ändrade | Oförändrade accepterade |
|---|---:|---:|---:|---:|---:|
| baseline / llama3.2:3b | 24 | 24 | 12 | 4 | 8 |
| baseline / qwen3.5:4b | 24 | 20 | 16 | 11 | 5 |
| final / llama3.2:3b | 24 | 20 | 12 | 4 | 8 |
| final / qwen3.5:4b | 24 | 19 | 18 | 12 | 6 |
| diagnostic-qwen9b / qwen3.5:9b | 24 | 23 | 22 | 15 | 7 |

De 48 slutliga småmodellfallen och24 förregistrerade 9B-fallen gav totalt **62/72 accepterade svar, 52/72 som även klarade de begränsade kontrollerna**, där 31 både ändrades och klarade dessa kontroller. Dessa tal är **inte semantisk accuracy**. Sju 9B-svar var oförändrade och lägeskvalitet är inte verifierad bara för att text/ordantal skiljer sig.

Det finns konkreta betydelse- och språkfel även bland kontroller som passerar: ändrad URL-attribution, tidslinje följd som regelefterlevnad, och ett vanligt svenskt ord som överbeskyddas som namn och får fel grammatisk roll. Flera korrekta parafraser ligger samtidigt utanför de handskrivna mönstren och blir `unassessed`. Kodagentens exempelanteckningar är inte en oberoende mänsklig språkbedömning.9B är en ytterligare samma-familjsdiagnos, inte en experimentellt isolerad parameterstorlekseffekt eller produktionsrekommendation.

Alla misslyckade kandidater är kvar, inklusive en avbruten10 cells-körning. Bokstavlig värdeordbok, läsbara namn/datum och redigeringsplaner gav inte tillräcklig säker nytta och finns inte som produktionsfallback. Slutkoden behåller det enklare opaka protokollet med exakta markörer och tydliga begränsade efterkontroller.

Granskning efter de 72 fallen fann en tecken-/suffixlucka och ett prefixfel i auditkontrollen. Frysta rårapporter, toolhash och källsnapshots är kvar. Den korrigerade validatorn spelades upp mot samma sparade providerutdata: **0 av de 62 tidigare accepterade slut-/diagnossvaren avvisas ytterligare**, medan 10 äldre llama-baselinesvar och 3 äldre Qwen-baselinesvar skulle stoppas av de starkare kontrollerna. Alla **72/72providerförfrågningar är byte-identiska** under senaste builder/protection/prompt. Ingen omgenerering eller förbättrad text har lagts in i rapporterna.

Sex nya verkliga sv/en-prov med negativa/positiva tal och intervall kördes därefter på senaste backend: Qwen 9B 2/2 och Qwen 4B 2/2 accepterade med begränsade kontroller; llama 0/2, med säkra502-avvisanden. Därmed är även den senaste API-koden faktiskt modelltestad, men provet är för litet för säkerhets-/kvalitetsgarantier.

[Full metod, lägesutfall och begränsningar](HUMANIZER_QUALITY.md), [korrigerad efterbedömning](../data/humanizer/reassessment-v2.json), [72request-replay](../data/humanizer/request-replay-v2.json), [senaste verkliga teckenprov](../data/humanizer/runs/signed-canary.json), [konkreta exempelanteckningar](../data/humanizer/agent-review-notes.json).

OpenAI/kompatibel extern provider har protokoll-/feltester med mockar men inga nya verifierade livekörningar här. Inga användarkonfigurationer ändrades och inga modeller hämtades eller manuellt avlastades. Kallstart efter kontrollerad modellurladdning har inte mätts.

## Bygge, drift och återstående krav

Aktuell bundle: JS **82,847byte gzip**, CSS **5,028byte gzip**, inom gränserna100000/10000. ML och benchmarkdata ingår inte i produktionscontainern eller webbundlen. [Analys/bundlemätning](evidence/round2/performance.json), [API/minne](evidence/round2/api-performance.json), [axe](evidence/round2/accessibility.json), [container](evidence/round2/container-results.json). RSS är för hela benchmarkprocessen, inte isolerad allokering eller peak.

CI installerar låsta ML-testberoenden, verifierar arkiv och auditerade fristående scorer på historiska, moderna och blandade data, samt kör tester, audits/Gitleaks, två byggjämförelser, browser/axe/prestanda och två-worker-container. Riktiga modelltester är opt-in lokala data, inte låtsad inferens i CI. Slutstatus för GitHub Actions ska läsas på aktuellt PR-huvud.

Kvar till 9,5: större modern rättighets-/författargranskad och matchad korpus med en ny orörd extern audit; lägre verifierad mänsklig FPR; separat kalibrering; blindad språk-/fakta-/tonbedömning med fler modellfamiljer; färre falska skyddsavvisanden och oförändrade lägen; manuell tillgänglighet, proxy/TLS/identitetslivscykel och publik drift. Se [scorecard](../QUALITY-SCORECARD.md) och [progress](../PROGRESS.md). Ingen publik deployment eller merge har genomförts.
