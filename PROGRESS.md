# TextLab v3 — genomförande

Utgångspunkt: `origin/main` vid `721e3d384aacfb2e5edee2ddece2e6986bc0ee61`. Arbetsbranch: `codex/textlab-v3`. Senast uppdaterad 2026-11-02.

## Genomfört

- Granskat befintlig kod, tester, dokumentation och CI; verifierat v2-baseline (16 Node, 30 pytest, lyckat bygge).
- Behållit React/Vite/FastAPI och lokal analys. Utökat beskrivande signaler, språk-/strukturavstående, exakta evidensintervall och osäkerhetsinformation.
- Byggt benchmark med proveniens/rättigheter, grouped splits, exakt-/närdupliceringskontroll, validation-only tröskelval, mätetal med korrekta nämnare och separat AI-redigerad grupp.
- Sex modellstyrda redigeringslägen, strikt kompatibel adapter, riktiga readiness-prober, fler skyddade värden och användarvalda exakta termer.
- Delad atomisk SQLite-kvot/samtidighet/budget för en värds workers, separata användartoken, tidiga authkontroller, tids-/body-/svarsgränser, säker felhantering och klientavbrott.
- Tydligare original/resultat/återställning, diff/kopia/export, språkval, exakta markeringar, bättre kontrast, fokus och smala skärmar.
- CI med läsrättighet, låsta installationer, SHA-pinnade actions, audits/hemlighetsskanning, reproducerbara byggen, browser/axe/prestanda/containerkontroller och artefakter. Inga automatcommits till main.
- Kört riktiga lokala Ollama-försök och skiljt teknisk integration från språklig kvalitet. En observerad betydelseförskjutning finns dokumenterad.
- Oberoende kodgranskning fann UI-krasch vid felaktig API-metadata; regression och korrigering ingår i slutverifieringen.
- Samlat en historisk, källspårbar sv/en-pilot med 36 mänskliga utdrag och 24 verkliga modellgenereringar. Tränat och fryst en separat experimentell TF-IDF/logistisk baslinje; den moderna kontrollen avslöjade 2/8 felaktiga mänskliga flaggningar.
- Rättat granskningsfynd om återanvänd tröskelvalidering som test, om cachade loggars modellidentitet, om prefixbedömning av enheter och om överskrivning av fryst evidens. Vikter/tröskel/testutfall och ursprungliga rapporter är bevarade.
- Slutfört 48 slutliga jämförelseanrop, 24 anrop med större modell och 6 teckenprov; lagt till atomiska enheter, tecken-/suffixkontroller, begränsade betydelsemarkörer och korrekt serialiserad kvotreservation. Begränsad kontrollpassning är inte semantisk precision.

## Evidens och öppna krav

Exakta slutresultat och rårapporter redovisas i `docs/VERIFICATION.md`. Syntetiska benchmarktal används inte som detektionsprecision. Målet 9,5/10 är inte ett förutbestämt resultat; `QUALITY-SCORECARD.md` redovisar kvarstående luckor.

1. En liten historisk pilot och en modern för-LLM-kontroll finns nu med källor/villkor/proveniensluckor. En tränad offlinebaslinje finns, men bred modern matchad data, låg populations-FPR och separat kalibrering saknas. Den är inte aktiv i produkten.
2. Semantisk ekvivalens och konsekvent förbättring i alla sex lägen är inte verifierade. Skyddade strängar kan flyttas så betydelsen ändras; vissa små modellförsök avvisas eller är oförändrade.
3. OpenAI och kompatibel extern modell har mockade protokolltester, men inga riktiga nycklar/behörigheter för liveprov i körningen.
4. Kallstart efter verifierad modellurladdning är inte mätt. Första observerade anrop är inte samma mått. Provider-side avbrott/fakturering kräver separat verifiering.
5. Flera maskiner, publik identitetslivscykel, TLS/proxy, penetrationstest och publik deployment är inte verifierade.
6. Automatiska axe-kontroller kompletterar inte fullständig manuell WCAG-/skärmläsargranskning.

## Nästa rekommenderade arbete

Bygg en större modern, rättighets-/författargranskad korpus med matchade ämnen/genrer/längder och en ny fryst extern audit. Behåll de rapporterade 2/8 moderna felen synliga; justera inte modellen på samma kontroll och kalla den sedan oberoende test. Kalibrering kräver separat data. Gör en blindad redaktionell modellutvärdering med faktakorrekthet, språk, ton och förändrade förbehåll innan humanizern får hög kvalitetsklassning. Verifiera därefter en explicit vald driftmiljö.

## GitHub-leverans

[Pull Request #1](https://github.com/sharbel0022/AiDetector/pull/1) är öppen mot `main`; ingen merge är genomförd. Kodcommit `29b4c90` följs av verifieringsdokumentation och denna leveransnotering. `main` var oförändrad vid fetch, `721e3d384aacfb2e5edee2ddece2e6986bc0ee61`. Arbetskopian är bevarad. Läs aktuell [GitHub Actions-status](https://github.com/sharbel0022/AiDetector/actions) för PR-huvudet; slutstatus ersätts inte av lokal verifiering.
