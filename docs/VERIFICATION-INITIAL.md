# Slutverifiering — TextLab v3, 2026-11-02

## Omfattning och miljö

Utgångspunkt `origin/main`: `721e3d384aacfb2e5edee2ddece2e6986bc0ee61`. Branch `codex/textlab-v3`. Verifierad kodcommit: `29b4c9061f295953546685339d726127ab3e4c95`. Källan och versionssparade rårapporter finns i denna PR. En separat, färsk checkout användes eftersom Documents-arbetsmappen gav WinError 2 vid filskapande; ingen befintlig användarcheckout ändrades.

Windows 11 build 26300, Intel Core i7-14700K, 20 fysiska kärnor / 28 logiska trådar, 34 134 560 768 byte rapporterat RAM, Node 22.16.0, Python 3.13.15. Lokal GPU: NVIDIA GeForce RTX 5070, 12 227 MiB enligt nvidia-smi, drivrutin 621.01. Docker Desktop Engine 28.1.1 användes för Linux/Python 3.12 och två verkliga workers. Ollama 0.40.13. Modellformat, kvantisering och digest: [model-environment.json](evidence/model-environment.json).

## Automatiska kontroller

| Kontroll | Faktiskt resultat |
|---|---|
| V2-baseline | 16 Node och 30 pytest godkända; frontend byggdes |
| `npm test` | **60 godkända, 0 misslyckade, 0 hoppade över** |
| `python -m pytest -q` | **77 godkända, 0 misslyckade**; 1 upstream TestClient/httpx-deprecationvarning |
| `tools/browser_checks.py` | 10 kontroller godkända, inklusive ingen analys-POST, originalrevisioner, XSS-text, API-fel, minnesbaserad token och mobilvy |
| `sites/src/ui_checks.py` | Godkänd separat svit: sex lägen, språk/termer, tangentbord, diff, clipboard, export, använd/återställ, avbrott, felaktig rewrite/health/status-metadata, dialogfokus och 320 px |
| `tools/accessibility_checks.py` | **0 axe-överträdelser i 11 vyer**, inklusive resultatpaneler och inställningar; [rårapport](evidence/accessibility.json) |
| Produktionsbygge | Lyckades; två nya byggen gav identiska SHA-256 för alla 3 filer; [manifest](evidence/build-sha256.json) |
| Runtime-/devberoenden | `pip-audit` hittade inga kända sårbarheter i låsta runtime- eller devgrafer vid körningen |
| Frontendberoenden | `npm audit --audit-level=moderate`: 0 kända sårbarheter |
| Hemligheter | Gitleaks 8.30.1 med verifierad binärchecksumma; historia och staged diff skannas före commit; inga fynd vid redovisad kontroll |
| Diff | `git diff --check` utan whitespacefel |
| Container | Dockerbygge godkänt; nonroot UID 10001, två workers, frontend/headers, auth401 samt delad rate: **2 accepterade, 10 avvisade**; [rårapport](evidence/container-results.json) |

Browser-/API-mockar verifierar protokoll, felhantering och användarflöden. De är inga bevis för språkmodellskvalitet. Axe är automatiserad och lämnar manuella kontrollpunkter; skärmläsar-/fullständig WCAG-granskning har inte genomförts.

## Verkliga modelltester — separat från godkända tekniska sviter

Det sista fullständiga provet använde syntetiska svenska/engelska original, samtliga sex lägen och två redan installerade modeller. **24 omskrivningar genomfördes; 23 accepterades och 1 avvisades.** Den skärpta checken avslutades korrekt med **exit 1** och `passed:false`. Den ska inte beskrivas som helt godkänd.

| Modell | Verifierad probe | Omskrivningar HTTP200 | Skyddskontroller | Oförändrade svar | Omskrivningslatens |
|---|---|---:|---|---:|---|
| `llama3.2:3b` | Ja | 12/12 | Alla 12 bevarade kontrollerade fixturevärden | 0 | 0,910–1,172 s |
| `qwen3.5:4b` | Ja | 11/12 | Alla 11 accepterade svar bevarade fixturevärden | 3 | 1,716–2,128 s för accepterade svar |

Qwen `sv/detailed` ändrade skyddade uppgifter och stoppades med HTTP502. Originalet förblev tillgängligt. En tidigare körning av samma funktionella backend hade ett avvisat llama `en/simple`-fall i stället; stokastisk stabilitet är inte verifierad. Båda körningarna finns sparade: [sista gated-provet](evidence/live-model-results.json), [föregående prov](evidence/live-model-results-prior.json). Välj inte bara lyckade körningar som kvalitetsbevis.

Första observerade prober: llama 0,932 s och Qwen 0,890 s. Modellerna var inte verifierat urladdade, så detta är **inte kallstartsmätningar**. `OLLAMA_THINK=false` användes i slutproven. Tidigare Qwen-försök med tänkande översteg den lilla probens outputbudget; detta motiverade en uttrycklig serverinställning, inte en falsk redo-status.

Exakta namn, siffror, datum, URL:er, citat och referenser kontrollerades i syntetiska fixtures. Automatiska strängkontroller bevisar inte korrekta relationer, betydelse eller ton. Ett tidigare diagnostiskt llama-prov flyttade ett datum från rapportens skrivtid till dess ämne trots bevarad datumsträng. I sista rårapporten finns också språkligt svaga formuleringar, exempelvis Qwen `en/simple`: "without making sure conclusions about why they happened". Inga blindade kvalitetsbetyg eller verifierad semantisk ekvivalens påstås. Lägen har olika promptinstruktioner men konsekvent förbättring är inte fastställd; tre sista Qwen-svar var oförändrade.

Standardmodellen `qwen2.5:7b` var inte installerad och rapporterades korrekt som otillgänglig. OpenAI/extern kompatibel modell testades med HTTP-mockar; riktiga nycklar saknades. Ingen användar-.env ändrades och inga modeller laddades ned eller avinstallerades.

## Detektor och benchmark

Metod: `style-heuristics-v3`, beskrivande stilmått med konservativt avstående. Ingen tränad klassificerare används. Ingen kalibrerad AI-sannolikhet finns. Ingen oberoende rättighetsgranskad sv/en-korpus fanns att träna eller mäta generalisering på.

**Accuracy, precision, recall, F1, mänskliga falska positiva, FNR och kalibrering för verklig detektionskvalitet: ej verifierade.** Antalet oberoende mänskliga testtexter är noll; en uppmätt mänsklig FPR kan därför inte anges.

Benchmarkverktyget beräknar diagnostiska tröskelmetrik, AUROC när båda klasser finns, Wilsonintervall med beroendevarning, coverage och avstående. AI-redigerat hålls utanför binär ground truth. Proveniens-/rättighetsfält, författare/dokument/källfamilj, relaterade källor och exakt-/närduplicering kontrolleras. Externa etiketter/rättigheter måste fortfarande granskas av en människa.

`detector.synthetic.jsonl` innehåller 14 tydligt märkta tekniska fixtures: train2/validation4/test8; av test8 får6 ett stilindex och2 avstår. Dessa är **inte oberoende kvalitetsevidens**, och deras artificiella etiketter ger inga accuracy-påståenden. Både fast tröskel och valideringsbaserat tröskelval kördes reproducerbart; CLI-hasharna regressionstestas. [Metod, schema och begränsningar](DETECTOR_BENCHMARK.md).

## Prestanda

Nedan gäller den angivna stationära datorn. Analysen mättes efter 10 uppvärmningsanrop, 100 gånger per språk/längd. Ingen generell mobil- eller produktionslatens hävdas.

JS: **82,847 byte gzip**, CSS: **5,028 byte gzip** (gränser 100 000 / 10 000). Båda passerade.

| Språk | Tecken | p50 ms | p95 ms |
|---|---:|---:|---:|
| sv | 1000 | 0.66 | 1.11 |
| sv | 6000 | 2.91 | 3.81 |
| sv | 12000 | 5.76 | 7.26 |
| en | 1000 | 0.49 | 0.74 |
| en | 6000 | 3.08 | 3.81 |
| en | 12000 | 6.30 | 7.50 |

Verklig lokal HTTP: 40 samtidiga health-anrop gav40 HTTP200, p95 **110.44 ms**. Åtta samtidiga för långa omskrivningar gav8 HTTP422. ASGI med explicit 10ms mockmodell: 20 omskrivningar om8 000tecken, p95 **30.97 ms**; åtta samtidiga gav2 accepterade och6 HTTP429. Detta mäter integrationskostnad, inte verklig inferens.

RSS är rapporterad för hela benchmarkprocessen före/efter och inkluderar Python/Node, framework och GC. Det är inte isolerad per-request-allokering eller en verifierad peak-minnesgräns. Se [analys/bundle](evidence/performance.json) och [API/minne](evidence/api-performance.json). Modellkallstart, verklig global produktionslast och lågpresterande mobiler är inte mätta.

## Granskning och leveransgränser

En separat agent granskade diffen och verifierade auth-/SQLite-/avbrotts-/benchmarkgränser. Den fann ett viktigt metadatafel som kunde krascha React. Felen reproducerades med röda unit- och browsertester, därefter valideras alla renderade rewrite/health/status-fält innan state uppdateras; originalet behålls. Två mindre fynd åtgärdades: livecheck ger nu exit1 vid fel och devberoendens transitive versioner är låsta. Containerkontrollen fångade även saknad CSP; regression observerades misslyckas före fix, följt av full grön pytest och browserkontroll.

CI är ändrat till contents:read, explicita pipefail-kommandon, SHA-pinnade actions, låsta beroenden, audits, checksummeverifierad Gitleaks, tester/fixture/buildjämförelse, browser/axe/performance och två-worker-container. Workflow-artefakten ersätter gamla v2-buildfiler och ingen bot skriver till main. GitHub Actions-slutstatus måste läsas från det faktiska PR-huvudet; lokal framgång ersätter inte CI-evidens.

Ingen publik URL, ChatGPT Site eller molndeployment finns för denna leverans. Produktionsberedskap och samtliga kvalitetsmål är inte verifierade till9,5/10. [Scorecard](../QUALITY-SCORECARD.md) anger lägre bedömningar och kvarstående evidensgap; [driftdokumentet](OPERATIONS.md) beskriver bland annat en-värdsgränsen, tokenlivscykel, TLS och leverantörsrisker.
