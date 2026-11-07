# TextLab V4 — verifiering och releaseunderlag

Datum: 2026-11-07. V4 bygger på `5c6328d7c341411042c7d2db150cb88578998302`
och bevarar V3 och `main` i samma Git-historik. Den här rapporten skiljer
körda V4-prov från historisk modellevidens. Den funktionella kandidaten
`2f83163d20d4ef98c1d6a2676eb0505a4090bfba` har verifierats både lokalt och
i GitHub Actions. Slutlig tagg, main-integration och branchrensning är separata
releaseåtgärder efter godkända kontrollpunkter.

## GitHub Actions

[PR-körning 42367167445](https://github.com/sharbel0022/AiDetector/actions/runs/42367167445)
och [push-körning 42367164123](https://github.com/sharbel0022/AiDetector/actions/runs/42367164123)
är båda **success** för kandidaten ovan. Artefakten hämtades och dess SHA-256
kontrollerades mot GitHubs digest. Efter den körningen uppdaterades endast
UI:s versionsetiketter till V4 och releaseunderlaget; den nya kandidaten ska
passera samma fullständiga CI i [PR #2](https://github.com/sharbel0022/AiDetector/pull/2)
innan taggning.

| Kontroll i CI | Faktiskt resultat |
|---|---|
| Python / Node | 309 / 70 passerade; Python 3.12.16 och Node 22.23.4 |
| Browser | 10 huvudkontroller passerade; dessutom sex lägen, språk, skyddade termer, tangentbord, diff, TXT-export, oförändrat resultat, avbrott, felmetadata och dialogfokus |
| Mobil | 390 px och 320 px verifierade utan horisontellt överflöde |
| axe-core | 0 automatiskt upptäckta överträdelser på 11 skärmlägen; fyra `incomplete`-markeringar kvar för manuell bedömning |
| Container | Byggd; nonroot UID 10001; två produktionsprocesser; autentisering och säkerhetshuvuden verifierade |
| Delad containerkvot | 2 anrop accepterade och 10 rate limited över de två processerna |
| Säkerhet / bygge | Audits och historikskanning utan fynd; två identiska produktionsbyggen; bundle-/prestandagränser passerade |
| Offlineevidens | Dataintegritet, frysta modeller, parade redigeringar, klassificerarjämförelse och historisk humanizeråterspelning passerade |

Se [CI-manifest](evidence/v4/ci-verification.json),
[browserrapport](evidence/v4/ci/browser-results.json),
[tillgänglighet](evidence/v4/ci/accessibility.json) och
[containerrapport](evidence/v4/ci/container-results.json).
Browser- och humanizertesterna använder kontrollerade modellsvar. Ingen
modellkvalitet eller publik driftsättning kan utläsas ur gröna CI-prov.

## Lokalt verifierat

| Kontroll | Resultat | Evidens |
|---|---|---|
| Python, hela sviten | **309 passerade**, en befintlig Starlette/httpx-varning | [Logg](evidence/v4/python-tests.txt) |
| JavaScript, hela sviten | **70 passerade** | [Logg](evidence/v4/node-tests.txt) |
| Produktionsbygge | Två identiska byggen, Vite 7.3.7 | [SHA-256](evidence/v4/build-sha256.txt) |
| Node-analys och bundlegränser | Godkända | [Mätning](evidence/v4/performance.json) |
| Riktigt lokalt HTTP/API och samtidighet | Godkända | [Mätning](evidence/v4/api-performance.json) |
| npm-beroenden | 0 kända sårbarheter vid körningen | [Audit](evidence/v4/npm-audit.json) |
| Python runtimeberoenden | 0 kända sårbarheter vid körningen | [Audit](evidence/v4/pip-audit.json) |
| Python ML-beroenden | 0 kända sårbarheter vid körningen | [Audit](evidence/v4/pip-audit-ml.json) |
| Historisk Git-hemlighetsskanning | 8 tidigare commits, inga fynd | [Rapport](evidence/v4/secrets-history-before-v4.json) |
| Offlineklassificerare och dataseparation | Utfört, ingen produktionsaktivering | [Jämförelse](DETECTOR_V4.md) |
| Tidigare modellsvar återspelade | 72 rader granskade; 62 tidigare accepterade svar återspelade utan nya modellanrop | [Rapport](evidence/v4/humanizer-reassessment.json) |

Den lokala HTTP-mätningen omfattar 40 samtidiga health-anrop, åtta för stora
omskrivningar och lång text/samtidighet med en uttryckligen mockad provider.
Modellgenereringshastighet mäts inte. Se rårapporten för antal, statuskoder,
percentiler och minnesmätningens begränsningar.

## Faktiska reparerade fel och verifierade gränser

- Överlapp mellan uttryckliga skyddade textdelar och namn/citat kunde lämna ord
  oskyddade. Felet från PR #1 reproducerades; överlappande intervall sammanfogas
  nu före maskering. De nya regressionerna passerar.
- OpenAI-konfiguration har egna modellvariabler och lånar aldrig en Ollama-
  standardmodell. Saknad konfiguration gör inga HTTP-anrop.
- OpenAI-modellåtkomst kontrolleras före generering. Ogiltig nyckel/modell,
  nekad åtkomst, rate limits, timeout, felaktigt schema, refusals, för stora och
  ofullständiga svar testas med HTTP-mockar.
- Motstridiga `APP_ENV`/`TEXTLAB_ENV` stoppar uppstarten; ett utvecklingsvärde får
  inte tyst slå ut produktionskontroller. Okända miljövärden avvisas.
- Server och UI använder samma UTF-16-baserade textgränser. Ogiltiga surrogater
  och för långa emojiindata avvisas före modellåtkomst.
- Återställning av långa skyddade citat kunde överskrida UI:s utmatningsgräns
  trots ett giltigt maskerat modellsvar. Felet reproducerades med ASCII och
  emoji. Sluttexten valideras nu igen; exakt 16 000 UTF-16-enheter tillåts,
  större resultat avvisas kontrollerat före API-svar.
- Original som lämnas oförändrat bevaras exakt, förklaras i UI och ger ingen
  skenbar språkförbättring. Missformad/inkonsekvent metadata avvisas.
- Auth, origin, bodygränser, kvotreservationer, flera användare/processer,
  avbrott och skyddade tal, tecken, enheter, citat och referenser täcks av sviten.
- Python- och browseranalys jämförs över 84 fullständiga svar: explicita
  kantfall samt alla 60 pilot- och åtta moderna regressionsutdrag.

## Separat kodgranskning

En ny granskare kontrollerade kandidatens providers, AIService, konfiguration,
skyddade fakta, Unicode, frontendkontrakt, ML-dataseparation och container-/CI-
koppling. Granskaren körde 81 fokuserade tester och hittade utmatningsfelet
ovan. Efter reparationen granskades ändringen separat och samtliga fyra
gränsregressioner passerade. Inga öppna kritiska eller viktiga fynd återstår
inom den granskade omfattningen. Granskningen ersätter inte de live- och
exekveringsprov som uttryckligen anges som ej verifierade nedan.

## Korrekt tolkning av modellevidensen

Ingen OpenAI-nyckel eller vald OpenAI-modell finns i körmiljön. Ollama är inte
installerad och port 11434 har ingen körande tjänst. **Inga nya riktiga OpenAI-
eller Ollama-genereringar har körts för V4.** Det är inte samma sak som en
misslyckad livekvalitetsmätning; den mätningen är inte genomförd.

Återspelningen använder tidigare sparade svar från två mindre modeller och
Qwen 9B. Alla 62 tidigare API-accepterade svar passerar även den nuvarande
validatorn; de 62 jämförda requests är byte-identiska. Totalt 52 av de 72
historiska fallen klarar de begränsade fallkontrollerna. Det är **inte** semantisk
accuracy och bevisar inte att samtliga sex lägen ger tillräcklig nytta.

Alternativa ord- och ord/teckenklassificerare tränades bara på train och valdes
bara med validation. Baslinjen behölls. Den återanvända historiska testmängden
har perfekta utfall för alla tre, men är ingen ny oberoende testmängd. Baslinjens
kända två falska flaggningar av åtta moderna mänskliga utdrag återkommer exakt.
De åtta utdragen kommer från fyra språk/artikelkällor och två ämnesgrupper,
vilket ytterligare begränsar slutsatser. Experimentmodellerna är avstängda i
produkten och inga AI-författarskapssannolikheter visas.

## Exekveringsgränser i den lokala miljön

Playwrights Chromium-download gav en ogiltig/tom zip. Installerad system-Chromium
kunde inte starta eftersom miljön avvisade en socketoperation. Docker saknas
helt: ingen binary, daemon eller socket. Browser-, axe- och containerprov utfördes
därför i kandidatens GitHub Actions och passerade där. Tidigare grön V3-CI är
historik och räknas inte som en ny V4-körning.

## Säkerhet och begränsningar

- Modellval och provider-URL är serverkonfiguration. Nycklar går inte till
  frontend. `.env` är exkluderad från Git och containerbygget.
- Det finns ingen publik anonym betald genereringsendpoint. Extern åtkomst
  kräver TextLab-autentisering, även när en modellnyckel finns på servern.
- Tokenbudgetar begränsar användning men garanterar ingen kostnad i kronor.
- Exakta bevarandekontroller och begränsade betydelsemarkörer är separata;
  `semantic_equivalence_verified` förblir false och granskning krävs alltid.
- Flerhostdrift, manuell språkbedömning, oberoende penetrationstest och manuell
  skärmläsargranskning är inte verifierade. Ingen publik deployment hävdas.

[Arkitektur](ARCHITECTURE.md) · [API](API.md) · [Drift](DEPLOYMENT.md) ·
[Lokal körsammanfattning](evidence/v4/local-verification.json)
