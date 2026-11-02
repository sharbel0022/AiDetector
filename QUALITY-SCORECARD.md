# Kvalitetsbedömning — TextLab v3

Målet är 9,5/10 per område. Det målet är **inte uppnått eller förutsatt**. Betygen nedan är interna tekniska bedömningar av leveransen, inte statistiskt uppmätta produktbetyg. De bygger på redovisad evidens och sänks vid bristande oberoende verifiering. Exakta körresultat finns i [VERIFICATION](docs/VERIFICATION.md).

| Område | Bedömning | Evidens | Återstår till 9,5 |
|---|---:|---|---|
| Arkitektur | 8,5/10 | Lokal analys, separat serveradapter, delad atomisk kvotmodul, validerad UI-gräns, två-worker-container | Verifierad flerhostarkitektur och tydligare uppdelning av kvarvarande stor backendmodul |
| Kodkvalitet | 8,0/10 | Regressioner, oberoende granskning, diffkontroll, inga nya runtimebibliotek; granskad metadatafix | Mer konsekvent formattering och statisk typ-/lintkontroll i befintlig kompakt kod |
| Detektionsmotor | 5,0/10 | Källspårbar 60-raderspilot, tränad offlinebaslinje och auditerad dataisolering; extern kontroll visar 2/8 mänskliga ursprungsutdrag felaktigt flaggade | Större modern matchad korpus, lägre verifierad mänsklig FPR, färsk extern audit och separat kalibrering; pilotmodellen är inte aktiv i produkten |
| Humanizer | 6,5/10 | Baseline 48 + slutjämförelse 48 + större modellprov 24; 62/72 accepterade slut-/diagnossvar, 52/72 klarar begränsade kontroller, endast 31 även ändrade. Sex senaste teckenprov gav 4 accepterade/2 säkert avvisade | Blindad bedömning av alla fakta/relationer/ton, bättre lägesnytta och färre avvisanden; konkreta betydelsefel finns även bland passerade kontroller |
| Säkerhet | 8,0/10 | Token per användare, atomiska delade gränser, tids-/bytegränser, avbrott, CSP, audits och hemlighetsskanning | Oberoende penetrationstest, distribuerad drift, proxy/TLS/egress och identitetslivscykel i verklig miljö |
| Integritet | 8,5/10 | Ingen text-/nyckelpersistens, minnesbaserad webbkod, inga analys-POST:ar, hashade kvotidentiteter | Leverantörs-/hostingvillkor, logg- och retentiongranskning i vald deployment |
| UI/UX | 8,5/10 | Två browserflöden: original/diff/kopia/export/återställning, avbrott och fel; desktop/smala skärmar | Användartester, fler riktiga arbetsflöden och modellkvalitet utan säkerhetsavvisanden |
| Tillgänglighet | 8,0/10 | 0 axe-överträdelser i 11 kontrollerade vyer; tangentbord, fokus, kontrast och 320 px | Manuell WCAG-/skärmläsarbedömning, zoom/high contrast och fler webbläsare |
| Prestanda | 8,5/10 | Bundlegater, sex 100-sample analysmätningar, API-/minnesrapporter och samtidighetsprov | Lågpresterande mobiler, verklig produktionslast, isolerad allokering och verifierad kallstart |
| Tester | 9,0/10 | 64 Node + 210 pytest godkända, rådataintegritet, två läckagegrindar, 72 byte-identiska replayanrop, verkliga modell-/teckenprov samt browser/axe/container | Större oberoende kvalitetskorpus, fler APIbehörigheter, manuell språkbedömning, fuzz/last och bredare browsermatris |
| Dokumentation | 9,0/10 | README, progress, metod/schema, arkitektur/drift, slutverifiering och versionssparade rårapporter | Fler operatörsprov från en faktisk deployment och extern läsgranskning |
| Produktionsberedskap | 6,5/10 | Byggd nonroot-container, två riktiga workers, gemensam auth/ratekontroll; CI förberett | Publik miljö med TLS/URL, larm/backup/återställning, credential-livscykel och godkänd modell-/säkerhetskvalitet |

De nya pilotresultaten är mätta, men generell detektionsprecision och låg populations-FPR är inte verifierade. Den historiska testmängdens 0/12 mänskliga fel ger fortfarande en övre Wilson-gräns på 24,25 %; den moderna lilla kontrollen gav 2/8 flaggningar. Därför är experimentmodellen inte aktiverad i produkten och ingen AI-sannolikhet visas. Syntetiska fixtures är enbart tekniska tester.

Humanizerbetyget höjs inte utifrån 22/24 begränsade kontrollpass för 9B-modellen. Även den ändrade betydelsen i vissa passerade svar, och sju svar var oförändrade. Kontroller kan också avvisa säkra parafraser. Ett 502-svar är ett misslyckat modellfall med fungerande skydd, inte en lyckad omskrivning. [Verifieringen](docs/VERIFICATION.md) och [humanizerns rådata/metod](docs/HUMANIZER_QUALITY.md) redovisar gränserna.
