# Publiceringsunderlag — TextLab v3

Ingen publik tjänst eller ChatGPT Site har publicerats under v3-arbetet. Lokal bygg-/containerverifiering redovisas i `docs/VERIFICATION.md`.

Kör `npm ci` och `npm run build`. `dist/` innehåller statisk frontend; GitHub Actions sparar den som `textlab-verification`. Äldre incheckade v2-byggfiler ersätts av versionskopplade CI-artefakter.

En statisk frontend kan göra lokal stilanalys. För humanizern krävs en tillgänglig backend; statisk publicering startar inte Python eller Ollama. Backend serverar `dist/` om katalogen finns vid start. Samma origin ger enklast nätverkskonfiguration. Vid separat hosting: ange backendens betrodda HTTPS-origin i frontendinställningarna och frontendens origin i `ALLOWED_ORIGINS`. API-nycklar stannar på servern.

Använd `TEXTLAB_ENV=production`, explicita `ALLOWED_HOSTS`, säkra origins och autentisering. En privat delad kod ersätter inte användarhantering. Publik fleranvändardrift kräver användartoken och delade kvoter. Se `docs/OPERATIONS.md`.

`docker build -t textlab:v3 .` bygger frontend och en Python 3.12-server som kör som UID 10001. Montera beständig lokal `/state` för gemensamma kvoter och tillför konfiguration genom skyddad env-fil. Containern använder två workers, utan accesslogg eller betrodda proxyheaders. Konfigurationsfel stoppar produktionsstart. Lägg TLS och ytterligare nätverksgränser vid en betrodd reverse proxy.

Ingen molnresurs har provisionerats eller orelaterad befintlig Site ändrats. En framtida deployment måste redovisa verklig URL, deployment-ID, commit-SHA, TLS-/auth-verifiering och riktigt modelltest innan den markeras som klar.
