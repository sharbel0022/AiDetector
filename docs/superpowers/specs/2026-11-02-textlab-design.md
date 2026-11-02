# TextLab v2 design

## Intent
Upgrade the supplied v1 HTML prototype into a React application with a FastAPI AI rewriting backend. Save the project to sharbel0022/AiDetector. The user also requests ChatGPT Sites publication.

## Decisions
- React/Vite frontend in `sites/`; FastAPI backend in `backend/`.
- Analysis stays in the browser. Explainable style signals, sentence highlights and an explicit insufficient-text state replace unsupported claims about authorship. A style index is never a probability.
- Rewriting uses a real configured model: local Ollama by default, optional OpenAI Responses API. Never silently substitute rules or a mock when a provider is unavailable.
- Natural, simple and professional tones; Swedish and English; original/result comparison; copy and text export.
- Protect exact numbers, URLs, bracketed references and quotations using opaque tokens and post-generation checks. These checks do not verify semantic equivalence or factual truth.
- No server-side text persistence, no analytics, no credentials in frontend or git. Require an application token for remote requests and production deployments. Bounded requests, deadlines, concurrency and rate limits.

## Approaches considered
Standalone HTML is easy to distribute but cannot safely hold API credentials. A hosted-only API would require a provisioned service and credentials. Selected implementation: a portable frontend plus a local-first backend; cloud configuration is explicit. This is the implementer's choice consistent with the accepted v2 proposal.

## Verification
Node unit tests for the analyzer and benchmark metrics; pytest for provider boundaries, preservation and API security; production build; Playwright desktop/mobile flows. Provider mocks test protocol handling, not actual model quality. No detector accuracy claim without an independent labelled corpus.

## Publication boundary
The repository is empty and write access is verified. The exposed Sites connector contains only an existing MG Fakturakoll application's operational tools; no new-site creation or publication action has been found. Do not touch MG Fakturakoll. Package the frontend and document this block rather than claim publication.
