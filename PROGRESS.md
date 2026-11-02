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

## Evidens och öppna krav

Exakta slutresultat och rårapporter redovisas i `docs/VERIFICATION.md`. Syntetiska benchmarktal används inte som detektionsprecision. Målet 9,5/10 är inte ett förutbestämt resultat; `QUALITY-SCORECARD.md` redovisar kvarstående luckor.

1. Oberoende rättighetsgranskat sv/en-material över författare, genrer, längder och modellfamiljer saknas. Ingen tränad/kalibrerad klassificerare har byggts; precision och mänskliga falska positiva är ej verifierade.
2. Semantisk ekvivalens och konsekvent förbättring i alla sex lägen är inte verifierade. Skyddade strängar kan flyttas så betydelsen ändras; vissa små modellförsök avvisas eller är oförändrade.
3. OpenAI och kompatibel extern modell har mockade protokolltester, men inga riktiga nycklar/behörigheter för liveprov i körningen.
4. Kallstart efter verifierad modellurladdning är inte mätt. Första observerade anrop är inte samma mått. Provider-side avbrott/fakturering kräver separat verifiering.
5. Flera maskiner, publik identitetslivscykel, TLS/proxy, penetrationstest och publik deployment är inte verifierade.
6. Automatiska axe-kontroller kompletterar inte fullständig manuell WCAG-/skärmläsargranskning.

## Nästa rekommenderade arbete

Samla och granska oberoende data innan modellval/träning. Jämför enkla TF-IDF/logistiska baselines med aktuella heuristiker på författar-/dokumentgrupperade splitar; kalibrera enbart på separat validering och prioritera låg mänsklig falskpositiv frekvens. Gör en blindad redaktionell modellutvärdering med faktakorrekthet, språk, ton och förändrade förbehåll innan humanizern får hög kvalitetsklassning. Verifiera därefter en explicit vald driftmiljö.
