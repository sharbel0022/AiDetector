# Experimental trained detector pilot

This offline experiment trains a real classifier and reports a held-out evaluation. It is **not approved for production**, does not change the browser analyzer, and does not provide a calibrated probability of AI authorship. The human material is historical writing, so era, spelling, genre, topic and publisher can confound the labels. A good pilot score cannot establish reliability on contemporary writing.

## Frozen pilot results

The [raw frozen report](../models/experimental/pilot-v1/report.json), [JSON model](../models/experimental/pilot-v1/model.json), [standalone reproduction](../models/experimental/pilot-v1/reproduced-test.json) and [pre-outcome protocol](../models/experimental/protocol-v1.json) are checked in. The 60-row corpus contains 36 historical human excerpts and 24 actual logged generations. Train/validation/test sizes are 30/10/20. The threshold used six human and four AI validation rows; it was frozen at margin `-0.042347328445350954` before test scoring.

| Frozen test | Human FP / assessed human | AI TP / all AI | Abstentions | F1 | AUROC |
| --- | ---: | ---: | ---: | ---: | ---: |
| Primary trained model | 0 / 12 | 8 / 8 | 0 / 20 | 1.000 | 1.000 |
| Descriptive style threshold 65 | 0 / 12 | 0 / 8 | 0 / 20 | 0.000 | 1.000 |
| Train Qwen; unseen Llama test | 0 / 12 | 4 / 4 | 0 / 16 | 1.000 | 1.000 |
| Train Llama; unseen Qwen test | 0 / 12 | 3 / 4 | 0 / 16 | 0.857 | 1.000 |

This is a small, easy historical-versus-modern pilot, **not 100% demonstrated detector reliability**. The primary test has only four independent source/author families. For 0/12 excerpt false positives, the observation-level Wilson 95% upper bound is **24.25%** and may already be too narrow because excerpts are dependent. For 0/4 source groups with any human false positive, the separate group-level upper bound is **48.99%**. Neither result establishes a population FPR below 5%. Both methods rank this pilot perfectly by AUROC; the style threshold's zero recall shows that its arbitrary operating point fails, not that its ranking is worse here.

The test includes ten English and ten Swedish rows, four genres with five rows each, 17 medium-length and three long rows. There is no short-text test evidence. A held-out Qwen example is missed in the Llama-only diagnostic despite a perfect ranking, demonstrating sensitivity to the frozen threshold/model distribution. No features or thresholds were changed after these outcomes.

Dataset file SHA-256: `50d65f6d8422d3c9d51f72fa4c7c07d0bf721e097ab604c71c2c502c69ff173a`. Primary model SHA-256: `150100c166288c06a0d8c8f930564aff30bb95180eb6b1c2495062bbd8e7fe5d`. JSON export versus scikit-learn maximum absolute margin error: `9.992007221626409e-16`. The standalone evaluator reproduced all 20 test margins and metrics exactly.

## Frozen protocol

The protocol and the two model-holdout diagnostics were declared before examining this pilot's held-out outcomes. There is no hyperparameter search. `tools/train_baseline.py` fixes:

- Character 3–5-gram TF-IDF, lowercase, minimum document frequency 2, maximum 20,000 features, sublinear term frequency, smoothed IDF and L2 normalization.
- Balanced logistic regression, L2 penalty, C=1, `liblinear`, seed 42, maximum 1,000 iterations. Vocabulary, IDF and coefficients use **only train rows**.
- The existing analyzer's language and minimum-length/structure guard for eligibility. Model and frozen style comparator use the same guard; zero vocabulary overlap adds a model abstention.
- A threshold selected **only on validation rows**, maximizing recall of all validation AI examples subject to observed assessed-human FPR <=5%. Ties prefer lower FPR, then a lower threshold. A threshold above every validation score is allowed and flags no examples. With six validation human excerpts, the constraint allows zero observed false positives; it does **not** certify a population FPR below 5%.
- One primary held-out test evaluation against the descriptive analyzer at its frozen, arbitrary style threshold 65. Training or validation performance is never presented as test performance.
- Two separate model-holdout diagnostics: train and select the threshold on `llama3.2:3b`, then test the unseen `qwen3.5:4b`; reverse those roles for the other diagnostic. Human train/validation/test groups stay fixed. Both diagnostics are reported without choosing a winner or changing the primary fit.

The minimum engineering gates require assessed human and AI counts of 4/4 in train and 2/2 in both validation and test. Train needs at least two source groups per class; validation and test need at least one. These low gates prevent meaningless fits and undefined comparisons, **not** statistical inadequacy. The actual corpus remains an exploratory convenience sample.

## Source and leakage controls

The collector's source manifest and raw generation logs are the evidence for corpus construction. The training script invokes the existing strict `validateDataset` implementation in `tools/evaluate.mjs` before fitting. This checks rights/label metadata, duplicate and near-duplicate text, grouped authors/documents/source families and related-source components across **all** splits. Metadata remains an assertion: the evaluator cannot independently verify authorship or rights.

Only text enters the feature matrix. Labels, author IDs, source IDs, model names and split metadata are not input features. This avoids direct metadata leakage but cannot remove indirect textual signals such as old spelling or publishing conventions. Excerpts commissioned from the same source family share a split. Sources/authors are held out; multiple excerpts within a family remain dependent. Per-model slices in the primary fit are not unseen-model tests; the separate diagnostics provide that narrower check.

## Reproduce and inspect

Install the project development requirements and the optional training dependency lock:

```sh
python -m pip install -r requirements-dev.txt -r requirements-ml.txt
python tools/train_baseline.py --data data/pilot/corpus.jsonl --output models/experimental/pilot-v1
python tools/model_evaluate.py --data data/pilot/corpus.jsonl --model models/experimental/pilot-v1/model.json
python -m pytest tests/test_model_baseline.py -q
```

The output directory must not exist; frozen runs are preserved. `--fixture` is reserved for constructed engineering fixtures and marks the report accordingly. Fixture results are not quality evidence.

`model.json` stores vocabulary, IDF, coefficients, intercept, frozen validation threshold, training source/group IDs, canonical configuration hash, dataset-file hash, code hashes and actual runtime/dependency versions. It contains no executable model serialization. Scoring uses Python's standard library plus Node for the shared audit; it never loads pickle/joblib. The report verifies the exported scorer against scikit-learn's margins, including held-out texts. Its recorded error must be <=1e-10. These are uncalibrated decision margins; converting them through a sigmoid would still not establish calibrated authorship probabilities.

`report.json` records test predictions and language, genre, length and model slices; exact human false-positive counts and both assessed/all-human denominators; coverage and label-specific abstentions; F1 and tie-aware AUROC; and the full two model-holdout diagnostics with their JSON weights. The primary trained and style results share a test corpus and eligibility policy. Undefined metrics remain `null`.

Wilson 95% intervals describe observation-level proportions and can be too narrow because source excerpts are dependent. A separate source-group result counts groups with **any** assessed human false positive. This is a different quantity from excerpt-level FPR. Its interval assumes independent, exchangeable source groups and also cannot justify a population claim from this convenience sample. Zero false positives in a small sample does not establish safety. F1/AUROC confidence intervals and probability calibration are not invented.

## Interpretation and next evidence

The frozen report provides measured pilot outcomes, not a numerical product-quality grade. Development after examining it needs a fresh external holdout. A defensible next corpus needs contemporary human writing, documented native/non-native writers, matched prompts/topics/genres/lengths, more independent authors and publishers, AI-edited and translated writing, adversarial paraphrases and more unseen model families. Separate group-disjoint calibration data and a larger untouched audit would be required before any probability or production decision.

Implementation follows the official [scikit-learn TF-IDF reference](https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.text.TfidfVectorizer.html) and [logistic regression reference](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html). These references describe the algorithm; they do not validate this detector.
