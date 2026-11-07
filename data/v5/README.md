# V5 data references and curated import contract

No corpus is duplicated in this directory. V5 reads the existing audited files,
preserves their bytes, and marks every previously inspected test as historical
diagnostic evidence. `referenced-sources.json` records input hashes and counts.

The actual pilot contains 60 rows: 36 historical human excerpts and 24 recorded
local model generations. The 8 modern human rows and existing edited examples
are historical diagnostics. The separate `data/v5-mixed-regression` corpus is
derived from the same known sources and adds **zero independent families**.

## Import a rights-reviewed corpus

Use JSONL with one object per document. Use the same schema for separately
annotated segment examples, with each row's text containing the exact segment.
Do not label an arbitrary sentence using its parent document's AI score.

| Field | Required meaning |
| --- | --- |
| `source_id` | Unique immutable record ID |
| `document_id` | Original document ID, shared by every excerpt/derivative |
| `author_id` | Stable author or jointly authored family; identify aliases |
| `source_group_id` | Broad source/topic/prompt family shared by paired examples |
| `language` | `sv` or `en`, reviewed against source |
| `genre` | Academic, business, technical, article, report, etc. |
| `split` | `train`, `calibration`, `validation`, or `test` |
| `label` | `human`, `ai`, `ai-edited`, or `mixed`; only human/AI fit the binary model |
| `model` | Null for human; exact generating model/version for AI and edited AI |
| `text` | Exact text, at most 12,000 UTF-16 units |
| `text_sha256` | Optional source integrity hash; must match UTF-8 text if supplied |
| `provenance.source` | Retained source URL or generation-record path |
| `provenance.rights` | `status: verified`, lawful `basis`, recorded `evidence` |
| `provenance.label` | Recorded `method` and `evidence` for origin |

AI label methods accepted are `generation-log`, `edit-log`, or
`verified-generation`. Record the actual prompt/request, returned text hash,
provider/model version, date, and generation settings in the referenced log.
Do not use another detector's prediction as an origin label. A human label must
have verified source attribution; the word `human` alone is insufficient.

Add applicable lineage fields: `related_source_id`, `parent_source_id`,
`parent_source_ids`, `paraphrase_group_id`, `derivative_group_id`,
`prompt_family_id`, `lineage_ids`, `commissioning_human_author_id`.
Connected source, document, author, family, parent, paraphrase, derivative and
normalized-text identities **must remain in one split**. If a relationship is
unknown, resolve it before asserting independence. The checker cannot discover
undisclosed aliases or semantic paraphrases automatically.

For training, use `python -m tools.train_v5 --data PATH --output-dir NEW_PATH`.
This command validates the import before fitting; the default evidence use is
historical diagnostic. It performs no scraping, generation, provider calls or
unreviewed download. Use a new output directory when preserving an earlier run.
Existing outputs are rejected unless `--overwrite` is explicitly supplied.

## Fresh independent evaluation manifest

Only use `--evidence-use fresh-independent-holdout --manifest PATH` after an
independent custodian has frozen the test set and documented its provenance.
The manifest has this structure (angle-bracket values are placeholders):

```json
{
  "schemaVersion": "textlab-v5-data-manifest-1",
  "rightsReview": {
    "reviewer": "<reviewer identity>",
    "reviewedAt": "<ISO date>",
    "evidence": "<rights and per-source label review record>"
  },
  "testFreeze": {
    "canonicalRowsSha256": "<SHA256 of canonical test-row array in JSONL order>",
    "frozenAt": "<ISO date before evaluation>",
    "custodian": "<independent custodian>",
    "record": "<immutable external freeze record>",
    "neverUsedForDevelopment": true
  }
}
```

The hash uses `ai.detector.linear.digest(test_rows)` (sorted object keys,
compact JSON, UTF-8, unescaped Unicode, no nonfinite numbers). A supplied manifest
records an accountable review; it does not prove that the assertion is true.
Review the external record before deployment. Known pilot/modern/edited/mixed
test text or identities are rejected as fresh evidence, even with a manifest.
Candidate fitting, calibration fitting and threshold selection each use their
own disjoint split. Inspecting or tuning against a test set consumes its
independent status for later development.

For segment classification add `--segment-data PATH` and, for genuinely new
evidence, its own `--segment-evidence-use` and `--segment-manifest`. Segment
calibration is fitted only from the segment corpus's calibration split and is
never borrowed from the document model.
