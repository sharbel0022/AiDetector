# TextLab v3: detector method and benchmark protocol

## What is shipped and what is measured

TextLab ships a deterministic, local **descriptive style analyzer**, `style-heuristics-v3`. It does not ship a trained AI-authorship classifier. `authorship` is always `undetermined`; there is no authorship probability. The browser's style index is an unweighted mean of five manually scaled language measurements. It is not a validated decision threshold, confidence estimate, or percentage of AI-written words.

Repository inspection on 2026-11-02 found no independently labelled, rights-verified corpus, original generation logs, documented human authorship records, or trained classifier artifact. Consequently no model was fitted, calibrated, or advertised as accurate. The checked-in JSONL is explicitly synthetic engineering material. Its labels are assigned to exercise code paths; even its rows labelled `human` are constructed fixtures and are not verified human writing.

The benchmark reports `qualityEvidence: false`. In independent-data mode the tool validates the *presence and consistency of provenance assertions*, not the truth of external rights or labels. A separate reviewer must audit these before interpreting a report as quality evidence. Passing schema validation alone is not that audit.

## Analyzer measurements

Unicode words retain UTF-16 start/end offsets into the original string. Comparison keys use NFKC normalization and lowercase. Sentence segmentation is a heuristic using punctuation and newlines, with a small abbreviation exception list; it is not a full language parser. All weights and scaling constants below are manually chosen, not fitted or benchmark validated. With `clamp(x) = min(1,max(0,x))`:

| Signal | Raw measurement | Display contribution, 0–1 |
| --- | --- | --- |
| Sentence uniformity | Population standard deviation of sentence word counts divided by mean (CV) | `clamp(1 − CV / 0.65)` |
| Repeated openings | Extra occurrences of the same normalized first two sentence words | `clamp(extra / sentenceCount × 2)` |
| Fixed phrases | Exact whole-word matches in eleven listed Swedish/English phrases | `clamp(matches / wordCount × 100)` |
| Limited lexical variation | Moving-average type–token ratio (MATTR), 50-word window | `clamp((0.8 − MATTR) / 0.4)` |
| Repeated phrases | Fraction of token positions covered by repeated four-word sequences within sentences | Raw fraction |

`styleIndex = round(20 × sum(five contributions))`. The phrase list includes ordinary formulations used by people. Repetition can come from quotations, instructions, legal wording, topic restrictions, translation or deliberate rhetoric. No individual feature establishes AI use. Lexical types are surface forms, not lemmas.

Repeated-sequence examples are greedily selected from 12 down to 4 words, without overlapping selected examples; at most 20 groups and 30 displayed occurrences per group are included. This display cap does not cap the raw repeated-four-word coverage measurement. Opening examples are also capped at 30 occurrences per group. Uniformity and MATTR are whole-text aggregates and have no fabricated single-word highlights.

`evidence` entries contain `{id,feature,start,end,text,explanation}`. Ranges are half-open UTF-16 indices, so `source.slice(start,end) === text`, including text preceded by emoji and CRLF. Evidence types may overlap; a renderer should merge or partition intervals without losing source text. They explain a measured writing pattern, not causal authorship attribution. `signals[].evidenceIds` link measurements to exact examples.

## Abstention and uncertainty

An index requires at least 80 words, four segments containing words, and sufficient lexical support for the selected Swedish/English language. Script alone does not imply language support. The language guard uses fixed function-word lists: at least six matches, three distinct matching words, match fraction at least 0.08, and at least 1.8 times the other supported language's count. Non-Latin letter share above 20% or an unsupported requested language produces unsupported status. A detected Swedish/English mismatch or uncertain lexical evidence also abstains.

These are conservative engineering gates, not validated language-identification or uncertainty models. Technical prose, names, mixed language, fragments and unusual styles can be rejected even when they contain valid Swedish or English. Abbreviations, quotes and sentence boundaries can be missegmented. No numeric statistical authorship confidence is available, including when the style index is present.

Statuses are `analyzed`, `insufficient`, `unsupported`, `language_uncertain`, `language_mismatch` and `insufficient_structure`. Machine-readable `abstentionReasons` are separate from Swedish user-facing `uncertainty.reasons` and `languageAssessment.reason`. Signals and examples may still be inspected after abstention; they are not an authorship decision.

## Reproduce the engineering fixture

Run from the repository root with Node 22 or newer:

```sh
npm test
node tools/evaluate.mjs tools/fixtures/detector.synthetic.jsonl --fixture
node tools/evaluate.mjs tools/fixtures/detector.synthetic.jsonl --fixture --select-threshold
```

Redirect the first evaluation's JSON output to an artifact if desired. Direct `node` execution produces JSON only; `npm run evaluate -- ...` also prints npm's command banner. Omitting `--fixture` intentionally rejects the checked-in fixture. Repeated direct runs with the same runtime, source and inputs produce identical output. CLI reports include exact dataset-file, analyzer and evaluator SHA-256 hashes; the programmatic API includes an ordered parsed-record hash. No timestamps or random sampling are used.

The fixture has **14 records: 2 train, 4 validation and 8 test**, with 7 `human`, 4 `ai` and 3 `ai-edited` assigned labels in total. Test contains 4 `human`, 2 `ai` and 2 `ai-edited` fixtures. Six test fixtures receive descriptive indices, while two abstain for unsupported language and short text. It exercises Swedish, English and unsupported French; story, report, email, instruction, note and essay metadata; short, medium and long length slices. The long instruction repeats paragraphs deliberately. All group ids are distinct across documents; duplicate and split checks pass.

**Do not cite this fixture's accuracy, F1 or AUROC as detector performance.** It is too small, constructed, and deliberately easy in some cases. The automated regression suite also tests hard failures for missing provenance, wrong labels, model metadata, grouped leakage, duplicate text, near duplicates, and prohibited test-set threshold tuning.

## Independent corpus format

Supply UTF-8 JSONL, one object per line, maximum 10 MB, 2,000 records and 12,000 UTF-16 characters per text. Rows cannot be silently truncated. Each row needs:

```json
{
  "source_id": "corpus-document-001",
  "text": "The actual text, obtained with documented permission.",
  "label": "human",
  "language": "en",
  "genre": "essay",
  "split": "test",
  "author_id": "documented-author-001",
  "document_id": "document-001",
  "source_group_id": "topic-and-source-family-001",
  "model": null,
  "provenance": {
    "kind": "independent",
    "source": "https://example.org/source-or-accession",
    "rights": {
      "status": "verified",
      "basis": "license",
      "license": "Actual applicable license identifier",
      "evidence": "Rights audit reference, date and scope"
    },
    "label": {
      "method": "verified-source",
      "evidence": "Independent authorship evidence or audit reference"
    }
  }
}
```

The example is a schema illustration, not a licensed corpus row. `rights.basis` must be `owned`, `license` or `public-domain`; a license basis requires a license field. Cite a permission record, a license applicable to the actual text, or a jurisdiction-specific public-domain assessment in `rights.evidence`. Public availability alone is insufficient. Do not check in confidential personal text or unrestricted copyrighted material.

Labels are `human`, `ai`, or `ai-edited`. Human label provenance must be `self-authored` or `verified-source`. AI requires `generation-log` evidence and a nonempty versioned `model`; retain prompts, generation settings, timestamps and output hashes in the referenced evidence. AI-edited requires `edit-log` evidence and model metadata: document the initial source, model intervention and subsequent human editing. Do not silently pool AI-edited with either binary class. `related_source_id`, when present, refers to the original or another source-family member and can reference an external parent shared by several rows.

Record `author_id` for the actual documented author or generation session/commission, rather than reusing the model name as an author for every output. `document_id` joins excerpts of one document. `source_group_id` must join related prompts, source passages, translations, revisions and commissioned variants even if they have different authors or models. A human original and its AI rewrite belong in the same group. Group metadata is a manually audited claim; changing identifiers to make validation pass defeats the holdout.

Partition all such groups into `train`, `validation` and `test` before feature selection. Preserve a source manifest and frozen membership. The evaluator rejects any author, document, source group or related-source component that crosses splits. It checks the **whole dataset before selecting the test split**. A test split is mandatory. The current descriptive method does not train on the train split; it is retained so a future learned baseline can use the same audited protocol.

Exact duplicate checks ignore case, punctuation and whitespace after Unicode normalization. Five-token shingle-set Jaccard similarity at least 0.8 is also rejected. Both checks apply within splits as well as across them, preventing duplicated test examples from inflating counts. They do not detect all paraphrases or translations and can overflag heavily templated documents. Review and group underlying sources; do not merely lower the threshold to bypass a failure. Very short texts use shorter available shingles.

## Thresholds, metrics and their denominators

```sh
node tools/evaluate.mjs path/to/audited-corpus.jsonl 65
node tools/evaluate.mjs path/to/audited-corpus.jsonl --select-threshold
```

A fixed threshold must be declared before reading test outcomes. The default 65 is arbitrary; it is not a validated AI boundary. Optional selection evaluates integer thresholds 0–100 using **only assessed human/AI validation rows**, maximizing F1 and breaking ties by lower FPR and then a higher threshold. It requires both classes. The selected threshold is frozen before scoring the held-out test report. Do not repeatedly alter features or settings after examining test results; use a fresh external holdout after development.

The report includes the confusion matrix, accuracy, precision, assessed recall, F1, FPR, FNR and tie-aware AUROC. Binary metrics exclude `ai-edited`; those rows have a separate count, coverage and descriptive flag rate. Threshold-free AUROC uses style scores as rankings only and excludes abstentions. An absent class or zero denominator yields `null`, never a perfect or zero-error claim.

`total`, `assessed`, `abstained`, per-label abstentions and coverage include all labels. `binaryAssessed` gives the actual accuracy denominator. Assessed recall and FNR exclude abstained AI; `recallAllAI` includes abstained AI in its denominator. This separation makes selective coverage visible. Reports include language, genre, word-count (`short` <80, `medium` 80–299, `long` >=300), model slices, source-group counts and abstention reasons. Slice membership is test-only, while metadata counts cover every split.

Wilson 95% intervals are supplied for proportions, with their denominators and an explicit observation-level assumption. They are **not** adjusted for repeated authors/source families and can be too narrow; use grouped resampling and a larger external corpus before inferential claims. F1 and AUROC intervals are not fabricated. Small slices carry an explicit warning.

Calibration is marked unavailable. There is no Brier score, expected calibration error or reliability diagram because the analyzer has no independently calibrated probability. Dividing styleIndex by 100 does not create one. Future probability calibration would need group-separated calibration data distinct from model/threshold selection and a fresh held-out audit, with class prevalence and out-of-distribution behavior reported.

## Evidence and limits

The lexical-diversity measurement follows the moving-window construction in [Covington & McFall, *Cutting the Gordian Knot: The Moving-Average Type–Token Ratio (MATTR)*](https://www.tandfonline.com/doi/abs/10.1080/09296171003643098). That supports using MATTR to describe lexical diversity; it does **not** validate MATTR as an AI-authorship detector.

[Sadasivan et al., *Can AI-Generated Text be Reliably Detected?*](https://arxiv.org/abs/2303.11156) studies paraphrasing attacks, spoofing and distribution-dependent limits of detection. These findings motivate adversarial/editing slices and cautious interpretation; they do not measure TextLab's performance. [Weber-Wulff et al., *Testing of Detection Tools for AI-Generated Text*](https://arxiv.org/abs/2306.15666) evaluates available tools and effects of translation and obfuscation, supporting the need to test those conditions separately.

A future trained detector should be compared with this frozen descriptive baseline on a rights-reviewed, independently labelled corpus, with grouped splits, unseen-model and time-based holdouts, native/non-native writing, genre/length balance and AI-edited variants. Statistical quality must be reported alongside coverage, human false positives, uncertainty and limits. No amount of synthetic fixture testing substitutes for that evidence.
