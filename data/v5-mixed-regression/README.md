# Exact mixed-origin regression documents

These **24 derived documents are historical diagnostics, not a new independent
corpus or quality holdout**. They concatenate archived human and generated texts
from the existing audited 60-row pilot. Twelve documents are Swedish and twelve
English; all 12 existing source families and source splits are retained. No new
independent source families or fresh model generations were created.

Each record preserves parent IDs, complete inherited provenance/attribution,
original hashes and exact half-open UTF-16 origin intervals. The only transformation
is concatenation with two newline characters. Original bytes inside each parent
span remain unchanged. The selected parent labels retain all qualifications in
[the pilot source audit](../../docs/PILOT_CORPUS.md).

`knownAiWordShare` describes the share of words copied from the AI-labelled parent.
It is a construction label, not a classifier probability, detection result or
measure of semantic AI influence. Separator whitespace contributes no words.
Mixed documents deliberately reuse parents; the extra row count cannot be used
to narrow confidence intervals or justify activating segment percentages.

Reproduce without replacing these files:

```sh
python tools/mixed_v5.py --output artifacts/mixed-v5-reproduced
python -m pytest tests/test_mixed_v5.py -q
```

The builder first runs the existing source corpus integrity audit. It rejects
changed parent hashes, unknown pure origins and partition/language inconsistencies.
It never truncates source texts or overwrites an existing output directory.
