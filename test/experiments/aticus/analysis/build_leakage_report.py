#!/usr/bin/env python3
"""Build a comparative HTML leakage audit report for ATICUS F05 variants."""

from __future__ import annotations

import argparse
import ast
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Iterable

from collections import Counter

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml


LOGGER = logging.getLogger("build_leakage_report")
PIPELINE_ORDER = ["synchro_all", "synchro_auto", "synchro_none", "asynOW_none"]
PHASE_DIR_MAP = {
    "f05": "f05_modeling",
    "f05_modeling": "f05_modeling",
}


@dataclass
class ArtifactBundle:
    """Resolved files for one experiment variant."""

    variant_dir: Path
    outputs_yaml: Path | None = None
    leakage_json: Path | None = None
    split_dataset: Path | None = None
    training_dataset: Path | None = None


@dataclass
class ConfigAudit:
    """All information needed to render one configuration block."""

    manifest_row: dict[str, Any]
    variant: str
    pipeline: str
    status: str
    variant_dir: Path | None = None
    outputs: dict[str, Any] = field(default_factory=dict)
    leakage_report: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    interpretation: list[str] = field(default_factory=list)
    derived_metrics: dict[str, Any] = field(default_factory=dict)
    top_tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    error_message: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a comparative ATICUS leakage audit report.")
    parser.add_argument("--manifest", required=True, help="Path to manifest CSV.")
    parser.add_argument("--output-html", required=True, help="Path to output HTML file.")
    parser.add_argument("--output-dir", default=None, help="Directory where figures and auxiliary files will be written.")
    parser.add_argument("--title", default="Leakage audit report", help="Title shown in the HTML report.")
    parser.add_argument("--log-level", default="INFO", help="Logging level. Example: INFO, DEBUG.")
    return parser.parse_args()


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, str(level).upper(), logging.INFO),
        format="[%(levelname)s] %(message)s",
    )


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[4]


def load_manifest(manifest_path: Path) -> pd.DataFrame:
    """Load and normalize the manifest CSV."""
    df = pd.read_csv(manifest_path)
    df.columns = [str(col).strip() for col in df.columns]
    if "phase" in df.columns:
        df["phase"] = df["phase"].astype(str).str.strip()
    if "pipeline" in df.columns:
        df["pipeline"] = df["pipeline"].astype(str).str.strip()
    return df


def select_target_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Keep F05 rows, preserving the preferred pipeline order when possible."""
    if "phase" in df.columns:
        df = df[df["phase"].astype(str).isin({"f05", "f05_modeling"})].copy()
    if "pipeline" in df.columns:
        df["pipeline_order"] = df["pipeline"].map({name: idx for idx, name in enumerate(PIPELINE_ORDER)}).fillna(999)
        df = df.sort_values(["pipeline_order", "pipeline", "variant"]).drop(columns=["pipeline_order"])
    return df.reset_index(drop=True)


def phase_dir_name(phase_value: str) -> str:
    value = str(phase_value).strip()
    return PHASE_DIR_MAP.get(value, value)


def safe_yaml_load(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def resolve_variant_artifacts(row: dict[str, Any], repo_root: Path) -> ArtifactBundle:
    """Resolve the most useful artifacts for one manifest row."""
    phase_name = phase_dir_name(row.get("phase", "f05"))
    variant = str(row["variant"]).strip()
    variant_dir = repo_root / "executions" / phase_name / variant
    if not variant_dir.exists():
        raise FileNotFoundError(f"Variant directory not found: {variant_dir}")

    bundle = ArtifactBundle(variant_dir=variant_dir)
    outputs_yaml = variant_dir / "outputs.yaml"
    if outputs_yaml.exists():
        bundle.outputs_yaml = outputs_yaml
        outputs = safe_yaml_load(outputs_yaml)
        artifacts = outputs.get("artifacts", {})
        leakage_rel = artifacts.get("split_hash_leakage", {}).get("path")
        if leakage_rel:
            leakage_candidate = variant_dir / leakage_rel
            if leakage_candidate.exists():
                bundle.leakage_json = leakage_candidate
        dataset_rel = artifacts.get("labeled_dataset", {}).get("path")
        if dataset_rel:
            dataset_candidate = variant_dir / dataset_rel
            if dataset_candidate.exists():
                bundle.training_dataset = dataset_candidate

    if bundle.leakage_json is None:
        fallback = variant_dir / "05_modeling_split_hash_leakage.json"
        if fallback.exists():
            bundle.leakage_json = fallback

    if bundle.training_dataset is None:
        fallback = variant_dir / "05_modeling_training_dataset.parquet"
        if fallback.exists():
            bundle.training_dataset = fallback

    split_candidates = list(variant_dir.glob("*split*.parquet")) + list(variant_dir.glob("*split*.csv"))
    for candidate in split_candidates:
        if candidate.is_file():
            bundle.split_dataset = candidate
            break

    return bundle


def normalize_events(value: Any) -> tuple[int, ...]:
    """Normalize OW_events from native lists, ndarrays or serialized strings."""
    if value is None:
        return tuple()
    if isinstance(value, np.ndarray):
        return tuple(int(v) for v in value.tolist())
    if isinstance(value, (list, tuple)):
        return tuple(int(v) for v in value)
    text = str(value).strip()
    if text == "":
        return tuple()
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(text)
            if isinstance(parsed, (list, tuple)):
                return tuple(int(v) for v in parsed)
        except Exception:
            continue
    text = text.strip("[]")
    if not text:
        return tuple()
    parts = [chunk.strip() for chunk in text.replace(";", ",").split(",") if chunk.strip()]
    return tuple(int(part) for part in parts)


def build_exact_key(events: tuple[int, ...]) -> str:
    return json.dumps(list(events), separators=(",", ":"))


def build_unordered_key(events: tuple[int, ...]) -> str:
    counter = Counter(events)
    return "|".join(f"{key}:{counter[key]}" for key in sorted(counter))


def build_label_profile(neg_count: int, pos_count: int) -> str:
    if pos_count > 0 and neg_count == 0:
        return "only_positive"
    if neg_count > 0 and pos_count == 0:
        return "only_negative"
    return "mixed_labels"


def compute_split_label_summary(df: pd.DataFrame, key_col: str) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for split_name, group in df.groupby("split"):
        key_label_counts = group.groupby([key_col, "label"]).size().unstack(fill_value=0)
        pos_col = key_label_counts[1] if 1 in key_label_counts.columns else pd.Series(0, index=key_label_counts.index)
        neg_col = key_label_counts[0] if 0 in key_label_counts.columns else pd.Series(0, index=key_label_counts.index)
        summary[split_name] = {
            "only_negative": int(((neg_col > 0) & (pos_col == 0)).sum()),
            "only_positive": int(((pos_col > 0) & (neg_col == 0)).sum()),
            "mixed_labels": int(((pos_col > 0) & (neg_col > 0)).sum()),
        }
    return summary


def compute_intersection_report(
    left_split: str,
    right_split: str,
    split_keys: dict[str, set[str]],
    key_label_counts: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    shared_keys = split_keys[left_split] & split_keys[right_split]
    label_breakdown = {"only_negative": 0, "only_positive": 0, "mixed_labels": 0}
    for key in shared_keys:
        left_neg = int(key_label_counts[left_split].get(0, pd.Series(dtype=int)).get(key, 0))
        left_pos = int(key_label_counts[left_split].get(1, pd.Series(dtype=int)).get(key, 0))
        right_neg = int(key_label_counts[right_split].get(0, pd.Series(dtype=int)).get(key, 0))
        right_pos = int(key_label_counts[right_split].get(1, pd.Series(dtype=int)).get(key, 0))
        label_breakdown[build_label_profile(left_neg + right_neg, left_pos + right_pos)] += 1
    return {
        "shared_keys_count": int(len(shared_keys)),
        "shared_keys": sorted(shared_keys),
        "pct_of_left": float(len(shared_keys) / len(split_keys[left_split])) if split_keys[left_split] else 0.0,
        "pct_of_right": float(len(shared_keys) / len(split_keys[right_split])) if split_keys[right_split] else 0.0,
        "label_breakdown": label_breakdown,
        "left_split": left_split,
        "right_split": right_split,
    }


def compute_overlap_section(df: pd.DataFrame, key_col: str, key_name: str) -> dict[str, Any]:
    split_keys: dict[str, set[str]] = {}
    split_counts: dict[str, pd.Series] = {}
    key_label_counts: dict[str, pd.DataFrame] = {}
    for split_name, group in df.groupby("split"):
        keys = group[key_col].astype(str)
        split_keys[split_name] = set(keys.tolist())
        split_counts[split_name] = keys.value_counts()
        key_label_counts[split_name] = group.groupby([key_col, "label"]).size().unstack(fill_value=0)

    pair_intersections = {}
    summary_rows = []
    for left_split, right_split in [("train", "val"), ("train", "test"), ("val", "test")]:
        if left_split not in split_keys or right_split not in split_keys:
            continue
        report = compute_intersection_report(left_split, right_split, split_keys, key_label_counts)
        pair_name = f"{left_split}_{right_split}"
        pair_intersections[pair_name] = report
        summary_rows.append(
            {
                "pair": pair_name,
                "shared_keys": report["shared_keys_count"],
                "pct_of_left": report["pct_of_left"],
                "pct_of_right": report["pct_of_right"],
                "left_split": left_split,
                "right_split": right_split,
                **report["label_breakdown"],
            }
        )

    all_three = split_keys.get("train", set()) & split_keys.get("val", set()) & split_keys.get("test", set())
    triple_counts = {"only_negative": 0, "only_positive": 0, "mixed_labels": 0}
    for key in all_three:
        neg_total = 0
        pos_total = 0
        for split_name in ("train", "val", "test"):
            neg_total += int(key_label_counts[split_name].get(0, pd.Series(dtype=int)).get(key, 0))
            pos_total += int(key_label_counts[split_name].get(1, pd.Series(dtype=int)).get(key, 0))
        triple_counts[build_label_profile(neg_total, pos_total)] += 1
    triple_intersection = {
        "shared_keys_count": int(len(all_three)),
        "shared_keys": sorted(all_three),
        "pct_of_train": float(len(all_three) / len(split_keys.get("train", set()))) if split_keys.get("train") else 0.0,
        "pct_of_val": float(len(all_three) / len(split_keys.get("val", set()))) if split_keys.get("val") else 0.0,
        "pct_of_test": float(len(all_three) / len(split_keys.get("test", set()))) if split_keys.get("test") else 0.0,
        "label_breakdown": triple_counts,
    }
    summary_rows.append(
        {
            "pair": "train_val_test",
            "shared_keys": triple_intersection["shared_keys_count"],
            "pct_of_left": triple_intersection["pct_of_train"],
            "pct_of_right": triple_intersection["pct_of_test"],
            "left_split": "train",
            "right_split": "test",
            **triple_counts,
        }
    )

    top_keys = sorted(
        set().union(*(set(report["shared_keys"]) for report in pair_intersections.values())),
    )
    top_shared_rows = []
    for key in top_keys:
        train_count = int(split_counts.get("train", pd.Series(dtype=int)).get(key, 0))
        val_count = int(split_counts.get("val", pd.Series(dtype=int)).get(key, 0))
        test_count = int(split_counts.get("test", pd.Series(dtype=int)).get(key, 0))
        train_neg = int(key_label_counts.get("train", pd.DataFrame()).get(0, pd.Series(dtype=int)).get(key, 0))
        train_pos = int(key_label_counts.get("train", pd.DataFrame()).get(1, pd.Series(dtype=int)).get(key, 0))
        val_neg = int(key_label_counts.get("val", pd.DataFrame()).get(0, pd.Series(dtype=int)).get(key, 0))
        val_pos = int(key_label_counts.get("val", pd.DataFrame()).get(1, pd.Series(dtype=int)).get(key, 0))
        test_neg = int(key_label_counts.get("test", pd.DataFrame()).get(0, pd.Series(dtype=int)).get(key, 0))
        test_pos = int(key_label_counts.get("test", pd.DataFrame()).get(1, pd.Series(dtype=int)).get(key, 0))
        preview = df.loc[df[key_col] == key, "events_preview"].iloc[0]
        top_shared_rows.append(
            {
                "key": key,
                "key_type": key_name,
                "label_profile": build_label_profile(train_neg + val_neg + test_neg, train_pos + val_pos + test_pos),
                "train_count": train_count,
                "train_neg_count": train_neg,
                "train_pos_count": train_pos,
                "val_count": val_count,
                "val_neg_count": val_neg,
                "val_pos_count": val_pos,
                "test_count": test_count,
                "test_neg_count": test_neg,
                "test_pos_count": test_pos,
                "total_count": train_count + val_count + test_count,
                "n_splits_present": int(sum(v > 0 for v in [train_count, val_count, test_count])),
                "events_preview": preview,
            }
        )
    top_shared_rows = sorted(
        top_shared_rows,
        key=lambda row: (-row["n_splits_present"], -row["total_count"], row["key"]),
    )[:20]

    max_overlap_pct = 0.0
    for pair_data in pair_intersections.values():
        max_overlap_pct = max(max_overlap_pct, pair_data["pct_of_left"], pair_data["pct_of_right"])
    max_overlap_pct = max(
        max_overlap_pct,
        triple_intersection["pct_of_train"],
        triple_intersection["pct_of_val"],
        triple_intersection["pct_of_test"],
    )
    return {
        "key_name": key_name,
        "split_sizes_unique_keys": {
            f"n_{key_name}_train": int(len(split_keys.get("train", set()))),
            f"n_{key_name}_val": int(len(split_keys.get("val", set()))),
            f"n_{key_name}_test": int(len(split_keys.get("test", set()))),
        },
        "split_label_summary": compute_split_label_summary(df, key_col),
        "pair_intersections": pair_intersections,
        "triple_intersection": triple_intersection,
        "summary_rows": summary_rows,
        "top_shared_keys": top_shared_rows,
        "possible_leakage": bool(any(item["shared_keys_count"] > 0 for item in pair_intersections.values())),
        "high_leakage_warning": bool(triple_intersection["shared_keys_count"] > 0 or max_overlap_pct >= 0.01),
        "max_overlap_pct": float(max_overlap_pct),
    }


def counter_similarity(counter_a: Counter[int], counter_b: Counter[int]) -> float:
    keys = set(counter_a) | set(counter_b)
    if not keys:
        return 1.0
    numerator = sum(min(counter_a.get(key, 0), counter_b.get(key, 0)) for key in keys)
    denominator = sum(max(counter_a.get(key, 0), counter_b.get(key, 0)) for key in keys)
    return float(numerator / denominator) if denominator else 0.0


def compute_near_duplicates(df: pd.DataFrame, threshold: float = 0.80, top_k_examples: int = 20) -> dict[str, Any]:
    unique_df = (
        df[["split", "label", "exact_key", "unordered_key", "seq_len", "events_counter", "events_preview"]]
        .drop_duplicates(subset=["split", "exact_key", "label"])
        .reset_index(drop=True)
    )
    pairwise: dict[str, dict[str, Any]] = {}
    near_pairs: list[dict[str, Any]] = []
    for left_split, right_split in [("train", "val"), ("train", "test"), ("val", "test")]:
        left_df = unique_df[unique_df["split"] == left_split]
        right_df = unique_df[unique_df["split"] == right_split]
        pairs: list[dict[str, Any]] = []
        for seq_len, left_group in left_df.groupby("seq_len"):
            right_group = right_df[right_df["seq_len"] == seq_len]
            if right_group.empty:
                continue
            for _, left_row in left_group.iterrows():
                for _, right_row in right_group.iterrows():
                    if left_row["unordered_key"] == right_row["unordered_key"]:
                        continue
                    similarity = counter_similarity(left_row["events_counter"], right_row["events_counter"])
                    if similarity < threshold:
                        continue
                    if int(left_row["label"]) == 1 and int(right_row["label"]) == 1:
                        label_profile = "only_positive"
                    elif int(left_row["label"]) == 0 and int(right_row["label"]) == 0:
                        label_profile = "only_negative"
                    else:
                        label_profile = "mixed_labels"
                    pairs.append(
                        {
                            "left_split": left_split,
                            "right_split": right_split,
                            "left_label": int(left_row["label"]),
                            "right_label": int(right_row["label"]),
                            "label_profile": label_profile,
                            "similarity_score": float(similarity),
                            "seq_len": int(seq_len),
                            "left_exact_key": left_row["exact_key"],
                            "right_exact_key": right_row["exact_key"],
                            "left_preview": left_row["events_preview"],
                            "right_preview": right_row["events_preview"],
                        }
                    )
        pairs = sorted(pairs, key=lambda row: (-row["similarity_score"], row["left_exact_key"], row["right_exact_key"]))
        pair_key = f"{left_split}_{right_split}"
        pairwise[pair_key] = {
            "n_pairs": int(len(pairs)),
            "n_only_negative": int(sum(item["label_profile"] == "only_negative" for item in pairs)),
            "n_only_positive": int(sum(item["label_profile"] == "only_positive" for item in pairs)),
            "n_mixed_labels": int(sum(item["label_profile"] == "mixed_labels" for item in pairs)),
            "examples": pairs[:top_k_examples],
        }
        near_pairs.extend(pairs)
    return {
        "threshold": float(threshold),
        "similarity_definition": "sum(min(count_a[e], count_b[e])) / sum(max(count_a[e], count_b[e]))",
        "candidate_strategy": {
            "base_unit": "unique exact sequences per split+label",
            "same_length_only": True,
            "unordered_duplicates_excluded": True,
        },
        "pairwise": pairwise,
        "n_total_pairs": int(len(near_pairs)),
        "max_similarity": float(max((row["similarity_score"] for row in near_pairs), default=0.0)),
    }


def preview_events(events: tuple[int, ...], max_items: int = 12) -> str:
    if not events:
        return "[]"
    head = ", ".join(str(v) for v in events[:max_items])
    suffix = ", ..." if len(events) > max_items else ""
    return f"[{head}{suffix}]"


def load_split_dataset(bundle: ArtifactBundle) -> pd.DataFrame:
    """Fallback loader for datasets with split, label and OW_events columns."""
    candidates = [bundle.split_dataset, bundle.training_dataset]
    for candidate in candidates:
        if candidate is None or not candidate.exists():
            continue
        if candidate.suffix.lower() == ".parquet":
            df = pd.read_parquet(candidate)
        elif candidate.suffix.lower() == ".csv":
            df = pd.read_csv(candidate)
        else:
            continue
        normalized_cols = {str(col).strip().lower(): col for col in df.columns}
        if "split" not in normalized_cols or "ow_events" not in normalized_cols or "label" not in normalized_cols:
            continue
        out = pd.DataFrame(
            {
                "split": df[normalized_cols["split"]].astype(str).str.strip().str.lower(),
                "label": df[normalized_cols["label"]].astype(int),
                "OW_events": df[normalized_cols["ow_events"]],
            }
        )
        return out
    raise FileNotFoundError("No split dataset with columns split, label and OW_events was found.")


def build_report_from_dataset(df: pd.DataFrame) -> dict[str, Any]:
    """Recompute leakage if the precomputed F05 JSON is not available."""
    work = df.copy()
    work["sequence"] = work["OW_events"].apply(normalize_events)
    work["exact_key"] = work["sequence"].apply(build_exact_key)
    work["unordered_key"] = work["sequence"].apply(build_unordered_key)
    work["events_counter"] = work["sequence"].apply(Counter)
    work["seq_len"] = work["sequence"].apply(len)
    work["events_preview"] = work["sequence"].apply(preview_events)
    exact = compute_overlap_section(work, "exact_key", "exact_key")
    unordered = compute_overlap_section(work, "unordered_key", "unordered_key")
    near = compute_near_duplicates(work)
    return {
        "exact_duplicates": exact,
        "unordered_duplicates": unordered,
        "near_duplicates": near,
        "possible_leakage": bool(exact["possible_leakage"] or unordered["possible_leakage"] or near["n_total_pairs"] > 0),
        "high_leakage_warning": bool(exact["high_leakage_warning"] or unordered["high_leakage_warning"] or near["n_total_pairs"] > 0),
        "max_overlap_pct": float(max(exact["max_overlap_pct"], unordered["max_overlap_pct"], near["max_similarity"])),
    }


def load_config_audit(row: dict[str, Any], repo_root: Path) -> ConfigAudit:
    """Load one configuration, preferring the precomputed F05 leakage JSON."""
    variant = str(row["variant"]).strip()
    pipeline = str(row.get("pipeline", variant))
    try:
        bundle = resolve_variant_artifacts(row, repo_root)
        outputs = safe_yaml_load(bundle.outputs_yaml) if bundle.outputs_yaml else {}
        if bundle.leakage_json and bundle.leakage_json.exists():
            leakage_report = json.loads(bundle.leakage_json.read_text(encoding="utf-8"))
        else:
            LOGGER.warning("Leakage JSON missing for %s. Recomputing from split dataset.", variant)
            split_df = load_split_dataset(bundle)
            leakage_report = build_report_from_dataset(split_df)
        audit = ConfigAudit(
            manifest_row=row,
            variant=variant,
            pipeline=pipeline,
            status="ok",
            variant_dir=bundle.variant_dir,
            outputs=outputs,
            leakage_report=leakage_report,
        )
        derive_metrics(audit)
        audit.interpretation = generate_interpretation(audit)
        audit.top_tables = build_top_tables(audit)
        return audit
    except Exception as exc:
        LOGGER.exception("Failed loading variant %s", variant)
        return ConfigAudit(
            manifest_row=row,
            variant=variant,
            pipeline=pipeline,
            status="error",
            error_message=str(exc),
        )


def pair_pct(section: dict[str, Any], pair_key: str, side: str) -> float:
    pair_data = section.get("pair_intersections", {}).get(pair_key, {})
    key = "pct_of_left" if side == "left" else "pct_of_right"
    return float(pair_data.get(key, 0.0))


def pair_count(section: dict[str, Any], pair_key: str) -> int:
    return int(section.get("pair_intersections", {}).get(pair_key, {}).get("shared_keys_count", 0))


def pair_positive_share(section: dict[str, Any], pair_key: str) -> float:
    pair_data = section.get("pair_intersections", {}).get(pair_key, {})
    total = int(pair_data.get("shared_keys_count", 0))
    if total == 0:
        return 0.0
    return float(pair_data.get("label_breakdown", {}).get("only_positive", 0) / total)


def derive_metrics(audit: ConfigAudit) -> None:
    """Compute the high-level metrics used in plots and interpretations."""
    outputs_metrics = audit.outputs.get("metrics", {})
    outputs_exports = audit.outputs.get("exports", {})
    exact = audit.leakage_report.get("exact_duplicates", {})
    unordered = audit.leakage_report.get("unordered_duplicates", {})
    near = audit.leakage_report.get("near_duplicates", {})

    metrics = {
        "n_train": int(outputs_metrics.get("n_train", 0)),
        "n_val": int(outputs_metrics.get("n_val", 0)),
        "n_test": int(outputs_metrics.get("n_test", 0)),
        "exact_train_val_pct_train": pair_pct(exact, "train_val", "left"),
        "exact_train_val_pct_val": pair_pct(exact, "train_val", "right"),
        "exact_train_test_pct_train": pair_pct(exact, "train_test", "left"),
        "exact_train_test_pct_test": pair_pct(exact, "train_test", "right"),
        "unordered_train_val_pct_train": pair_pct(unordered, "train_val", "left"),
        "unordered_train_val_pct_val": pair_pct(unordered, "train_val", "right"),
        "unordered_train_test_pct_train": pair_pct(unordered, "train_test", "left"),
        "unordered_train_test_pct_test": pair_pct(unordered, "train_test", "right"),
        "near_train_val_pairs": int(near.get("pairwise", {}).get("train_val", {}).get("n_pairs", 0)),
        "near_train_test_pairs": int(near.get("pairwise", {}).get("train_test", {}).get("n_pairs", 0)),
        "near_val_test_pairs": int(near.get("pairwise", {}).get("val_test", {}).get("n_pairs", 0)),
        "near_total_pairs": int(near.get("n_total_pairs", 0)),
        "exact_positive_share_train_val": pair_positive_share(exact, "train_val"),
        "exact_positive_share_train_test": pair_positive_share(exact, "train_test"),
        "unordered_positive_share_train_val": pair_positive_share(unordered, "train_val"),
        "unordered_positive_share_train_test": pair_positive_share(unordered, "train_test"),
        "high_warning": bool(audit.leakage_report.get("high_leakage_warning", False)),
        "possible_leakage": bool(audit.leakage_report.get("possible_leakage", False)),
        "dedup_mode": str(outputs_exports.get("deduplication_mode", audit.manifest_row.get("dedup", ""))),
        "dedup_effective": str(outputs_exports.get("deduplication_mode_effective", "")),
        "parent": str(outputs_exports.get("parent_f04", audit.manifest_row.get("parent", ""))),
        "parent_f02": str(outputs_exports.get("parent_f02", audit.manifest_row.get("parent_f02", ""))),
        "positive_ratio_train": float(outputs_metrics.get("positive_ratio_train", 0.0)),
        "positive_ratio_val": float(outputs_metrics.get("positive_ratio_val", 0.0)),
        "positive_ratio_test": float(outputs_metrics.get("positive_ratio_test", 0.0)),
    }

    warnings = []
    if metrics["exact_train_val_pct_val"] > 0.05 or metrics["exact_train_test_pct_test"] > 0.05:
        warnings.append("Exact leakage > 5 %")
    if metrics["unordered_train_val_pct_val"] > 0.10 or metrics["unordered_train_test_pct_test"] > 0.10:
        warnings.append("Unordered leakage > 10 %")
    if metrics["exact_train_val_pct_val"] > 0.30 or metrics["exact_train_test_pct_test"] > 0.30:
        warnings.append("More than 30 % of val/test exact keys are present in train")
    if max(metrics["exact_positive_share_train_val"], metrics["exact_positive_share_train_test"]) > 0.50:
        warnings.append("Leakage is concentrated in positive sequences")
    audit.warnings = warnings
    metrics["warning_label"] = "HIGH" if warnings else "LOW"
    audit.derived_metrics = metrics


def generate_interpretation(audit: ConfigAudit) -> list[str]:
    """Generate readable, data-driven text for one configuration."""
    if audit.status != "ok":
        return [f"No se pudo analizar la configuración {audit.variant}: {audit.error_message}"]

    m = audit.derived_metrics
    sentences: list[str] = []
    if m["exact_train_val_pct_val"] >= 0.50:
        sentences.append("Más del 50 % de los hashes exactos de validación aparecen también en entrenamiento, lo que indica una superposición muy fuerte entre splits.")
    elif m["exact_train_val_pct_val"] >= 0.30:
        sentences.append("Una fracción importante de los hashes exactos de validación ya está presente en entrenamiento, lo que sugiere contaminación relevante entre splits.")
    elif m["exact_train_val_pct_val"] <= 0.01 and m["exact_train_test_pct_test"] <= 0.01:
        sentences.append("El leakage exacto entre entrenamiento, validación y test es bajo, lo que apunta a una separación más limpia de secuencias exactas.")

    if m["unordered_train_val_pct_val"] > m["exact_train_val_pct_val"] + 0.05:
        sentences.append("Al ignorar el orden, el solape crece de forma visible, lo que sugiere reutilización de las mismas bolsas de eventos con ordenaciones distintas.")

    if m["near_train_val_pairs"] > 0 or m["near_train_test_pairs"] > 0:
        if m["near_total_pairs"] > 5000:
            sentences.append("El número de near duplicates es alto; aunque no sean copias exactas, hay muchas ventanas muy parecidas entre splits.")
        else:
            sentences.append("Se observan near duplicates entre splits, señal de que parte de la estructura de eventos se repite aunque no siempre con coincidencia exacta.")

    if max(m["exact_positive_share_train_val"], m["exact_positive_share_train_test"]) >= 0.50:
        sentences.append("El leakage exacto se concentra principalmente en secuencias positivas repetidas.")
    elif max(m["exact_positive_share_train_val"], m["exact_positive_share_train_test"]) <= 0.10:
        sentences.append("La parte positiva no domina el leakage exacto; el solape está más repartido entre negativos y patrones mixtos.")

    if m["dedup_mode"] == "auto" and m["dedup_effective"] == "neg_only":
        sentences.append("La deduplicación automática terminó actuando solo sobre negativos, así que los patrones positivos repetidos pueden seguir inflando las métricas.")
    elif m["dedup_mode"] == "all":
        sentences.append("La deduplicación completa reduce la reutilización exacta, pero no evita por sí sola la aparición de near duplicates.")
    elif m["dedup_mode"] == "none":
        sentences.append("Sin deduplicación previa, cualquier reutilización de secuencias entre splits se traslada directamente al leakage observado.")

    if audit.warnings:
        sentences.append("Las métricas de esta configuración podrían estar sobreestimadas por la superposición de patrones entre entrenamiento y evaluación.")

    if not sentences:
        sentences.append("La configuración presenta un perfil de leakage intermedio, sin una única señal dominante pero con suficiente solape como para merecer revisión manual.")
    return sentences


def build_top_tables(audit: ConfigAudit) -> dict[str, pd.DataFrame]:
    """Prepare HTML-friendly top tables."""
    if audit.status != "ok":
        return {}
    tables: dict[str, pd.DataFrame] = {}
    exact_rows = audit.leakage_report.get("exact_duplicates", {}).get("top_shared_keys", [])
    unordered_rows = audit.leakage_report.get("unordered_duplicates", {}).get("top_shared_keys", [])
    near_rows: list[dict[str, Any]] = []
    for pair_name, pair_data in audit.leakage_report.get("near_duplicates", {}).get("pairwise", {}).items():
        for example in pair_data.get("examples", [])[:8]:
            near_rows.append({"pair": pair_name, **example})

    if exact_rows:
        tables["exact"] = pd.DataFrame(exact_rows)[["label_profile", "train_count", "val_count", "test_count", "total_count", "n_splits_present", "events_preview"]]
    if unordered_rows:
        tables["unordered"] = pd.DataFrame(unordered_rows)[["label_profile", "train_count", "val_count", "test_count", "total_count", "n_splits_present", "events_preview"]]
    if near_rows:
        tables["near"] = pd.DataFrame(near_rows)[["pair", "label_profile", "similarity_score", "left_label", "right_label", "left_preview", "right_preview"]]
    return tables


def build_summary_dataframe(audits: list[ConfigAudit]) -> pd.DataFrame:
    rows = []
    for audit in audits:
        row = {
            "variant": audit.variant,
            "pipeline": audit.pipeline,
            "status": audit.status,
            "measure": audit.manifest_row.get("measure", ""),
            "direction": audit.manifest_row.get("direction", ""),
            "ow": audit.manifest_row.get("ow", ""),
            "pw": audit.manifest_row.get("pw", ""),
            "lt": audit.manifest_row.get("lt", ""),
            "dedup": audit.manifest_row.get("dedup", ""),
            "seed": audit.manifest_row.get("seed", ""),
        }
        row.update(audit.derived_metrics)
        rows.append(row)
    return pd.DataFrame(rows)


def save_figure(fig: plt.Figure, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def make_plots(summary_df: pd.DataFrame, audits: list[ConfigAudit], figures_dir: Path) -> dict[str, Path]:
    """Generate all requested PNG charts."""
    figures_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    ok_df = summary_df[summary_df["status"] == "ok"].copy()
    if ok_df.empty:
        return paths

    ok_df = ok_df.sort_values("pipeline")
    pipelines = ok_df["pipeline"].tolist()
    x = np.arange(len(ok_df))
    width = 0.36

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(x - width / 2, ok_df["exact_train_val_pct_val"] * 100.0, width=width, label="train-val")
    ax.bar(x + width / 2, ok_df["exact_train_test_pct_test"] * 100.0, width=width, label="train-test")
    ax.set_title("Exact leakage by pipeline")
    ax.set_ylabel("% of val/test exact keys present in train")
    ax.set_xticks(x)
    ax.set_xticklabels(pipelines, rotation=20, ha="right")
    ax.legend()
    paths["exact_bar"] = save_figure(fig, figures_dir / "exact_leakage_comparison.png")

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(x - width / 2, ok_df["unordered_train_val_pct_val"] * 100.0, width=width, label="train-val")
    ax.bar(x + width / 2, ok_df["unordered_train_test_pct_test"] * 100.0, width=width, label="train-test")
    ax.set_title("Unordered leakage by pipeline")
    ax.set_ylabel("% of val/test unordered keys present in train")
    ax.set_xticks(x)
    ax.set_xticklabels(pipelines, rotation=20, ha="right")
    ax.legend()
    paths["unordered_bar"] = save_figure(fig, figures_dir / "unordered_leakage_comparison.png")

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(x - width / 2, ok_df["near_train_val_pairs"], width=width, label="train-val")
    ax.bar(x + width / 2, ok_df["near_train_test_pairs"], width=width, label="train-test")
    ax.set_title("Near duplicates by pipeline")
    ax.set_ylabel("Near duplicate pairs")
    ax.set_xticks(x)
    ax.set_xticklabels(pipelines, rotation=20, ha="right")
    ax.legend()
    paths["near_bar"] = save_figure(fig, figures_dir / "near_duplicates_comparison.png")

    fig, ax = plt.subplots(figsize=(10, 5))
    neg = []
    pos = []
    mixed = []
    for audit in audits:
        if audit.status != "ok":
            continue
        pair_data = audit.leakage_report["exact_duplicates"]["pair_intersections"]["train_val"]
        total = max(int(pair_data["shared_keys_count"]), 1)
        breakdown = pair_data["label_breakdown"]
        neg.append(100.0 * breakdown["only_negative"] / total)
        pos.append(100.0 * breakdown["only_positive"] / total)
        mixed.append(100.0 * breakdown["mixed_labels"] / total)
    ax.bar(pipelines, neg, label="only_negative")
    ax.bar(pipelines, pos, bottom=neg, label="only_positive")
    ax.bar(pipelines, mixed, bottom=np.array(neg) + np.array(pos), label="mixed_labels")
    ax.set_title("Exact train-val leakage composition")
    ax.set_ylabel("% of shared exact keys")
    ax.legend()
    plt.xticks(rotation=20, ha="right")
    paths["stacked_labels"] = save_figure(fig, figures_dir / "label_profile_stacked.png")

    heatmap_pipelines = []
    heatmap_values = []
    for audit in audits:
        if audit.status != "ok":
            continue
        pair_data = audit.leakage_report["exact_duplicates"]["pair_intersections"].get("train_val", {})
        label_breakdown = pair_data.get("label_breakdown", {})
        heatmap_pipelines.append(audit.pipeline)
        heatmap_values.append(
            [
                float(label_breakdown.get("only_positive", 0)),
                float(label_breakdown.get("only_negative", 0)),
            ]
        )
    if heatmap_values:
        matrix = np.array(heatmap_values, dtype=float).T
        fig, ax = plt.subplots(figsize=(10, 3.8))
        im = ax.imshow(matrix, cmap="YlGnBu", aspect="auto")
        ax.set_title("Exact train-val leakage by label profile (raw counts)")
        ax.set_xticks(np.arange(len(heatmap_pipelines)))
        ax.set_xticklabels(heatmap_pipelines, rotation=20, ha="right")
        ax.set_yticks([0, 1])
        ax.set_yticklabels(["leakage positivos", "leakage negativos"])
        for row_idx in range(matrix.shape[0]):
            for col_idx in range(matrix.shape[1]):
                ax.text(col_idx, row_idx, f"{int(matrix[row_idx, col_idx])}", ha="center", va="center", color="black")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="shared exact keys")
        paths["positive_negative_heatmap"] = save_figure(fig, figures_dir / "positive_negative_heatmap.png")

    for audit in audits:
        if audit.status != "ok":
            continue
        exact = audit.leakage_report["exact_duplicates"]
        matrix = np.array(
            [
                [
                    exact["pair_intersections"]["train_val"]["pct_of_right"] * 100.0,
                    exact["pair_intersections"]["train_test"]["pct_of_right"] * 100.0,
                ],
                [
                    exact["pair_intersections"]["val_test"]["pct_of_right"] * 100.0,
                    exact["triple_intersection"]["pct_of_test"] * 100.0,
                ],
            ]
        )
        fig, ax = plt.subplots(figsize=(5, 4))
        im = ax.imshow(matrix, cmap="YlOrRd")
        ax.set_title(f"Exact overlap heatmap - {audit.pipeline}")
        ax.set_xticks([0, 1])
        ax.set_yticks([0, 1])
        ax.set_xticklabels(["train-test", "all_three"])
        ax.set_yticklabels(["train-val", "val-test"])
        for i in range(matrix.shape[0]):
            for j in range(matrix.shape[1]):
                ax.text(j, i, f"{matrix[i, j]:.1f}%", ha="center", va="center", color="black")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        paths[f"heatmap_{audit.variant}"] = save_figure(fig, figures_dir / f"heatmap_{audit.variant}.png")

    return paths


def warning_badge_text(audit: ConfigAudit) -> str:
    if audit.status != "ok":
        return "ERROR"
    return "HIGH" if audit.warnings else "LOW"


def render_table(df: pd.DataFrame, float_cols: Iterable[str] | None = None) -> str:
    frame = df.copy()
    for col in float_cols or []:
        if col in frame.columns:
            frame[col] = frame[col].map(lambda value: f"{100.0 * float(value):.2f}%" if abs(float(value)) <= 1.0 else f"{float(value):.2f}")
    return frame.to_html(index=False, classes="dataframe report-table", border=0, escape=True)


def build_config_overview_table(audits: list[ConfigAudit]) -> pd.DataFrame:
    rows = []
    for audit in audits:
        row = {
            "variant": audit.variant,
            "pipeline": audit.pipeline,
            "measure": audit.manifest_row.get("measure", ""),
            "direction": audit.manifest_row.get("direction", ""),
            "ow": audit.manifest_row.get("ow", ""),
            "pw": audit.manifest_row.get("pw", ""),
            "lt": audit.manifest_row.get("lt", ""),
            "dedup": audit.manifest_row.get("dedup", ""),
            "seed": audit.manifest_row.get("seed", ""),
            "parent": audit.derived_metrics.get("parent", audit.manifest_row.get("parent", "")),
            "parent_f02": audit.derived_metrics.get("parent_f02", audit.manifest_row.get("parent_f02", "")),
            "status": audit.status,
        }
        rows.append(row)
    return pd.DataFrame(rows)


def render_overlap_section(title: str, section: dict[str, Any]) -> str:
    summary_df = pd.DataFrame(section.get("summary_rows", []))
    label_df = pd.DataFrame.from_dict(section.get("split_label_summary", {}), orient="index").reset_index().rename(columns={"index": "split"})
    sizes_df = pd.DataFrame([section.get("split_sizes_unique_keys", {})])
    top_df = pd.DataFrame(section.get("top_shared_keys", []))
    html = [f"<div class='panel'><h4>{escape(title)}</h4>"]
    if not sizes_df.empty:
        html.append(render_table(sizes_df))
    if not label_df.empty:
        html.append("<p class='caption'>Desglose de claves únicas por split y perfil de label.</p>")
        html.append(render_table(label_df))
    if not summary_df.empty:
        html.append("<p class='caption'>Intersecciones por pares y triple intersección.</p>")
        html.append(render_table(summary_df, float_cols=["pct_of_left", "pct_of_right"]))
    if not top_df.empty:
        html.append("<p class='caption'>Top patrones compartidos.</p>")
        show_cols = [col for col in ["label_profile", "train_count", "val_count", "test_count", "total_count", "n_splits_present", "events_preview"] if col in top_df.columns]
        html.append(render_table(top_df[show_cols]))
    html.append("</div>")
    return "".join(html)


def render_near_section(section: dict[str, Any]) -> str:
    rows = []
    examples = []
    for pair_name, pair_data in section.get("pairwise", {}).items():
        rows.append(
            {
                "pair": pair_name,
                "n_pairs": pair_data.get("n_pairs", 0),
                "n_only_negative": pair_data.get("n_only_negative", 0),
                "n_only_positive": pair_data.get("n_only_positive", 0),
                "n_mixed_labels": pair_data.get("n_mixed_labels", 0),
            }
        )
        for item in pair_data.get("examples", [])[:8]:
            examples.append({"pair": pair_name, **item})
    html = [
        "<div class='panel'><h4>near_duplicates</h4>",
        "<ul class='compact-list'>",
        f"<li>threshold = {section.get('threshold', 0.0):.2f}</li>",
        f"<li>similarity_definition = {escape(str(section.get('similarity_definition', '')))}</li>",
        f"<li>n_total_pairs = {int(section.get('n_total_pairs', 0))}</li>",
        "</ul>",
    ]
    if rows:
        html.append(render_table(pd.DataFrame(rows)))
    if examples:
        ex_df = pd.DataFrame(examples)
        show_cols = [col for col in ["pair", "label_profile", "similarity_score", "left_label", "right_label", "left_preview", "right_preview"] if col in ex_df.columns]
        html.append(render_table(ex_df[show_cols]))
    html.append("</div>")
    return "".join(html)


def rank_variants(summary_df: pd.DataFrame, metric_col: str, ascending: bool, label: str) -> str:
    ok_df = summary_df[summary_df["status"] == "ok"].copy()
    if ok_df.empty or metric_col not in ok_df.columns:
        return f"<p>{escape(label)}: no data available.</p>"
    ranked = ok_df.sort_values(metric_col, ascending=ascending)[["pipeline", "variant", metric_col]]
    ranked = ranked.rename(columns={metric_col: label})
    return render_table(ranked)


def overall_conclusion(audits: list[ConfigAudit], summary_df: pd.DataFrame) -> list[str]:
    ok_df = summary_df[summary_df["status"] == "ok"].copy()
    if ok_df.empty:
        return ["No se pudo cargar ninguna configuración, así que no hay base suficiente para una conclusión comparativa."]

    contamination_score = (
        ok_df["exact_train_val_pct_val"]
        + ok_df["exact_train_test_pct_test"]
        + ok_df["unordered_train_val_pct_val"]
        + ok_df["unordered_train_test_pct_test"]
    )
    most_contaminated = ok_df.iloc[int(contamination_score.argmax())]
    cleanest = ok_df.iloc[int(contamination_score.argmin())]
    positive_focus = ok_df.iloc[int(ok_df["exact_positive_share_train_val"].fillna(0.0).argmax())]
    near_focus = ok_df.iloc[int(ok_df["near_total_pairs"].fillna(0).argmax())]

    conclusions = [
        f"La configuración que aparece más contaminada en conjunto es {most_contaminated['pipeline']} ({most_contaminated['variant']}).",
        f"La configuración que parece más limpia dentro del grupo comparado es {cleanest['pipeline']} ({cleanest['variant']}).",
        f"La mayor concentración de leakage positivo se observa en {positive_focus['pipeline']} ({positive_focus['variant']}).",
        f"La configuración con más near duplicates es {near_focus['pipeline']} ({near_focus['variant']}).",
    ]

    auto_rows = ok_df[
        ok_df["pipeline"].astype(str).str.contains("auto", case=False, na=False)
    ]
    none_rows = ok_df[
        ok_df["pipeline"].astype(str).str.contains("none", case=False, na=False)
    ]
    if not auto_rows.empty and not none_rows.empty:
        if auto_rows["exact_positive_share_train_val"].mean() >= none_rows["exact_positive_share_train_val"].mean():
            conclusions.append("Hay indicios de que deduplicar solo negativos no es suficiente, porque el leakage positivo sigue siendo dominante en las configuraciones automáticas.")
        else:
            conclusions.append("La deduplicación automática reduce parte del leakage, pero conviene vigilar los patrones positivos y los near duplicates antes de darla por suficiente.")
    return conclusions


def build_html(
    title: str,
    manifest_path: Path,
    audits: list[ConfigAudit],
    summary_df: pd.DataFrame,
    plot_paths: dict[str, Path],
    output_html: Path,
) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    config_table = build_config_overview_table(audits)
    executive_table = summary_df[
        [
            "pipeline",
            "variant",
            "exact_train_val_pct_val",
            "exact_train_test_pct_test",
            "unordered_train_val_pct_val",
            "unordered_train_test_pct_test",
            "near_train_val_pairs",
            "near_train_test_pairs",
            "exact_positive_share_train_val",
            "warning_label",
        ]
    ].copy()

    def rel_path(name: str) -> str:
        return escape(str(plot_paths[name].relative_to(output_html.parent)).replace("\\", "/"))

    sections = []
    for audit in audits:
        if audit.status != "ok":
            sections.append(
                f"""
                <section class="panel">
                  <h3>{escape(audit.pipeline)} ({escape(audit.variant)})</h3>
                  <p class="warning">No se pudo cargar esta configuración: {escape(audit.error_message or 'unknown error')}</p>
                </section>
                """
            )
            continue

        metrics = audit.derived_metrics
        warnings_html = "".join(f"<li>{escape(item)}</li>" for item in audit.warnings) or "<li>Sin warnings críticos.</li>"
        interp_html = "".join(f"<li>{escape(text)}</li>" for text in audit.interpretation)
        kpis = f"""
        <div class="kpi-grid">
          <div class="metric-card"><div class="metric-label">train / val / test</div><div class="metric-value">{metrics['n_train']} / {metrics['n_val']} / {metrics['n_test']}</div></div>
          <div class="metric-card"><div class="metric-label">Exact train-val</div><div class="metric-value">{100.0 * metrics['exact_train_val_pct_val']:.2f}%</div></div>
          <div class="metric-card"><div class="metric-label">Exact train-test</div><div class="metric-value">{100.0 * metrics['exact_train_test_pct_test']:.2f}%</div></div>
          <div class="metric-card"><div class="metric-label">Unordered train-val</div><div class="metric-value">{100.0 * metrics['unordered_train_val_pct_val']:.2f}%</div></div>
          <div class="metric-card"><div class="metric-label">Near pairs train-val</div><div class="metric-value">{metrics['near_train_val_pairs']}</div></div>
          <div class="metric-card"><div class="metric-label">Warning</div><div class="metric-value">{warning_badge_text(audit)}</div></div>
        </div>
        """
        heatmap_key = f"heatmap_{audit.variant}"
        heatmap_html = ""
        if heatmap_key in plot_paths:
            heatmap_html = f"<img class='plot' src='{rel_path(heatmap_key)}' alt='Heatmap {escape(audit.variant)}' />"
        sections.append(
            f"""
            <section class="panel">
              <h3>{escape(audit.pipeline)} ({escape(audit.variant)})</h3>
              <p class="caption">
                measure={escape(str(audit.manifest_row.get('measure', '')))} |
                direction={escape(str(audit.manifest_row.get('direction', '')))} |
                ow={escape(str(audit.manifest_row.get('ow', '')))} |
                pw={escape(str(audit.manifest_row.get('pw', '')))} |
                lt={escape(str(audit.manifest_row.get('lt', '')))} |
                dedup={escape(str(metrics.get('dedup_mode', '')))} |
                effective={escape(str(metrics.get('dedup_effective', '')))}
              </p>
              {kpis}
              <div class="two-col">
                <div>
                  <h4>Interpretación automática</h4>
                  <ul>{interp_html}</ul>
                  <h4>Warnings</h4>
                  <ul>{warnings_html}</ul>
                </div>
                <div>
                  <h4>Heatmap de intersección</h4>
                  {heatmap_html}
                </div>
              </div>
              {render_overlap_section('Exact duplicates', audit.leakage_report['exact_duplicates'])}
              {render_overlap_section('Same events, different order', audit.leakage_report['unordered_duplicates'])}
              {render_near_section(audit.leakage_report['near_duplicates'])}
            </section>
            """
        )

    css = """
    body { font-family: Arial, sans-serif; max-width: 1680px; margin: 0 auto; padding: 24px; color: #222; line-height: 1.55; background: #f7f7f7; }
    h1, h2, h3, h4 { color: #111; }
    h2 { margin-top: 34px; border-bottom: 2px solid #ddd; padding-bottom: 6px; }
    .lead { color: #444; font-size: 1.04rem; }
    .panel { background: white; border: 1px solid #ddd; border-radius: 12px; padding: 20px; margin: 18px 0; box-shadow: 0 1px 4px rgba(0,0,0,0.05); }
    .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 14px; margin: 18px 0 24px; }
    .metric-card { background: #fff; border: 1px solid #ddd; border-radius: 10px; padding: 12px 14px; }
    .metric-label { color: #666; font-size: 0.9rem; margin-bottom: 6px; }
    .metric-value { font-size: 1.35rem; font-weight: bold; }
    .two-col { display: grid; grid-template-columns: repeat(auto-fit, minmax(480px, 1fr)); gap: 20px; }
    .plot { width: 100%; border: 1px solid #eee; border-radius: 8px; background: #fff; }
    .report-table { width: 100%; border-collapse: collapse; margin: 10px 0 18px; font-size: 0.94rem; }
    .report-table th, .report-table td { border: 1px solid #ddd; padding: 8px 10px; vertical-align: top; text-align: left; }
    .report-table th { background: #f1f3f5; }
    .compact-list { margin-top: 0; }
    .warning { color: #a33; font-weight: bold; }
    .caption { color: #555; margin: 6px 0 12px; }
    .plot-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(440px, 1fr)); gap: 18px; }
    .pill-high { background: #ffe3e3; color: #9b2226; border: 1px solid #f5b5b5; }
    .pill-low { background: #e6fcf5; color: #0b6e4f; border: 1px solid #b7ebdb; }
    .pill { display: inline-block; padding: 4px 10px; border-radius: 999px; font-size: 0.9rem; font-weight: bold; }
    @media (max-width: 768px) { body { padding: 14px; } .panel { padding: 14px; } }
    """

    conclusion_html = "".join(f"<li>{escape(text)}</li>" for text in overall_conclusion(audits, summary_df))
    return f"""
    <html>
      <head>
        <meta charset="utf-8" />
        <title>{escape(title)}</title>
        <style>{css}</style>
      </head>
      <body>
        <h1>{escape(title)}</h1>
        <p class="lead">Este informe compara leakage entre las configuraciones seleccionadas del experimento ATICUS usando artefactos de la fase F05.</p>
        <div class="panel">
          <p><strong>Manifest:</strong> {escape(str(manifest_path))}</p>
          <p><strong>Generated at:</strong> {escape(generated_at)}</p>
          <p><strong>Configurations loaded:</strong> {len(audits)}</p>
        </div>

        <h2>Configuraciones Analizadas</h2>
        <div class="panel">{render_table(config_table)}</div>

        <h2>Resumen Ejecutivo Comparativo</h2>
        <div class="panel">
          <p class="caption">Las columnas de leakage exacto y unordered están expresadas como porcentaje de claves de validación o test que ya aparecían en train.</p>
          {render_table(executive_table, float_cols=[
              'exact_train_val_pct_val',
              'exact_train_test_pct_test',
              'unordered_train_val_pct_val',
              'unordered_train_test_pct_test',
              'exact_positive_share_train_val',
          ])}
        </div>

        <div class="plot-grid">
          <div class="panel"><h3>Exact leakage</h3><img class="plot" src="{rel_path('exact_bar')}" alt="Exact leakage comparison" /></div>
          <div class="panel"><h3>Unordered leakage</h3><img class="plot" src="{rel_path('unordered_bar')}" alt="Unordered leakage comparison" /></div>
          <div class="panel"><h3>Near duplicates</h3><img class="plot" src="{rel_path('near_bar')}" alt="Near duplicate comparison" /></div>
          <div class="panel"><h3>Leakage por label</h3><img class="plot" src="{rel_path('stacked_labels')}" alt="Stacked label leakage" /></div>
          <div class="panel"><h3>Heatmap Positivos vs Negativos</h3><img class="plot" src="{rel_path('positive_negative_heatmap')}" alt="Positive negative leakage heatmap" /></div>
        </div>

        <h2>Sección Por Configuración</h2>
        {''.join(sections)}

        <h2>Comparación Cruzada</h2>
        <div class="panel">
          <h3>Ranking por menor leakage total</h3>
          {rank_variants(summary_df.assign(total_exact=summary_df['exact_train_val_pct_val'] + summary_df['exact_train_test_pct_test']), 'total_exact', True, 'total_exact')}
          <h3>Ranking por mayor leakage positivo</h3>
          {rank_variants(summary_df, 'exact_positive_share_train_val', False, 'positive_share_train_val')}
          <h3>Ranking por near duplicates</h3>
          {rank_variants(summary_df, 'near_total_pairs', False, 'near_total_pairs')}
        </div>

        <h2>Conclusión Final Automática</h2>
        <div class="panel">
          <ul>{conclusion_html}</ul>
        </div>
      </body>
    </html>
    """


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)

    manifest_path = Path(args.manifest).resolve()
    output_html = Path(args.output_html).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else output_html.parent
    figures_dir = output_dir / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    repo_root = repo_root_from_script()
    manifest_df = load_manifest(manifest_path)
    target_rows = select_target_rows(manifest_df)
    LOGGER.info("Loaded %s candidate rows from manifest.", len(target_rows))

    audits = [
        load_config_audit(row._asdict() if hasattr(row, "_asdict") else row.to_dict(), repo_root)
        for _, row in target_rows.iterrows()
    ]
    summary_df = build_summary_dataframe(audits)
    plot_paths = make_plots(summary_df, audits, figures_dir)

    required_plots = {"exact_bar", "unordered_bar", "near_bar", "stacked_labels"}
    missing = required_plots - set(plot_paths)
    if missing:
        LOGGER.warning("Some requested plots could not be generated: %s", ", ".join(sorted(missing)))

    html = build_html(args.title, manifest_path, audits, summary_df, plot_paths, output_html)
    output_html.write_text(html, encoding="utf-8")
    LOGGER.info("HTML report written to %s", output_html)


if __name__ == "__main__":
    main()
