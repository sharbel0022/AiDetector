# TextLab V5 API

Basadress lokalt: `http://127.0.0.1:8767`. Alla begäranden och svar använder UTF-8. Teckengränser räknas i UTF-16-enheter, som JavaScript-strängar; en emoji utanför BMP använder två enheter.
Utvecklingsläget visar OpenAPI på `/api/docs`; produktionsläget stänger dessa sidor.

## Åtkomst och gemensamma gränser

`/api/rewrite`, `/api/provider-status`, `/api/detect` och `/api/usage` kräver autentisering vid
extern åtkomst. Använd `Authorization: Bearer TEXTLAB_ATKOMSTKOD`.
Ange aldrig OpenAI-nyckeln i webbläsaren. Origin måste ingå i `ALLOWED_ORIGINS`.
Utan konfigurerad token tillåts endast lokal utvecklingsåtkomst från loopback.

Standarder: 20 skyddade anrop/minut/användare, högst två samtidiga modellgenereringar,
100 000 bodybyte, 200 000 bytes modellsvar, 120 sekunders modelltimeout.
Alla servervalda begränsningar kontrolleras även om klienten kringgår UI.
Modell/leverantör/URL kan inte väljas i en begäran.

| Metod och sökväg | Funktion | Modellanrop |
|---|---|---|
| `GET /api/health` | Process, version, konfiguration och textgräns | Nej |
| `GET /api/provider-status` | Cachad, begränsad genereringsprobe | Kan ske |
| `POST /api/detect` | Lokal backendinferens, segment, evidenskrav och stilanalys | Ingen generativ leverantör |
| `POST /api/rewrite` | Skyddad textredigering | Ja, med giltig konfiguration |
| `GET /api/usage` | Den autentiserade användarens aggregerade förbrukning | Nej |

## Health och modellstatus

Health returnerar `status`, `version`, `provider`, `model`, `auth_required`,
`auth_mode`, `model_verified: false`, `text_storage: false`, `max_input_chars`
och `provider_configured`. Konfigurerad är inte samma sak som verifierad.

Providerstatus returnerar `provider`, `model`, `configured`, `ready`, `verified`
och ett begränsat `message`. Statusproben använder högst 128 outputtoken och
15 sekunder, eller kortare konfigurerad timeout. Resultat cachas per worker:
60 sekunder vid framgång, 5 sekunder vid fel. Auth och rategräns gäller också vid
cacheträff. `ready: true` betyder ett giltigt syntetiskt testsvar.

Vid saknad OpenAI-konfiguration startar backend och status förklarar:

> OpenAI är inte konfigurerat. Lägg till OPENAI_API_KEY och OPENAI_MODEL i serverns .env.

Inga verkliga provideranrop sker innan erforderlig konfiguration finns.

## Detektor

```json
{"text":"En svensk text att undersöka.","language":"auto"}
```

`text`: 1–12 000 UTF-16-enheter. `language`: `auto` (standard), `sv` eller `en`.
Okända JSON-fält avvisas. Modellfil, trösklar och valideringsstatus kan inte
skickas av klienten. Automatiken är en konservativ språkregel med möjlighet
att avstå; dess styrka är inte en statistiskt kalibrerad språksannolikhet.

Svaret behåller det beskrivande V4-kontraktet: `method`,
`status`, `styleIndex`, ord-/tecken-/meningsantal, `signals`, `evidence`,
`features`, `languageAssessment`, `abstentionReasons`, `uncertainty`,
`limitations` och `authorship: "undetermined"`.

Färre än 80 ord, färre än fyra meningar eller otillräckligt språkstöd ger
`styleIndex: null`. Ett numeriskt stilindex är aldrig AI-sannolikhet.
Dessutom returneras `detector` och `segments`. Stilindex påverkar aldrig de
publicerade ML-sannolikheterna eller segmentetiketterna.

| `detector`-fält | Betydelse |
|---|---|
| `version`, `modelVersion` | API-metod och laddad modellversion |
| `status` | `model_unavailable`, `abstained`, `unverified` eller `available` |
| `category` | `ai_like`, `human_like`, `mixed`, `uncertain` eller `insufficient` |
| `documentProbability` | AI-klassens kalibrerade sannolikhet i intervallet 0–1, annars null |
| `aiMarkedPercent` | Andel ord i AI-markerade analyserbara segment, 0–100, annars null |
| `documentValidated` | Dokumentets beslutsmetod har klarat evidenskraven |
| `calibrationValidated` | Dokumentets kalibrering har separat stöd |
| `segmentValidated` | Segmentens beslutsmetod har separat stöd |
| `segmentCalibrationValidated` | Segmentens sannolikheter har separat kalibreringsstöd |
| `analyzedWords`, `excludedWords`, `flaggedWords` | Ord som kan analyseras, exkluderas respektive flaggas |
| `totalSegments`, `flaggedSegments` | Segmentantal och antal AI-markerade segment |
| `reasons`, `gates`, `calibrationStatus`, `scoreSemantics` | Förklaringar, evidenskrav och måttens tolkning |

Dokumentsannolikhet kräver både giltig dokumentvalidering och kalibrering.
Textandel kräver giltig segmentvalidering. Segmentens egna sannolikheter kräver
dessutom separat segmentkalibrering. Noll flaggningar med stängd validering
betyder inte 0 % AI. **Den medföljande piloten ger null för båda procentmåtten.**

Varje segment har `id`, `start`, `end`, `text`, `wordCount`, `category`,
`probability`, `reason` och `eligible`. Intervallen är halvöppna, icke
överlappande UTF-16-positioner i exakt originaltext. `eligible` beskriver
analyserbarhet, inte verifierad klassificering. Kategorier är `ai_like`,
`human_like`, `uncertain` och `unassessed`. Mellanrum mellan segment bevaras.
Förklaringar återger beslutsgräns eller avståendeskäl; de bevisar inte författarskap.

Ord räknas med projektets gemensamma Unicode-regel, en gång per icke överlappande
segment. `aiMarkedPercent = 100 × flaggedWords / analyzedWords`. Om nämnaren
är noll blir resultatet null. Hela dokumentets ordantal inkluderar även de
exkluderade orden. `mixed` kräver både AI-liknande och mänskligt-liknande lokala
segment med validerad segmentmetod. En ensam dokumentpoäng räcker inte.

`languageAssessment` redovisar begärt, valt och faktiskt bedömt språk, metod och
eventuell konflikt med manuellt val. Detaljer om modellformat, gränser,
kalibrering och aktiveringskrav finns i [DETECTOR_V5.md](DETECTOR_V5.md).

## Humanizer

```json
{
  "text":"Åsa Öberg betalade 125 kr. Vi har sparat originalet.",
  "language":"sv",
  "tone":"professional",
  "protected_terms":["Åsa Öberg"]
}
```

`text`: 10–8 000 tecken, med en eventuell lägre servergräns från health.
`tone`: `natural`, `simple`, `professional`, `academic`, `concise`, `detailed`.
`protected_terms`: högst 40 unika, icke-tomma textdelar om högst 160 tecken som
måste förekomma exakt i originalet. `__TL_` är reserverat för interna markörer.

Svaret innehåller:

| Fält | Betydelse |
|---|---|
| `text` | Validerad text, högst 16 000 tecken |
| `provider`, `model` | Serverns använda konfiguration |
| `diff` | Ordnade `{kind,text}` där kind är equal/insert/delete |
| `protected_count` | Antal skyddade markörer |
| `unchanged`, `explanation` | Om originalet behållits och vad resultatet betyder |
| `review_required` | Alltid true |
| `preservation.exact_values_checked` | Exakta kontroller kördes |
| `preservation.semantic_equivalence_verified` | Alltid false |
| `warning` | Förklarar begränsningar och granskningsbehov |
| `usage` | Leverantörens användningsmetadata, eller null för en äldre injicerad adapter |

### Faktisk användning och kostnadsuppskattning

`usage` innehåller `provider`, det returnerade `model`-ID:t, `recorded_at` i UTC,
`latency_ms`, `input_tokens`, `output_tokens`, `total_tokens`,
`cached_input_tokens`, `total_tokens_source` och `cost`. Saknade eller ogiltiga
räknare är null. Textlängd används inte som om den vore uppmätta token.

`total_tokens_source` är `provider`, `derived_from_provider` eller `unknown`.
Det härledda värdet är summan av två faktiska delräknare. Ett returnerat totalvärde
som motsäger delräknarna behandlas som okänt. Ollamas lokala tokenräknare stöds;
ingen kostnad för lokal el/hårdvara konstrueras.

`cost` har `currency: "USD"`, `estimated_amount`, `pricing_version` och
`status: "estimated" | "unknown" | "not_applicable"`. En känd uppskattning har
även `source` och `verified_at`. Exakta modell-ID:n och priser finns i
[model-prices.json](../config/model-prices.json). Uppskattningen gäller den
dokumenterade texttjänstenivån och inkluderar inte skatt, krediter eller
avtalade priser. Okänd modell, saknade nödvändiga usage-fält eller annan
tjänstenivå ger null i stället för en gissning.

## Aggregerad förbrukning

`GET /api/usage` använder endast anropets autentiserade identitet. Endpointen
tar inget användar-ID och ger inga andra användares totalsummor eller
global budget. Statistik gäller innevarande UTC-dygn.

| Fält | Innehåll |
|---|---|
| `period` | UTC-start, slut och tidszon |
| `requests` | Antal bokförda modellreservationer, inklusive prober och fel |
| Tokenfält | Summa rapporterade räknare; null när inga av befintliga anrop rapporterat värdet |
| `unreported_counters` | Antal saknade värden per räknare; en delsumma är inte hela förbrukningen |
| `estimated_cost` | Känd USD-delsumma och antal anrop med okänd/ej tillämplig kostnad |
| `reservations` | Kvarstående budgetbelastning, väntande och orapporterade anrop |
| `budget` | Egna konfigurerade gränser, belastning, återstående belopp och redovisningsmetod |
| `outcomes` | Applikationsutfall: accepted/rejected/probe/not_evaluated |
| `models` | Provider, faktiskt respektive begärt modell-ID och anropsantal |
| `retention_days`, `text_storage` | 31 dygns metadatapolicy, ingen användartext |
| `legacy_usage_unavailable` | Äldre kvotbelastning saknar rekonstruerbar faktisk usage; även övriga totalsummor är då ofullständiga |

Modellens svar kan kosta även om texten sedan stoppas av bevarandekontroller.
Providerutfall och applikationsutfall bokförs därför separat. Fullständiga
providerdata stämmer av reservationen atomiskt. Saknad usage, timeout, avbrott
eller processkrasch återbetalar inte en okänd förbrukning. Upprepade avstämningar
får inte dubblera debiteringen. Den verkliga leverantörsfakturan är separat.

`reservations.legacy_reserved_tokens` bevarar kvoter från en äldre databas utan
att kalla dem faktiska token. Om en USD-gräns aktiveras efter tidigare okänd
kostnad eller äldre kvotbelastning kan dagens kostnad inte verifieras; nya
anrop stoppas då till nästa UTC-dygn. USD-gränser kräver en beständig databas.

## Fel

Fel returneras som `{"detail":"begränsat felmeddelande"}` utan källtext,
leverantörens råfel eller hemligheter. `401` gäller saknad/felaktig TextLab-kod,
`403` otillåten extern åtkomst/origin, `408` bodytimeout, `413` för stor body,
`422` felaktig inmatning, `429` kvot/samtidighet/rategräns, `502` ogiltigt
modellsvar eller stoppad bevarandekontroll, `503` saknad konfiguration eller
otillgänglig tjänst och `504` modelltimeout. Avbruten klient kan ge `499`.

HTTP-fel från modellen översätts till begränsade, åtgärdbara meddelanden.
Ingen automatisk alternativ omskrivning eller annan modell ersätter ett fel.
Källtexten ligger kvar hos klienten. `Retry-After` följer kvotfel där väntetid kan
anges; en upprepad begäran kan skapa ny faktisk leverantörskostnad.
