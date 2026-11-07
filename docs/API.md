# TextLab V4 API

Basadress lokalt: `http://127.0.0.1:8767`. Alla begäranden och svar använder UTF-8. Teckengränser räknas i UTF-16-enheter, som JavaScript-strängar; en emoji utanför BMP använder två enheter.
Utvecklingsläget visar OpenAPI på `/api/docs`; produktionsläget stänger dessa sidor.

## Åtkomst och gemensamma gränser

`/api/rewrite`, `/api/provider-status` och `/api/detect` kräver autentisering vid
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
| `POST /api/detect` | Beskrivande stilanalys, osäkerhet och evidens | Nej |
| `POST /api/rewrite` | Skyddad textredigering | Ja, med giltig konfiguration |

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
{"text":"En svensk text att undersöka.","language":"sv"}
```

`text`: 1–12 000 tecken. `language`: `sv` eller `en`. Okända JSON-fält avvisas.
Svaret använder samma beskrivande kontrakt som webbläsaranalysen: `method`,
`status`, `styleIndex`, ord-/tecken-/meningsantal, `signals`, `evidence`,
`features`, `languageAssessment`, `abstentionReasons`, `uncertainty`,
`limitations` och `authorship: "undetermined"`.

Färre än 80 ord, färre än fyra meningar eller otillräckligt språkstöd ger
`styleIndex: null`. Ett numeriskt stilindex är aldrig AI-sannolikhet.
Produktionskontraktet har ingen aktiverad ML-författarskapsklassificering.
Evidenspositioner anges som halvöppna UTF-16-intervall för JavaScript-klienter.

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
