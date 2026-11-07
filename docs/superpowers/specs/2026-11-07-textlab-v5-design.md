# TextLab V5 design

The user supplied the detailed V5 specification on 7 November 2026 and explicitly
requested autonomous implementation, verification, commits, a pushed
`feature/textlab-v5` branch and a pull request. The base is
`ab16164c7baef1863cbdbd0a6b52f4fa0fc1e237`. Do not merge main or delete branches or
historical artifacts in this development phase.

## Decisions

Keep React/Vite, FastAPI and the `AIService` boundary. Preserve the V4 descriptive
style analyzer and existing OpenAI Responses, Ollama and compatible adapters.
Add a trained, reproducible detector behind independently enforced document,
calibration and segment validation gates. An unavailable or unvalidated model
must return explicit abstention and null probability/share fields. Document
confidence and the word-weighted share of flagged segments are distinct measures.
No document score may manufacture sentence labels.

Training, calibration, threshold selection and evaluation must be source-family
disjoint. Reused historical pilot/test material stays clearly labelled historical
diagnostics. Record rights, source/author/document/derivative provenance, model
configuration and hashes. Do not manufacture corpus size, labels, independent
holdouts or detector quality from mocked model results.

Use UTF-16 offsets throughout the API and browser. Segment text must reconstruct
the exact original substring, including emoji and combining characters. Count
non-overlapping analyzable word tokens once; report exclusions and abstentions.
Detect Swedish/English conservatively and retain explicit manual selection.

The interface uses an original responsive two-panel workspace with input/counts,
clear results, separate confidence/share cards, uncertainty, accessible text
highlights and details, and exports. It keeps style observations visibly separate.
Humanizer results always preserve and compare the original, and require review.

Provider usage is actual when returned, otherwise unavailable. Costs use a
versioned source-backed price catalogue, with null for unknown models. Shared
SQLite stores principal digests and usage metadata, never texts or raw tokens.
Existing atomic reservations bound concurrent paid calls; untrusted clients do
not select models, URLs or prices.

## Verification

Run existing Python and Node suites before changes. Add behavioral regression
tests for validation gates, split leakage, calibration, UTF-16 segmentation,
word shares, language choice, response validation, provider usage, concurrent
budget enforcement and unauthorized access. Run full suites, production build,
browser/mobile/axe checks, reproducible model benchmarks, dependency and secret
checks, and Docker checks where the environment supports them. Perform an
independent code review before push. Report live-model limitations separately
from integration results. A 9.5/10 quality target is not an awarded score.
