# Kvalitetsbedömning — TextLab V5

**9,5/10 är inte verifierat.** V5 har en fungerande tränad detektorpipeline,
separata evidenskrav, ett omarbetat granskningsgränssnitt och mätt
leverantörsförbrukning. Detektorns moderna regression visar fortfarande två
falska positiva av åtta mänskliga utdrag. Några nya generativa modellprov
kunde inte köras i denna miljö. Dessa begränsningar går inte att kompensera
med fler gröna programtester.

Betygen nedan är en manuell teknisk bedömning av kandidaten, inte statistiska
mått, en extern certifiering eller procentuell träffsäkerhet. Modellernas
empiriska kvalitet redovisas separat. CI- och granskningsresultat finns i
[verifieringsrapporten](docs/VERIFICATION-V5.md); slutbedömningen förutsätter
att kandidatens faktiska kontroller är avslutade.

| Område | Bedömning / 10 | Faktiskt underlag och kvarstående gräns |
|---|---:|---|
| Arkitektur och API | 9 | AIService, rena modulansvar, säker JSON-inferens, fyra separata evidensgrindar, tydliga kontrakt |
| Funktionell kod och reproduktion | 9 | Fulla Python-/Node-sviter, deterministisk modell, reproducerbart bygge; slutlig browser/container-verifiering ska bindas till aktuell CI |
| UI och användbarhet | 8,5 | Två paneler, auto/manuellt språk, exakta segment, original/diff, export och ofullständig usage; ingen oberoende användarstudie eller manuell skärmläsargranskning |
| Säkerhet och drift | 8,5 | Auth före body, origin/host, begränsade svar, kvoter, textfria loggar, audits och secretskanning; inget oberoende pentest eller verifierad fler-värdsdrift |
| Token- och kostnadsbokföring | 9 | Faktiska provider-räknare, versionspriser, atomiska reserveringar, avstämning, fel/avbrott och migreringstest; leverantörsfaktura och okända modellpriser förblir externa |
| AI Detector, produktionsberedskap | 3 | Riktig modell och diagnostik finns. Modern FPR 2/8, ingen oberoende kalibrering eller validerad segmentmodell; alla procentgrindar är stängda |
| AI Humanizer, verifierad språk-/betydelsekvalitet | 6 | Starkare begränsade skydd och bevarad jämförelse; historiska betydelserisker, inga nya liveprov eller blindad bedömning av nya promptar |
| Dokumentation och evidensintegritet | 9 | Faktisk arkitektur, API, drift, källgranskning, modeller och rapporter; 247 äldre evidensfiler bevarade byte för byte |

Dessa betyg ska inte medelvärdesberäknas till ett marknadsföringsbetyg. En
statistiskt osäker detektor blir inte tillförlitlig av en välbyggd frontend.

## Vad som krävs för en högre bedömning

1. **Ny oberoende detektorevidens.** Moderna svenska och engelska mänskliga texter
   med verifierbara etiketter/rättigheter, flera genrer/längder, ämnes- och
   tidsmatchade verkliga genereringar från flera modellfamiljer, samt grupperade
   författare, källor och derivat. En separat fryst utvärdering ska ägas av någon
   som inte anpassar modellen efter dess resultat.
2. **Kalibrering och segmentkvalitet.** Separata tränings-, kalibrerings-,
   validerings- och testmängder; låg övre falskpositivgräns, tillräcklig recall,
   täckning och segmentprecision, plus kalibreringsfel på held-out data. Varken
   en logistisk sigmoid eller kända andelar i konstruerade blandningar räcker.
3. **Nya verkliga humanizerprov.** Kör konfigurerad OpenAI och tillgängliga lokala
   modeller i alla sex lägen, behåll misslyckade utdata, och granska betydelse,
   grammatisk kvalitet och lägestrogenhet blindat. Granska även när konservativa
   regler stoppar korrekta omskrivningar.
4. **Drift- och användningsvalidering.** Manuell tangentbords-/skärmläsargranskning,
   användbarhetsprov, realistisk last och felåterställning samt en separat
   säkerhetsgranskning i den tänkta driftmiljön.

Originalet till det tidigare rapporterade testet med 572 ord och 47 meningar
saknas. Den regressionen kan läggas till först när faktisk originaltext finns;
texten har inte återskapats eller hittats på.

Den tidigare bedömningen är bevarad i
[QUALITY-SCORECARD-V4.md](docs/QUALITY-SCORECARD-V4.md).
