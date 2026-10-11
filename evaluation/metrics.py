"""Evaluation metrics with explicit denominators and input validation.

These utilities measure clustering agreement, evidence-package/reference
integrity, RCA ranking (when ranked predictions and root-cause labels exist),
and latency. They do not infer causality and do not generate model predictions.

Clustering scores require semantic ground-truth labels. RCA ranking scores require
incident-level root-cause labels. Passing tests or validating evidence structures
is not a substitute for either form of ground truth.
"""
from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from statistics import mean, median
from typing import Any

from sklearn.metrics import (
    adjusted_rand_score,
    homogeneity_completeness_v_measure,
    normalized_mutual_info_score,
)


def _string_sequence(values: Sequence[str], name: str, *, allow_empty: bool = True) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{name} must be a sequence of strings, not a single string")
    result = list(values)
    if not allow_empty and not result:
        raise ValueError(f"{name} must not be empty")
    for index, value in enumerate(result):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name}[{index}] must be a non-blank string")
        if value != value.strip():
            raise ValueError(f"{name}[{index}] must not have surrounding whitespace")
    return result


def _purity(clusters: Sequence[str], labels: Sequence[str]) -> float:
    by_cluster: dict[str, Counter[str]] = {}
    for cluster_id, label in zip(clusters, labels):
        by_cluster.setdefault(cluster_id, Counter())[label] += 1
    return sum(max(counts.values()) for counts in by_cluster.values()) / len(labels)


def clustering_quality(
    ground_truth_labels: Sequence[str],
    predicted_cluster_ids: Sequence[str],
    *,
    noise_label: str | None = "noise",
) -> dict[str, Any]:
    """Score predicted clusters against available ground-truth grouping labels.

    ``noise_label`` points are treated as singleton clusters for ARI/NMI and the
    purity score, matching the project's existing ``score_partition`` convention.
    ``noise_coverage`` and ``purity_excluding_noise`` are reported separately so
    a method cannot hide a large noise fraction behind a high conditional score.
    Missing labels must be filtered by the caller and their coverage reported.
    """
    truth = _string_sequence(ground_truth_labels, "ground_truth_labels")
    predicted = _string_sequence(predicted_cluster_ids, "predicted_cluster_ids")
    if len(truth) != len(predicted):
        raise ValueError("ground_truth_labels and predicted_cluster_ids must have equal length")
    if noise_label is not None and (not isinstance(noise_label, str) or not noise_label.strip()):
        raise ValueError("noise_label must be a non-blank string or None")
    n = len(truth)
    if n == 0:
        return {
            "n_events": 0,
            "n_labels": 0,
            "n_clusters": 0,
            "adjusted_rand_index": None,
            "normalized_mutual_info": None,
            "homogeneity": None,
            "completeness": None,
            "v_measure": None,
            "purity": None,
            "noise_coverage": None,
            "purity_excluding_noise": None,
        }

    # Choose a private string namespace that cannot collide with caller labels.
    # This matters when noise points are scored as singleton clusters.
    private_prefix = "__evaluation_noise_singleton__"
    while any(cluster.startswith(private_prefix) for cluster in predicted):
        private_prefix = "_" + private_prefix
    evaluated_clusters = [
        f"{private_prefix}{index}"
        if noise_label is not None and cluster == noise_label
        else cluster
        for index, cluster in enumerate(predicted)
    ]
    homogeneity, completeness, v_measure = homogeneity_completeness_v_measure(
        truth, evaluated_clusters
    )
    non_noise_pairs = [
        (cluster, label)
        for cluster, label in zip(predicted, truth)
        if noise_label is None or cluster != noise_label
    ]
    n_non_noise = len(non_noise_pairs)
    non_noise_purity = (
        _purity(
            [cluster for cluster, _ in non_noise_pairs],
            [label for _, label in non_noise_pairs],
        )
        if n_non_noise
        else None
    )
    return {
        "n_events": n,
        "n_labels": len(set(truth)),
        "n_clusters": len(set(evaluated_clusters)),
        "adjusted_rand_index": float(adjusted_rand_score(truth, evaluated_clusters)),
        "normalized_mutual_info": float(normalized_mutual_info_score(truth, evaluated_clusters)),
        "homogeneity": float(homogeneity),
        "completeness": float(completeness),
        "v_measure": float(v_measure),
        "purity": float(_purity(evaluated_clusters, truth)),
        "noise_coverage": n_non_noise / n if noise_label is not None else 1.0,
        "purity_excluding_noise": float(non_noise_purity) if non_noise_purity is not None else None,
    }


def event_reference_integrity(
    referenced_event_ids: Iterable[str], known_event_ids: Iterable[str]
) -> dict[str, Any]:
    """Measure whether referenced event IDs resolve against a canonical event set.

    Duplicate references are counted as individual references: the denominator is
    the number of reference occurrences, not the number of unique IDs.
    """
    if isinstance(referenced_event_ids, (str, bytes)):
        raise TypeError("referenced_event_ids must be an iterable of IDs, not a single string")
    if isinstance(known_event_ids, (str, bytes)):
        raise TypeError("known_event_ids must be an iterable of IDs, not a single string")
    references = list(referenced_event_ids)
    known = set(_string_sequence(list(known_event_ids), "known_event_ids"))
    unknown: list[str] = []
    valid_count = 0
    for index, value in enumerate(references):
        if isinstance(value, str) and value.strip() and value == value.strip() and value in known:
            valid_count += 1
        else:
            if isinstance(value, str):
                unknown.append(value)
            else:
                unknown.append(f"<invalid-type:{type(value).__name__}>@{index}")
    total = len(references)
    return {
        "n_references": total,
        "n_valid_references": valid_count,
        "n_invalid_references": total - valid_count,
        "valid_event_reference_rate": valid_count / total if total else None,
        "unknown_or_invalid_event_ids": sorted(set(unknown)),
    }


def package_validity_summary(valid_flags: Sequence[bool]) -> dict[str, Any]:
    """Summarize package-level validation outcomes with visible denominators."""
    flags = list(valid_flags)
    for index, flag in enumerate(flags):
        if type(flag) is not bool:
            raise TypeError(f"valid_flags[{index}] must be bool")
    valid_count = sum(flags)
    total = len(flags)
    return {
        "n_packages_evaluated": total,
        "n_valid_packages": valid_count,
        "n_invalid_packages": total - valid_count,
        "valid_package_rate": valid_count / total if total else None,
    }


def evidence_package_integrity(
    packages: Sequence[Any], known_event_ids: Iterable[str]
) -> dict[str, Any]:
    """Validate evidence packages and measure ID references against the event store.

    ``packages`` may contain ``EvidencePackage`` instances or their JSON-compatible
    mappings. Pydantic schema/cross-field validation is applied to mappings. Event
    existence is checked separately because an otherwise schema-valid package can
    still refer to an ID absent from the canonical event store.

    Validation errors are summarized by exception class only so this report does
    not accidentally persist log contents or sensitive validator values.
    """
    from pydantic import ValidationError
    from src.evidence.schemas import EvidencePackage

    known = set(_string_sequence(list(known_event_ids), "known_event_ids"))
    valid_packages = 0
    schema_valid_package_refs: list[str] = []
    relationships: list[tuple[str, str, str, str, str, str]] = []
    error_types: Counter[str] = Counter()
    package_reference_status: list[bool] = []
    unknown_ids: set[str] = set()

    for item in packages:
        try:
            package = item if isinstance(item, EvidencePackage) else EvidencePackage.model_validate(item)
        except (ValidationError, TypeError, ValueError):
            error_types["schema_or_type_validation_error"] += 1
            package_reference_status.append(False)
            continue

        valid_packages += 1
        refs_for_package: list[str] = []
        for candidate in package.candidates:
            refs_for_package.extend([candidate.candidate_event_id, candidate.candidate.event_id])
            refs_for_package.extend(candidate.supporting_events)
            refs_for_package.extend(candidate.contradicting_events)
            for evidence in candidate.evidence_items:
                refs_for_package.extend([
                    evidence.source_event_id,
                    evidence.target_event_id,
                    evidence.candidate_event_id,
                    evidence.event_id,
                ])
                relationships.append((
                    evidence.candidate_event_id,
                    evidence.source_event_id,
                    evidence.target_event_id,
                    evidence.evidence_type.value,
                    evidence.polarity,
                    evidence.relation,
                ))
        schema_valid_package_refs.extend(refs_for_package)
        missing = {ref for ref in refs_for_package if ref not in known}
        unknown_ids.update(missing)
        package_reference_status.append(not missing)

    package_count = len(packages)
    # Duplicate signatures preserve direction, candidate scope, type, polarity and
    # relation text. An intentional opposing-polarity item is not a duplicate.
    relationship_counts = Counter(relationships)
    duplicate_occurrences = sum(count - 1 for count in relationship_counts.values() if count > 1)
    reference_metrics = event_reference_integrity(schema_valid_package_refs, known)
    valid_store_packages = sum(package_reference_status)
    return {
        "n_packages_evaluated": package_count,
        "n_schema_valid_packages": valid_packages,
        "n_schema_invalid_packages": package_count - valid_packages,
        "schema_valid_package_rate": valid_packages / package_count if package_count else None,
        "n_packages_with_all_event_ids_in_store": valid_store_packages,
        "package_store_reference_rate": valid_store_packages / package_count if package_count else None,
        "event_references": reference_metrics,
        "n_relationship_records": len(relationships),
        "n_duplicate_relationship_occurrences": duplicate_occurrences,
        "duplicate_relationship_rate": (
            duplicate_occurrences / len(relationships) if relationships else None
        ),
        "unknown_event_ids": sorted(unknown_ids),
        "validation_error_types": dict(sorted(error_types.items())),
    }


def _normalise_truth_causes(value: str | Sequence[str], incident_index: int) -> set[str]:
    if isinstance(value, str):
        causes = [value]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        causes = list(value)
    else:
        raise TypeError(f"ground_truth_causes[{incident_index}] must be a string or sequence of strings")
    if not causes:
        raise ValueError(f"ground_truth_causes[{incident_index}] must not be empty")
    validated = _string_sequence(causes, f"ground_truth_causes[{incident_index}]", allow_empty=False)
    if len(set(validated)) != len(validated):
        raise ValueError(f"ground_truth_causes[{incident_index}] contains duplicates")
    return set(validated)


def ranked_root_cause_metrics(
    ranked_predictions: Sequence[Sequence[str]],
    ground_truth_causes: Sequence[str | Sequence[str]],
    *,
    ks: Sequence[int] = (1, 3),
) -> dict[str, Any]:
    """Measure ranking quality against incident-level root-cause labels.

    Top-k accuracy is 1 when at least one labelled true cause occurs in the first
    k unique ranked candidates. Recall@k is the fraction of the incident's labelled
    true-cause set retrieved in the top k. For a single-label benchmark they match.
    Empty rankings contribute zero instead of being silently dropped.
    """
    if isinstance(ranked_predictions, (str, bytes)):
        raise TypeError("ranked_predictions must be a sequence of ranked candidate sequences")
    if isinstance(ground_truth_causes, (str, bytes)):
        raise TypeError("ground_truth_causes must be a sequence with one entry per incident")
    predictions = list(ranked_predictions)
    truth_values = list(ground_truth_causes)
    if len(predictions) != len(truth_values):
        raise ValueError("ranked_predictions and ground_truth_causes must have equal length")
    validated_ks: list[int] = []
    for index, k in enumerate(ks):
        if isinstance(k, bool) or not isinstance(k, int) or k < 1:
            raise ValueError(f"ks[{index}] must be a positive integer")
        if k not in validated_ks:
            validated_ks.append(k)
    if not validated_ks:
        raise ValueError("ks must contain at least one positive integer")

    total = len(predictions)
    hits_by_k = {k: 0 for k in validated_ks}
    recalls_by_k = {k: [] for k in validated_ks}
    reciprocal_ranks: list[float] = []
    exact_top1 = 0
    for index, (ranking_value, truth_value) in enumerate(zip(predictions, truth_values)):
        if isinstance(ranking_value, (str, bytes)):
            raise TypeError(f"ranked_predictions[{index}] must be a sequence, not a string")
        ranking = _string_sequence(list(ranking_value), f"ranked_predictions[{index}]")
        if len(set(ranking)) != len(ranking):
            raise ValueError(f"ranked_predictions[{index}] contains duplicate candidates")
        truths = _normalise_truth_causes(truth_value, index)
        first_rank = next((rank for rank, candidate in enumerate(ranking, start=1) if candidate in truths), None)
        reciprocal_ranks.append(1.0 / first_rank if first_rank is not None else 0.0)
        if ranking and ranking[0] in truths:
            exact_top1 += 1
        for k in validated_ks:
            found = set(ranking[:k]) & truths
            if found:
                hits_by_k[k] += 1
            recalls_by_k[k].append(len(found) / len(truths))

    def rate(numerator: int) -> float | None:
        return numerator / total if total else None

    return {
        "n_incidents": total,
        "top_1_accuracy": rate(exact_top1),
        "mean_reciprocal_rank": mean(reciprocal_ranks) if reciprocal_ranks else None,
        "top_k_accuracy": {str(k): rate(hits_by_k[k]) for k in validated_ks},
        "recall_at_k": {
            str(k): mean(recalls_by_k[k]) if recalls_by_k[k] else None for k in validated_ks
        },
        "evaluated_k": validated_ks,
    }


def latency_summary_ms(samples_ms: Sequence[float]) -> dict[str, Any]:
    """Return mean/median/p95 latency; empty inputs report nulls, not zero latency."""
    samples = list(samples_ms)
    numeric: list[float] = []
    for index, value in enumerate(samples):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"samples_ms[{index}] must be numeric")
        number = float(value)
        if not math.isfinite(number) or number < 0:
            raise ValueError(f"samples_ms[{index}] must be finite and non-negative")
        numeric.append(number)
    if not numeric:
        return {"n_samples": 0, "mean_ms": None, "median_ms": None, "p95_ms": None, "min_ms": None, "max_ms": None}
    sorted_values = sorted(numeric)
    # Nearest-rank p95: transparent and well-defined for small samples.
    p95_index = max(0, math.ceil(0.95 * len(sorted_values)) - 1)
    return {
        "n_samples": len(numeric),
        "mean_ms": mean(numeric),
        "median_ms": median(numeric),
        "p95_ms": sorted_values[p95_index],
        "min_ms": sorted_values[0],
        "max_ms": sorted_values[-1],
    }
