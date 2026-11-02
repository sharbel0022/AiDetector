# TextLab v3 design

## Authority and intent
The supplied Swedish v3 brief authorizes autonomous implementation, testing, refactoring, branch push and a PR without merging. It explicitly prioritizes correctness, safety and measured evidence over cosmetics and unsupported quality claims. No additional design approval is required by that instruction.

## Existing baseline
Fetched `origin/main` at `721e3d384aacfb2e5edee2ddece2e6986bc0ee61`. React/Vite frontend, FastAPI backend, local style heuristics, three rewrite tones, placeholder preservation and provider mocks already function. Initial Node suite: 16 passed. Initial frontend build succeeded. No labelled corpus, trained model or configured provider credentials are present in this checkout/environment.

## Approaches considered
1. Train an authorship classifier now: rejected because independent licensed training/validation/test data are unavailable. A toy classifier would undermine the brief.
2. Keep the existing stack, strengthen descriptive analysis, strict evaluation gates, providers, shared security state and accessible workflows: selected by the implementer, preserving compatibility and deployability.
3. Replace the application/platform: rejected because it discards working features without addressing evidence gaps.

## Boundaries
- Style index remains a descriptive score. Authorship is undetermined; confidence is not fabricated. Abstain on inadequate or unsupported text.
- Add measured lexical/structural/repetition signals with exact offsets and language caveats. No unmeasured perplexity or semantic model claims.
- Benchmark requires provenance/rights and document/author/related-family split isolation. Mixed AI-edited text is a separate group; calibration requires calibrated probability predictions.
- Preserve provider adapters and add six distinct editing instructions. Validate protected content and explicitly require semantic review.
- Public users require distinct server-verified credentials and atomic shared quotas/concurrency. Shared SQLite is single-host multiworker only; multiple hosts need an external authenticated gateway/store.
- Input/body/provider response bounds, deadlines, cancellation and safe messages constrain resource use. No text/credential persistence in frontend.
- Improve keyboard/mobile/error/restore/export workflows without changing TextLab identity.
- CI is read-only, deterministic and fail-fast; builds are artifacts, not commits to main.
- Prepare a container and operations guide; deployment and real model quality remain unverified unless actually exercised.

## Verification
TDD for behavioral changes; Node and pytest suites; Playwright desktop/mobile and real backend local analysis; dependency audits; repeat-build hashes; environment-labelled latency/memory/bundle measurements; independent whole-change review. Mock model responses prove integration only.

## Environment exception
The assigned Documents workspace rejects file creation with WinError 2 despite readable ACLs. The isolated fresh clone is under `%TEMP%/codex-textlab-v3/AiDetector`; no existing user checkout is changed. GitHub is the durable delivery destination.
