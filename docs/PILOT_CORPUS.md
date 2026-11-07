# Historical pilot corpus: scope and audit

This is a real, small historical pilot: **36 human excerpts from 12 books by 12 authors plus 24 actual local model outputs**. It is separate from engineering fixtures. It supports reproducible pilot experiments; it does not establish reliable authorship detection for modern writing.

Collection/access date: **2026-11-02**. Frozen corpus: `data/pilot/corpus.jsonl`, SHA256 `50d65f6d8422d3c9d51f72fa4c7c07d0bf721e097ab604c71c2c502c69ff173a`.

## Frozen source and split contract

The contract was declared before generation and before training/evaluation in `data/pilot/contract.json`. Each language has 3 train, 1 validation and 2 test historical authors, with one book per author. Each source contributes 3 human excerpts and one output from each of 2 models. Author, source family and related-source links remain in one split. No text was replaced because of detector/model outcomes.

| Source catalog | Historical author / death | Language | Genre | Split | Publication evidence year |
| --- | --- | --- | --- | --- | --- |
| [1342](https://www.gutenberg.org/ebooks/1342) | Jane Austen (d. 1817) | en | fiction | train | 1894 |
| [1400](https://www.gutenberg.org/ebooks/1400) | Charles Dickens (d. 1870) | en | fiction | train | 1867 |
| [2009](https://www.gutenberg.org/ebooks/2009) | Charles Darwin (d. 1882) | en | science | train | 1872 |
| [34901](https://www.gutenberg.org/ebooks/34901) | John Stuart Mill (d. 1873) | en | essay | validation | 1901 (dated introduction) |
| [3420](https://www.gutenberg.org/ebooks/3420) | Mary Wollstonecraft (d. 1797) | en | essay | test | 1792 (work; PG edition unspecified) |
| [205](https://www.gutenberg.org/ebooks/205) | Henry David Thoreau (d. 1862) | en | memoir | test | 1854 (work; PG edition unspecified) |
| [30078](https://www.gutenberg.org/ebooks/30078) | August Strindberg (d. 1912) | sv | fiction | train | 1914 |
| [28610](https://www.gutenberg.org/ebooks/28610) | Viktor Rydberg (d. 1895) | sv | fiction | train | 1915 |
| [14144](https://www.gutenberg.org/ebooks/14144) | Per Teodor Cleve (d. 1905) | sv | biography | train | 1886 |
| [26479](https://www.gutenberg.org/ebooks/26479) | Toini Topelius (d. 1910) | sv | fiction | validation | 1889 |
| [46538](https://www.gutenberg.org/ebooks/46538) | Emilie Flygare-Carlén (d. 1892) | sv | fiction | test | 1849 |
| [59646](https://www.gutenberg.org/ebooks/59646) | Georg August Wallin (d. 1852) | sv | travel | test | 1864 |

An evidence-driven replacement occurred before generation: Almqvist / PG14670 was excluded because its physical edition/date and spelling normalization could not be identified confidently. Toini Topelius / PG26479 has an explicit 1889 title page. The exclusion and replacement are recorded in the contract.

| Split | Human | AI | Total | Independent historical source families |
| --- | ---: | ---: | ---: | ---: |
| train | 18 | 12 | 30 | 6 |
| validation | 6 | 4 | 10 | 2 |
| test | 12 | 8 | 20 | 4 |
| total | 36 | 24 | 60 | 12 |

There are 18 human and 12 AI examples per language. Repeated passages from a book are dependent observations; 60 rows do not mean 60 independent sources. `author_id`/`document_id` represent historical authors/books for human rows. AI rows use `commission-pg{id}` and `generation-pg{id}`, with the real generator in `model` and the commissioning historical author separately in `commissioning_human_author_id`. They share `source_group_id=pg{id}` and explicit related-source anchors with the commissioning book. A metadata correction introduced these commission IDs after generation, before model fitting; texts, prompts, splits and family membership stayed fixed. The combined dataset has 24 author IDs and 24 document IDs but only 12 historical authors and 12 source families.

## Source, rights and human-label evidence

For every book, `data/pilot/manifest.json` contains exact catalog/raw URLs, raw-download SHA256, archived catalog SHA256, author/death evidence, publication evidence, access date and excerpt offsets/hashes. Catalog HTML and complete raw UTF-8 downloads are retained under `data/pilot/sources/` for offline review. Local Git attributes preserve archived source bytes and force LF for hashed JSON/JSONL, including on Windows. `raw_url` is the exact downloaded file, not an inferred mirror. Each catalog's copyright row says “Public domain in the USA.” The embedded license in each raw file was also checked and retained. The text entered the dataset only from raw book bodies; **automatically generated catalog summaries never enter human examples**.

The primary policy references are the [Project Gutenberg license](https://www.gutenberg.org/policy/license.html) and [permissions policy](https://www.gutenberg.org/policy/permission.html). Those pages distinguish the underlying book text from Project Gutenberg branding/license terms, warn that copyright varies by country, and explain that digital texts may not preserve exact printed spelling. Complete downloads retain their embedded notices; this corpus cites the source in its reference metadata. [Swedish copyright law, section 43](https://www.riksdagen.se/sv/dokument-och-lagar/dokument/svensk-forfattningssamling/lag-1960729-om-upphovsratt-till-litterara-och_sfs-1960-729/) and the [PRV FAQ](https://www.prv.se/sv/upphovsratt/om-upphovsratt/fragor-och-svar-om-upphovsratt/) provide primary references for the ordinary 70 years after death term. All 12 sampled historical authors died by 1912, over 100 years before collection. These sources support a scoped rights audit, not universal legal clearance for every country or every possible editorial contribution. The primary rights pages are archived and hashed in the manifest.

Human labels use `verified-source` because the passages are attributed to historical publications predating generative LLMs. This is an authorship **inference**, not proof that a modern digital transcription has never been normalized, proofread or touched by AI. Several Gutenberg files were updated in 2024–2026; PG2009 specifically reports an October 2026 update. No independent scan-to-text collation or chain-of-custody investigation was performed. Thus `provenance.kind=independent` distinguishes the real-source dataset from synthetic engineering fixtures; it does not mean independent forensic verification. The schema's `rights.status=verified` records this source/policy review, while the validator checks only metadata assertions and integrity.

Publication details and remaining gaps:

- Nine sources have an explicit historical edition year in the downloaded title/front matter. Mill's introduction is dated 1901 and states the work was published 1859. Courtney's introduction is excluded from excerpts.
- Wollstonecraft's 1792 publication is supported by [Columbia University Rare Book Library's title-page record](https://online-exhibitions.library.columbia.edu/exhibits/show/cc/item/59). The unattributed biographical sketch is excluded. The exact physical edition transcribed by PG3420 remains unidentified.
- Thoreau's 1854 publication is supported by [Digital Thoreau's reproduced title page](https://commons.digitalthoreau.org/walden/). Only Walden passages are used; the later Civil Disobedience section is excluded. The exact physical edition transcribed by PG205 remains unidentified.
- Austen's 1894 Saintsbury preface and illustrations are excluded. Darwin's selected passages are main prose, with no glossary/index excerpt. Strindberg and Rydberg excerpts are story bodies. Wallin's travel diary excerpts exclude Elmgren's foreword/biography; the catalog additionally records editor Sven Gabriel Elmgren (1817–1897), whose death evidence is archived. Catalog contributor rows are captured separately in the manifest. Other modern transcription/proofreading contributors are not treated as historical authors, and their intervention is not independently audited.

## Extraction and integrity

The frozen rule starts at body fractions 0.18, 0.48 and 0.78, advances to a paragraph boundary, combines short paragraphs and, if needed, stops a long paragraph at a sentence boundary within 180–300 whitespace-delimited words. All 36 selected excerpts were reviewed for main-body attribution. Offsets are half-open **Unicode code-point indices in the entire UTF-8-sig-decoded original raw download, preserving its newline bytes**. Whitespace is folded with `" ".join(text.split())`; spelling, OCR, punctuation, case and historical language are preserved. Each saved excerpt can be reconstructed exactly from its raw offsets. This is a modest deterministic sampling rule, not random sampling of authors or literature.

The human passages range 183–296 words; AI outputs range 162–323 words by whitespace count. Every actual completed generation was retained, including outputs outside the requested 180–250 word target. No output was selected or rejected based on detector scores or linguistic quality. At least one Thoreau passage contains numerical accounting/table-like prose. There are no examples below 80 words, no code, and no substantial coverage of long documents; only a few AI outputs exceed 300 words.

Raw-download hashes:

| Gutenberg ID | Raw SHA256 |
| --- | --- |
| 1342 | `3f6bb9d6f78e0293b56acd4714dd68cb7d6d1d293402031ce9d5a216bcaf9d75` |
| 1400 | `9a637118af8e953e9764ec603d9b0a032883384d465acac2e27966a80cf1c6f8` |
| 2009 | `2b13c8524d813e706ad23336d81a142d48b44f1f96788b41494a0a83e1b82f88` |
| 34901 | `9ecc51191d7ba36f99b0f17b2f60ed54c3929577856f47f0616d8f198422b657` |
| 3420 | `7d79652f43541759d8ff0ce467372fa4a534d3f9dc32013e01ca99ea04b286a8` |
| 205 | `2d9a76a2e3e8195c69430516ebd33c4d0757a53ad432ff6186b7b794e6fe99f9` |
| 30078 | `07aef01be5944b2808ab97ecd3693f0753673544c2594ffe646b687ace867cd6` |
| 28610 | `9813a6699a17546e8e38d3fbfc84455b940e55de19cbb960b345381993bdf723` |
| 14144 | `7116922ffd3cdee27b310a6f557076df86b16dbe6caced0f7c6caea091e61bee` |
| 26479 | `b3ded9f5f91bd18c0075c472d5ea0f1c24efcc6d94dc145ba9bff8a80f20d530` |
| 46538 | `48918bc6732561b2f2ae0cc35f1faeca83b7371484b40cc63c26b5d45ebf9a03` |
| 59646 | `ddd1b123000c224afd7f12db58b861ef497ba630cef1fabd67160f82608e40fa` |

## Actual AI generation evidence

`data/pilot/ai.jsonl` contains 24 AI passages: 12 from `llama3.2:3b` and 12 from `qwen3.5:4b`. `data/pilot/logs/pg*-ai-*.json` retains the complete request, original prompt, options, model digest, timestamps, unmodified Ollama response, raw-response-field SHA256, request SHA256 and final text SHA256. `/api/version`, `/api/tags` and each model's full `/api/show` output (including its installed license) are retained. No model was downloaded or unloaded by the collector.

| Installed tag | Digest | Installed license snapshot |
| --- | --- | --- |
| llama3.2:3b | `a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72` | Llama 3.2 Community License Agreement; `logs/model-llama3-2-3b.json` |
| qwen3.5:4b | `2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd` | Apache License 2.0; `logs/model-qwen3-5-4b.json` |

Generation settings: `seed=20261102`, `temperature=0.7`, `top_p=0.9`, `num_predict=900`, `num_ctx=4096`, `think=false`, nonstreaming `/api/generate`. There was one request per source/model and no retry or cherry-picking. Both models returned completed outputs with `done_reason=stop`. A fixed seed and digest improve traceability but do not guarantee bit-for-bit replay across hardware/runtime versions.

The source-specific prompts request an original passage in the corresponding language/genre and a nineteenth-century literary register, on an independently worded topic. They contain no human excerpt and no book/author name. This avoids deliberate quotation but cannot rule out model memorization. The prompts are **loosely matched commissions**, not sentence-level paraphrases or tightly matched continuations. AI data use `generation-log` labels. `rights.basis=owned` is the schema's operator-commissioned-output assertion; it does not assert that generated output is copyrightable or that installation alone grants unrestricted rights. The retained model license terms remain relevant, and no cross-jurisdiction output-rights determination was made. Source-book rights and model-output rights are separate audit records.

## Reproduction

From the repository root, with the retained snapshots:

```powershell
python tools/corpus_collect.py verify
python -m unittest discover -s tools -p test_corpus_collect.py
node tools/evaluate.mjs data/pilot/corpus.jsonl 65
```

The last command runs the existing descriptive heuristic diagnostic at a fixed threshold; it is not a learned detector quality claim. The learned pilot pipeline has its own frozen protocol and reports.

`python tools/corpus_collect.py build` reconstructs human rows and the manifest from retained raw bytes and the frozen contract, then combines them with the AI JSONL. `build --download` deliberately refreshes snapshots and hashes from upstream and therefore creates a new source snapshot, not a verification of the old one. Preserve the frozen corpus before refreshing it. `python tools/corpus_collect.py generate` requires the two already-installed Ollama models and only fills missing output records; existing logs can be replayed into metadata without new generation. It should not be run concurrently with another GPU experiment. No model download/unload operation exists in the script.

`verify` checks frozen contract/source/policy hashes, exact source extraction, human JSONL agreement, AI request/response hashes, installed-model snapshot digests, commissioning metadata, source-family split grouping and combined JSONL equality. `tools/evaluate.mjs` separately enforces its strict provenance schema and exact/near-duplicate leakage checks. These consistency checks cannot establish legal rights, authorship truth, semantic independence or absence of training contamination.

## Interpretation limits

The held-out test has only 12 human and 8 AI examples from 4 source families. One human false positive changes overall test FPR by 8.3 percentage points and language-specific FPR by 16.7 points. Passages from the same book are correlated. The validation split has only 2 source families, so threshold estimates are unstable.

Historical Swedish spelling, punctuation, literary register, source formatting, length and topic may reveal **era or source**, rather than AI authorship. Language/genre coverage is uneven: training includes science and biography, validation includes an English essay and Swedish fiction, and test includes essay, memoir, fiction and travel. Several genres have no independent train/validation/test coverage. Public-domain books may already be in both generators' pretraining data. Two small local models do not represent the diversity of present or future generators. There are no modern emails, contemporary student essays, business prose, mixed human/AI edits or representative short texts in this core corpus. AI-edited supplements must remain explicitly separate and grouped with their human parents.

No reliable modern-writing accuracy, calibrated AI probability, universal low false-positive rate or resistance to humanization follows from this pilot. A useful next benchmark needs consented contemporary human sources across authors/domains, more independent groups, additional generators and preregistered external test data.
