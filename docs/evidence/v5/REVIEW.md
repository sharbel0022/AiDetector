# V5 review record

Separate agent reviews examined the detector/data pipeline, frontend state and
browser contracts, and provider/ledger/security integration. These are code
reviews and reproducible engineering checks, not an independent human audit or
evidence that the language models are accurate.

## Findings addressed

| Finding | Repair and regression evidence |
| --- | --- |
| Binary assessed observations could exceed the reported assessed count | Require `binaryAssessed <= assessed <= total`; malformed summaries fail the evidence gate |
| Empty or internally inconsistent calibration summaries could pass | Require positive consistent counts, distinct decile bins, integral observed AI counts matching truth labels, count-derived Wilson intervals and recomputed ECE; semantic regressions recompute the evidence bindings so they exercise validation rather than only hash rejection |
| A cancelled rewrite could leave aggregate usage looking current | Keep last-read snapshots and uncertainty per connection/access-code scope, expose manual refresh and timestamp, and retain the warning through delayed billing and later reads |
| Byte equality failed across training environments for numerical rounding | Validate both artifacts independently, compare finite floats within `1e-12` absolute plus relative tolerance, and require exact structure, data identities, counts, gates and recorded prediction categories; retain byte equality for repeated training in the same CI environment |
| Accessible button names omitted visible version/word-count text | Derive names from visible content and attach supplemental segment instructions with `aria-describedby`; keep the original axe rules enabled |
| Generic labeled containers were reported as inconclusive ARIA semantics | Give the style value, segment legend and source controls explicit group roles; the subsequent audit no longer reports those findings |
| A result-card heading broke awkwardly at 320 px | Stack metric cards below 381 px; retain overflow checks at 320 and 390 px |
| Headless print output lacked page margins and could split metric rows | Set print margins and keep related metric labels, values and signal rows together; inspect the PDF rendered from the expanded report state |

The calibration changes and reproduction checker were cross-reviewed by the
other reviewer. No additional blocking findings remained in those reviews.
Direct format checks exercised the actual calibration writer with observation
counts through 50,000 and exact/adjacent bin boundaries. They establish writer
compatibility, not calibration quality.

## Limits that remain explicit

- Brier is a supplied bounded metric; bin means cannot reconstruct individual
  squared errors. Integrity hashes are not signatures or proof of provenance.
- Future fitted calibration artifacts retain an exact `scoredRowsSha256` check;
  supporting score-rounding differences safely requires auditable fitting rows.
- No new generative requests were possible in the supplied environment. Saved
  model outputs were replayed without representing them as new prompt tests.
- Browser/provider fixtures validate interfaces. Only the separately identified
  bundled-detector browser call tests the actual model integration, and that
  integration result does not validate detection quality.
- Automated accessibility checks do not replace manual assistive-technology or
  user testing. The audit retains both violations and inconclusive checks.

See [the verification report](../../VERIFICATION-V5.md) for the actual CI run,
counts, reproducible measurements and remaining model limitations.
