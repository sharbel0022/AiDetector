# TextLab V4 implementation design

The supplied **AI DETECTOR FINAL V4** request authorizes autonomous implementation,
verification, integration into `main`, and deletion of redundant branches after
their work is integrated and secured. This design records implementation choices;
it does not replace the supplied acceptance requirements.

## Existing system and approach

Start from `codex/textlab-v3` (`5c6328d`), which contains `main` (`721e3d3`) and
the existing detector experiments, model logs, safety controls and React UI.
Keep the established `sites/` frontend directory. Extract the large backend
module into cohesive AI modules, with a central `ai/ai.py` service. A full directory
rename adds migration risk without changing user behavior; a single giant AI file
would make the project harder to maintain. Neither is needed.

The browser keeps local style analysis for privacy and offline operation. The
backend additionally offers the same conservative style-analysis contract through
`AIService.detect`. Model-based authorship classification stays offline and
experimental. The previously inspected external human corpus is regression data,
never a newly independent holdout.

## Responsibilities and contracts

- `backend/config.py`: typed environment configuration and legacy aliases.
- `backend/main.py`: FastAPI routes, authentication, body bounds, cancellation,
  shared quotas, deployment and static hosting.
- `ai/contracts.py`: validated requests and bounded model output.
- `ai/ai.py`: `detect`, `humanize`, `provider_status` orchestration.
- `ai/providers/`: server-selected OpenAI Responses, Ollama, compatible provider.
- `ai/humanizer/`: prompts, exact preservation checks, surface-risk heuristics,
  comparison output. These do not prove semantic equivalence.
- `ai/detector/`: Unicode-aware descriptive style analysis, explicit uncertainty.
- `tools/`: reproducible offline model comparisons, browser and runtime checks.

Existing `/api/rewrite`, `/api/provider-status`, `/api/health` contracts remain.
An unchanged rewrite adds `unchanged` and `explanation`; all rewrites require
human review. `/api/detect` makes no paid API request. Keys never enter the UI.
Provider/model selection remains server-controlled to bound spending and prevent
arbitrary endpoint/model requests. Missing OpenAI configuration must allow startup
and give the requested actionable Swedish error before network activity.

## Acceptance and release gates

Run the full Node/Python suites, deterministic build, browser interactions,
accessibility, security/dependency checks, performance and container checks when
the runtime can execute them. Report unrun or blocked checks explicitly. Probe
already installed models; do not invent live results or download large models
without need. Compare alternatives using existing train/validation/test splits,
label reused data correctly and preserve all historical evidence.

Only release a verified candidate. Re-fetch remote refs before mutation, preserve
ancestry, create a versioned tag, verify `main`, then remove redundant branch refs.
Do not circumvent GitHub checks, protection or permission errors. No 9.5/10 claim
without evidence supporting that assessment.
