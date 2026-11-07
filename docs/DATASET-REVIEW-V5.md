# V5 external dataset review

Reviewed 7 November 2026. This is a source/access review, not newly validated
training data. None of the previewed external texts were added to the training,
calibration, threshold-selection or evaluation corpus.

## RAID

The [publisher's dataset card](https://huggingface.co/datasets/liamdugan/raid/blob/main/README.md)
declares MIT and English, Czech and German. Its schema preserves human source IDs,
generation IDs, adversarial ancestry, model, decoding, penalty and domain. These
are useful for grouping derivatives. The card does not supply per-row human
author identity or source-specific rights review. It provides no Swedish subset.
The [research paper](https://aclanthology.org/2024.acl-long.674/) describes a
multi-model robustness benchmark; its results cannot be transferred to TextLab.

The current environment retrieved the card, dataset metadata and small previews
through the documented [Dataset Viewer API](https://huggingface.co/docs/dataset-viewer/rows).
A bounded query for human book rows returned HTTP 500. No repeated bulk download
or outcome-based source substitution was performed.

**Disposition:** suitable for a future separately documented external benchmark
after auditing upstream rights, authors and overlap; not represented as a cleared
Swedish/English production corpus. The publisher's dataset-level license is
recorded, but it is not treated as independent verification of every underlying
source. Preview data are not model-quality evidence. A source ID alone does not
establish author-disjoint train/test partitions.

## MultiSocial

The [authors' official dataset record](https://zenodo.org/records/13846152)
restricts access, describes noncommercial research use, and warns that the
human-written labels and anonymization may be imperfect. Its listed languages
do not include Swedish. The [official repository](https://github.com/kinit-sk/multisocial)
links to that access-controlled record.

**Disposition:** not imported. No access request, account creation, agreement or
third-party communication was submitted. Its availability does not satisfy this
product's required Swedish coverage or unrestricted permitted use.

## Available project data

The project's existing 60 pilot rows, eight modern-human regression excerpts and
12 logged AI-edited derivatives remain intact. Their original source and rights
records remain the authority. Priorly examined test rows are historical diagnostic
material, not a new untouched holdout. No original text for the user's reported
572-word / 47-sentence example was available; it is not reconstructed.

There is no configured OpenAI credential/model in this environment, no repository
`.env`, and no responding local Ollama service. No fresh generative calls were
performed to manufacture paired training material. Larger, matched, separately
calibrated corpora remain a concrete requirement before detector activation.

## Required next data contribution

Provide texts with verified origin and permitted reuse, including Swedish and
English academic, business, report, article and technical writing, short and long
documents, real generated counterparts and known mixed/edited segment origins.
Record original document, author, source family, date, rights evidence,
transformation/parent IDs and model/run information. Assign the entire connected
lineage to one split before training. Reserve separate calibration,
threshold-selection and untouched test families. Evaluate document decisions and
segment decisions independently; more dependent excerpts do not increase the
number of independent source families.

See [model evaluation](MODEL_EVALUATION.md) and [detector implementation](DETECTOR_V5.md)
for the implemented input contract, reproducible commands and actual measurements.
