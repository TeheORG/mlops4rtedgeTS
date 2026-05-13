from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


VARIANT_RE = re.compile(r"^v(\d+)$")


def natural_variant_key(value: Any) -> tuple[int, str]:
    text = str(value or "")
    match = VARIANT_RE.match(text)
    if match:
        return (int(match.group(1)), text)
    return (10**9, text)


def discover_project_root(explicit_root: str | None = None) -> Path:
    if explicit_root:
        return Path(explicit_root).resolve()
    return Path(__file__).resolve().parents[4]


def analysis_root(project_root: Path) -> Path:
    return project_root / "test" / "experiments" / "jenofonte" / "analysis"


def outputs_dir(project_root: Path) -> Path:
    return analysis_root(project_root) / "outputs"


def safe_read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def safe_read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def safe_number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        if pd.isna(value):
            return default
        return int(value)
    except Exception:
        return default


def safe_entropy(values: list[float]) -> float:
    total = sum(v for v in values if v > 0)
    if total <= 0:
        return 0.0
    entropy = 0.0
    for value in values:
        if value <= 0:
            continue
        prob = value / total
        entropy -= prob * math.log(prob)
    return float(entropy)


def extract_band_labels_from_bands(bands: list[Any]) -> list[str]:
    clean_bands = [safe_int(v) for v in bands if v is not None]
    if not clean_bands:
        return []
    points = [0] + clean_bands + [100]
    return [f"{points[i]}_{points[i + 1]}" for i in range(len(points) - 1)]


def classify_event_density(empty_rows_ratio: float) -> str:
    if empty_rows_ratio > 0.98:
        return "sparse"
    if 0.90 <= empty_rows_ratio <= 0.98:
        return "medium"
    return "dense"


def classify_extreme_focus(rare_event_ratio: float) -> str:
    if rare_event_ratio >= 0.60:
        return "high"
    if rare_event_ratio >= 0.35:
        return "medium"
    return "low"


def classify_band_degeneracy(max_band_ratio: float) -> str:
    if max_band_ratio >= 0.95:
        return "degenerate"
    if max_band_ratio >= 0.80:
        return "concentrated"
    return "distributed"


def classify_extreme_occupancy(extreme_band_ratio: float) -> str:
    if extreme_band_ratio >= 0.80:
        return "high"
    if extreme_band_ratio >= 0.50:
        return "medium"
    return "low"


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def compute_variant_score(
    normalized_event_entropy: float,
    catalog_coverage_ratio: float,
    rare_event_ratio: float,
    empty_rows_ratio: float,
    top1_event_ratio: float,
) -> float:
    rare_bonus = 1.0 - min(abs(rare_event_ratio - 0.45) / 0.45, 1.0)
    score = (
        0.30 * clamp01(normalized_event_entropy)
        + 0.25 * clamp01(catalog_coverage_ratio)
        + 0.20 * clamp01(rare_bonus)
        + 0.15 * clamp01(1.0 - empty_rows_ratio)
        + 0.10 * clamp01(1.0 - top1_event_ratio)
    )
    return float(score)


def compute_band_occupancy_metrics(band_occupancy: dict[str, Any]) -> dict[str, Any]:
    items = [(str(k), safe_number(v)) for k, v in (band_occupancy or {}).items()]
    labels = [label for label, _ in items]
    counts = [count for _, count in items]
    total_band_count = sum(counts)
    n_active_bands = sum(1 for count in counts if count > 0)
    max_band_count = max(counts) if counts else 0.0
    max_band_ratio = (max_band_count / total_band_count) if total_band_count > 0 else 0.0
    nonzero_counts = [count for count in counts if count > 0]
    min_nonzero_band_count = min(nonzero_counts) if nonzero_counts else 0.0
    extreme_band_count = 0.0
    if counts:
        extreme_band_count = counts[0] + counts[-1] if len(counts) > 1 else counts[0]
    extreme_band_ratio = (extreme_band_count / total_band_count) if total_band_count > 0 else 0.0
    middle_band_count = max(total_band_count - extreme_band_count, 0.0)
    middle_band_ratio = (middle_band_count / total_band_count) if total_band_count > 0 else 0.0
    occupancy_entropy = safe_entropy(counts)
    normalized_occupancy_entropy = 0.0
    if n_active_bands > 1:
        normalized_occupancy_entropy = occupancy_entropy / math.log(n_active_bands)
    return {
        "band_occupancy_json": json.dumps(dict(items), ensure_ascii=True),
        "band_labels_measure": "|".join(labels),
        "n_active_bands": int(n_active_bands),
        "total_band_count": float(total_band_count),
        "max_band_count": float(max_band_count),
        "max_band_ratio": float(max_band_ratio),
        "min_nonzero_band_count": float(min_nonzero_band_count),
        "extreme_band_count": float(extreme_band_count),
        "extreme_band_ratio": float(extreme_band_ratio),
        "middle_band_count": float(middle_band_count),
        "middle_band_ratio": float(middle_band_ratio),
        "occupancy_entropy": float(occupancy_entropy),
        "normalized_occupancy_entropy": float(normalized_occupancy_entropy),
        "band_degeneracy_flag": classify_band_degeneracy(float(max_band_ratio)),
        "extreme_occupancy_flag": classify_extreme_occupancy(float(extreme_band_ratio)),
    }


def load_f02_variant_data(variant_dir: Path) -> dict[str, Any]:
    outputs = safe_read_yaml(variant_dir / "outputs.yaml")
    params = safe_read_yaml(variant_dir / "params.yaml")
    artifacts = outputs.get("artifacts", {}) if isinstance(outputs, dict) else {}

    stats_rel = ((artifacts.get("stats") or {}).get("path")) if isinstance(artifacts, dict) else None
    catalog_rel = ((artifacts.get("catalog") or {}).get("path")) if isinstance(artifacts, dict) else None

    stats = safe_read_json(variant_dir / stats_rel) if stats_rel else safe_read_json(variant_dir / "02_events_stats.json")
    catalog = safe_read_json(variant_dir / catalog_rel) if catalog_rel else safe_read_json(variant_dir / "02_events_catalog.json")

    return {
        "variant_dir": variant_dir,
        "variant_f02": variant_dir.name,
        "outputs": outputs,
        "params": params,
        "stats": stats,
        "catalog": catalog,
    }


def parse_global_row(payload: dict[str, Any]) -> dict[str, Any]:
    outputs = payload.get("outputs", {})
    params = payload.get("params", {})
    stats = payload.get("stats", {})
    global_stats = stats.get("global", {}) if isinstance(stats, dict) else {}
    metrics = outputs.get("metrics", {}) if isinstance(outputs, dict) else {}
    exports = outputs.get("exports", {}) if isinstance(outputs, dict) else {}
    parameters = params.get("parameters", {}) if isinstance(params, dict) else {}

    bands = parameters.get("bands") or []
    band_labels = extract_band_labels_from_bands(list(bands))
    n_rows_out = safe_number(metrics.get("n_rows_out"))
    total_events = safe_number(global_stats.get("total_events_generated", metrics.get("total_events_generated")))
    catalog_coverage = safe_number(global_stats.get("catalog_coverage_ratio", metrics.get("catalog_coverage_ratio")))
    rare_event_ratio = safe_number(global_stats.get("rare_event_ratio", metrics.get("rare_event_ratio")))
    empty_rows_ratio = safe_number(global_stats.get("empty_rows_ratio", metrics.get("empty_rows_ratio")))
    top1_event_ratio = safe_number(global_stats.get("top1_event_ratio", metrics.get("top1_event_ratio")))
    normalized_event_entropy = safe_number(global_stats.get("normalized_event_entropy", metrics.get("normalized_event_entropy")))

    row = {
        "variant_f02": payload.get("variant_f02"),
        "bands_raw": json.dumps(list(bands), ensure_ascii=True),
        "n_bands": len(bands),
        "band_labels": "|".join(band_labels),
        "event_strategy": parameters.get("strategy", ""),
        "Tu": safe_number(exports.get("Tu", parameters.get("Tu"))),
        "n_rows_in": safe_number(metrics.get("n_rows_in")),
        "n_rows_out": n_rows_out,
        "execution_time": safe_number(metrics.get("execution_time")),
        "total_events_generated": total_events,
        "mean_events_per_row": safe_number(global_stats.get("mean_events_per_row", metrics.get("mean_events_per_row"))),
        "std_events_per_row": safe_number(global_stats.get("std_events_per_row")),
        "max_events_per_row": safe_number(global_stats.get("max_events_per_row")),
        "p95_events_per_row": safe_number(global_stats.get("p95_events_per_row")),
        "empty_rows_ratio": empty_rows_ratio,
        "nonempty_rows_ratio": safe_number(global_stats.get("nonempty_rows_ratio")),
        "n_event_types_catalog": safe_number(global_stats.get("n_event_types_catalog", exports.get("n_types"))),
        "n_event_types_observed": safe_number(global_stats.get("n_event_types_observed", exports.get("n_types_observed"),)),
        "catalog_coverage_ratio": catalog_coverage,
        "rare_event_count": safe_number(global_stats.get("rare_event_count")),
        "rare_event_ratio": rare_event_ratio,
        "rare_event_types_observed": safe_number(global_stats.get("rare_event_types_observed")),
        "rare_event_type_ratio": safe_number(global_stats.get("rare_event_type_ratio")),
        "top1_event_ratio": top1_event_ratio,
        "top5_event_ratio": safe_number(global_stats.get("top5_event_ratio")),
        "event_entropy": safe_number(global_stats.get("event_entropy", metrics.get("event_entropy"))),
        "normalized_event_entropy": normalized_event_entropy,
        "n_consecutive_steps": safe_number(global_stats.get("n_consecutive_steps")),
        "consecutive_ratio": safe_number(global_stats.get("consecutive_ratio")),
        "n_broken_steps": safe_number(global_stats.get("n_broken_steps")),
        "broken_ratio": safe_number(global_stats.get("broken_ratio")),
        "n_transition_events": safe_number(global_stats.get("n_transition_events", metrics.get("n_transition_events"))),
        "n_unique_transition_types_observed": safe_number(global_stats.get("n_unique_transition_types_observed")),
        "transition_coverage_ratio": safe_number(global_stats.get("transition_coverage_ratio")),
        "jump_size_mean": safe_number(global_stats.get("jump_size_mean", metrics.get("jump_size_mean"))),
        "jump_size_std": safe_number(global_stats.get("jump_size_std")),
        "pct_jump_eq_1": safe_number(global_stats.get("pct_jump_eq_1")),
        "pct_jump_ge_2": safe_number(global_stats.get("pct_jump_ge_2")),
        "pct_jump_ge_3": safe_number(global_stats.get("pct_jump_ge_3")),
    }

    row["events_per_million_rows"] = (total_events / n_rows_out * 1e6) if n_rows_out > 0 else 0.0
    row["effective_catalog_unused_ratio"] = 1.0 - catalog_coverage
    row["event_density_flag"] = classify_event_density(empty_rows_ratio)
    row["extreme_focus_flag"] = classify_extreme_focus(rare_event_ratio)
    row["variant_score"] = compute_variant_score(
        normalized_event_entropy=normalized_event_entropy,
        catalog_coverage_ratio=catalog_coverage,
        rare_event_ratio=rare_event_ratio,
        empty_rows_ratio=empty_rows_ratio,
        top1_event_ratio=top1_event_ratio,
    )
    return row


def parse_measure_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    stats = payload.get("stats", {})
    per_measure = stats.get("per_measure", {}) if isinstance(stats, dict) else {}
    rows: list[dict[str, Any]] = []

    for measure_name in sorted(per_measure):
        measure_stats = per_measure.get(measure_name) or {}
        band_occupancy = measure_stats.get("band_occupancy", {}) or {}
        occupancy = compute_band_occupancy_metrics(band_occupancy)
        n_events_generated = safe_number(measure_stats.get("n_events_generated"))

        row = {
            "variant_f02": payload.get("variant_f02"),
            "measure_name": measure_name,
            "n_events_generated": n_events_generated,
            "n_unique_event_types_observed": safe_number(measure_stats.get("n_unique_event_types_observed")),
            "top1_ratio": safe_number(measure_stats.get("top1_ratio")),
            "rare_event_ratio": safe_number(measure_stats.get("rare_event_ratio")),
            "mean_events_per_row_contributed": safe_number(measure_stats.get("mean_events_per_row_contributed")),
            "jump_size_mean": safe_number(measure_stats.get("jump_size_mean")),
            "is_eventless_measure": bool(n_events_generated == 0),
        }
        row.update(occupancy)
        rows.append(row)

    return rows


def build_master_tables(project_root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    exec_dir = project_root / "executions" / "f02_events"
    payloads = [
        load_f02_variant_data(variant_dir)
        for variant_dir in sorted(exec_dir.iterdir(), key=lambda p: natural_variant_key(p.name))
        if variant_dir.is_dir() and (variant_dir / "outputs.yaml").exists()
    ]

    global_rows = [parse_global_row(payload) for payload in payloads]
    measure_rows = []
    for payload in payloads:
        measure_rows.extend(parse_measure_rows(payload))

    global_df = pd.DataFrame(global_rows)
    if not global_df.empty:
        global_df = global_df.sort_values("variant_f02", key=lambda s: s.map(lambda x: natural_variant_key(x))).reset_index(drop=True)

    measure_df = pd.DataFrame(measure_rows)
    if not measure_df.empty:
        measure_df = measure_df.sort_values(
            ["measure_name", "variant_f02"],
            key=lambda s: s.map(lambda x: natural_variant_key(x) if s.name == "variant_f02" else str(x)),
        ).reset_index(drop=True)

    return global_df, measure_df


def build_variant_summary(global_df: pd.DataFrame) -> pd.DataFrame:
    if global_df.empty:
        return pd.DataFrame()
    preferred_first = [
        "variant_f02",
        "event_strategy",
        "n_bands",
        "bands_raw",
        "band_labels",
        "variant_score",
    ]
    preferred_last = [
        "event_density_flag",
        "extreme_focus_flag",
    ]

    available_first = [col for col in preferred_first if col in global_df.columns]
    available_last = [col for col in preferred_last if col in global_df.columns and col not in available_first]
    middle_cols = [
        col for col in global_df.columns
        if col not in set(available_first) and col not in set(available_last)
    ]
    ordered_cols = available_first + middle_cols + available_last

    sort_col = "variant_score" if "variant_score" in global_df.columns else "variant_f02"
    ascending = sort_col != "variant_score"
    return global_df[ordered_cols].sort_values(sort_col, ascending=ascending).reset_index(drop=True)


def build_measure_summary(measure_df: pd.DataFrame) -> pd.DataFrame:
    if measure_df.empty:
        return pd.DataFrame()
    summary = (
        measure_df.groupby("measure_name", dropna=False)
        .agg(
            n_variants=("variant_f02", "nunique"),
            mean_n_events_generated=("n_events_generated", "mean"),
            mean_extreme_band_ratio=("extreme_band_ratio", "mean"),
            mean_max_band_ratio=("max_band_ratio", "mean"),
            mean_rare_event_ratio=("rare_event_ratio", "mean"),
            mean_occupancy_entropy=("occupancy_entropy", "mean"),
            mean_normalized_occupancy_entropy=("normalized_occupancy_entropy", "mean"),
            pct_eventless=("is_eventless_measure", "mean"),
        )
        .reset_index()
        .sort_values("measure_name")
    )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build F02 master tables for Jenofonte")
    parser.add_argument("--project-root", default=None, help="Project root path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = discover_project_root(args.project_root)
    out_dir = outputs_dir(project_root)
    out_dir.mkdir(parents=True, exist_ok=True)

    global_df, measure_df = build_master_tables(project_root)
    variant_summary = build_variant_summary(global_df)
    measure_summary = build_measure_summary(measure_df)

    global_df.to_csv(out_dir / "f02_master_global.csv", index=False, encoding="utf-8")
    measure_df.to_csv(out_dir / "f02_master_measure.csv", index=False, encoding="utf-8")
    variant_summary.to_csv(out_dir / "f02_variant_summary.csv", index=False, encoding="utf-8")
    measure_summary.to_csv(out_dir / "f02_measure_summary.csv", index=False, encoding="utf-8")

    print(f"f02_master_global.csv -> {out_dir / 'f02_master_global.csv'}")
    print(f"f02_master_measure.csv -> {out_dir / 'f02_master_measure.csv'}")
    print(f"f02_variant_summary.csv -> {out_dir / 'f02_variant_summary.csv'}")
    print(f"f02_measure_summary.csv -> {out_dir / 'f02_measure_summary.csv'}")


if __name__ == "__main__":
    main()
