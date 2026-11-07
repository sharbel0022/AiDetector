# Inventering inför V4

GitHub kontrollerades på nytt 2026-11-07 innan V4-kandidaten publicerades.

| Referens | Ursprunglig commit | Status och bevarande |
|---|---|---|
| `main` | `721e3d384aacfb2e5edee2ddece2e6986bc0ee61` | Förfader till V3; hela historiken följer med |
| `codex/textlab-v3` | `5c6328d7c341411042c7d2db150cb88578998302` | Fem nya commits över main; V4 bygger direkt på detta head |
| PR #1 | `codex/textlab-v3` → `main` | Öppen vid inventering; dess kod och alla commits ingår i V4 |

Inga andra fjärrbrancher eller taggar fanns vid inventeringen. Båda brancherna
rapporterades oskyddade och repository-rulesets var tomma. Detta är en
ögonblicksbild; refs och skyddsstatus ska kontrolleras igen före release.

V3:s senaste PR-körning var
[41522809070](https://github.com/sharbel0022/AiDetector/actions/runs/41522809070),
och push-körning
[41522797218](https://github.com/sharbel0022/AiDetector/actions/runs/41522797218)
var också grön. Dessa räknas inte som V4-verifiering.

## Säkrat innehåll

De fem V3-commitsen innehåller frontend, lokal stilanalys, skyddad modellredigering,
autentisering, delad SQLite-kvotkontroll, verifiering och dokumentation, följt av
auditerade offlineexperiment och sparade modell-/datakvalitetsresultat. Inget
av detta förkastas med en squash eller genom att ersätta Git-historiken.

Alla befintliga `data/`- och `models/`-artefakter bevaras. En saknad källsnapshot
för den historiska betydelsevalidatorn har lagts till från V3-commiten, med sitt
ursprungliga SHA-256 i filnamnet. Historiska rapporters källhashar jämförs med
deras oförändrade snapshots; de får inte omtolkas som nya körningar av V4.

PR #1:s rapporterade överlappningsfel för exempelvis `Alice Smith` och det
uttryckligen skyddade `Smith works` har reproducerats och reparerats. Automatiska
och uttryckliga intervall samlas nu separat och sammanfogas före maskering.

## Migrering

- Ingen databas- eller dataschemamigrering krävs. Befintlig lokal SQLite-
  kvotdatabas och per-användaridentiteter behålls.
- API-kompatibla V3-fält behålls; V4 lägger till `unchanged`, `explanation`,
  `max_input_chars`, `provider_configured` och `/api/detect`.
- Backendhjälpare som används av äldre verktyg har explicita kompatibilitets-
  exporter; implementationen finns på ett ställe i `ai/`.
- Gamla `AI_MODEL`, `TEXTLAB_REQUEST_TIMEOUT` och `TEXTLAB_ENV` stöds enligt
  dokumenterad prioritet. Motstridiga miljöalias stoppar uppstarten.
- Docker måste byggas om eftersom runtime nu även innehåller `ai/`.

Release och radering sker först när kandidatens nya CI är godkänd och varje
fjärrbranch som raderas har verifierats vara en förfader till `main`.
