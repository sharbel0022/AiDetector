# Installation och drift av TextLab V4

## Lokalt på Windows

Använd Node.js 22.12+ och Python 3.12+ för den låsta utvecklings- och ML-miljön.

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

Frontend: `http://127.0.0.1:5173`. Backend: `http://127.0.0.1:8767`.
Vite skickar `/api` vidare till backend. Om PowerShell blockerar aktivering, kör
backend och frontend i två terminaler:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8767 --no-access-log --no-proxy-headers
npm run dev:web
```

På Linux/macOS används `.venv/bin/python` och `source .venv/bin/activate`.
För enbart runtime används `requirements-lock.txt`; experimentens scikit-learn
behövs inte för webbappen.

## OpenAI: välj modell utan kodändring

Ändra bara serverns `.env` och starta om backend:

```dotenv
AI_PROVIDER=openai
OPENAI_API_KEY=DIN_NYCKEL
OPENAI_MODEL=MODELL_ID
```

`MODELL_ID` måste finnas tillgänglig för projektets nyckel och stödja Responses API
med strikt JSON-schema. Modellen väljs på servern. Ett modellnamn i klientens JSON
accepteras inte. `OPENAI_MODEL` har företräde framför det äldre `AI_MODEL`.
Saknas nyckel eller modell startar webbappen ändå och visar ett konfigurationsfel.

Kontrollera modellstatus i UI. Ett godkänt statusanrop är en liten riktig
generering och kan kosta pengar. Det bevisar formatstöd för det anropet, inte
generell korrekthet eller språkredigeringskvalitet. Inga liveprov ska rapporteras
som genomförda bara för att konfigurationen ser korrekt ut.

Lägg aldrig nyckeln i `VITE_*`, frontendinställningar, Git eller containerimagen.
`.env.example` är en mall utan hemligheter. Variabelnamn med äldre `TEXTLAB_*`
och `AI_MODEL` behålls för kompatibilitet; undvik motstridiga dubbla inställningar. Om både `APP_ENV` och `TEXTLAB_ENV` anges måste de betyda samma miljö; konflikt avbryter uppstarten för att inte försvaga produktionsskydd.

## Ollama och lokala modeller

```dotenv
AI_PROVIDER=ollama
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3.5:9b
OLLAMA_THINK=false
```

Starta Ollama och kontrollera installerade modeller med `ollama list`. Modellnamnet
ovan är ett konfigurationsexempel. Det förutsätter att modellen faktiskt är
installerad och att maskinens minne räcker. TextLab laddar inte ner modeller
automatiskt. Välj en annan kompatibel installerad modell genom att ändra
`OLLAMA_MODEL`; det äldre `AI_MODEL` kan fortfarande användas.

I container betyder `127.0.0.1` containern själv. En extern Ollama-server måste
enligt appens konfiguration nås över HTTPS. Använd en betrodd TLS-proxy eller
kör backend lokalt tillsammans med Ollama. Exponera inte en oskyddad modelltjänst
publikt för att få anslutningen att fungera.

En befintlig kompatibel Chat Completions-adapter finns kvar via
`AI_PROVIDER=compatible`, `AI_MODEL`, `AI_COMPATIBLE_URL` och
`AI_COMPATIBLE_KEY`. Den kräver strikt schemaformat; inget ostrukturerat fallbackläge
används. URL:er är serverkonfiguration och omdirigeringar följs inte.

## Text-, tid- och budgetgränser

```dotenv
AI_MAX_INPUT_CHARS=8000
AI_REQUEST_TIMEOUT=120
TEXTLAB_MAX_OUTPUT_TOKENS=6000
TEXTLAB_REQUESTS_PER_MINUTE=20
TEXTLAB_MAX_CONCURRENT=2
TEXTLAB_DAILY_TOKEN_BUDGET=250000
TEXTLAB_GLOBAL_DAILY_TOKEN_BUDGET=1000000
```

En lägre `AI_MAX_INPUT_CHARS` (10–8 000) annonseras till UI och kontrolleras av
servern. Den lokala stilanalysen har separat gräns 12 000 tecken. Budgeten
reserverar hela modellbegärans UTF-8-byte, en marginal och högsta outputbudget.
Det är en konservativ användningsgräns, inte en garanti i kronor. Sätt också
projektgränser hos leverantören. Fel och avbrott återbetalar inte reservationer.

## Privat och delad drift

För privat fjärråtkomst, sätt en lång slumpmässig `TEXTLAB_TOKEN`. Klienten anger
denna TextLab-kod under Inställningar. Utan token är skyddade API:er endast
tillgängliga från loopback i utvecklingsläge.

Produktionsdrift kräver:

- `TEXTLAB_ENV=production` eller dess alias `APP_ENV=production`.
- Explicit `ALLOWED_HOSTS` och `ALLOWED_ORIGINS`, med HTTPS för externa origins.
- En privat token om minst 32 tecken, eller `TEXTLAB_AUTH_MODE=multiuser` och
  separata SHA-256-tokenhashar i `TEXTLAB_USER_TOKENS`.
- En skyddad, absolut `TEXTLAB_STATE_DB`-sökväg på lokal disk, gemensam för alla
  workers. Fleranvändarläge kräver denna delade fil.

`--no-proxy-headers` förhindrar att obetrodda forwarded-headers ger lokal åtkomst.
Behåll detta om proxyarkitekturen inte har verifierats separat. SQLite är avsett
för flera processer på en värd. Flera repliker på olika värdar kräver gemensam
extern auth/kvotlagring och är inte en verifierad konfiguration här.

## Bygg och container

```powershell
npm run build
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8767 --no-access-log --no-proxy-headers
```

Backend serverar den byggda `dist/`-katalogen. Starta om backend efter första
bygget om den redan var igång när katalogen skapades.

```powershell
docker build -t textlab:v4-review .
python tools/container_checks.py --image textlab:v4-review
```

Imagen innehåller `backend/`, `ai/`, runtimeberoenden och byggd frontend. Den
innehåller inte `.env`, dataset eller experimentmodeller. Runtime använder UID
10001, två workers och `/state` för gemensamma kvoter. Containerprovet skapar en
tillfällig lokal container och tar bort den efter verifiering. En verklig deployment
behöver TLS, hemlighetshantering, loggkontroll och återställningsplan för kvotdata.

## Verifiera en installation

```powershell
npm test
python -m pytest -q
npm run build
npm run performance
python -m playwright install chromium
python tools/browser_checks.py
python sites/src/ui_checks.py
python tools/accessibility_checks.py
python tools/api_performance.py
```

De fyra sista kommandona kräver en startad byggd backend. Webbläsarproven använder
uttryckligen mockade modellresultat; de mäter gränssnittet. En befintlig Chromium
kan väljas med `TEXTLAB_BROWSER_EXECUTABLE` när Playwrights standardbinary saknas.
Det upphäver inga begränsningar i exekveringsmiljön.

Riktiga modellprov är separata och kräver installerad/konfigurerad modell:

```powershell
python tools/live_model_checks.py --models qwen3.5:9b --output artifacts/live-model-results-v4.json
```

Använd nya filnamn för varje modellkörning. Bevara misslyckade resultat.
Se [V4-rapporten](VERIFICATION-V4.md) för vad som faktiskt kördes i leveransen,
[API](API.md) och [arkitekturen](ARCHITECTURE.md) för gränser och dataflöden.
