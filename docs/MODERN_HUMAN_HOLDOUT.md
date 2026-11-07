# Modern human-origin robustness diagnostic

The unchanged experimental model falsely flagged **2 of 8** pre-2018 Wikipedia passages: **25% observed human-origin false-positive rate**, with no abstentions. English and Swedish each have 1/4 flagged passages. This external diagnostic exposes a failure hidden by the perfect historical pilot. It does not justify deploying the trained detector or assigning it a high quality grade.

The frozen [report](../data/modern-human/report.json), [manifest](../data/modern-human/manifest.json), [corpus](../data/modern-human/corpus.jsonl), [protocol](../data/modern-human/protocol.json), raw API responses and extracted source paragraphs are checked in. The primary model, its threshold and its original test results were not changed. The final manifest was hashed before this diagnostic's first and only scoring run.

| Frozen method | Human-origin false flags | Coverage | Observation-level Wilson 95% FPR interval |
| --- | ---: | ---: | ---: |
| Trained character TF-IDF/logistic model | 2 / 8 (25%) | 8 / 8 | 7.15–59.07% |
| Frozen descriptive style threshold 65 | 0 / 8 | 8 / 8 | 0–32.44% |

Each language has four passages from two articles. The trained model's English and Swedish FPR intervals are each 4.56–69.94% under an independent-observation assumption. Both paired topic families contain at least one false flag: **2/2 groups**, group-level Wilson 95% interval 34.24–100% for the distinct quantity “group has any false flag.” The sample is tiny, topics and contributors are dependent, and these intervals do not provide population guarantees. There are no AI examples here, so accuracy, precision, recall, F1 and AUROC are explicitly unavailable. The style method's zero false flags says nothing about its AI recall on this set.

The trained false flags were `wikipedia-en-816636789-p2` (Photosynthesis) and `wikipedia-sv-42244645-p2` (Bro). Their uncalibrated margins were approximately -0.0357241 and 0.0267045 against the already frozen threshold -0.0423473. The result is consistent with the historical training corpus's era/genre confound; it does not isolate a causal explanation. No threshold adjustment was made after seeing these passages or outcomes.

## Predeclared sources and availability

Before retrieving detector outcomes, six paired topics were declared: Photosynthesis/Fotosyntes, Bridge/Bro, Library/Bibliotek, Volcano/Vulkan, Telephone/Telefon and Bicycle/Cykel. For each article the official MediaWiki revision API requested the latest revision at or before `2018-01-01T00:00:00Z`; the parse API rendered that exact revision ID.

Only four articles could be retrieved in two bounded attempts. The initial parallel attempt and a subsequent paced sequential attempt both encountered Wikimedia HTTP 429 for the other eight predeclared articles; their bodies and status metadata are archived. Both attempts yielded identical eight-passage corpus bytes. No replacement topics or outcome-based source selection were used. The completed sources are:

| Article | Revision | Timestamp UTC |
| --- | ---: | --- |
| English Photosynthesis | [816636789](https://en.wikipedia.org/w/index.php?oldid=816636789) | 2017-12-22 17:29:15 |
| Swedish Fotosyntes | [42127203](https://sv.wikipedia.org/w/index.php?oldid=42127203) | 2017-11-19 13:11:59 |
| English Bridge | [817433099](https://en.wikipedia.org/w/index.php?oldid=817433099) | 2017-12-28 10:01:18 |
| Swedish Bro | [42244645](https://sv.wikipedia.org/w/index.php?oldid=42244645) | 2017-12-20 16:23:58 |

This falls short of the intended 12 articles/up to 24 passages. Four articles give only **two paired topic source families**, not eight independent authors or documents. Cross-language counterparts share a source-group ID because translation or shared content is possible. All Wikipedia contributors share one conservative author ID; individual authorship is not established.

## Literal extraction, labels and rights

`tools/modern_human_collect.py` extracts paragraph text with Python's HTML parser. It retains link/emphasis text, decodes HTML entities, removes tables, navigation, references, figures, block quotes and math elements, and normalizes whitespace. It takes the first two disjoint runs of complete consecutive paragraphs reaching 180–300 words; oversized paragraphs are skipped rather than truncated or rewritten. No summaries or new LLM calls were used. Every excerpt has offsets and a SHA-256 hash against its archived extracted source. Raw revision metadata, raw rendered HTML JSON, timestamps, request URLs and response hashes make the transformation inspectable.

The `human` label means **pre-LLM collaborative-publication inference**. The timestamp does not prove that every word was typed by a person, exclude bots/templates/copied material, or verify contributor identities. No complete contributor-history or talk-page copyright audit was performed. Those are explicit source/label audit gaps; the data should not be represented as individually verified human authorship.

Each language's archived `rightsinfo` API response explicitly declares [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Attribution is to Wikipedia contributors, with a permanent revision URL and contributor-history link in every record. The extracted corpus is offered under CC BY-SA 4.0, with HTML stripping, citation removal and whitespace normalization recorded as modifications. Wikimedia's [Terms of Use, section 7](https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use#7._Licensing_of_Content) describe attribution and reuse, including exceptions for outside material. The site-wide license declaration does not independently clear every imported quotation or additional attribution requirement; non-prose and block quotations were excluded, and no full rights audit of each contribution is claimed.

## Frozen evidence and verification

Corpus SHA-256: `3266a5d574d61a11db438823c99e4e0fd80b25c664aca22a2cd568524592299b`.

Pre-scoring final manifest SHA-256: `0301874dab2bfc37f714f619dba3fa4dead2ce34f410cd866e85ed6f74839eab`.

Unchanged model SHA-256: `150100c166288c06a0d8c8f930564aff30bb95180eb6b1c2495062bbd8e7fe5d`.

The first collector's source snapshot and manifest are retained because only request pacing changed for the bounded retry. The final manifest records both attempts. Focused tests check extraction, reference/navigation removal, literal offset reconstruction, the revision cutoff, raw-response hashes, immutable reports and the archived collector snapshot. The strict shared Node audit checks duplicate, family and split leakage. This holdout was scored once through the JSON-weight scorer after the manifest freeze; the tool refuses to overwrite its report.

```sh
python -m pytest tools/test_modern_human_collect.py -q
# For a new independent collection only; preserve the checked-in frozen run:
python tools/modern_human_collect.py collect --output path/to/new-collection
python tools/modern_human_collect.py evaluate --output path/to/new-collection
```

Future development needs a larger, rights-reviewed contemporary corpus and a fresh untouched audit. This frozen failure must remain visible; it should not be used to tune the current model or threshold and then rebrand the same passages as a successful test.
