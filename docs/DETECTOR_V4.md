# V4 detector: local style analysis and offline comparison

V4 adds a Python entry point for the existing descriptive style analysis. The
browser remains the default local path. The application does not load the
experimental classifiers and does not produce an AI authorship probability.

## Application contract

`ai.detector.features.analyze_text(text, language='sv')` returns the same JSON
contract as `sites/src/analyzer.mjs`. The central service can call this bounded
synchronous function from its asynchronous API. The module imports only the
Python standard library and makes no provider or network call.

The contract retains `method: style-heuristics-v3`, `authorship: undetermined`,
`benchmarkStatus: not_evaluated`, and
`uncertainty.probabilityAvailable: false`. Its five signals describe sentence
length variation, repeated openings, a fixed phrase list, moving-average lexical
diversity, and repeated word sequences. Their unweighted style index is not a
classifier score or confidence estimate.

Text with fewer than 80 words or four sentences abstains from a style index.
The conservative Swedish/English function-word rule also abstains for uncertain,
mismatched, and unsupported language. Signals remain descriptive, with explicit
limitations. Prompt-like instructions inside input are treated as ordinary text.

Word boundaries accept Unicode letters and numbers, combining marks within
words, and internal apostrophes or hyphens. NFKC/lowercase normalization is used
for comparisons without changing the original evidence text. Character counts,
the 12,000-character limit, sentence spans, marker spans, and evidence spans use
**UTF-16 code units**, matching JavaScript and frontend selection offsets.
Emoji therefore occupy two units per supplementary code point. JavaScript
whitespace rules and positive decimal rounding are preserved explicitly.

The contract tests compare the full Python response to the existing JavaScript
implementation, allowing only floating-point representation noise. They cover
short and unsupported input, language mismatch, repetition, instruction-like
text, astral characters, emoji sequences, combining accents, fullwidth digits,
unusual whitespace, abbreviations, and exact evidence slices. They also compare
all 60 pilot records and all eight modern-human regression excerpts. These tests
establish engineering compatibility on their inputs; they do not validate
authorship detection. Python's Unicode normalization/category database follows
the installed interpreter, while browser Unicode support follows its engine;
newly assigned characters can require a future parity update.

## Offline classifier experiment

The complete machine-readable result is
[`evidence/v4/classifier-comparison.json`](evidence/v4/classifier-comparison.json).
`tools/compare_classifiers.py` compares these fixed representations:

| Candidate | Representation | Fitted features |
| --- | --- | ---: |
| Audited baseline | Character TF-IDF, lengths 3–5 | 14,488 |
| Word alternative | Word TF-IDF, lengths 1–2 | 906 |
| Combined alternative | Equal word and character blocks, then global L2 normalization | 15,394 |

The baseline is the unchanged audited JSON artifact in
`models/experimental/pilot-v1-audited/model.json`. Alternatives use the same
balanced logistic regression settings: `C=1`, `solver=liblinear`, random seed 42,
and at most 1,000 iterations. Vocabulary, document frequency, IDF, and coefficients
are fitted only on eligible **training** records. The CLI exports a report and
weight fingerprints; it does not export or activate a production model.

The corpus contains 36 historical human excerpts and 24 generated examples,
equally split between Swedish and English. Its frozen partitions are:

| Partition | Human | AI | Source families | Permitted use in V4 |
| --- | ---: | ---: | ---: | --- |
| Training | 18 | 12 | 6 | Fit alternatives |
| Validation | 6 | 4 | 2 | Select alternative thresholds and choose candidate |
| Existing test | 12 | 8 | 4 | Historical development diagnostics only |

The existing dataset audit checks source, author, document and related-family
separation, exact duplicates, and near-duplicate token shingles. The comparison
also verifies that training and validation records match the audited baseline's
development fingerprints. This guards against silently comparing a frozen model
against a different development corpus. It does not prove independent source
authorship or remove historical genre and era confounding.

Each alternative's threshold maximizes validation recall over all AI examples
subject to an **observed** validation human false-positive rate at most 5%.
With six human examples, this permits no observed false positives; it does not
establish a population FPR below 5%. The baseline keeps its original threshold.
Candidate choice then uses validation recall, lower validation FPR, higher
coverage, and a fixed final preference for the existing baseline, word model,
then combined model. Every threshold and the candidate choice are fixed before
historical test margins are computed. The modern-human regression corpus is
loaded only after the comparison has completed.

### Validation results used for selection

Recall and false-negative rate concern the AI label. Precision concerns flagged
examples. Coverage is assessed examples divided by all examples. All ten
validation examples were assessed.

| Candidate | TP / FP / TN / FN | Precision | Recall | F1 | FPR | FNR | AUROC | Coverage |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Audited baseline | 4 / 0 / 6 / 0 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 | 1.000 | 1.000 |
| Word alternative | 3 / 0 / 6 / 1 | 1.000 | 0.750 | 0.857 | 0.000 | 0.250 | 0.958 | 1.000 |
| Combined alternative | 4 / 0 / 6 / 0 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 | 1.000 | 1.000 |

The comparison retains the **audited baseline** under the fixed tie-break. It
does not show a reason to replace it with an alternative. This is a development
choice on a tiny reused validation set, not evidence of a generally best model.

### Reused historical test diagnostics

All three candidates produced TP=8, FP=0, TN=12 and FN=0 on the same existing
20-example test split. Precision, recall, F1, AUROC and coverage were each 1.0;
FPR and FNR were each 0.0. These are explicitly **historical development
diagnostics**, since those texts and prior results had already been inspected.
They must not be described as a new independent evaluation.

Even if the excerpts were independent, zero false positives among 12 humans
would have a Wilson 95% upper bound of about 24.25%. The excerpts actually come
from only four human source families, so observation-level intervals can be too
narrow. The report includes source-family, language, genre, length and model
slices and preserves the original warnings alongside each metric.

### Known modern-human errors are preserved

The regression replay uses only the unchanged baseline and its unchanged
threshold. It reproduces every saved historical margin exactly, including these
two false positives:

- `wikipedia-en-816636789-p2`
- `wikipedia-sv-42244645-p2`

There are **eight excerpts**, from four article/language sources and two topic
families, rather than eight independent articles. Two of eight assessed human
excerpts are flagged: **25% observed FPR at 100% coverage**. Both topic families
contain a false positive. The observation-level Wilson interval is approximately
7.15%–59.07%, with dependence making that interval potentially too narrow.

This corpus has no AI class, so binary precision, recall, F1, FNR and AUROC are
reported as unavailable. The historical-publication inference for human origin
does not exclude bots, templates, copying or uncertain contributor identity.
Collection gaps and source-audit limitations are retained in the report. These
already examined examples are regression evidence only and never select a
representation, threshold or winning model. The alternatives were not scored
on them.

## Calibration and production decision

No probability calibration was fitted. A separate calibration corpus with
disjoint source families is unavailable, and the reused validation set has only
ten excerpts from two families. Adding a calibrated classifier here would add
fitted parameters without credible calibration evidence. Logistic margins remain
ranking scores, never authorship probabilities.

The combination of historical test reuse, strong era/genre confounding, only two
generator models, dependent excerpts, and the existing modern-human false
positives prevents a production reliability claim. No classifier is activated,
and the offline comparison does not change the application's descriptive
`benchmarkStatus`. A future quality assessment requires fresh contemporary human
and generated material, disjoint source families, documented rights and labels,
and a frozen plan before examining the new holdout.

## Reproduction and verification

Run from the repository root with the locked ML environment installed:

```sh
.venv/bin/python -m pytest tests/test_detector_service.py tests/test_classifier_comparison.py -q
.venv/bin/python tools/compare_classifiers.py --output /tmp/textlab-v4-comparison.json
```

Choose a new output path for each run. The writer refuses to replace existing
evidence. No network or installed generative model is needed. The report records
input hashes, code hashes, candidate configuration, training and validation
provenance, model weight fingerprints, dependency versions, margins, confusion
counts and intervals. Old corpora, model weights and reports are unchanged.

Tests reject non-training fit rows, mismatched frozen development provenance,
test-based candidate selection, and overwriting existing reports. A regression
test changes only historical test text and checks that training fingerprints,
weights, selected thresholds and the winning candidate remain identical. A
separate regression checks the exact existing modern-human margins and both
known false-positive source IDs.
