# TextLab V5 detector

## What is implemented and what is available

V5 supplies a real trained TF-IDF/logistic-regression model through the local
API, numerical JSON inference, exact source segments, language metadata, and
four separate evidence gates. The bundled model is a **historical pilot**.
Document classification, document probability, segment classification and
segment probability do not meet the release criteria. The user receives
descriptive style analysis and unavailable AI percentages.

This separation is intentional: a working classifier and matching numerical
export do not establish generalization or calibrated authorship likelihood.
The known modern-human regression remains 2 false positives among 8 examples.
See [MODEL_EVALUATION.md](MODEL_EVALUATION.md) and the machine-readable
[`evaluation.json`](../models/v5/evaluation.json).

## Runtime contract

```python
from ai.detector.runtime import analyze_v5
result = analyze_v5(text, language="auto", model_path=None)
```

The default artifact is `models/v5/detector.json`. Deployment may provide a
trusted server-side path; request bodies cannot select an artifact. The function
returns all existing V4 style fields with their existing meanings, plus
`detector` and `segments`. `features.py` remains unchanged, including its frozen
Python/JavaScript parity behavior.

| Field | Meaning |
| --- | --- |
| `detector.modelVersion` | Weight/data-derived identifier; null if unavailable |
| `documentProbability` | Calibrated AI-class probability in `[0,1]`, or null |
| `aiMarkedPercent` | AI-classified words / analyzable words × 100, or null |
| `category` | `ai_like`, `human_like`, `mixed`, `uncertain`, `insufficient` |
| `documentValidated` | Independent document classification gate |
| `calibrationValidated` | Independent document calibration gate |
| `segmentValidated` | Independent segment classification gate |
| `segmentCalibrationValidated` | Independent segment calibration gate |
| `status` | `available`, `unverified`, `abstained`, `model_unavailable` |
| `calibrationStatus` | `validated` or `unavailable` |
| `analyzedWords` | Words in eligible segments; analyzable coverage, not a quality claim |
| `flaggedWords` | Words in validated AI-like segments; otherwise zero |
| `excludedWords` | Total source word count minus analyzable words |
| `totalSegments`, `flaggedSegments` | Integer counts, never null |
| `gates`, `reasons` | Explicit gate decisions and machine-readable reasons |

Document probability requires both document classification and document
calibration validation. Segment labels and marked-word percentage require
segment validation. Numeric segment probabilities additionally require segment
calibration validation. A document score never labels a sentence. A `mixed`
category requires both validated human-like and AI-like local decisions; it
leaves the independent document probability unchanged.

`segments` contains string `id`, UTF-16 `start`/`end`, exact `text`, integer
`wordCount`, `eligible`, `category`, nullable `probability`, and human-readable
`reason`. Segment categories are `ai_like`, `human_like`, `uncertain`, and
`unassessed`. All segments remain unassessed for the bundled artifact.

## Segmentation, offsets and percentages

Segmentation uses the frozen source sentence/newline boundaries. Quotes after
sentence punctuation stay in the source span; no text is normalized or rewritten
for highlighting. Offsets count UTF-16 code units, matching JavaScript slicing.
Astral characters consume two units; combining marks retain their original
positions. Spans are ordered, non-overlapping and source exact. Whitespace gaps
are allowed. Every token belongs to exactly one returned segment.

The word rule is the existing Unicode rule: a letter/number starts a word;
letters, numbers and combining marks continue it; internal apostrophes and
hyphens can join word parts. Punctuation, emoji and whitespace are not words.
A segment is analyzable if it has at least 12 words, independently supported
language, and vocabulary coverage in the available model. The 12-word rule is
an engineering eligibility minimum, **not evidence that 12 words suffice for
accurate attribution**. Unsupported or ambiguous language, shorter segments,
and out-of-vocabulary segments are excluded. An unavailable model excludes all
words. With an available but unvalidated model, eligibility can be shown while
classifications remain unavailable.

When the independent segment gate passes:

```text
aiMarkedPercent = 100 × flaggedWords / analyzedWords
```

Uncertain eligible segments remain in the denominator. Unassessed/excluded
segments do not. No overlapping window is counted twice. An empty denominator
returns null. A high document probability is never substituted for this share.

Documents require supported language, at least 80 words, four sentences, and
vocabulary coverage. The operating points are learned from validation rows,
not manually selected display bands. Scores above the AI threshold are AI-like;
scores below the separately selected human threshold are human-like; the gap is
uncertain. Without independent classification validation the model abstains.

## Language behavior

`auto` applies the existing conservative function-word and script rule, then
selects Swedish or English. Manual `sv`/`en` can produce a visible mismatch and
abstention. The existing `languageAssessment` adds `selected`, `effective`,
`method: function-word-and-script-v1`, and `confidence: null`. This is a language
heuristic, not a validated probabilistic language classifier. Segment eligibility
rechecks the segment's own language markers; a supported document does not
automatically make every embedded passage supported.

## Model and numerical inference

The offline CLI compares three prespecified alternatives with the same logistic
classifier: character TF-IDF 3–5-grams, word TF-IDF 1–2-grams, and combined word
and character blocks. Vocabulary and smoothed IDF fit on training data only.
Term frequencies use `1 + log(count)`. Each block is L2-normalized, then combined
blocks receive a global L2 normalization. Logistic regression uses `C=1`,
balanced classes, `liblinear`, seed 42 and at most 1,000 iterations.

Validation chooses thresholds and the candidate; historical test scores are
computed afterward. A tie uses the prespecified character, word, combined order.
The character model wins this small validation comparison. The export contains
14,488 numerical features. It is an actual fitted model, not a phrase-list score.
No transformer improvement is claimed: the available rights-reviewed corpus
cannot establish that added complexity would generalize better.

Production imports no sklearn, joblib, torch or pickle. The safe loader accepts
one/two whitelisted blocks, bounded dimensions, contiguous vocabulary indices,
finite coefficients, positive IDF values, and an integrity hash. It rejects
duplicate JSON keys, nonfinite values, malformed schema and files over 8 MB.
At most four stat-keyed artifacts are cached. Missing or corrupt models fail
closed while preserving style analysis. User text is not sent to a provider.

Integrity hashes detect accidental mutation and bind reports to weights and
thresholds. They are **not signatures, proof of source rights, or proof that a
claimed independent test was independent**. Operators must review provenance
and protect model files as deployment inputs.

## Calibration and release gates

Platt calibration is fitted only on a separate calibration split, after training
and candidate choice. It never fits on threshold selection or test data. The
document and segment mappings are separate artifacts. Missing calibration means
no public probability. ECE and Brier score are computed on the held-out data;
the report also contains reliability-bin counts and observed-fraction intervals.

The versioned release policy requires fresh frozen independent test provenance,
disjoint lineage, matching weight/threshold/calibration hashes, at least 200
examples per binary class overall and 100 per language, at least 20 source
families per class overall and 10 per language, coverage at least 70%, a 95%
Wilson human false-positive upper bound at most 5%, and an AI recall lower bound
at least 70%. Segment classification also requires a precision lower bound of
90%. Calibrated probability additionally needs at least 100 fitting examples per
class and held-out ECE ≤ 0.05 and Brier ≤ 0.20 overall and for both languages.

These are conservative **release requirements chosen for this implementation**,
not validated population guarantees. Convenience sampling, correlated sources,
unknown genres, later generators and dataset shift still limit any passing
result. Numeric/interval/count consistency checks prevent malformed metadata
from enabling a gate. The bundled evidence cannot satisfy these requirements.

## Reproduction and future imports

```bash
python -m tools.train_v5 --output-dir artifacts/v5-reproduced
python -m tools.evaluate_v5 --data data/modern-human/corpus.jsonl \
  --model artifacts/v5-reproduced/detector.json --output artifacts/v5-modern-human.json
```

Use the repository's pinned offline ML requirements to train. Runtime needs only
the normal API dependencies. Use a separate output directory for exploratory
runs. Existing outputs are rejected unless `--overwrite` is explicitly supplied.
`--data`, `--manifest`, `--evidence-use`, `--segment-data`,
`--segment-manifest`, and `--segment-evidence-use` provide a reusable curated-data
path. Details and the independent-custodian manifest format are in
[`data/v5/README.md`](../data/v5/README.md). Known historical text/families cannot
be relabeled as a fresh test. A replay command never changes release gates.

The risk-focused tests cover missing/corrupt artifacts, numerical export,
nonfinite weights, language mismatch, exact Unicode spans, word accounting,
independent calibration, source lineage leakage, forged validation booleans,
invalid metrics and mixed classification. Engineering fixtures test the code;
they are never counted as detector-quality evidence.
