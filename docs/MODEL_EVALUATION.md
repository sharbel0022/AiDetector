# V5 model evaluation and evidence limits

## Decision

The bundled V5 detector is an operational, reproducible historical pilot. **All
production inference gates remain closed.** The service reports no AI-class
probability and no AI-marked percentage. The preserved modern-human diagnostic
has 2 false positives out of 8 human examples (25%; 95% observation-level Wilson
interval approximately 7.1–59.1%). That known failure and the absence of an
independent calibration/segment corpus prevent a defensible reliability claim.

Sources of every value below are the generated
[`models/v5/evaluation.json`](../models/v5/evaluation.json), the frozen-model
[`modern-human-reproduced.json`](../models/v5/modern-human-reproduced.json), and
the existing source manifests. Earlier V3/V4 data, models and reports are
preserved. No historical test has been renamed an independent holdout.

## Available evidence

| Corpus/stage | Human | AI | Source families | Evidence use |
| --- | ---: | ---: | ---: | --- |
| Pilot training | 18 | 12 | 6 | Vocabulary/IDF/classifier fitting |
| Pilot validation | 6 | 4 | 2 | Threshold and candidate choice |
| Calibration | 0 | 0 | 0 | Unavailable |
| Pilot historical test | 12 | 8 | 4 | Previously inspected diagnostic |
| Modern-human control | 8 | 0 | 2 topic families | Previously inspected regression |

The 60-row pilot consists of 36 historical human excerpts and 24 actual retained
local generations from `llama3.2:3b` and `qwen3.5:4b`. Historical texts and model
outputs carry their existing source, rights, origin-label and generation-log
records. Swedish and English are represented, but this is not a contemporary,
balanced, multi-genre population sample. The human source era differs strongly
from model output; topic, publisher spelling and wording can act as confounders.

The modern control has four Swedish and four English human encyclopedia
examples from pre-modern-LLM revisions. Those labels are attributed collaborative
publication inferences, not verification of every word or exclusion of bots.
The two topics (photosynthesis and bridges) produce four language-specific
documents, eight excerpts, and one shared collaborative-author identifier.
Languages derived from the same topic are related source families. Eight rows
therefore do not imply eight independent sources, and the shared author identity
means even topic-family intervals need careful interpretation.

Existing AI-edited pairs and 24 exact mixed compositions are further historical
diagnostics. Mixed compositions preserve source chunks and UTF-16 origin spans,
but add **zero new independent source families**. They can test alignment and
accounting; they cannot validate a sentence classifier or calibrate probabilities.
No model API or local generator was available for new generations during this
implementation. No new text was fabricated and labeled as independent evidence.

The separate [AI-edited replay](../models/v5/ai-edited-reproduced.json) uses the
existing test partition: 12 human parent excerpts and four retained AI edits.
None of the four edits crosses the diagnostic AI threshold. Edited human text
is not a pure AI-origin class; this is not a measured four-example false-negative
rate and does not measure how much an AI influenced the text.

The [mixed runtime replay](../models/v5/mixed-segments-reproduced.json) checks the
eight constructed documents inheriting the historical test split, from four
existing families. All 3,973 source words remain accounted for, with exact
UTF-16 text intervals and zero sentences crossing origin boundaries. This is
alignment evidence. Segment classification coverage is zero because the segment
gate is closed; precision, human false-positive rate and percentage error are
null. Construction-origin word shares never replace unavailable detector shares.
The other 16 constructed documents retain their train/validation ancestry and
are not silently moved into the replay test partition.

## Candidate comparison

All three models fit only pilot training rows. Thresholds and candidate selection
use only validation rows. Test and modern-human scores are computed after those
choices. The candidate order and fixed hyperparameters are recorded in the
report. Model selection maximizes validation AI recall subject to observed human
FPR ≤ 5%, then uses lower FPR, coverage, and the prespecified candidate order.
Observed zero error on six validation humans is not a 5% population guarantee.

| Candidate | Features | Validation AI found | Validation human FP | Historical test AI found | Historical human FP |
| --- | ---: | ---: | ---: | ---: | ---: |
| Character 3–5 grams, selected | 14,488 | 4/4 | 0/6 | 8/8 | 0/12 |
| Word 1–2 grams | 906 | 3/4 | 0/6 | 8/8 | 0/12 |
| Word + character | 15,394 | 4/4 | 0/6 | 8/8 | 0/12 |

The combined model ties on the limited validation operating results; it does
not justify a complexity or accuracy claim. The character model wins the
prespecified tie. Reusing familiar candidates and familiar historical data is
an engineering comparison, **not a fresh estimate of model improvement**.
The actual numerical model is exported and used by runtime eligibility/inference
machinery behind the closed gates. Maximum JSON-vs-sklearn margin discrepancy in
the recorded parity check is approximately `4.55e-15`.

## What the reported scores establish

The selected model's 20 historical test examples yield accuracy, precision,
recall, F1 and AUROC of 1.0 at the frozen AI threshold, with coverage 1.0.
The sample is too small and too familiar to support a production claim:

| Historical selected-model measure | Estimate | 95% Wilson interval |
| --- | ---: | ---: |
| Human false-positive rate | 0/12 = 0% | approximately 0–24.2% |
| AI recall | 8/8 = 100% | approximately 67.6–100% |
| Accuracy | 20/20 = 100% | approximately 83.9–100% |
| Modern-human false-positive rate | 2/8 = 25% | approximately 7.1–59.1% |

The JSON report includes confusion matrices, FPR/FNR, accuracy, precision,
recall, F1, AUROC, coverage, ambiguous decisions, class counts, family counts,
observation intervals, and family-level any-false-positive intervals. AUROC is
null for the all-human modern control because no AI class is present. It also
contains language, genre, length and generator slices and individual diagnostic
scores tied to source IDs. These private diagnostic margins are never public
authorship probabilities.

Both Swedish and English historical test slices have 6 human and 4 AI examples,
with 0 false positives and 4 AI detections. Both modern-human language slices
have 1 false positive among 4 humans. Tiny slices and only four historical test
families make any apparent perfect score highly uncertain. Observation intervals
assume independent observations; several excerpts from one source violate that
assumption. Family counts and any-flag intervals provide another view, not a cure
for convenience sampling or shared authorship.

## Calibration, segment evidence and abstention

There is no separate calibration split in the available pilot. ECE, Brier score
and probability reliability therefore remain unavailable, rather than being
calculated from a logistic sigmoid and presented as validated probabilities.
The reusable pipeline fits Platt calibration when a separate reviewed calibration
split exists, then evaluates it on held-out rows. Calibration-fitting counts,
reliability-bin counts and Wilson observed-fraction intervals are retained.

No separately trained and independently evaluated segment model is bundled.
Runtime creates exact source spans, rechecks language and word eligibility, and
reports the absence of segment evidence. It does not transfer the document label
to every sentence. A future segment corpus has its own train, calibration,
validation and test stages, its own numerical model and two own evidence gates.
Segment AI precision must meet the separate release criterion before word-share
percentages can appear. A future numeric segment probability additionally needs
its own calibration gate.

The system abstains on unsupported/mismatched/uncertain language, short documents,
insufficient sentence structure, unknown vocabulary, missing model files and
unverified evidence. Document and segment eligibility differ and are reported
separately. The uncertain interval between independently selected operating
points is also an explicit category. No absence of an AI flag is presented as
proof of human authorship.

## Data audit and path to a meaningful independent result

The importer checks source/author/document/family identities, parents,
paraphrase/derivative/prompt groups, commissioning authors, exact normalized text
hashes, retained rights and origin-label evidence. Connected identities cannot
cross train, calibration, validation and test. Hashes and split footprints bind
the exported artifact to the reviewed rows. A fresh-test claim additionally
requires an externally recorded rights review and an independent custodian's
frozen test hash. Known historical test text and identities are rejected.

This mechanism checks supplied metadata; it cannot independently certify an
author, unknown alias, hidden paraphrase, license assertion or test custodian.
Dataset review must investigate those facts. Self-hashes are integrity checks,
not authenticity signatures. Repeated adaptation after a test run consumes
that test's independent status, even when source groups are disjoint.

A suitable next corpus needs contemporary Swedish and English human examples
with verified rights, multiple genres and lengths, matched topics and time
periods, retained generations from multiple model families and versions,
separately labeled AI edits and exact mixed-origin spans, and an untouched
custodian-held evaluation set. Authors, source documents, commissioned prompt
families, paraphrases and derivatives must remain grouped. The release policy
and minimum counts are documented in [DETECTOR_V5.md](DETECTOR_V5.md); satisfying
the minimum counts alone is insufficient. Low false-positive bounds, recall,
coverage, calibration and independent provenance must also pass overall and by
language. No numerical 9.5/10 detector-quality rating is supported by this data.

## Reproduce

```bash
python -m tools.train_v5 --output-dir artifacts/v5-reproduced
python -m tools.evaluate_v5 --data data/modern-human/corpus.jsonl \
  --model artifacts/v5-reproduced/detector.json --output artifacts/v5-modern-human.json
python -m pytest tests/test_v5_detector_runtime.py tests/test_v5_detector_training.py
python -m tools.evaluate_mixed_v5 --output artifacts/v5-mixed-segments.json
```

Training requires the pinned ML dependency set. JSON inference does not.
The report stores Python/library versions, code hashes, canonical dataset hashes,
thresholds, model hashes and export-parity error. Use a new output directory to
retain past runs; existing outputs are rejected unless `--overwrite` is explicit.
Unit tests with in-memory artificial scores validate software
behavior only; their examples are not added to any quality report or corpus.
