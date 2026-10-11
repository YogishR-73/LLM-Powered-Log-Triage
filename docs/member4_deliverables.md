# Member 4 Deliverables Index

This file is the entry point for Member 4 — Evaluation & System.

## Documentation

- [`research_protocol.md`](research_protocol.md) — research questions, hypotheses, baselines, metric definitions, experiment procedure, reporting rules, and references.
- [`dataset_card.md`](dataset_card.md) — dataset suitability, label discipline, provenance checklist, and current dataset selection status.
- [`architecture.md`](architecture.md) — pipeline diagram, service-evidence boundary, synthetic incident timeline, and artifact map.
- [`review1_evaluation_report.md`](review1_evaluation_report.md) — verification output and scope limitations.
- [`initial_results_summary.md`](initial_results_summary.md) — concise, factual Review 1 results summary.
- [`../artifacts/review1_validation/verification_summary.json`](../artifacts/review1_validation/verification_summary.json) — machine-readable check results and scope limitations.
- [`security_review.md`](security_review.md) — targeted source-review findings, risks, and unrun security scans.
- [`HANDOFF_MEMBER2.md`](HANDOFF_MEMBER2.md) — Member 2 graph integration notes.
- [`figures/architecture.svg`](figures/architecture.svg) and [`figures/synthetic_timeline.svg`](figures/synthetic_timeline.svg) — standalone vector diagrams.

## Code

- `evaluation/metrics.py` — clustering scores, evidence-package integrity, event-reference rates, root-cause ranking metrics, and latency summaries. These functions score supplied data; they do not generate LLM predictions.
- `experiments/run_experiments.py` — calls the existing log-intelligence pipeline and records dataset/config/environment/runtime/artifact provenance.
- `experiments/evaluate_evidence_package.py` — validates package structure and cross-references against the canonical event JSONL.
- `experiments/verify_run_artifacts.py` — verifies generated artifact hashes and refuses paths outside the run directory.
- `tests/test_evaluation_metrics.py` and `tests/test_experiment_runner.py` — unit tests for edge cases and run metadata.

## Machine-readable demonstration outputs

- `artifacts/review1_synthetic_smoke/` — logs, events, clusters, run manifest, experiment manifest, and artifact hashes from a 10-line synthetic smoke fixture.
- `artifacts/review1_synthetic_smoke_verification.json` — verification output for artifact hashes.
- `artifacts/review1_validation/` — recorded pytest output, compile check, and machine-readable validation summary.
- `artifacts/review1_synthetic_evidence/evidence_package.json` — synthetic evidence package with two candidates and four authored evidence items.
- `artifacts/review1_synthetic_evidence/evidence_integrity.json` — schema/reference-integrity metrics for that synthetic package.

All files under these synthetic demonstration paths are examples—not real production incidents, ground-truth causal annotations, or empirical RCA evaluation.

## Reproduce and verify

```bash
python -m pytest -q
python -m experiments.verify_run_artifacts --run-dir artifacts/review1_synthetic_smoke
python -m experiments.evaluate_evidence_package \
  --package artifacts/review1_synthetic_evidence/evidence_package.json \
  --events-jsonl data/synthetic_evidence_events.jsonl \
  --out /tmp/evidence_integrity_check.json
```

## Still required from the team

Select and download the exact public dataset release, check its licence and sensitive-data profile, run it from the actual integrated branch, and record the outputs. RCA comparison remains future work until a prediction stage and incident-level root-cause labels are available. Run the dependency and static security scanners in a resolved environment; the current handoff does not claim these scans passed.
