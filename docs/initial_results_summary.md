# Initial Results Summary (Review 1)

This summary is intentionally limited to verification and synthetic smoke-test outputs from the handoff snapshot. It must not be cited as a real-dataset or RCA benchmark result.

| Result | Observed | Interpretation |
|---|---:|---|
| Integrated local test suite | 232 passed, 1 skipped | Software tests included in this package pass in the tested local environment |
| Synthetic smoke input | 10 raw log lines | Small, project-generated fixture; no external source |
| Events extracted | 10 | Parsing/extraction smoke test succeeded |
| Parse failures | 0 | No failures on the synthetic fixture; says nothing about a new dataset's failure rate |
| Ingestion accounting | `true` | Manifest accounts for these input lines/events under the implementation's accounting rule |
| Unique templates | 10 | Manifest value from this exact smoke run; not a real dataset statistic |
| Clusters generated | 8 | Descriptive smoke-test output only; no semantic grouping score because there are no independent ground-truth labels |
| Evidence/reference metrics | 1 synthetic package valid; 24/24 references resolve; 0 duplicate relationship occurrences | Controlled synthetic evidence package only; this does not measure whether relationships are truthful |
| RCA ranking metrics | Utility unit tests pass against synthetic rankings | No LLM predictions were produced; no RCA performance claim |
| Current dependency vulnerability scan | Not run | Installation attempt failed because package index DNS/network access was unavailable |
| Current Bandit scan | Not run | Installation attempt failed because package index DNS/network access was unavailable |

The run used Python 3.13.5, scikit-learn 1.8.0, NumPy 2.3.5, TF-IDF/SVD embeddings, an agglomerative clustering configuration with distance threshold 0.5, and seed 0. The recorded single-run wall time was 77.141 ms and must not be generalized. The repository CI workflow specifies Python 3.12; Python 3.12 was not available in this execution container.

## How to reproduce

Run the command from `docs/review1_evaluation_report.md`. Verify the artifacts afterward:

```bash
python -m experiments.verify_run_artifacts --run-dir artifacts/review1_synthetic_smoke
```

A fresh runtime may differ, and the manifest creation timestamp/runtime fields will change. The raw input hash, configuration hash, and output hashes should match for identical unchanged inputs/configuration when the same relevant software versions/configuration are used.

## Status

The required next step is selecting and executing the team's actual log dataset. Dataset candidates and label compatibility are described in `docs/dataset_card.md`. The future RCA experiment is contingent on an implemented prediction stage and incident-level root-cause ground truth.
