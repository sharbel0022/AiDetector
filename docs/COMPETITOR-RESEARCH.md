# Official-source product research for TextLab V5

Reviewed: 2026-11-07. Scope: official public product pages and documentation from GPTZero, Turnitin, Originality.ai and Copyleaks. This is a review of documented behavior, not an independent accuracy comparison or a hands-on audit of authenticated products. Product versions and interfaces change; historical documentation is identified below. No competitor's model, thresholds, branding or interface is copied.

## The central finding: percentages have different meanings

A document classification confidence and the fraction of text flagged by a segment classifier answer different questions. Providers do not consistently use the same definition, and definitions can change between versions. TextLab must name its metric, disclose the model/version and denominator, and independently validate each capability before displaying it.

| Product / source | Documented meaning and interaction | Implication for TextLab |
| --- | --- | --- |
| [GPTZero: interpreting results](https://support.gptzero.me/articles/4965048546-how-do-i-interpret-a-gptzero-result) | AI, Mixed and Human classifications are accompanied by confidence information. The score concerns the document classification, rather than a measured fraction of AI-authored text. The documentation cautions against using the result alone for consequential decisions. | Keep document probability separate from marked share. Present mixed and uncertain states explicitly, with review context. |
| [Turnitin: accessing the AI Writing Report](https://guides.turnitin.com/hc/en-us/articles/28457596598925-How-to-access-the-AI-Writing-Report) | Percentage refers to qualifying text identified as likely AI writing. The AI Writing view is distinct from similarity. In the 1–19% range, the report suppresses the precise percentage and highlights to reduce misinterpretation. Unprocessed/error states are distinct. | Describe coverage and exclusions. Use an explicit unavailable state rather than displaying zero. Do not copy Turnitin's thresholds. |
| [Originality 5.0 / 5.0 Max](https://help.originality.ai/en/article/originalityai-50-and-50-max-features-scores-and-pricing-z9kqn9/) | Version 5.0 describes an estimated portion of text, with Likely Original, Mixed and Likely AI bands. Older confidence scores are not the same measurement. | Always record the model and metric definition in reports. Do not compare scores across versions without establishing comparability. |
| [Copyleaks: AI-detection result schema](https://docs.copyleaks.com/reference/data-types/authenticity/results/ai-detection) | The documented response distinguishes classified sections and their positions. Legacy probability/confidence fields are deprecated, with removal scheduled for July 2026. | Integrate against a versioned, validated schema. Never silently interpret an arbitrary numeric field as probability or share. |

GPTZero states: “The AI detection score is not the percentage of AI in the document.” Originality's current guide states: “Because the scoring approach has changed, avoid treating an older confidence score and a new 5.0 score as equivalent measurements.” These are different products and metric definitions, not contradictory accuracy evidence.

## Input, navigation, highlights and mixed documents

### GPTZero

- [Long-document guidance](https://support.gptzero.me/articles/8816734668-how-do-i-scan-a-long-document-xl-documents) describes paste/upload workflows, basic and advanced views, page-level navigation and whole-document results. It distinguishes too-short, partially scanned and unscanned content.
- [Understanding an AI scan](https://gptzero.me/news/understand-gptzero-ai-scan) describes classification, probability/confidence and sentence-level contributions. Highlight explanations should therefore remain connected to the document context rather than appear as isolated accusations.
- [Assignment workflow](https://support.gptzero.me/articles/2654694997-how-do-i-create-and-grade-an-assignment) documents PDF/DOCX/TXT input, paste/upload/Drive options, separate report views and PDF export within the assignment workflow. This does not establish that every plan or standalone AI scan has identical export options.

### Turnitin

- [AI-writing detection model](https://guides.turnitin.com/hc/en-us/articles/28294949544717-AI-writing-detection-model) describes different detected writing categories and corresponding highlight focus. [Report navigation](https://guides.turnitin.com/hc/en-us/articles/28457596598925-How-to-access-the-AI-Writing-Report) describes access through the AI Writing view or classic toolbar.
- The denominator is qualifying text, which is not necessarily all characters or all uploaded content. A result should communicate this coverage, especially for documents with unsupported or excluded material.
- [Release notes archive](https://guides.turnitin.com/hc/en-us/articles/33092161932045-Release-notes-archive) records historical PDF-report downloading and interactive highlights. Historical release notes are evidence of those releases, not a guarantee of identical behavior in every present integration.

### Originality.ai

- [AI Scan help](https://help.originality.ai/en/article/ai-scan-cvlm33/) describes paste/upload and highlighted text. [The current 5.0 guide](https://help.originality.ai/en/article/originalityai-50-and-50-max-features-scores-and-pricing-z9kqn9/) introduces explicit mixed-content bands. TextLab uses its own validation and thresholds, not those bands.
- [False-positive guidance](https://help.originality.ai/en/article/most-common-reasons-for-false-positives-with-originality-1sf6ykc/) discusses context and limitations, while also containing descriptions of older confidence-score semantics. The version difference matters when interpreting public help pages.
- [How AI detection works](https://originality.ai/blog/how-does-ai-content-detection-work) and the [5.0 announcement](https://originality.ai/blog/introducing-originality-5-0-and-max) provide additional context for the change. No performance claim from these marketing pages is treated as independently verified.

### Copyleaks

- The [result schema](https://docs.copyleaks.com/reference/data-types/authenticity/results/ai-detection) documents section positions and classifications; this supports maintaining a precise link between a result and its source text.
- [AI Phrases Threshold Filter](https://help.copyleaks.com/s/article/AI-Phrases-Threshold-Filter) distinguishes darker phrase-level visibility from the overall score and broader highlights. A display filter should not silently recompute an underlying metric.
- [Testing methodology](https://copyleaks.com/ai-detector/testing-methodology) explains sensitivity settings and false-positive/false-negative tradeoffs. This is a reason to state evaluation scope, not a basis for importing advertised accuracy into TextLab.
- The [2023 FAQ PDF](https://copyleaks.com/wp-content/uploads/2023/05/ai-content-detector-faqs.pdf) is historical evidence of highlighted-text and percentage presentation. Its wording and old schema must not be assumed to describe the current API.

## Exports and mobile: evidence boundaries

Public documentation confirms some report exports and document navigation above, but this research did not include authenticated account access, plan-by-plan checks or real-device mobile testing of the competitors. No claim is made that a particular competitor's mobile layout, keyboard behavior or export is accessible or available across all plans.

TextLab's mobile and export requirements are therefore independently implemented and tested: a stacking two-panel layout; touch-sized controls; no horizontal document overflow at 320 px; keyboard-selectable segments; visible focus; text labels in addition to color; TXT and JSON reports; and a print layout that includes source text, definitions, model/validation information, coverage and limitations. Exported reports contain the text the user selected for export; credentials are never included.

## Adopted design principles

1. **Two separate metrics.** Document probability appears only when document validation and calibration are verified. Word-weighted AI-marked share appears only when segment validation is verified. Missing validation is a visible unavailable state, never a substitute style percentage.
2. **Explain the denominator.** Show analyzed, flagged and excluded words. The share is flagged words divided by analyzed words; it is not proof of how much a person or AI wrote.
3. **Read in context.** Render the complete original text. Highlight exact UTF-16 source intervals and provide a keyboard-accessible segment list with reasons. Preserve whitespace and render source as literal text.
4. **Treat uncertainty as a result.** Mixed, uncertain, insufficient and unassessed states are explicit. Do not invent precision for short, unsupported or unvalidated text.
5. **Separate stylistic observations.** Retain the local style analysis as an explanatory secondary view. A phrase pattern or style index is not evidence of authorship.
6. **Keep the workflow understandable.** Input and results stay adjacent on desktop and stack on small screens. Show counts, language selection, processing state, cancellation, errors and stale-result invalidation.
7. **Keep a reviewable record.** Reports include model version, validation flags, metric definitions, coverage, segment annotations and limitations. No accuracy claims are inferred from interface polish.
8. **Describe data handling accurately.** Local style analysis runs in the browser; ML analysis sends the entered text to the configured TextLab server; rewriting uses the configured provider. Humanizer results retain the original and offer a diff, with usage/cost only when reported.

These principles are product decisions derived from the cited documentation and TextLab's own requirements. They are not a reproduction of any competitor's visual identity or proprietary detection methods.
