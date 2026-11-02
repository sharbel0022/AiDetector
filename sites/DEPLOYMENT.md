# Sites / publiceringsunderlag

## Faktisk status
Ingen ny ChatGPT Site har skapats eller publicerats i denna session. Verktygsinventeringen gav endast operativa verktyg för en annan befintlig Site (MG Fakturakoll), inte generiska skapa-/publicera-åtgärder. Inga anrop gjordes som ändrar den andra appen.

## Filer
- `sites/`: React-källkod, byggs från repots rot med `npm ci` (när lockfil finns) och `npm run build`.
- `dist/`: genererad statisk frontend.
- `sites-build/`: kopia av godkänt produktionsbygge när GitHub Actions har lyckats.
- `backend/main.py`: FastAPI-servern som anropar AI-modellen.

## Import till en publiceringsmiljö
Importera frontend med dess JavaScript- och CSS-filer från det verifierade bygget. En statisk publicering ger lokal stilanalys, men gör inte en Python-server eller en lokal Ollama-installation tillgänglig automatiskt. Kontrollera den aktuella Sites-miljöns tillåtna import- och backendfunktioner innan den beskrivs som kompatibel.

För AI-omskrivning behövs en nåbar HTTPS-backend. Konfigurera serverns `ALLOWED_ORIGINS` med den verkliga publicerade webbplatsens origin och `ALLOWED_HOSTS` med backendens värdnamn. Sätt produktionsläge och en lång, slumpmässig åtkomstkod. Förvara alla leverantörsnycklar endast på servern.

## Godkännandekontroll efter publicering
1. Kontrollera den verkliga publika URL:en och att rätt GitHub-version visas.
2. Kör stilanalys med nätverksloggen öppen: texten får inte skickas.
3. Testa AI-omskrivning med en riktig konfigurerad modell, inte ett mockat svar.
4. Kontrollera citat, referenser, siffror, mobilvy, fel vid frånkopplad modell och att koder inte ligger i bundle/localStorage.
5. Dokumentera deployment-ID, commit-SHA, URL och testresultat. Markera inte denna kontroll som klar utan evidens.
