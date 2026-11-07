# TextLab v3 evidence iteration

User instruction: continue the existing PR toward 9.5/10, prioritizing verifiable detector data and real humanizer tests, without merging. Autonomous implementation remains authorized. Start: `78d4f70fc6bd188b0ff7e5b541f56f84759f2544`; branch `codex/textlab-v3`, PR #1.

## Design and preregistration

Retain the local descriptive product analyzer until a learned model has enough independent evidence. Build an explicitly experimental char-TFIDF/logistic-regression baseline on a source-audited historical sv/en pilot plus real local model generations. Freeze human author/source partitions, model hyperparameters and validation operating-point policy before reading test outcomes. Historical-human versus contemporary-AI is a severe domain confound, not deployment evidence. Do not turn its output into a calibrated authorship probability.

Humanizer work freezes checkable bilingual claim challenges and runs actual models before and after mechanism changes, separating tuning and holdout material. Exact values, negation/modality, relations, mode behavior and unchanged outputs are separate dimensions. No lexical assertion or model judge proves semantic equivalence.

The benchmark currently refuses even legitimate near-identical original/AI-edited pairs within one family. Permit only explicit documented dependencies within the same split/family, report them, and keep unrelated/cross-split duplicate rejection. Such observations cannot count as independent groups.

## Owners and tasks

- [x] Corpus owner: primary-source rights/publication audit; 12 authors in sv/en, 36 disjoint human excerpts and 24 logged actual model outputs. Frozen train/validation/test by author. Retain raw hashes, offsets, prompts, model digests and provenance.
- [x] Model owner: TDD training/export/parity/metrics, frozen char3–5 TFIDF and balanced L2 logistic regression; validation FPR policy <=5% observed, then recall. Actual heldout fit/report; no production registration or calibration claim.
- [x] Humanizer owner: preregister challenge sets, baseline actual inference, isolate cause of semantic/preservation failures, test-first improvement, actual before/after/holdout reports.
- [x] Coordinator: regression for related-edit duplicate policy, supplemental paired-edit material if sources support it, independent review, integrated verification, evidence/docs/scorecard update.
- [ ] Coordinator: commit and push current branch; update PR title/body for final scope; verify latest-head CI; no merge.

## Evidence rules

Never replace an inconvenient source or failed model run based on scores. Record source replacements only for provenance/download failures before generation. Never count synthetic challenge fixtures or AI-authored notes as independent human data. Report raw human false-positive denominators, confidence intervals, groups, abstentions, model/genre/language/length slices and historical-domain limitations. Keep previous reports; do not cherry-pick a green rerun. Record all code/data hashes and actual environment. A pilot can justify further investigation while still failing the 9.5 quality goal.
