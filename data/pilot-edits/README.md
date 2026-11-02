# Supplemental paired AI-edit diagnostic

This is separate from the frozen binary training pilot. It contains its original 36 historical human excerpts and **12 actual model-edited derivatives**, one from the first excerpt of each source family. Six edits use `llama3.2:3b`, six `qwen3.5:4b`, alternating within each language under a frozen selection rule. Every completed response is retained; all twelve differ from their input. The request asks for minimal readability/spelling modernization while retaining content; preserved meaning is **not independently verified**.

`contract.json` predates inference and binds source-file/tool/inventory hashes, selected original IDs, assigned model digests and request hashes. `inventory.json`, all twelve `logs/` records and `manifest.json` support offline replay. A cached log must match its planned model, response model, installed digest and exact request/source; changed frozen records are rejected. The tool never silently regenerates or replaces an inconvenient output.

Originals retain the [historical corpus rights/provenance](../../docs/PILOT_CORPUS.md); generated edits retain their input rights attribution and actual local-model logs. AI-derived text is an operator-commissioned output, not a claim of copyrightability. No human revision was performed after the model output. Original authors are not misattributed as authors of the generated version.

`related_source_id`, source family and split keep each edit with its original. The shared evaluator permits exact/near copies only as explicitly recorded dependent human/edit pairs; unrelated copies and cross-split leakage remain errors. The test split has **12 original excerpts plus 4 derivatives across the same 4 historical families**, not a fresh independent human test set.

The unchanged experimental detector flags **0/4** of those test derivatives, with no abstentions. This is a descriptive result for mixed AI-edited text, not four binary false negatives: these samples are deliberately excluded from human/AI confusion-matrix labels. The reused originals still have 0/12 human flags; that is not additional independent validation. Full margins and slices are in `model-report.json`; the local style-threshold comparison is in `style-report.json`.

```powershell
# Offline replay; makes no model requests and verifies all frozen logs
.venv\Scripts\python.exe tools/paired_edits.py
# Reproduce scoring with the fixed audited artifact (no training/tuning)
.venv\Scripts\python.exe tools/model_evaluate.py --data data/pilot-edits/corpus.jsonl --model models/experimental/pilot-v1-audited/model.json
```

The initial collection used explicit `--generate`; do not overwrite the checked-in run to obtain different results. Future interventions require a separately preregistered output directory. These edits assess a small robustness boundary and cannot establish authorship probabilities, modern-human performance or semantic editing quality.
