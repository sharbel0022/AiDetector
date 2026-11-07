# TextLab V4 — AI Detector & AI Humanizer

TextLab är en textverkstad för svenska och engelska. **AI Detector visar ett
förklarbart stilindex. AI Humanizer föreslår språkredigering med OpenAI, Ollama
eller en kompatibel modellserver.** Originalet bevaras och användaren kan jämföra,
kopiera, exportera och granska resultatet.

**Stilindex är inte AI-sannolikhet. Text kan inte säkert tillskrivas en människa
eller en AI enbart utifrån dess stil.** Den experimentella ML-klassificeraren är
inte aktiverad i webbappen. En omskrivning som klarar exakta kontroller kräver
fortfarande granskning av betydelse, relationer och nya påståenden.

## Nytt i V4

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
experimentverktygen. Separat uppstart och felsökning finns i
[installations- och driftguiden](docs/DEPLOYMENT.md).

Appen startar även utan konfigurerad modell. Den lokala stilanalysen fungerar
utan betalt AI-API. Humanizern visar ett ärligt fel när modellen saknas.

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
[verifieringsrapporten](docs/VERIFICATION-V4.md).

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

Webbläsaren beräknar ordvariation med MATTR, meningslängdsvariation,
återkommande inledningar, standardfraser och återkommande ordsekvenser.
Markeringarna pekar på faktiska textintervall. Analysen skickar ingen text till
backend eller modellleverantör. Ett separat `/api/detect`-gränssnitt erbjuder
motsvarande modellfria analys för serverintegrationer.

Stilindex visas först vid minst 80 ord, fyra meningar och tillräckligt stöd för
valt språk. Annars avstår analysen och förklarar varför. Namnet AI Detector
innebär inte att författarskap går att fastställa.

Den historiska TF-IDF/logistiska piloten bygger på 36 mänskliga utdrag och
24 genereringar. Den tidigare externa kontrollen gav **2 av 8 falska flaggningar
av mänskliga utdrag**. Det är ett känt generaliseringsproblem. Dessa exempel
är bevarade som regression, inte omdöpta till en ny oberoende testmängd.
Se [V4-jämförelsen](docs/DETECTOR_V4.md),
[experimentmodellen](docs/EXPERIMENTAL_DETECTOR.md) och
[metod och benchmark](docs/DETECTOR_BENCHMARK.md).

## Hur AI Humanizer fungerar

Sex lägen har separata instruktioner: **Naturlig, Enklare, Professionell,
Akademisk, Kortare och Utförligare**. Modellen får instruktion att inte lägga
till sakpåståenden, erfarenheter eller källor. Om ingen säker förbättring görs
kan originalet returneras oförändrat.

Backend maskerar identifierade tal, kända enheter, datum, namn, URL:er, citat,
referenser och användarens egna exakta uttryck. Överlappande skydd sammanfogas.
Svaret måste följa schema, vara fullständigt och klara bevarandekontrollerna.
Separata ytregler söker utvalda förändringar av negation, osäkerhet och orsak.

**Exakta kontroller är inte betydelseverifiering.** Namnidentifiering och
betydelserisker bedöms delvis heuristiskt. Även ett accepterat svar kan ändra
relationer eller lägga till något som inte fångas av reglerna. Därför är
`review_required` alltid true och `semantic_equivalence_verified` alltid false.
Se [humanizerns historiska kvalitetsrapport](docs/HUMANIZER_QUALITY.md).

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
python tools/compare_classifiers.py --output artifacts/classifier-comparison.json
docker build -t textlab:v4-review .
python tools/container_checks.py --image textlab:v4-review
```

Mockade providerresultat, återspelade historiska svar och verkliga modellanrop
är olika sorters evidens och redovisas separat. Ett tekniskt grönt testresultat
är inte ett mått på detektorns eller humanizerns språkförståelse.

## Publicering och säkerhet

Efter `npm run build` kan FastAPI servera `dist/` på port 8767. Använd HTTPS,
explicit host/origin och autentisering vid fjärrdrift. Privat drift använder
`TEXTLAB_TOKEN`; fleranvändarläge använder separata hashade token och gemensam
SQLite-kvotfil på en värd. Dagliga tokenreservationer och samtidighet begränsar
modellarbete. Sätt även kontogränser hos leverantören.

TextLab lagrar inte användartexter, omskrivningar eller råa token. Hosting,
proxy och modellleverantör kan ha egna logg- och lagringsregler. Nycklar eller
`.env` ska inte finnas i Git, frontend eller containerimage. Det finns ingen
verifierad arkitektur för flera värdar med separata kvotfiler.

## Dokumentation

- [Arkitektur med Mermaid-diagram](docs/ARCHITECTURE.md) och [diagramkälla](docs/ARCHITECTURE.mmd)
- [API-kontrakt](docs/API.md)
- [Installation, OpenAI, Ollama och deployment](docs/DEPLOYMENT.md)
- [V4-verifiering och kvarstående begränsningar](docs/VERIFICATION-V4.md)
- [Kvalitetsbedömning](QUALITY-SCORECARD.md)
- [Historisk V3-verifiering](docs/VERIFICATION.md)

Målet 9,5/10 är ett kvalitetsmål, inte ett förutbestämt betyg. Faktisk evidens
ska avgöra bedömningen.
