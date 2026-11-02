# Arkitektur, säkerhet och drift

## Flöden och lagring

React/Vite bygger en statisk frontend. Stilanalys körs synkront i webbläsaren och skickar ingen text till backend. Humanizern skickar original, språk, ton och eventuella exakta textdelar till FastAPI. Backend ersätter identifierade skyddsvärden med slumpmässiga markörer, anropar den serverkonfigurerade modellen, kontrollerar svar och återställer värden. Ingen alternativ regelbaserad omskrivning används vid modellfel.

`backend/main.py` ansvarar för validering, adaptrar och HTTP. `backend/limits.py` hanterar atomiska kvoter med SQLite-transaktioner. `sites/src/ui-state.mjs` validerar svar, diffar, evidensintervall och revisioner innan UI uppdateras. Detektorns metod och benchmarkgränser finns i `DETECTOR_BENCHMARK.md`.

Text och modellsvar sparas inte av applikationen. Åtkomsttoken finns endast i webbläsarminnet. SQLite lagrar hashade kvotidentiteter, förbrukningsreservationer, tidsstämplar och tillfälliga anropslås. Gamla poster rensas när nya kvotoperationer körs; det är inte en timerbaserad raderingsgaranti. Undvik request-/response-body-loggning, APM-inspelning och proxyloggning av Authorization.

## Privat och publik åtkomst

Privat läge: `TEXTLAB_AUTH_MODE=private`, lång slumpmässig `TEXTLAB_TOKEN`. Utan token tillåts skyddade anrop bara från loopback i utvecklingsläge. Produktionskonfiguration kräver autentisering och explicita hosts/origins. Behåll `--no-proxy-headers`; lita endast på en uttryckligen betrodd proxy om proxyheaders senare aktiveras.

Fleranvändarläge: `TEXTLAB_AUTH_MODE=multiuser` och `TEXTLAB_USER_TOKENS` som JSON-objekt med stabila användar-ID:n och SHA-256-hex av separata slumpmässiga bearer-token på minst 32 tecken. Distribuera råa token genom en säker kanal. Ta bort/rotera en användares hash och starta om alla processer för återkallelse. Det finns ingen självregistrering, OAuth, administratörsvy eller automatisk tokenrotation. Hashkonfigurationen kan inte bevisa att den ursprungliga token var slumpmässig; operatören ansvarar för det.

`TEXTLAB_STATE_DB` måste vara en absolut sökväg till samma SQLite-fil för alla workers på **en maskin**, på lokal disk med filrättigheter för servicekontot. Lägg aldrig filen i `dist/`, versionshantering eller en nätverksdisk. Både rate, daglig budget och samtidighet delas atomiskt mellan processer; lagringsfel avvisar anrop. Starta inte flera värdar med varsin fil: använd central autentisering och kvoter vid en extern gateway och en uttryckligen verifierad arkitektur för sådan drift.

Skydda tjänsten med HTTPS. Ange backendens värd i `ALLOWED_HOSTS` och exakt frontend-origin i `ALLOWED_ORIGINS` (inga paths, credentials eller wildcards). Samma origin och standardport minskar konfigurationsytan. HTTP tillåts bara på loopback. CORS är inte autentisering.

## Resurs- och kostnadsgränser

- Stilanalys: högst 12 000 JavaScript-tecken; omskrivning: 10–8 000 tecken.
- HTTP-body: 100 000 faktiska byte, även chunkade anrop; body-deadline 10 sekunder. Modellsvar: högst 200 000 byte och 16 000 texttecken. Skyddad prompt är separat begränsad.
- `TEXTLAB_REQUESTS_PER_MINUTE` omfattar autentiserade skyddade anrop, även statuskontroll. Okända token får ingen egen obegränsad kvotidentitet.
- `TEXTLAB_MAX_CONCURRENT` begränsar samtidiga modellförfrågningar från alla app-workers. Lås har deadline för återhämtning efter processkrasch. AI-leverantören kan fortsätta intern inferens efter HTTP-avbrott; konfigurera även dess kö och samtidighet.
- `TEXTLAB_DAILY_TOKEN_BUDGET` och `TEXTLAB_GLOBAL_DAILY_TOKEN_BUDGET` reserverar konservativt JSON-/UTF-8-input, promptmarginal och maxoutput före anrop. Misslyckade/avbrutna anrop återbetalas inte. UTC-dygn används. Detta är inga garantier om valuta eller leverantörsfakturering; sätt också leverantörens spending limits.
- `TEXTLAB_REQUEST_TIMEOUT` och `TEXTLAB_MAX_OUTPUT_TOKENS` är konfigurerbara. Deadline och klientavbrott avbryter HTTP-operationen och frigör applåset; provider-side fakturering/compute är separat.

`/api/health` är publik, liten och innehåller ingen text eller nyckel. `/api/provider-status` kräver samma auth/kvoter som omskrivning och provar faktisk syntetisk generering. Proben använder max 128 outputtoken och 15 sekunder, med begränsad workerlokal cache. Ett negativt svar kan betyda att en modell är långsam eller saknar kompatibelt format. `ready:true` intygar inte allmän modellkvalitet. En lyckad probe kan bli inaktuell om modellen senare stängs av.

## Modell- och betydelserisk

Ollama och kompatibel endpoint är serverkonfiguration, aldrig användarstyrda URL:er i API-payload. HTTP till externa modellvärdar och redirects är förbjudna. OpenAI använder Responses API och `store:false`; andra leverantörers retention måste granskas separat. Kompatibla modeller måste stödja schemaformatet. `OLLAMA_THINK=false` är standard för avgränsad textredigering; `true`/`default` är operatörsval som kräver egna modelltester.

Namnskyddet är heuristiskt, med konservativa kandidater och undantag för vanliga meningsinledningar. Det täcker inte alla namn, språk eller stavningar; välj exakta termer för särskilt viktiga värden. Maskering kan göra små modeller sämre. Felaktiga markörer stoppas och lämnar originalet orört.

Prompt injection begränsas genom separat systeminstruktion, JSON-fält för otillförlitlig text, inget verktygs-/fil-/nätverksanrop från modellen och validerade utdata. Det gör inte språkmodellen immun mot instruktioner i texten. Den får inga serverhemligheter. Backend hindrar inte varje ny sakuppgift eller ändrad logisk relation. Riktiga tester visade att en exakt bevarad datumsträng kan få ny grammatisk roll. Ingen semantisk ekvivalensmodell eller formell faktakontroll har validerats; mänsklig granskning krävs.

## Container och verifiering

`Dockerfile` bygger frontend från `package-lock.json`, installerar runtime från `requirements-lock.txt` och kör Python 3.12 som UID 10001. Miljön är production, två workers, delad `/state`-volym, ingen åtkomstlogg och inga proxyheaders. Tillför env-konfiguration vid start; lägg aldrig hemligheter i image eller Git. Rootless runtime är inte en fullständig containerhärdning: använd read-only appfilesystem, resursgränser, begränsad egress och betrodd reverse proxy i verklig drift.

```powershell
docker build -t textlab:v3-review .
python tools/container_checks.py --image textlab:v3-review
```

Kontrollverktyget skapar och tar bort en egen loopback-bunden testcontainer, utan publik URL, med en slumpmässig tillfällig användartoken. Det kontrollerar två workers, nonroot, frontend/headers, auth och gemensam rategräns. Ingen modell hämtas eller exponeras. Se `VERIFICATION.md` för verkligt körresultat.

Kör `npm ci` och `python -m pip install -r requirements-dev.txt` för låst verifieringsmiljö. `requirements-lock.txt` låser runtime inklusive befintliga pytest-beroenden; `requirements-dev-lock.txt` låser den verifierade testverktygsgrafen. Uppdatera lås genom kontrollerad dependency resolution, testa på Windows/Linux och kör audits igen. Containerbasernas taggar ska uppdateras och images säkerhetsskannas inför faktisk release; nuvarande basdigester redovisas endast när ett imagebygge faktiskt körts.

## Kvar före publik release

Verifiera vald modell med oberoende redaktionell bedömning, granska TLS/proxy/egress/loggar, besluta tokenlivscykel och personuppgiftsvillkor, sätt verkliga kontokostnadsgränser, verifiera backup/återställning av kvotfil och larm. Kör säkerhetsgranskning och manuell tangentbords-/skärmläsargranskning. En publik tjänst kräver en faktisk URL och deploymentbevis; sådana bevis finns inte i denna leverans.

Referenser: [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [Ollama thinking](https://docs.ollama.com/capabilities/thinking), [GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use), [Playwright assertions](https://playwright.dev/python/docs/test-assertions).
