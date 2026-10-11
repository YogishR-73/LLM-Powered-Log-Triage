# Dataset Card and Selection Decision

**Owner:** Member 4 — Evaluation & System  
**Protocol version:** 1.0  
**Status:** Dataset candidates researched; no public dataset is bundled in this repository snapshot. The only bundled log is a clearly labelled synthetic smoke-test fixture. Do not report it as real-world evidence.

## 1. Why one dataset is not enough for every research question

The project has two distinct data needs:

1. **Log pipeline and semantic grouping:** raw log lines that can be parsed into events; semantic ground-truth group labels are required before ARI/NMI/homogeneity/completeness can be reported as semantic-grouping performance.
2. **Root-cause analysis:** incident cases with defensible root-cause labels (preferably a labelled root-cause service and indicator) and enough telemetry to build temporal/dependency evidence. An anomaly label, event template, severity, or service name is not a root-cause label.

Do not conflate these tasks or transfer labels between them without an explicit, reviewed mapping.

## 2. Recommended dataset plan

### A. LogHub Linux — practical ingestion/parser smoke evaluation

- **Official source:** https://github.com/logpai/loghub (download table links to Zenodo record 8196385).
- **Description reported by LogHub:** Linux system logs.
- **Size reported by the repository:** 25,567 log lines, 2.25 MiB.
- **Label availability reported by LogHub:** not marked as labelled in its main dataset table.
- **Primary use:** ingestion, parser choice, normalization, event IDs, clustering artifact generation, parse-failure accounting, and runtime measurements.
- **Not justified by itself:** external semantic clustering quality without independently defined semantic group labels; incident-level RCA accuracy.
- **Status in this handoff:** recommended, not downloaded or run. A reproducible run must record the exact file checksum and download URL after retrieval.

LogHub states that some source datasets may not be sanitized, anonymized, or modified. Treat logs as potentially sensitive even when obtained from a public research collection. See the source's usage and citation instructions before redistribution.

### B. RCAEval RE2 — recommended later RCA benchmark

- **Official project:** https://github.com/phamquiluan/RCAEval
- **Versioned dataset record:** https://zenodo.org/records/14590730
- **Paper/preprint:** https://arxiv.org/abs/2412.17015
- **Published benchmark summary:** the current project repository describes nine datasets grouped into RE1/RE2/RE3, with 735 failure cases across three microservice systems and 11 fault types overall. RE2 comprises 270 cases (90 each for Online Boutique, Sock Shop, and Train Ticket); its cases include metrics and logs, while trace availability varies by system/case. The benchmark documents root-cause service and root-cause indicator annotations.
- **Primary use:** later incident-level RCA ranking evaluation; RE2 is more aligned with the evidence-grounded microservice RCA goal than anomaly-only log data.
- **Hosting/resource note:** the current project README recommends a Hugging Face Parquet copy (reported as 3.4 GB on disk) with a `cases.parquet` index to inspect case IDs/labels and select suite(s) or cases. The full original archive set is reported as about 5.2 GB compressed and about 38 GB extracted. Check those details against the chosen release at retrieval time.
- **Integration caveat:** RCAEval records are not a drop-in raw text file for this repository's `src.log_intelligence` CLI. The team must define a reviewed conversion from `logs.csv` to raw lines/canonical events and preserve incident boundaries, timestamps, service fields, and label linkage. The current `LogEvent` schema does not define first-class `TraceId`/`SpanId` fields; preserve trace-correlation fields in documented attributes or agree an explicit schema extension with Member 1 rather than silently dropping them. Keep train/dev/test splits grouped by incident/case to prevent leakage.
- **Resource caveat:** prefer a documented subset of RE2 cases to avoid a full bulk download, if the hosting format supports it. Store the exact selected case IDs; do not describe a subset as the entire benchmark.
- **Status in this handoff:** recommended, not downloaded or evaluated. No RCA score is claimed.

## 3. Label eligibility rules

| Label type | Valid use | Invalid inference |
|---|---|---|
| Event template / semantic category | External evaluation of semantic grouping if labels were assigned independently from the tested cluster result | Root-cause labels |
| Normal/anomalous | Anomaly detection/separation evaluation under its dataset definition | Root cause of an incident |
| Service identifier | Grouping/filtering by service; candidate/root-cause target only if the benchmark labels the correct root-cause service | Evidence that the service caused a failure by itself |
| Fault injection type and time | Slice analyses around the known injection and score the annotated benchmark target | Proof that the most temporally prior event caused an incident |
| Root-cause service/indicator | Incident-level ranking evaluation if the benchmark documents its meaning and mapping | Automatically accurate log-event attribution without a validated event mapping |

## 4. Required record for any chosen dataset

Fill every field before publishing a result:

- Dataset name and task-specific subset:
- Original source URL and release/commit/DOI:
- Download date (UTC):
- Licence/usage terms, redistribution decision:
- Exact file names and SHA-256 hashes:
- Number of raw lines / records / incidents:
- Data fields and label definitions:
- Label coverage, excluded or unlabelled records:
- Parser choice, text field, normalization and truncation:
- Ground-truth mapping and independent origin:
- Split procedure and leakage safeguards:
- Sensitive-data review/redaction decision:
- Known representativeness/annotation limitations:

## 5. Citation and usage

For LogHub, cite J. Zhu et al., “Loghub: A Large Collection of System Log Datasets for AI-driven Log Analytics,” ISSRE 2023, and follow the repository's source-specific citation/usage guidance. For RCAEval, cite L. Pham et al., “RCAEval: A Benchmark for Root Cause Analysis of Microservice Systems with Telemetry Data,” and the exact versioned dataset record used. Citations and licences must be checked against the selected release when it is downloaded.

## 6. Current package contents

The bundled `data/synthetic_review1_incident.log` is a synthetic smoke-test fixture generated for this repository. It has no external provenance, no official ground-truth semantic labels, and no validated causal truth. It may be used to demonstrate artifact generation and test parsing, but it must not be included in real-dataset statistics or used to claim RCA accuracy.
