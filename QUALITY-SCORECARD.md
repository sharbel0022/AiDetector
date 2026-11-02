# Kvalitetsbedömning — TextLab v3

Målet är 9,5/10 per område. Det målet är **inte uppnått eller förutsatt**. Betygen nedan är interna tekniska bedömningar av leveransen, inte statistiskt uppmätta produktbetyg. De bygger på redovisad evidens och sänks vid bristande oberoende verifiering. Exakta körresultat finns i [VERIFICATION](docs/VERIFICATION.md).

| Område | Bedömning | Evidens | Återstår till 9,5 |
|---|---:|---|---|
| Arkitektur | 8,5/10 | Lokal analys, separat serveradapter, delad atomisk kvotmodul, validerad UI-gräns, två-worker-container | Verifierad flerhostarkitektur och tydligare uppdelning av kvarvarande stor backendmodul |
| Kodkvalitet | 8,0/10 | Regressioner, oberoende granskning, diffkontroll, inga nya runtimebibliotek; granskad metadatafix | Mer konsekvent formattering och statisk typ-/lintkontroll i befintlig kompakt kod |
| Detektionsmotor | 4,0/10 | Reproducerbar beskrivande metod, avstående och benchmarkgrindar med testad metrik | Rättighetsgranskad oberoende data, mätt mänsklig FPR, jämförd tränad baseline, kalibrering och extern testmängd |
| Humanizer | 6,5/10 | Sex olika instruktioner, 24 verkliga modellfall: 23 accepterade och 1 säkert avvisat; exakta värden kontrollerade | Blindad språk-/betydelsebedömning, stabila förbättringar per läge, färre skyddsavvisanden och verifierad OpenAI/kompatibel modell |
| Säkerhet | 8,0/10 | Token per användare, atomiska delade gränser, tids-/bytegränser, avbrott, CSP, audits och hemlighetsskanning | Oberoende penetrationstest, distribuerad drift, proxy/TLS/egress och identitetslivscykel i verklig miljö |
| Integritet | 8,5/10 | Ingen text-/nyckelpersistens, minnesbaserad webbkod, inga analys-POST:ar, hashade kvotidentiteter | Leverantörs-/hostingvillkor, logg- och retentiongranskning i vald deployment |
| UI/UX | 8,5/10 | Två browserflöden: original/diff/kopia/export/återställning, avbrott och fel; desktop/smala skärmar | Användartester, fler riktiga arbetsflöden och modellkvalitet utan säkerhetsavvisanden |
| Tillgänglighet | 8,0/10 | 0 axe-överträdelser i 11 kontrollerade vyer; tangentbord, fokus, kontrast och 320 px | Manuell WCAG-/skärmläsarbedömning, zoom/high contrast och fler webbläsare |
| Prestanda | 8,5/10 | Bundlegater, sex 100-sample analysmätningar, API-/minnesrapporter och samtidighetsprov | Lågpresterande mobiler, verklig produktionslast, isolerad allokering och verifierad kallstart |
| Tester | 8,5/10 | 60 Node + 77 pytest godkända, browser/axe/container, liveprover med öppet redovisat misslyckande | Oberoende kvalitetskorpus, fler modell-/APIbehörigheter, fuzz/last och bredare browsermatris |
| Dokumentation | 9,0/10 | README, progress, metod/schema, arkitektur/drift, slutverifiering och versionssparade rårapporter | Fler operatörsprov från en faktisk deployment och extern läsgranskning |
| Produktionsberedskap | 6,5/10 | Byggd nonroot-container, två riktiga workers, gemensam auth/ratekontroll; CI förberett | Publik miljö med TLS/URL, larm/backup/återställning, credential-livscykel och godkänd modell-/säkerhetskvalitet |

Ingen accuracy, FPR, FNR eller kalibreringskvalitet för verklig AI-detektion är verifierad. Syntetiska fixtures används enbart för att testa beräkningar och datagrindar. Ingen semantisk likvärdighet eller detektorundvikande garanteras. Ett 502-svar som stoppar förändrade uppgifter räknas som ett misslyckat modellfall och en fungerande skyddskontroll, inte som en lyckad omskrivning.
