# Verification — 2026-11-02

## Locally executed
- `npm test`: 16 passed (analyzer and evaluation-metric tests).
- `python -m pytest -q`: 30 passed (API, preservation, adapters, security, error handling).
- Review regressions were observed failing before fixes: digits embedded in identifiers, oversized protected prompts, non-ASCII token handling.
- No independent reviewer/subagent was available; code review was performed inline.

## Not verified locally
- `npm install`: failed with `EAI_AGAIN` because this runtime cannot resolve the npm registry. Frontend dependency installation, production build and browser execution must be established by the actual GitHub Actions run, not inferred from the unit tests.
- No running Ollama model or OpenAI credentials were available. Model adapter tests use HTTP mocks. Language quality and real model inference are not verified.
- No labelled independent detector benchmark was supplied. No accuracy percentage is claimed.
- ChatGPT Sites publication is blocked: no new-site create/publish action was exposed. The existing MG Fakturakoll Site was not changed.

## CI evidence
The `Verify and build TextLab` workflow runs the complete tests, build and browser checks. Only on success does it commit `sites-build/verification.json`, the built static frontend and a dependency lock to main. Read the workflow conclusion and exact commit before claiming success. The browser report explicitly marks LLM responses as mocked and Sites publication as unverified.
