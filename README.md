# TextLab V5 — AI Detector & AI Humanizer

TextLab är en textverkstad för svenska och engelska. **AI Detector kör en tränad
textklassificerare och visar vilka bedömningar underlaget räcker till. AI Humanizer
föreslår språkredigering med OpenAI, Ollama eller en kompatibel modellserver.**
Originalet bevaras för jämförelse, kopiering och export.

**Den medföljande detektormodellen är en forskningspilot. Dokumentets AI-sannolikhet
och andelen AI-markerad text är spärrade eftersom oberoende validering och
kalibrering saknas.** Den moderna kontrollen ger fortfarande två falska positiva
av åtta mänskliga utdrag. Gränssnittet visar begränsningen i stället för en
påhittad procentsiffra. Textens författarskap kan inte bevisas av modellen.

## Nytt i V5

- Tränad TF-IDF/logistisk modell med jämförelse av ord-, tecken- och kombinerade
  representationer. Ren Python-inferens läser ett begränsat, integritetskontrollerat
  JSON-format; scikit-learn behövs bara för träning.
- Separata evidenskrav för dokumentklassificering, dokumentkalibrering,
  segmentklassificering och segmentkalibrering. Dokumentpoäng används aldrig
  automatiskt som meningsetiketter eller textandelar.
- Automatisk svenska/engelska, manuell överstyrning, exakt segmentering och
  förklaringar vid språkblandning eller otillräckligt underlag.
- Tvådelad arbetsyta med resultatkort, klickbara textsegment, osäkerhet,
  analyserbar täckning, TXT/JSON-export och utskriftsrapport.
- Faktiska tokenräknare, versionshanterade prisuppskattningar, egen aggregerad
  förbrukning och atomiska token-/kostnadsbudgetar utan användartext i loggen.
- Blandade regressioner med kända källintervall. De återanvänder historiska
  texter och räknas inte som ny oberoende kvalitetsdata.

## Bevarad grund från V4

- Centralt Python-gränssnitt i [`ai/ai.py`](ai/ai.py): `AIService.detect`,
  `AIService.humanize` och `AIService.provider_status`.
- Separata moduler för konfiguration, leverantörer, promptlägen, validering,
  Unicode-medveten stilanalys och textjämförelse. Den fungerande React-koden ligger
  kvar i `sites/`.
- OpenAI Responses API med serverns `OPENAI_API_KEY` och `OPENAI_MODEL`.
  Konfigurations-, modell-, åtkomst- och providerfel hanteras utan att exponera
  hemligheter. Ingen kodändring behövs för att byta till en kompatibel modell.
- Ollama och det äldre `AI_MODEL`-formatet stöds fortfarande. Modeller laddas
  inte ner automatiskt.
- Exakta skydd som överlappar namn eller citat sammanfogas så inget uttryckligt
  skydd tyst tappas. Begränsningar följer samma UTF-16-räkning i webb och API.
- Oförändrade modellsvar behåller hela originalet och får en tydlig förklaring.
- Alla tidigare korpusar, modellartefakter och rapporter är bevarade. Nya
  jämförelser märker återanvända testdata som historiska diagnostikdata.

## Installera och starta

Krav: Node.js 22.12+ och Python 3.12+ för den låsta test-/ML-miljön.

```powershell
git clone https://github.com/sharbel0022/AiDetector.git
cd AiDetector
git switch feature/textlab-v5
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
npm ci
Copy-Item .env.example .env
.\.venv\Scripts\Activate.ps1
npm run dev
```

Öppna `http://127.0.0.1:5173`. Backend använder port `8767`.
På Linux/macOS används `.venv/bin/python` och `source .venv/bin/activate`.
Enbart runtime behöver `requirements-lock.txt`; ML-beroenden används bara av
tränings- och utvärderingsverktygen. Separat uppstart och felsökning finns i
[installations- och driftguiden](docs/DEPLOYMENT.md).

Detektor och lokal stilanalys kräver ingen generativ API-nyckel. ML-analysen
skickar text till den egna TextLab-backenden, utan att skicka den till OpenAI
eller Ollama. Humanizern visar ett konfigurationsfel när dess modell saknas.

## Aktivera OpenAI

Ändra serverns `.env` och starta om backend:

```dotenv
AI_PROVIDER=openai
OPENAI_API_KEY=DIN_NYCKEL
OPENAI_MODEL=MODELL_ID
```

Välj ett modell-ID som projektets nyckel har tillgång till och som stöder
Responses API med strikt JSON-schema. Nyckeln stannar på backend och ska aldrig
klistras in i frontendens inställningar. TextLabs åtkomstkod är en separat kod.
Modellen väljs på servern; obehöriga användare kan inte välja en dyrare modell i
API-anropet. `OPENAI_MODEL` har företräde framför det äldre `AI_MODEL`.

Vid saknad konfiguration visas:

> OpenAI är inte konfigurerat. Lägg till OPENAI_API_KEY och OPENAI_MODEL i serverns .env.

Statuskontrollen kan göra en liten riktig generering och använder kvot. Ett
lyckat statusprov verifierar inte språk- eller betydelsekvalitet. Verkliga
OpenAI-resultat redovisas bara när de faktiskt har körts; se
[verifieringsrapporten](docs/VERIFICATION-V5.md).

## Använd Ollama

Starta Ollama, kontrollera `ollama list` och välj en installerad modell:

```dotenv
AI_PROVIDER=ollama
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3.5:9b
OLLAMA_THINK=false
```

Qwen-namnet är ett exempel, inte ett löfte om installation eller tillräckligt
minne på din dator. Andra kompatibla installerade modeller kan väljas via `.env`.
Inga automatiska modellnedladdningar sker. En befintlig kompatibel Chat Completions-
adapter finns kvar; dess konfiguration beskrivs i [driftguiden](docs/DEPLOYMENT.md).

## Hur AI Detector fungerar

Webbläsaren håller beskrivande stilanalys separat från serverns ML-resultat.
MATTR, meningsrytm, upprepningar och standardfraser är språkegenskaper;
stilindex är aldrig en sannolikhet för AI. Analysknappen använder `/api/detect`.

Servern delar upp originalet utan att ändra det och bedömer varje användbart
segment självständigt. Positioner är halvöppna UTF-16-intervall. Korta eller
språkligt osäkra segment kan exkluderas. Textandelen definieras som
`AI-markerade analyserbara ord / samtliga analyserbara ord × 100` och får
visas först efter separat validering av segmentmetoden. Dokumentets kalibrerade
klassannolikhet är ett annat mått. Inget av dem är den verifierade andelen
AI-författad text.

Stilindex visas först vid minst 80 ord, fyra meningar och tillräckligt stöd för
valt språk. Annars avstår analysen och förklarar varför. Namnet AI Detector
innebär inte att författarskap går att fastställa.

Träningen använder 60 spårbara historiska pilottexter från 12 källfamiljer:
36 mänskliga utdrag och 24 genereringar. Åtta moderna mänskliga utdrag,
tolv AI-redigerade texter och 24 konstruerade blandningar används som märkta
regressioner. Den moderna kontrollen ger fortfarande **2 av 8 falska positiva**.
Återanvända tester ger ingen ny oberoende evidens.
Se [V5-detektorn](docs/DETECTOR_V5.md),
[mätresultaten](docs/MODEL_EVALUATION.md) och
[datasetgranskningen](docs/DATASET-REVIEW-V5.md).

## Hur AI Humanizer fungerar

Sex lägen har separata instruktioner: **Naturlig, Enklare, Professionell,
Akademisk, Kortare och Utförligare**. Modellen får instruktion att inte lägga
till sakpåståenden, erfarenheter eller källor. Om ingen säker förbättring görs
kan originalet returneras oförändrat.

Backend maskerar identifierade tal, kända enheter, datum, namn, URL:er, citat,
referenser och användarens egna exakta uttryck. Överlappande skydd sammanfogas.
Svaret måste följa schema, vara fullständigt och klara bevarandekontrollerna.
Separata regler söker utvalda förändringar av negation, osäkerhet, orsak och
tidsrelationer. De kan missa betydelsefel och kan avvisa en säker redigering.

**Exakta kontroller är inte betydelseverifiering.** Namnidentifiering och
betydelserisker bedöms delvis heuristiskt. Även ett accepterat svar kan ändra
relationer eller lägga till något som inte fångas av reglerna. Därför är
`review_required` alltid true och `semantic_equivalence_verified` alltid false.
Se [humanizerns historiska kvalitetsrapport](docs/HUMANIZER_QUALITY.md) och
[V5-verifieringen](docs/VERIFICATION-V5.md).

## Förbrukning och budget

Leverantörens rapporterade input-, output- och totaltoken följer med resultatet.
En total som summeras från delräknare märks som härledd. Saknade värden visas
som **Ej tillgängligt**. `GET /api/usage` ger den autentiserade användarens
aggregerade UTC-dygn, ofullständig rapportering och kvarstående reservationer.
UI visar när uppgifterna senast hämtades och har en knapp för uppdatering.
Efter ett avbrutet anrop ligger osäkerhetsmarkeringen kvar: en ny totalsumma
bevisar inte att just det anropet är färdigt på servern.

[Prisregistret](config/model-prices.json) anger exakta modell-ID:n, valuta,
version, källdatum och officiella priskällor. Okända modeller eller tjänstenivåer
får ingen påhittad kostnad. Uppskattningar är inte fakturor. Valfria USD-gränser
kompletterar tokenbudgetarna; okända priser stoppar anrop när en sådan
kostnadsgräns krävs. Se [API](docs/API.md) och [drift](docs/DEPLOYMENT.md).

## Tester och bygg

```powershell
npm test
python -m pytest -q
npm run build
npm run performance
```

Starta den byggda backendservern och kör webbläsar-, tillgänglighets- och
API-prestandaproven enligt [driftguiden](docs/DEPLOYMENT.md). CI kör även
beroendegranskning, hemlighetsskanning, dataintegritet, två jämförda byggen och
en produktionscontainer med två workers.

```powershell
python -m tools.train_v5 --output-dir artifacts/v5-reproduced
python -m tools.check_v5_reproduction models/v5/detector.json artifacts/v5-reproduced/detector.json
python -m tools.evaluate_v5 --data data/modern-human/corpus.jsonl --output artifacts/v5-evaluation.json
docker build -t textlab:v5-review .
python tools/container_checks.py --image textlab:v5-review
```

Mockade providerresultat, återspelade historiska svar och verkliga modellanrop
är olika sorters evidens och redovisas separat. Ett tekniskt grönt testresultat
är inte ett mått på detektorns eller humanizerns språkförståelse.

## Publicering och säkerhet

Efter `npm run build` kan FastAPI servera `dist/` på port 8767. Använd HTTPS,
explicit host/origin och autentisering vid fjärrdrift. Privat drift använder
`TEXTLAB_TOKEN`; fleranvändarläge använder separata hashade token och gemensam
SQLite-kvotfil på en värd. Atomiska token- och kostnadsreservationer samt
samtidighetsgränser begränsar modellarbete. Sätt även kontogränser hos leverantören.

TextLab lagrar inte användartexter, omskrivningar eller råa åtkomsttoken.
Användnings- och kvotmetadata lagras utan text. Hosting,
proxy och modellleverantör kan ha egna logg- och lagringsregler. Nycklar eller
`.env` ska inte finnas i Git, frontend eller containerimage. Det finns ingen
verifierad arkitektur för flera värdar med separata kvotfiler.

## Dokumentation

- [Arkitektur med Mermaid-diagram](docs/ARCHITECTURE.md) och [diagramkälla](docs/ARCHITECTURE.mmd)
- [API-kontrakt](docs/API.md)
- [Installation, OpenAI, Ollama och deployment](docs/DEPLOYMENT.md)
- [V5-verifiering och kvarstående begränsningar](docs/VERIFICATION-V5.md)
- [Detektor och mätresultat](docs/MODEL_EVALUATION.md)
- [Konkurrenternas resultatsemantik](docs/COMPETITOR-RESEARCH.md)
- [Kvalitetsbedömning](QUALITY-SCORECARD.md)
- [Bevarad V4-verifiering](docs/VERIFICATION-V4.md)
- [Historisk V3-verifiering](docs/VERIFICATION.md)

Målet 9,5/10 är ett kvalitetsmål, inte ett förutbestämt betyg. Faktisk evidens
ska avgöra bedömningen.
