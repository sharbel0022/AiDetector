# TextLab V5 verification evidence

These files preserve the successful [GitHub Actions run 42379391802](https://github.com/sharbel0022/AiDetector/actions/runs/42379391802)
for code commit `d92b824c9055f4628511a1df955bc15bb1e01681`.
The downloaded ZIP matched its GitHub-reported SHA-256 before extraction.
[`manifest.json`](manifest.json) records the artifact identity and each preserved
file's SHA-256. Later documentation and print-pagination changes run the same
checks again on the [pull request](https://github.com/sharbel0022/AiDetector/pull/3).

| Evidence | Scope |
| --- | --- |
| `api-tests.txt`, `node-tests.txt` | 482 Python and 84 JavaScript tests; provider contracts use mocks |
| `browser-results.json` | 17 browser contract groups, including the built frontend calling the actual bundled detector |
| `accessibility.json` | Axe checks on 11 views; zero reported violations; contrast background determination remains inconclusive in two result views |
| `container-results.json` | Nonroot, two-worker container, real packaged detector, authenticated usage and shared rate limiting |
| `performance.json`, `api-performance.json` | Exact environment, frontend bundle sizes and local detector timings; generative timings are explicitly mocked |
| `v5-reproduction-check.json` | Independently valid artifacts, exact identities/counts/decisions and bounded cross-platform numerical differences |
| `humanizer-reassessment-v5.json` | Historical saved outputs replayed through the current validator; no new model requests |
| Audit files and `build-sha256.txt` | Dependency/security scans and matching build identities |
| `historical-preservation.json` | Separate local Git-blob comparison of 247 pre-existing data/model/evidence files |
| `REVIEW.md`, `visual-review.json` | Review findings, repairs, screenshot observations and declared-color contrast calculations |

## Screenshots and interpretation

- [`real-detector-v5.png`](real-detector-v5.png) is the built frontend displaying
  the **actual bundled model response**. Its evidence gates are closed and both
  percentages remain unavailable. This is integration evidence, not a test of
  detector accuracy.
- [`segments-v5-mobile-320.png`](segments-v5-mobile-320.png) uses a clearly labeled
  **UI fixture** to exercise four segment categories, keyboard details and the
  narrow layout. Its example percentages are not trained-model results.
- [`humanizer-v5.png`](humanizer-v5.png) uses a **mock provider** to verify original,
  diff and usage presentation. It is not a new generative model result.

The native print/PDF path was exercised and its rendered pages inspected. TXT
and JSON downloads preserve the source, model metadata, definitions and
limitations. These checks do not certify PDF/UA or assistive-technology support.

The code review and visual review were performed by separate agents; no external
human audit, user study or new independent language-model benchmark is implied.
