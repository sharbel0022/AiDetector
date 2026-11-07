# Kvalitetsbedömning — TextLab V4

**Målet 9,5/10 är inte verifierat.** V4 stärker strukturen, providerfel,
konfiguration, textskydd och testbarhet. Det gör inte de experimentella
författarskapsmodellerna statistiskt tillförlitliga eller humanizern semantiskt
verifierad. En teknisk grön testsuite får inte räknas som bevis för modellkvalitet.

| Område | Faktisk bedömning | Underlag / kvarstående gräns |
|---|---|---|
| Arkitektur | Tydligare och verifierbar | Central AIService, separata providers/kontrakt/validering, fungerande V3-moduler bevarade |
| Funktionell kod | Testad lokalt | 309 Python + 70 Node-tester, reproducerbart produktionsbygge och HTTP-/prestandaprov |
| AI Detector | Beskrivande stilverktyg; ej tillförlitlig författarskapsdetektor | Experiment hålls offline. Känd FPR 2/8 på mycket liten modern kontroll kvarstår |
| AI Humanizer | Skyddad redigering med obligatorisk granskning | Reparerat överlappningsfel. Historiska betydelseproblem kvarstår; inga nya liveprov här |
| OpenAI | Tekniskt förberett och mocktestat | Responses, modellåtkomst, schema, quota/errors; projektets verkliga nyckel/modell ej verifierad |
| Säkerhet | Kontroller och regressioner finns | Auth/origin/kvoter/timeout/bytegränser, hemlighetsskydd och audits; inget oberoende pentest |
| UI | Kontrakt och inmatning testade | Tydligt oförändrat resultat och servergräns; V4-browser/axe behöver kandidat-CI |
| Dataintegritet | Bevarad historik och skilda evidenstyper | Gamla dataset/modeller/loggar/snapshots kvar; inga återanvända testdata kallas oberoende |
| Prestanda | Lokala teknikmätningar | Bundle- och analysgränser samt HTTP-/ASGI-prov; inte verklig modellkallstart eller produktionslast |
| Dokumentation | Faktisk kodstruktur dokumenterad | Arkitektur/Mermaid, API, installation, OpenAI/Ollama, drift och verifieringsrapport |
| Releaseberedskap | Kandidat under slutverifiering | Separat kodgranskning klar, dess utmatningsfel reparerat; ny GitHub-CI och branchrensning återstår vid denna rapportversion |

Exakta resultat och verifieringsstatus finns i [V4-rapporten](docs/VERIFICATION-V4.md).
För att motivera 9,5/10 för hela produkten behövs större modern oberoende
kvalitetsdata, bättre verifierad mänsklig falskpositivfrekvens och blindad
redaktionell bedömning av verkliga modellutdata i samtliga lägen. En ny API-modell
eller fler gröna mocktester ersätter inte dessa krav.
