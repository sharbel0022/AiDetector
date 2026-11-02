# TextLab v2 — AiDetector

React-gränssnitt för lokal, förklarbar stilanalys och AI-baserad textredigering via FastAPI. Svenska och engelska stöds.

## Vad fungerar?

- **AI-detektor / stilanalys:** meningsrytm, ordvariation, återkommande inledningar och standardfraser, med förklaringar och meningar i sitt sammanhang. All analys sker i webbläsaren.
- **AI-humanizer:** riktig modellkoppling till lokal Ollama eller OpenAI Responses API. Naturligt, enklare eller professionellt tonläge. Ingen regelbaserad reservlösning som utger sig för att vara AI.
- **Granskning:** jämförelse med tillägg/borttagningar, kopiering och TXT-export. Siffror, URL:er, hakparentesreferenser och citat skyddas och kontrolleras efter generering.
- **Integritet:** TextLab har ingen texthistorik, databas eller spårningskod. Leverantörens egna lagringsregler kan fortfarande gälla vid AI-anrop.

**Viktig begränsning:** Stilindex 0–100 är INTE sannolikheten för AI-författarskap. Detektorn är en heuristisk stilmodell, inte en tränad och oberoende validerad AI-klassificerare. Korta texter under 80 ord får inget index. Använd inte resultatet som bevis för fusk eller som beslutsunderlag om en person. Omskrivning garanterar inte att fakta/betydelse bevaras eller att andra detektorer påverkas.

## Starta på Windows

Krav: Python 3.11+ och Node.js 22.12+ (eller en senare kompatibel LTS-version).

```powershell
git clone https://github.com/sharbel0022/AiDetector.git
cd AiDetector
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
npm install
Copy-Item .env.example .env
npm run dev
```

Öppna `http://127.0.0.1:5173`. Backend finns på port 8767. Behåll terminalen öppen. Vid problem med PowerShell-aktivering kan backend köras med `.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8767` och frontend separat med `npm run dev:web`.

### Lokal AI med Ollama

Installera/starta Ollama på samma dator som backend och hämta den konfigurerade modellen:

```powershell
ollama pull qwen2.5:7b
```

`qwen2.5:7b` är ett konfigurationsexempel, inte ett påstående om bästa eller senaste modell. Välj en modell som passar datorns minne och testa omskrivningskvaliteten. Ändra `AI_MODEL` i `.env` vid behov och starta om backend. Modellen måste vara installerad innan omskrivning fungerar. Kontrollera status i AI-humanizer-vyn.

### OpenAI som alternativ

Sätt `AI_PROVIDER=openai`, `AI_MODEL` till en modell ditt API-konto har åtkomst till och `OPENAI_API_KEY` i serverns `.env`. Modellen måste stödja Responses API och det strukturerade schemaformatet. Nyckeln får aldrig läggas i frontend eller skickas till GitHub. TextLab sätter `store: false`; detta är inte en generell garanti om leverantörens loggning/retention. API-användning kan medföra kostnader.

## Testa och bygga

```powershell
npm test
python -m pytest -q
npm run build
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8767
```

Efter byggning serverar backend frontend från `dist/`, på `http://127.0.0.1:8767`. Starta om en redan körande backend om `dist/` skapades efter serverstart.

Webbläsartester:

```powershell
python -m pip install playwright
python -m playwright install chromium
python tools/browser_checks.py
```

Starta den byggda appen på port 8767 först. Testerna använder kontrollerade API-svar för omskrivning. De verifierar inte verklig LLM-kvalitet.

GitHub Actions kör enhets-/API-tester, produktionsbygge och desktop-/mobiltester. Vid godkänd körning sparas byggd frontend i `sites-build/` och `package-lock.json` på `main`. Använd därefter `npm ci` för reproducerbara installationer. Build-artefakten innehåller skärmbilder och testresultat. Ett grönt bygge är inte en publicerad Site eller en verifierad AI-modell.

## Mät detektorn med egna etiketterade data

Skapa en JSONL-fil där varje rad har `source_id`, `language` (`sv`/`en`), `label` (`human`/`ai`) och `text`. Etiketterna måste ha känt ursprung; modellens gissning får inte användas som facit.

```powershell
npm run evaluate -- min-oberoende-testdata.jsonl 65
```

Rapporten innehåller förväxlingsmatris, precision, återkallning, falskpositiv frekvens, F1, täckning och språkgrupper. Avstådda bedömningar redovisas separat. Ingen verklig noggrannhet har uppmätts i detta repo utan ett sådant material. Välj tröskeln på separat valideringsdata, inte testdata. Separera författare, ämnen, dokumentfamiljer och generatorer mellan splitarna.

## Publicering och Sites

Källkoden till frontend finns i `sites/`. Se `sites/DEPLOYMENT.md`. Sites-publicering har **inte** verifierats: de tillgängliga Sites-verktygen i ursprungssessionen gäller en annan, befintlig app och kan inte skapa en ny Site. Den andra appen har inte ändrats.

För publik drift krävs HTTPS, en separat säkrad backend eller samma-origin-hosting, `TEXTLAB_ENV=production`, en slumpmässig `TEXTLAB_TOKEN` på minst 32 tecken, explicita `ALLOWED_HOSTS` utan `testserver` och korrekta `ALLOWED_ORIGINS`. Ange backend-adressen och TextLab-koden i Inställningar. Koden ligger endast i sidans minne; den är inte en OpenAI-nyckel. En delad åtkomstkod är avsedd för privat användning, inte en offentlig fleranvändartjänst. Fleranvändardrift kräver separat autentisering, kvoter och robust distribuerad begränsning.

## Tekniska referenser

- OpenAI, classifier limitations: https://openai.com/index/new-ai-classifier-for-indicating-ai-written-text/
- OpenAI, Responses API and structured outputs: https://developers.openai.com/api/docs/guides/structured-outputs
- Ollama, structured outputs: https://docs.ollama.com/capabilities/structured-outputs

## Projektstruktur

`sites/src/` UI och analys · `backend/` säker AI-koppling · `tests/` API-tester · `tools/` benchmark och webbläsartester · `docs/` design, plan och verifieringsstatus.
