# Humanizer quality evidence

This is a small, reproducible local-model challenge, not a semantic-accuracy certification. Exact protected strings, bounded claim patterns, editing usefulness and independent human judgment are different measurements. A returned rewrite still requires review.

The final implementation keeps the original short opaque-anchor protocol. Recognized number/unit pairs are now one protected value. A compact instruction reminds the editor to preserve actor/action/date/quantity relationships, uncertainty and the difference between simultaneous observations and causation. Detailed guidance clarifies existing wording rather than supplying missing reasoning. Every original marker must still occur exactly once. No literal-value dictionary, typed inventory, fuzzy matching, partial patch application, automatic repair or silent retry is used to pass preservation checks.

Selected English/Swedish negative, uncertainty, obligation and causal markers also undergo conservative count comparisons after restoration. Recognized quantities undergo an additional exact comparison. Post-review validation binds ASCII/Unicode unary signs to numeric expressions and units, distinguishes numeric ranges, and detects attached `/`, `·`, `^` or `*` suffix changes even with unsupported or spaced denominators. Production checks do not parse worded ratios such as “per kg” or arbitrary mathematical semantics. These are surface checks: they cannot establish scope, actor/date relationships, equivalent strength of synonyms, or absence of arbitrary added facts. They can reject safe paraphrases expressed with unrecognized wording. Names remain a capitalization heuristic plus user-selected exact terms; common words can be overprotected, and names can be missed.

The quota reservation uses the same secret-free request-body builder as all three provider adapters and readiness probes. It reserves the actual HTTPX-serialized nested JSON body bytes, an additional 1,024-byte protocol allowance and the output-token cap. Regression cases include long backslash-heavy text, quoted Unicode values and all three adapters. No provider header or credential is included in recorded prompts or quota storage.

## Frozen challenge

[`data/humanizer/challenges.json`](../data/humanizer/challenges.json) was written before the first prompt/mechanism change. Two development and two heldout sources cover Swedish and English. Each source is requested in all six modes: natural, simple, professional, academic, concise and detailed. Thus each complete model matrix has 24 calls. The cases contain multiple actors and dates, negation, uncertainty, permission/obligation, number/unit thresholds, literal quotations, citations and URLs.

The baseline contains 48 real Ollama calls across `llama3.2:3b` and `qwen3.5:4b`, including the comparative heldout cells. Candidate selection examined development outputs only. The final matrix uses the identical four sources and all six modes. “Heldout” here means reserved from candidate-output tuning: these are authored, frozen comparative challenges, not an unseen external test or a blinded experiment. The no-tuning declaration records the workflow; it is not proof of experimental blindness. Final heldout results do not guide further changes.

The fixture includes hand-authored required/forbidden patterns for selected claims. A recognized pattern is reported as `supported_pattern`; a missing realization is `unassessed`, which may mean a valid paraphrase outside the patterns. A forbidden pattern is `contradicted_pattern`. These labels are intentionally narrower than semantic correctness. Even `all_bounded_checks_pass` does not exclude an added claim or a changed relationship outside the patterns. Unit spelling expansions can fail exact expectations while preserving meaning.

Every run records the complete synthetic input, accepted output, API status, raw local provider request/response, timing, installed model digest, fixture SHA-256, backend SHA-256 and tool SHA-256. Each cell is one observation at temperature 0.3, and anchor nonces are random. Before/after differences therefore are descriptive observations, not a causal statistical estimate of quality improvement. First-observed latency includes any model loading; controlled cold-start performance is not asserted. The opt-in client alone uses a 300-second timeout, 6,000 output-token cap and large test budgets. Production resource defaults are unchanged.

## Recorded experiments

All candidate evidence is retained under [`data/humanizer/runs/`](../data/humanizer/runs/):

- `baseline.json`: complete original-protocol matrix, 24 requests per small model.
- `development-candidate.json`: literal protected-value dictionary; models frequently expanded the dictionary instead of keeping markers. Strict guards rejected these responses.
- `development-edit-plans.json`: short exact before/after edit proposals; small models invented source spans, overlapped proposals or touched protected anchors. The unsuccessful plan implementation was removed.
- `development-readable-source.json`: readable source with server-side exact-value checks; percentage spacing and quotation changes caused frequent rejection.
- `development-selective-anchors.json`: an intentionally interrupted experiment with readable actors/dates, retaining all 10 completed calls. It is incomplete and is not pooled with complete matrices.
- `development-typed-anchors.json`: a complete typed-role inventory candidate. It also performed poorly on the smaller model's Swedish cases and was rejected.

The final protocol does not retain dictionary-expansion acceptance or edit-plan fallback. This avoids carrying unsuccessful mechanisms into production. Failed candidate calls are evidence, not discarded attempts. [`final-protocol.json`](../data/humanizer/final-protocol.json) records the final source/fixture hashes before evaluation. [`diagnostic-plan.json`](../data/humanizer/diagnostic-plan.json) preselects the installed `qwen3.5:9b` for one additional 24-case diagnostic on the same protocol; its smaller installed size than the available Gemma 12B left more memory headroom. That model has no matched pre-change baseline, so this diagnostic cannot isolate a parameter-count effect.

## Observed results

Counts below use the corrected quantity-boundary assessor in [`reassessment-v2.json`](../data/humanizer/reassessment-v2.json). The original run reports remain unchanged. “Joint” means original API acceptance plus all bounded fixture checks; “joint changed” additionally requires different output from the source.

| Run/model | API accepted / 24 | Joint / 24 | Joint changed / 24 | Accepted unchanged |
| --- | ---: | ---: | ---: | ---: |
| Baseline llama3.2:3b | 24 | 12 | 4 | 8 |
| Final llama3.2:3b | 20 | 12 | 4 | 8 |
| Baseline qwen3.5:4b | 20 | 16 | 11 | 5 |
| Final qwen3.5:4b | 19 | 18 | 12 | 6 |
| Final diagnostic qwen3.5:9b | 23 | 22 | 15 | 7 |

These results do not establish a general quality improvement. Qwen 4B's joint count increased modestly in this one matrix; Llama's joint changed count did not improve and it rejected more requests. The 9B diagnostic did better on the bounded checks but still produced concrete meaning and language defects.

Mode behavior was uneven. Qwen 4B produced six distinct successful outputs for each English source; its concise outputs had 0.833 and 0.892 source word-count ratios. Its two accepted development Swedish outputs were both unchanged. Llama's four accepted development Swedish modes were all unchanged. The 9B model produced only two distinct outputs across all six heldout Swedish modes; concise shortened that source to a 0.968 ratio and the other five outputs were unchanged. Distinctness and shortening do not establish tone quality.

The six separate post-review signed-number network canaries are in [`runs/signed-canary.json`](../data/humanizer/runs/signed-canary.json). Each model received one English and one Swedish natural-mode case containing negative, explicit positive and range values. Both Qwen models returned 2/2 accepted outputs with bounded checks passing; Llama returned 0/2 accepted outputs because its candidates lost protected material and changed wording. Those rejections are not counted as successful editing. Two of the four accepted canaries were unchanged. Canary inputs were declared before their outputs and were not used for tuning.

## Review fixes and replay

Review found that the first assessor used substring counts, so `12 mg/kg` could incorrectly count as preserved `12 mg`. The corrected assessor checks numeric and unit boundaries for the fixture's declared quantity literals, including compound suffixes and signs. Frozen claim patterns and fixture text were not expanded to improve scores. Review also found that reusing a label could overwrite evidence; the current CLI exclusively creates its destination and refuses an existing file before opening any provider connection.

The frozen 72-call tool and backend are preserved as exact byte snapshots under [`tool-snapshots/`](../data/humanizer/tool-snapshots/) and [`backend-snapshots/`](../data/humanizer/backend-snapshots/). The sign/suffix validator fixes happened after those 72 calls and did not change their payload, protection, model settings or prompt. [`request-replay-v2.json`](../data/humanizer/request-replay-v2.json) rebuilds all 72 recorded requests using each recorded nonce and confirms 72/72 identical request SHA-256 values. The corrected validator then replays the original accepted raw model responses: zero final or diagnostic accepted responses become newly rejected. Ten baseline Llama and three baseline Qwen responses fail the newer conservative guards; this is a guard-replay result, not proof that all thirteen were semantically wrong. The separate signed canaries exercise the latest backend over real network calls.

[`agent-review-notes.json`](../data/humanizer/agent-review-notes.json) records concrete defects and bounded-check coverage gaps with source/output hashes. For example, 9B academic Swedish says “Information om Ytterligare” because an ordinary capitalized word was treated as a protected referent. Its academic English changes understandable chronology into “adherence to the timeline.” Both pass all bounded patterns. Llama's accepted Swedish simple/detailed outputs corrupt ordinary words while preserving the exact protected strings. Conversely, some unassessed patterns are plausible valid paraphrases, such as “its effectiveness in improving sleep has not been demonstrated.” These notes do not replace human adjudication.

## Interpreting results

An HTTP 200 means the provider produced a complete valid response and the production exact/risk checks accepted it. `accepted_bounded_checks_pass` additionally requires the frozen fixture's selected claim patterns and exact fixture values. `changed` means only that the accepted output differs from its input. Unchanged text is a permitted safe result, but it does not demonstrate useful editing. Length ratios and distinct outputs across modes demonstrate observable behavior, not tone fidelity.

No independent human adjudication or LLM-as-judge accuracy measurement has been performed. Coding-agent inspection can identify concrete defects in outputs, but it is not independent human ground truth. The raw outputs support a later blinded human review of all claims, added facts, naturalness and requested tone. Detailed mode is especially important to review: an output can retain every number and quotation yet change what a URL refers to or add an unsupported explanation.

## Reproduce

With the models already installed and Ollama running locally:

```powershell
.venv\Scripts\python.exe -m pytest -q --basetemp artifacts/pytest-humanizer-review
.venv\Scripts\python.exe tools/humanizer_quality.py --label local-check --models llama3.2:3b qwen3.5:4b
.venv\Scripts\python.exe tools/humanizer_quality.py --label replay-check --reassess data/humanizer/runs/baseline.json data/humanizer/runs/final.json data/humanizer/runs/diagnostic-qwen9b.json
```

The tool does not download or manually unload models, use a remote provider, or modify production settings. It writes each completed case incrementally and refuses existing output paths. A process interruption or setup failure can leave an incomplete/initializing report; such a report must not be silently treated as a complete comparison or overwrite the original baseline. Offline reassessment makes no new model requests. Local verification after the review fixes passed 208 pytest cases, with one upstream Starlette deprecation warning.
