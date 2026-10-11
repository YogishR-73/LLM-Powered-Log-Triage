# Research Protocol: Evidence-Grounded LLM Log Triage

**Owner:** Member 4 — Evaluation & System  
**Protocol version:** 1.0  
**Protocol date:** 2026-10-11  
**Status:** Review 1 plan; some methods remain unimplemented.  
**Experimental claims:** This protocol reports no comparative RCA improvement.

## 1. Objective and scope

The project will test whether explicit semantic, temporal, service-dependency, supporting, and contradicting evidence helps a language model rank root-cause hypotheses for distributed-system incidents. The system is an engineering decision-support tool: a prediction is a hypothesis until it is checked against incident ground truth and corroborating telemetry.

A chronological edge, semantic similarity, dependency edge, high score, valid evidence package, or passing test is not by itself proof of causality. The evaluation must distinguish four different things: successful parsing, semantic grouping quality, evidence-package integrity, and RCA quality.

### Primary research question

**RQ:** Does an evidence-grounded approach improve the quality and traceability of LLM-based root-cause ranking compared with direct-LLM and semantic-only-LLM baselines under controlled conditions?

### Supporting questions

- **RQ1 — Semantic grouping:** How well do event clusters agree with independently defined semantic-group labels, where such labels exist?
- **RQ2 — Evidence integrity:** What fraction of constructed packages pass their schema and cross-reference invariants, and what fraction of event-ID references resolve to the canonical event store?
- **RQ3 — RCA quality:** On a labelled incident benchmark, how does root-cause ranking compare across the three approaches?
- **RQ4 — Reliability and cost:** How do unsupported claims, invalid event citations, structured-output failures, latency, token use, and estimated cost compare?
- **RQ5 — Robustness:** How does performance change with missing timestamps, irrelevant log noise, duplicated records, contradictory signals, and incomplete dependency information?

## 2. Hypotheses to test

These are falsifiable proposals, not findings.

- **H1 — Clustering:** On a suitable labelled dataset, the configured clustering pipeline will perform better than a shuffled-assignment baseline on the preregistered primary external clustering metric (ARI). NMI, homogeneity, completeness, V-measure, purity, and noise coverage are secondary metrics.
- **H2 — RCA quality:** On labelled incident cases, the evidence-grounded approach will improve the preregistered ranking metric (recommendation: MRR) versus direct LLM, with Top-1 accuracy and Recall@3 reported as secondary metrics. This cannot be tested until RCA predictions and incident-level labels are available.
- **H3 — Traceability:** Packages produced from the canonical EventStore will attain 100% valid event references on controlled test fixtures. Any non-100% result must be investigated and reported, not silently dropped.
- **H4 — Counterevidence handling:** Keeping contradictory evidence explicit will reduce the rate of incorrect unqualified hypotheses on a separately annotated evaluation set compared with a version that removes contradictory evidence. This requires claim-level annotation and both implementations.
- **H5 — Efficiency trade-off:** The full evidence-grounded method may incur additional preprocessing cost or context/token use. Report measured component and end-to-end latency and model usage rather than assuming that it is faster or slower.

Before comparing methods, record the evaluation cases, primary metric, prompt versions, model/version, generation settings, candidate-space definition, exclusions, and aggregation/statistical plan. Do not change the primary metric after seeing scores without documenting the change as exploratory.

## 3. Current implementation boundary

| Component | Code status in this handoff | Can be measured now? |
|---|---|---|
| Raw-line ingestion, parsing, normalization, stable event IDs | Implemented in `src/log_intelligence.py` | Yes: line accounting, failures, event/artifact checks |
| Template extraction and text embedding | Implemented; `tfidf_svd` backend works locally; sentence-transformer backend is configurable | Yes, subject to environment/model availability |
| Semantic clustering | Implemented | Yes: cluster counts/artifacts now; external scores only if suitable independent labels exist |
| Template/single-cluster/shuffled clustering baselines | Implemented in labelled pipeline evaluation | Yes, only with valid labels; not RCA baselines |
| Run manifest and artifact hashes | Implemented; Member 4 wrapper adds dataset/environment/run metadata | Yes |
| Temporal graph and consumer-to-provider dependency graph | Member 2 modules supplied separately and integrated into this handoff build | Yes, through graph tests/demonstration; not causal proof |
| EventStore, schemas, evidence builder, graph adapter | Implemented | Yes: schema validity and cross-reference tests |
| RCA ranking metric utilities | Added in `evaluation/metrics.py` | Yes with supplied rankings and root-cause ground truth; does not generate predictions |
| Direct LLM / semantic-only LLM / evidence-grounded LLM comparative runner | Not implemented as a complete experiment loop | No comparative RCA results yet |
| Production LLM generation, claim verification, provider token/cost telemetry | Not implemented end-to-end in the supplied snapshot | No claims about them yet |

The deterministic evidence builder packages relationships supplied by upstream code. It does not select the true root cause, infer that a relationship is causal, call an LLM, or validate a natural-language claim against external truth.

## 4. Data and benchmark strategy

Use separate task-appropriate datasets rather than forcing one dataset to answer every question.

### 4.1 Log-pipeline smoke evaluation

The LogHub collection contains multiple system-log datasets and has source-specific usage/citation instructions. The LogHub Linux sample is comparatively small (25,567 lines, 2.25 MiB as listed by the project's dataset table) and is a candidate for parser/event-artifact demonstration. It is not marked as labelled in the main collection table, so it should not be used to report ARI/NMI semantic grouping unless independently justified labels are obtained. [LogHub](https://github.com/logpai/loghub)

LogHub notes that some supplied logs may not be sanitized, anonymized, or modified. Treat text as potentially sensitive even when the file is public; check usage terms and redact any sensitive information before external processing or redistribution.

### 4.2 Root-cause benchmark candidate

RCAEval provides 735 failure cases across three benchmark suites and three microservice systems. Its RE2 suite comprises 270 multi-source cases, including logs, traces, and metrics, and benchmark annotations include root-cause service and an indicator. This is better aligned with incident-level RCA than anomaly-only labels. Sources: [RCAEval repository](https://github.com/phamquiluan/RCAEval), [versioned Zenodo record](https://zenodo.org/records/14590730), and [RCAEval paper/preprint](https://arxiv.org/abs/2412.17015).

RCAEval is not a drop-in raw log file for the current CLI. The team must document a conversion that preserves service, timestamp, incident boundaries, and label linkage; select and record a subset/case list; and ensure that case IDs are split without leakage. Do not treat `inject_time`, fault type, or anomaly indication as equivalent to a root-cause event unless that mapping is supported by the benchmark's definitions.

Dataset candidates, label semantics, size, source, and status are tracked in `docs/dataset_card.md`. No public dataset was included in the supplied ZIP. The bundled log fixture is synthetic and is only a test/demo input.

## 5. Baselines and fair comparison

All RCA baselines must run on the same incident cases and candidate-service/event space, be scored against the same labels, and use a common output schema. Use the same underlying model where practical, with documented prompt/input differences as the experimental treatment. Record truncation and context/token budgets, since evidence packages can change the amount of information given to the model.

- **B1 — Direct LLM:** Input raw/preprocessed incident logs; return ranked root-cause candidates and concise justifications with event references where available.
- **B2 — Semantic-only LLM:** Input the same incident's structured events and semantic groups, without temporal/dependency graph evidence; return the same output schema.
- **B3 — Evidence-grounded LLM:** Input structured events plus a validated package containing candidate IDs, supporting and contradicting evidence, relationship types/directions, and scores/provenance when supplied; return the same output schema.

If evidence verification is later evaluated, specify it as a separate ablation (for example B3 without verification versus B3 with verification) rather than quietly changing only one baseline. Current deterministic graph/evidence builders are preprocessing components, not an implemented RCA prediction system.

## 6. Metrics and definitions

### 6.1 Parsing / pipeline integrity

- **Line/event accounting:** record total, blank, continuation, successfully extracted event, partial event, and parse-failure counts from the run manifest.
- **Artifact integrity:** verify every declared artifact exists, is readable, and matches the manifest's SHA-256 digest.
- **Latency:** report repeated wall-clock measurements when comparing settings; list environment, input size, and run count. Do not equate one smoke-run runtime with a generalized performance claim.

### 6.2 Semantic grouping

The current implementation provides ARI, NMI, homogeneity, completeness, V-measure, purity, noise coverage, and purity excluding noise.

- **Primary:** ARI, adjusted for chance.
- **Secondary:** NMI, homogeneity, completeness, V-measure, purity.
- **Noise:** always report noise coverage and purity among non-noise records separately.
- **Baselines:** template identity, single cluster, and shuffled assignments, as provided by the pipeline.
- **Label rule:** use only records with valid independent semantic labels and report their coverage. Do not use test-derived templates/cluster IDs as their own independent ground truth.

Scikit-learn documents that ARI is adjusted for chance; NMI is not. For small/imbalanced samples, a random assignment can yield non-zero values for unadjusted information/entropy metrics, so ARI should be the principal external clustering score and other metrics secondary. See [scikit-learn clustering evaluation](https://scikit-learn.org/stable/modules/clustering.html).

### 6.3 Evidence integrity and quality

- **Schema-valid package rate:** packages passing declared schema and cross-field invariants divided by packages evaluated.
- **Package store-reference rate:** packages in which every event ID resolves to the canonical event store divided by packages evaluated.
- **Valid event-reference rate:** valid event-ID reference occurrences divided by total reference occurrences. Always include numerator and denominator.
- **Duplicate relationship rate:** duplicate relationship occurrences divided by relationship records, using a defined fingerprint that preserves endpoints, direction, type, candidate scope, polarity, and relation.
- **Evidence precision/recall and attribution correctness:** only report when evidence-item relevance/attribution has independent ground-truth annotation. Schema validity cannot measure evidential relevance.

Target 100% for package schema/store-reference checks on controlled tests; production/run results must still report actual counts and invalid cases.

### 6.4 RCA and LLM reliability (future stage)

- **Top-1 accuracy:** fraction of incidents where the first candidate matches any accepted gold root cause.
- **Top-k accuracy:** fraction of incidents with at least one correct gold root cause in the first k candidates.
- **Recall@k:** fraction of gold causes retrieved in the first k candidates; for single-gold cases, this matches Top-k accuracy.
- **MRR:** mean reciprocal rank of the first correct candidate; a miss contributes zero.
- **Unsupported-claim rate:** unsupported factual/cause claims divided by claims judged under a prewritten annotation rubric.
- **Invalid-citation rate:** evidence references in outputs that do not resolve to provided events divided by references emitted.
- **Schema failure rate:** outputs failing the specified output schema divided by outputs produced.

RCA ranking requires incident-level root-cause labels and ranked predictions. Unsupported-claim metrics require a labelled review rubric and preferably independent raters. If using two human annotators, report agreement and adjudication rules.

### 6.5 Efficiency

Record end-to-end runtime and stage runtimes, model name/revision, call count, input/output tokens, retry/error counts, and cost calculation basis where applicable. Do not infer token/cost metrics when no model is called. Report median and p95 over repeated cases, not only the mean; preserve the raw per-case values in machine-readable outputs.

## 7. Experimental procedure

### Stage A — Integration and smoke test

1. Record code commit, Python version, dependencies, and OS/hardware.
2. Run compilation and the full test suite. Save command, exit code, and output.
3. Confirm Member 2 modules are in the same branch before calling the demo end-to-end.
4. Run a small input, inspect parse failures, and verify `ingest.accounting_ok`.
5. Verify event IDs are stable under repeat runs with the same logical source name/input.
6. Check artifacts against `run_manifest.json` hashes and retain `experiment_manifest.json`.

### Stage B — Real log dataset

1. Record source/release/licence and compute the raw file checksum.
2. Inspect the parser's sample detection; document explicitly chosen parser if auto-detection is wrong.
3. Choose one primary text field (`template` or `message`) and record all embedding/clustering settings and random seeds.
4. Run ingestion/clustering, inspect events/clusters, count failures/partial events/unassigned clusters, and save all artifacts.
5. If suitable independent semantic labels exist, calculate cluster metrics and baselines; otherwise mark semantic scores `not available` rather than using synthetic labels.

### Stage C — Evidence validation

1. Construct a package from existing canonical events and graph links.
2. Verify every candidate ID, endpoint ID, support/contradiction summary, and score is consistent.
3. Test unknown IDs, duplicate links, contradictory signals, missing timestamps, equal timestamps, and dependency direction.
4. Save the serialized package and a metrics record containing denominators and rejected-package reasons.

### Stage D — RCA experiment (only after implementation)

1. Freeze dataset/case IDs, gold labels, candidates, prompts, model versions/settings, and primary metric before scoring.
2. Run B1/B2/B3 on identical cases; retain full raw outputs and normalized rankings.
3. Score Top-1, Top-3, Recall@k, MRR; measure unsupported claims and invalid citations with a written rubric.
4. Compare paired per-incident results. For formal claims, use paired bootstrap confidence intervals over incidents (and explain any repeated-run variability); avoid overclaiming when sample size is small.
5. Report negative and null results, failures/timeouts, excluded cases, and costs alongside successes.

## 8. Reproducibility requirements

Each run must retain:

- repository commit SHA and protocol version;
- dataset source/release, licence, exact filenames, checksums, split/case IDs, label definitions, and label coverage;
- Python/runtime/platform and resolved dependency versions or a lockfile;
- parser, text field, embedding backend/model/revision, clustering algorithm/parameters, and seeds;
- graph time window, dependency-direction convention/source, and edge thresholds;
- model/provider/version, prompt version, generation parameters, token usage, retries, and cost when applicable;
- elapsed time, parse failures, skipped metrics/reasons, output paths, raw metrics, and artifact hashes.

The standard pipeline `run_manifest.json` includes config/input/label hashes, ingestion accounting, selected environment versions, and hashes for generated artifacts. `experiments/run_experiments.py` supplements this with dataset provenance, run time, git commit if available, and measured-metric availability. A config hash alone does not guarantee bit-for-bit reproducibility across software/model/hardware versions.

## 9. Research-integrity and security rules

- Do not report empirical gains until each compared method has actually been run on the same cases.
- Do not use a public log's anomaly label to claim semantic grouping or RCA quality without a valid task/label mapping.
- Do not use synthetic examples as evidence of real-world performance.
- Do not treat the highest score as a calibrated probability unless calibration was independently assessed.
- Do not imply graph relations prove causality.
- Do not persist credentials, cookies, access tokens, personal data, or private infrastructure names in generated artifacts or external LLM requests. Logs are untrusted input and may carry prompt-injection strings.
- Report failures and missing measurements, not just successful outputs.

NIST's Generative AI Profile discusses confabulation and associated risks, including confidently stated incorrect content or citations; use independent output verification and human oversight as the future LLM stage is built. See [NIST AI 600-1](https://doi.org/10.6028/NIST.AI.600-1). For LLM-specific security threats, see the [OWASP Top 10 for LLM Applications 2025](https://genai.owasp.org/resource/owasp-top-10-for-llm-applications-2025/).

## 10. Review 1 acceptance criteria

The evaluation/methodology work is review-ready when the team can show:

1. A reproducible command to process a selected dataset and machine-readable artifacts plus run manifest.
2. Dataset provenance, licence/terms, label meanings, coverage, and known limitations.
3. Semantic scores only where proper labels exist; baseline scores generated from the same labelled records.
4. A traceable evidence package whose event IDs resolve to the canonical event store and whose summaries match its evidence items.
5. The three RCA baselines and metrics specified, with clear labels for “implemented,” “tested,” and “experimentally evaluated.”
6. A results table with true denominators, run configuration, and no fabricated RCA comparisons.
7. A diagram/timeline that labels temporal/dependency links as candidate evidence, not causal proof.

## 11. Current results statement

The bundled fixture `data/synthetic_review1_incident.log` is synthetic. It is suitable for reproducibility smoke tests, parser-artifact checks, and demonstration diagrams only. The public datasets described in `docs/dataset_card.md` were researched but not downloaded or executed in this handoff, because neither dataset was present in the supplied project ZIP and the environment could not retrieve the archive. Accordingly, this handoff makes **no real-dataset semantic-quality claim and no RCA-performance claim**. Replace this section with verified run numbers after the team executes the pipeline on the selected release.

## References

1. Scikit-learn, “Clustering performance evaluation.” https://scikit-learn.org/stable/modules/clustering.html
2. Zhu, J. et al. (2023), “Loghub: A Large Collection of System Log Datasets for AI-driven Log Analytics,” ISSRE. Dataset repository and citation guidance: https://github.com/logpai/loghub
3. Jiang, Z. et al. (2024), “A Large-scale Evaluation for Log Parsing Techniques: How Far are We?” ISSTA. https://arxiv.org/abs/2308.10828
4. Pham, L. et al., “RCAEval: A Benchmark for Root Cause Analysis of Microservice Systems with Telemetry Data.” https://arxiv.org/abs/2412.17015
5. OpenTelemetry, “Logs Data Model.” https://opentelemetry.io/docs/specs/otel/logs/data-model/
6. Autio, C. et al. (2024), NIST AI 600-1, “Artificial Intelligence Risk Management Framework: Generative Artificial Intelligence Profile.” https://doi.org/10.6028/NIST.AI.600-1
7. OWASP, “Top 10 for Large Language Model Applications 2025.” https://genai.owasp.org/resource/owasp-top-10-for-llm-applications-2025/
8. Python Packaging Authority, `pip-audit` usage and limitations. https://github.com/pypa/pip-audit
