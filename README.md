# TextLab v3 — AiDetector

En lokal textverkstad för svenska och engelska: förklarbar **stilanalys** i webbläsaren och AI-baserad textredigering genom en egen FastAPI-backend.

## Nytt i v3

- Lokal stilanalys med meningsrytm, MATTR-ordvariation, återkommande inledningar, standardfraser, trigram och strukturmått. Markeringar visar exakta textintervall. Språk som inte stöds, fel språkval och otillräcklig text ger avstående.
- Sex redigeringslägen: naturlig, enklare, professionell, akademisk, kortare och utförligare. Ollama, OpenAI Responses API och konfigurerbar kompatibel Chat Completions-tjänst med strikt JSON-schema.
- Original/resultat sida vid sida, ändringsmarkeringar, kopiera, TXT-export, använd som nytt original och återställ originalet. Tangentbord, smala skärmar och fel-/avbrottshantering har förbättrats.
- Skyddade siffror, datum, URL:er, citat, referenser och namnkandidater samt egna exakta textdelar. Felaktiga modellsvar stoppas. Strängkontroller verifierar **inte** betydelsebevarande.
- Faktisk syntetisk generering vid modellkontroll. Separat användaråtkomst och atomiskt delade kvoter/samtidighetsgränser för flera processer på en värd. Begränsade body-/modellsvar, tidsgränser och avbrott.
- Benchmark med proveniens-/rättighetskrav, separata datasplitar, läckagekontroller, AI-redigerade texter som separat grupp och språk-/genre-/längd-/modellresultat.

**Stilindex 0–100 är inte AI-sannolikhet.** Ingen tränad klassificerare eller oberoende verifierad detektionsprecision finns. Minst 80 ord och tillräckligt språkligt underlag krävs för ett index. Använd inte analysen som bevis om vem som skrivit en text eller för beslut om en person. Se [metod och benchmark](docs/DETECTOR_BENCHMARK.md).

## Verifieringsstatus

Enhets-, API-, webbläsar- och automatiska tillgänglighetstester, produktionsbygge, beroendegranskning och prestandamätningar har körts lokalt. Riktiga Ollama-anrop redovisas separat från mockade integrationstester. Verifieringen hittade betydelseförskjutning trots bevarade strängvärden. [Exakta resultat och begränsningar](docs/VERIFICATION.md), [kvalitetsbedömning](QUALITY-SCORECARD.md), [återstående arbete](PROGRESS.md).

Ingen publik deployment hävdas. Ett lokalt containerbygge är inte en publicerad tjänst.

## Starta på Windows

Krav: Node.js 22.12+ och Python 3.11+. Körningen använder också Python 3.12 i container och 3.13 på Windows.

```powershell
git clone https://github.com/sharbel0022/AiDetector.git
cd AiDetector
git switch codex/textlab-v3
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
npm ci
Copy-Item .env.example .env
.\.venv\Scripts\Activate.ps1
npm run dev
```

Öppna `http://127.0.0.1:5173`. Om aktivering blockeras, kör backend med venv-Python och frontend separat:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8767 --no-access-log --no-proxy-headers
npm run dev:web
```

Efter `npm run build` serverar backend `dist/` på `http://127.0.0.1:8767`; starta om backend om katalogen skapades efter serverstart.

### Anslut en modell

**Ollama:** starta en lokal tjänst och sätt `AI_MODEL` i `.env` till en installerad modell. Standardvärdet `qwen2.5:7b` är ett exempel, inte ett löfte om tillgänglighet eller kvalitet. V3 laddar inte ned modeller automatiskt. `OLLAMA_THINK` styr resonemang; standard är avstängt för begränsade redigeringsanrop. Starta om backend efter ändringar. Modellstatus gör en liten riktig generering och använder kvot.

**OpenAI:** sätt `AI_PROVIDER=openai`, `AI_MODEL` och `OPENAI_API_KEY` på servern. Modellen måste stödja Responses API och strikt JSON-schema. `store:false` ersätter inte leverantörens lagringsregler. API-nycklar stannar på servern.

**Kompatibel tjänst:** sätt `AI_PROVIDER=compatible`, `AI_MODEL`, `AI_COMPATIBLE_URL` (betrodd HTTPS-basadress inklusive eventuell `/v1`) och `AI_COMPATIBLE_KEY`. Strikt JSON-schema i Chat Completions krävs; ingen tyst övergång till ostrukturerade svar sker. HTTP tillåts bara på loopback. Verklig extern modellåtkomst för denna adapter har inte verifierats.

En godkänd probe verifierar en liten generering, inte redigeringskvalitet. Granska resultatets betydelse även när skyddade värden passerar.

## Testa, bygga och mäta

```powershell
npm ci
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
npm test
.\.venv\Scripts\python.exe -m pytest -q
npm run build
npm run performance
.\.venv\Scripts\python.exe -m playwright install chromium
```

Starta byggd backend på port 8767 och kör:

```powershell
.\.venv\Scripts\python.exe tools/browser_checks.py
.\.venv\Scripts\python.exe sites/src/ui_checks.py
.\.venv\Scripts\python.exe tools/accessibility_checks.py
.\.venv\Scripts\python.exe tools/api_performance.py
```

Webbläsartesterna mockar språkmodellsvaren. API-mätningen skiljer verkliga lokala HTTP-anrop från ASGI-omskrivningar med uttryckligen mockad modell. `artifacts/` innehåller rapporter och skärmbilder. Vid låst standardtemp på Windows: `python -m pytest -q --basetemp=.venv/pytest-local`.

Valfria riktiga modelltester använder syntetiska original och redan installerade modeller:

```powershell
.\.venv\Scripts\python.exe tools/live_model_checks.py --models llama3.2:3b --output artifacts/live-model-results.json
```

## Benchmark

```powershell
# Tekniska fixtures; inga kvalitetstal för detektorn
npm run evaluate -- tools/fixtures/detector.synthetic.jsonl --fixture
# Eget granskat material enligt JSONL-schemat
npm run evaluate -- independent.jsonl --select-threshold
```

Tröskelval sker på valideringssplit och resultat på testsplit. Metadata är påståenden som kräver extern kontroll av rättigheter/etiketter. Se [schema och mätetal](docs/DETECTOR_BENCHMARK.md). Kalibrering är otillgänglig eftersom stilindex inte är en sannolikhet. Oberoende precision och falskpositiv frekvens är **ej verifierade**.

## Drift och integritet

Privat drift använder en serverhanterad åtkomstkod. Publik fleranvändardrift kräver `TEXTLAB_AUTH_MODE=multiuser`, separata SHA-256-hashade användartoken och `TEXTLAB_STATE_DB` till samma SQLite-fil på lokal disk för alla processer. Detta stöder flera processer på **en värd**; flera värdar kräver externa centrala auth-/kvotsystem. Använd TLS, explicita hosts/origins och leverantörens kontogränser. Se [drift/arkitektur](docs/OPERATIONS.md) och [.env.example](.env.example).

TextLab sparar inte källtext, omskrivningar eller råa åtkomsttoken. SQLite sparar hashade kvotidentiteter, tidsstämplar och reservationer. Webbläsarkoden finns bara i minnet. Leverantör, proxy och hosting kan ha egna lagringsregler. Promptinstruktioner och strängkontroller undanröjer inte all prompt injection eller semantisk risk.

CI har endast läsrättigheter, låsta installationer och verifierade actions-SHA:er. Den kör tester, audits, hemlighetsskanning, två jämförda byggen och sparar artefakter. CI skriver inte till `main`. Äldre `sites-build/` ersätts av workflow-artefakten. Se [publiceringsunderlag](sites/DEPLOYMENT.md).
