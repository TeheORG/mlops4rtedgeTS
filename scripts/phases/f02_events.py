#!/usr/bin/env python3

import argparse
import html
import math
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import matplotlib.pyplot as plt


from scripts.core.artifacts import (
    sha256_of_file,
    save_outputs_yaml,
    load_params,
    get_variant_dir,
    save_json
)
from scripts.core.phase_io import load_phase_outputs, resolve_artifact_path
from scripts.core.traceability import validate_outputs


# ============================================================
# CONSTANTES
# ============================================================

PHASE = "f02_events"
PROJECT_ROOT = REPO_ROOT

TARGET_CANDIDATE_MIN_UNIQUE_TYPES = 3
TARGET_CANDIDATE_MIN_RATIO = 0.001

MEASURE_SCORE_WEIGHT_EVENTS = 0.35
MEASURE_SCORE_WEIGHT_OCCUPANCY_ENTROPY = 0.25
MEASURE_SCORE_WEIGHT_UNIQUE_TYPES = 0.20
MEASURE_SCORE_WEIGHT_DOMINANCE = 0.10
MEASURE_SCORE_WEIGHT_RARE_EVENTS = 0.10
MEASURE_SCORE_UNIQUE_TYPES_NORMALIZER = 10
MEASURE_SCORE_RARE_EVENT_RATIO_NORMALIZER = 0.20


# ============================================================
# FUNCIONES DE NEGOCIO (adaptadas de 02_prepareeventsds)
# ============================================================

def compute_minmax(df: pd.DataFrame, measure_cols):
    return {
        col: {
            "min": float(df[col].min()),
            "max": float(df[col].max()),
        }
        for col in measure_cols
    }


def compute_cuts_and_labels(minmax_stats, pct_thresholds):
    pct_list = [0.0] + pct_thresholds + [100.0]
    out = {}

    for col, mm in minmax_stats.items():
        mn, mx = mm["min"], mm["max"]
        r = mx - mn

        if r == 0:
            cuts = np.array([mn, mx])
            labels = ["0_100"]
        else:
            cuts = np.array([mn + p / 100 * r for p in pct_list])
            labels = [
                f"{int(pct_list[i])}_{int(pct_list[i + 1])}"
                for i in range(len(pct_list) - 1)
            ]

        out[col] = {"cuts": cuts, "labels": labels}

    return out


def build_event_catalog(bands, strategy, nan_mode):
    event_to_id = {}
    next_id = 1

    strat = strategy.lower()
    nan_keep = (nan_mode.lower() == "keep")

    for col, info in bands.items():
        labels = info["labels"]

        if strat in ("transitions", "both"):
            for a in labels:
                for b in labels:
                    if a != b:
                        event_to_id[f"{col}_{a}-to-{b}"] = next_id
                        next_id += 1

        if strat in ("levels", "both"):
            for a in labels:
                event_to_id[f"{col}_{a}"] = next_id
                next_id += 1

        if nan_keep:
            event_to_id[f"{col}_NaN_NaN"] = next_id
            next_id += 1

    return event_to_id


def assign_bands_to_column(values, cuts, labels):
    is_nan = np.isnan(values)
    idx = np.searchsorted(cuts, values, side="right") - 1
    idx = np.clip(idx, 0, len(labels) - 1)

    labels_arr = np.array(labels, dtype=object)
    assigned = labels_arr[idx]
    assigned[is_nan] = None

    kind = np.where(is_nan, "NaN", "band")

    return kind, assigned


def generate_events(df, epoch_col, measure_cols, bands, event_to_id, strategy, nan_mode, Tu):

    N = len(df)
    epochs = df[epoch_col].values.astype(np.int64)

    is_consecutive = np.zeros(N, dtype=bool)
    is_consecutive[1:] = (np.diff(epochs) == Tu)

    strat = strategy.lower()
    nan_keep = nan_mode.lower() == "keep"

    events_column = [[] for _ in range(N)]

    prev_kind = {col: None for col in measure_cols}
    prev_label = {col: None for col in measure_cols}

    col_kind = {}
    col_label = {}

    for col in measure_cols:
        vals = df[col].values
        cuts = bands[col]["cuts"]
        labels = bands[col]["labels"]

        k_arr, lbl_arr = assign_bands_to_column(vals, cuts, labels)
        col_kind[col] = k_arr
        col_label[col] = lbl_arr

    for i in range(N):
        row_events = []

        for col in measure_cols:
            curr_k = col_kind[col][i]
            curr_lbl = col_label[col][i]

            if i > 0 and is_consecutive[i] and strat in ("transitions", "both"):
                pk = prev_kind[col]
                pl = prev_label[col]
                if pk == "band" and curr_k == "band" and pl != curr_lbl:
                    ev = event_to_id.get(f"{col}_{pl}-to-{curr_lbl}")
                    if ev:
                        row_events.append(ev)

            if curr_k == "band" and strat in ("levels", "both"):
                ev = event_to_id.get(f"{col}_{curr_lbl}")
                if ev:
                    row_events.append(ev)

            elif curr_k == "NaN" and nan_keep:
                ev = event_to_id.get(f"{col}_NaN_NaN")
                if ev:
                    row_events.append(ev)

            prev_kind[col] = curr_k
            prev_label[col] = curr_lbl

        events_column[i] = row_events

    return pd.DataFrame({
        epoch_col: df[epoch_col].values,
        "events": events_column
    })


def build_event_metadata(event_to_id, bands):
    metadata = {}
    transition_catalog_count = 0
    level_catalog_count = 0

    for event_name, event_id in event_to_id.items():
        measure = None
        for col in bands.keys():
            prefix = f"{col}_"
            if event_name.startswith(prefix):
                measure = col
                payload = event_name[len(prefix):]
                break

        if measure is None:
            continue

        labels = bands[measure]["labels"]
        first_label = labels[0] if labels else None
        last_label = labels[-1] if labels else None
        label_to_idx = {label: idx for idx, label in enumerate(labels)}

        meta = {
            "event_id": int(event_id),
            "event_name": event_name,
            "measure_name": measure,
            "kind": "unknown",
            "rare": False,
            "rare_direction": None,
            "jump_size": None,
        }

        if payload == "NaN_NaN":
            meta["kind"] = "nan"
        elif "-to-" in payload:
            src, dst = payload.split("-to-", 1)
            meta["kind"] = "transition"
            meta["rare"] = dst in {first_label, last_label}
            if dst == first_label:
                meta["rare_direction"] = "low"
            elif dst == last_label:
                meta["rare_direction"] = "high"
            if src in label_to_idx and dst in label_to_idx:
                meta["jump_size"] = int(abs(label_to_idx[dst] - label_to_idx[src]))
            transition_catalog_count += 1
        else:
            meta["kind"] = "level"
            meta["rare"] = payload in {first_label, last_label}
            level_catalog_count += 1

        metadata[int(event_id)] = meta

    return metadata, int(transition_catalog_count), int(level_catalog_count)


def compute_transition_stats(event_counts, event_metadata, transition_catalog_count):
    transition_counts = []
    jump_sizes = []

    for event_id, count in event_counts.items():
        meta = event_metadata.get(int(event_id), {})
        if meta.get("kind") != "transition":
            continue
        transition_counts.append(int(count))
        jump_size = meta.get("jump_size")
        if jump_size is not None:
            jump_sizes.extend([int(jump_size)] * int(count))

    n_transition_events = int(sum(transition_counts))
    n_unique_transition_types_observed = int(len(transition_counts))
    transition_coverage_ratio = (
        float(n_unique_transition_types_observed / transition_catalog_count)
        if transition_catalog_count > 0 else 0.0
    )

    if jump_sizes:
        jump_arr = np.array(jump_sizes, dtype=float)
        jump_size_mean = float(jump_arr.mean())
        jump_size_std = float(jump_arr.std())
        pct_jump_eq_1 = float((jump_arr == 1).mean())
        pct_jump_ge_2 = float((jump_arr >= 2).mean())
        pct_jump_ge_3 = float((jump_arr >= 3).mean())
    else:
        jump_size_mean = 0.0
        jump_size_std = 0.0
        pct_jump_eq_1 = 0.0
        pct_jump_ge_2 = 0.0
        pct_jump_ge_3 = 0.0

    return {
        "n_transition_events": n_transition_events,
        "n_unique_transition_types_observed": n_unique_transition_types_observed,
        "transition_coverage_ratio": transition_coverage_ratio,
        "jump_size_mean": jump_size_mean,
        "jump_size_std": jump_size_std,
        "pct_jump_eq_1": pct_jump_eq_1,
        "pct_jump_ge_2": pct_jump_ge_2,
        "pct_jump_ge_3": pct_jump_ge_3,
    }


def safe_ratio(num, den):
    return float(num / den) if den else 0.0


def safe_entropy_from_counts(counts):
    positive_counts = [float(count) for count in counts if count > 0]
    total = float(sum(positive_counts))
    if total <= 0:
        return 0.0, 0.0

    probs = np.array([count / total for count in positive_counts], dtype=float)
    entropy = float(-(probs * np.log(probs)).sum())
    normalized_entropy = float(entropy / math.log(len(probs))) if len(probs) > 1 else 0.0

    return entropy, normalized_entropy


def compute_band_occupancy_metrics(band_counts):
    counts = [int(count) for count in band_counts.values()]
    total_band_count = int(sum(counts))
    nonzero_counts = [count for count in counts if count > 0]
    n_active_bands = int(len(nonzero_counts))
    max_band_count = int(max(counts)) if counts else 0
    min_nonzero_band_count = int(min(nonzero_counts)) if nonzero_counts else 0

    labels = list(band_counts.keys())
    first_label = labels[0] if labels else None
    last_label = labels[-1] if labels else None
    extreme_band_count = int(sum(
        int(band_counts.get(label, 0))
        for label in {first_label, last_label}
        if label is not None
    ))
    middle_band_count = int(total_band_count - extreme_band_count)
    occupancy_entropy, normalized_occupancy_entropy = safe_entropy_from_counts(counts)

    return {
        "total_band_count": total_band_count,
        "n_active_bands": n_active_bands,
        "max_band_count": max_band_count,
        "max_band_ratio": safe_ratio(max_band_count, total_band_count),
        "min_nonzero_band_count": min_nonzero_band_count,
        "extreme_band_count": extreme_band_count,
        "extreme_band_ratio": safe_ratio(extreme_band_count, total_band_count),
        "middle_band_count": middle_band_count,
        "middle_band_ratio": safe_ratio(middle_band_count, total_band_count),
        "occupancy_entropy": occupancy_entropy,
        "normalized_occupancy_entropy": normalized_occupancy_entropy,
    }


def compute_measure_quality_scores(per_measure):
    max_log_events = max(
        (math.log1p(float(stats["n_events_generated"])) for stats in per_measure.values()),
        default=0.0,
    )

    for stats in per_measure.values():
        n_events = int(stats["n_events_generated"])
        if n_events == 0 or max_log_events <= 0:
            score = 0.0
        else:
            normalized_log_events = safe_ratio(math.log1p(float(n_events)), max_log_events)
            score = (
                MEASURE_SCORE_WEIGHT_EVENTS * normalized_log_events
                + MEASURE_SCORE_WEIGHT_OCCUPANCY_ENTROPY * float(stats["normalized_occupancy_entropy"])
                + MEASURE_SCORE_WEIGHT_UNIQUE_TYPES * min(
                    safe_ratio(
                        float(stats["n_unique_event_types_observed"]),
                        MEASURE_SCORE_UNIQUE_TYPES_NORMALIZER,
                    ),
                    1,
                )
                + MEASURE_SCORE_WEIGHT_DOMINANCE * (1 - min(float(stats["top1_ratio"]), 1))
                + MEASURE_SCORE_WEIGHT_RARE_EVENTS * min(
                    safe_ratio(
                        float(stats["rare_event_ratio"]),
                        MEASURE_SCORE_RARE_EVENT_RATIO_NORMALIZER,
                    ),
                    1,
                )
            )

        stats["measure_transition_score"] = float(score)
        stats["high_target_candidate"] = bool(
            n_events > 0
            and int(stats["n_unique_event_types_observed"]) >= TARGET_CANDIDATE_MIN_UNIQUE_TYPES
            and int(stats["high_rare_event_count"]) > 0
            and float(stats["high_rare_event_ratio"]) >= TARGET_CANDIDATE_MIN_RATIO
        )
        stats["low_target_candidate"] = bool(
            n_events > 0
            and int(stats["n_unique_event_types_observed"]) >= TARGET_CANDIDATE_MIN_UNIQUE_TYPES
            and int(stats["low_rare_event_count"]) > 0
            and float(stats["low_rare_event_ratio"]) >= TARGET_CANDIDATE_MIN_RATIO
        )

    return per_measure


def build_target_candidates(per_measure):
    candidates = {}

    for measure, stats in per_measure.items():
        high_candidate = bool(stats["high_target_candidate"])
        low_candidate = bool(stats["low_target_candidate"])
        high_count = int(stats["high_rare_event_count"])
        low_count = int(stats["low_rare_event_count"])
        high_ratio = float(stats["high_rare_event_ratio"])
        low_ratio = float(stats["low_rare_event_ratio"])

        candidates[measure] = {
            "high": {
                "candidate": high_candidate,
                "extreme_event_count": high_count,
                "extreme_event_ratio": high_ratio,
                "reason": "passes high target candidate rules" if high_candidate else "does not pass high target candidate rules",
            },
            "low": {
                "candidate": low_candidate,
                "extreme_event_count": low_count,
                "extreme_event_ratio": low_ratio,
                "reason": "passes low target candidate rules" if low_candidate else "does not pass low target candidate rules",
            },
        }

    return candidates


def compute_global_gate_flags(global_stats):
    activity_flag = "reject" if (
        global_stats["total_events_generated"] == 0
        or global_stats["empty_rows_ratio"] >= 0.995
    ) else "warning" if global_stats["empty_rows_ratio"] >= 0.99 else "ok"

    diversity_flag = "reject" if global_stats["normalized_event_entropy"] < 0.30 else (
        "warning" if global_stats["normalized_event_entropy"] < 0.50 else "ok"
    )
    catalog_flag = "reject" if global_stats["catalog_coverage_ratio"] < 0.10 else (
        "warning" if global_stats["catalog_coverage_ratio"] < 0.20 else "ok"
    )
    dominance_flag = "reject" if global_stats["top1_event_ratio"] > 0.50 else (
        "warning" if global_stats["top1_event_ratio"] > 0.30 or global_stats["top5_event_ratio"] > 0.70 else "ok"
    )
    continuity_flag = "reject" if (
        global_stats["pct_jump_eq_1"] < 0.70
        or global_stats["pct_jump_ge_3"] > 0.10
    ) else "warning" if (
        global_stats["pct_jump_eq_1"] < 0.85
        or global_stats["pct_jump_ge_3"] > 0.05
    ) else "ok"
    measure_coverage_flag = "reject" if global_stats["non_eventless_measure_ratio"] < 0.30 else (
        "warning" if global_stats["non_eventless_measure_ratio"] < 0.50 else "ok"
    )

    flags = {
        "activity_flag": activity_flag,
        "diversity_flag": diversity_flag,
        "catalog_flag": catalog_flag,
        "dominance_flag": dominance_flag,
        "continuity_flag": continuity_flag,
        "measure_coverage_flag": measure_coverage_flag,
    }

    if "reject" in flags.values():
        gate_status = "reject"
    elif "warning" in flags.values():
        gate_status = "warning"
    else:
        gate_status = "candidate"

    return {**flags, "f02_gate_status": gate_status}


def compute_f02_quality_score(global_stats):
    return float(
        0.25 * global_stats["normalized_event_entropy"]
        + 0.20 * min(safe_ratio(global_stats["catalog_coverage_ratio"], 0.50), 1)
        + 0.20 * global_stats["non_eventless_measure_ratio"]
        + 0.15 * global_stats["pct_jump_eq_1"]
        + 0.10 * (1 - min(safe_ratio(global_stats["top1_event_ratio"], 0.50), 1))
        + 0.10 * min(safe_ratio(global_stats["nonempty_rows_ratio"], 0.05), 1)
    )


def format_pct(x):
    return f"{100 * float(x):.2f}%"


def format_float(x, digits=3):
    return f"{float(x):.{digits}f}"


def html_escape(value):
    return html.escape("" if value is None else str(value))


def fmt_float(x, digits=3):
    try:
        return f"{float(x):.{digits}f}"
    except (TypeError, ValueError):
        return "n/a"


def fmt_pct(x):
    try:
        return f"{100 * float(x):.2f}%"
    except (TypeError, ValueError):
        return "n/a"


def badge(text, kind):
    return f'<span class="badge {html_escape(kind)}">{html_escape(text)}</span>'


def pass_fail_badge(ok):
    return badge("OK" if ok else "FAIL", "ok" if ok else "reject")


def metric_status(value, op, threshold):
    try:
        val = float(value)
    except (TypeError, ValueError):
        return False
    if op == ">":
        return val > threshold
    if op == ">=":
        return val >= threshold
    if op == "<":
        return val < threshold
    if op == "<=":
        return val <= threshold
    return False


def render_gate_criteria_table(global_stats):
    rows = [
        ("Actividad", "total_events_generated", "> 0", "Debe generar algún evento", ">", 0, "int"),
        ("Actividad", "empty_rows_ratio", "< 0.995", "No puede estar prácticamente vacía", "<", 0.995, "pct"),
        ("Diversidad", "normalized_event_entropy", ">= 0.50", "Debe haber diversidad suficiente", ">=", 0.50, "float"),
        ("Dominancia", "top1_event_ratio", "<= 0.30", "No debe dominar una única transición", "<=", 0.30, "pct"),
        ("Dominancia", "top5_event_ratio", "<= 0.70", "No deben dominar solo cinco eventos", "<=", 0.70, "pct"),
        ("Catálogo", "catalog_coverage_ratio", ">= 0.20", "Debe usarse una parte mínima del catálogo", ">=", 0.20, "pct"),
        ("Continuidad", "pct_jump_eq_1", ">= 0.85", "La mayoría de transiciones deben ser locales", ">=", 0.85, "pct"),
        ("Continuidad", "pct_jump_ge_3", "<= 0.05", "No debe haber demasiados saltos bruscos", "<=", 0.05, "pct"),
        ("Cobertura de medidas", "non_eventless_measure_ratio", ">= 0.50", "Al menos la mitad de medidas deben generar eventos", ">=", 0.50, "pct"),
    ]
    body = []
    for block, metric, threshold_text, interpretation, op, threshold, fmt in rows:
        value = global_stats.get(metric)
        ok = metric_status(value, op, threshold)
        if fmt == "pct":
            value_text = fmt_pct(value)
        elif fmt == "int":
            value_text = html_escape(value if value is not None else "n/a")
        else:
            value_text = fmt_float(value)
        body.append(
            "<tr>"
            f"<td>{html_escape(block)}</td>"
            f"<td><code>{html_escape(metric)}</code></td>"
            f"<td>{html_escape(threshold_text)}</td>"
            f"<td>{html_escape(interpretation)}</td>"
            f"<td>{value_text}</td>"
            f"<td>{pass_fail_badge(ok)}</td>"
            "</tr>"
        )
    return (
        '<table class="tbl decision-table">'
        "<thead><tr><th>Bloque</th><th>Métrica</th><th>Threshold</th><th>Interpretación</th><th>Valor actual</th><th>Estado</th></tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
    )


def render_target_rule_table():
    rows = [
        ("High", "high_rare_event_count", "> 0"),
        ("High", "high_rare_event_ratio", ">= 0.001"),
        ("Low", "low_rare_event_count", "> 0"),
        ("Low", "low_rare_event_ratio", ">= 0.001"),
        ("Ambos", "n_unique_event_types_observed", ">= 3"),
    ]
    body = "".join(
        "<tr>"
        f"<td>{html_escape(target)}</td>"
        f"<td><code>{html_escape(metric)}</code></td>"
        f"<td>{html_escape(threshold)}</td>"
        "</tr>"
        for target, metric, threshold in rows
    )
    return (
        '<table class="tbl compact">'
        "<thead><tr><th>Target</th><th>Métrica</th><th>Threshold</th></tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


def render_band_occupancy_table(band_occupancy):
    if not isinstance(band_occupancy, dict) or not band_occupancy:
        return "<p class=\"muted\">Sin ocupación de bandas.</p>"
    rows = "".join(
        f"<tr><td>{html_escape(band)}</td><td>{html_escape(count)}</td></tr>"
        for band, count in band_occupancy.items()
    )
    return (
        '<table class="tbl mini">'
        "<thead><tr><th>Banda</th><th>Count</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def render_measure_details(measure_stats):
    fields = [
        ("top1_ratio", "pct"),
        ("rare_event_ratio", "pct"),
        ("n_active_bands", "raw"),
        ("max_band_ratio", "pct"),
        ("extreme_band_ratio", "pct"),
        ("occupancy_entropy", "float"),
        ("normalized_occupancy_entropy", "float"),
        ("band_degeneracy_flag", "bool"),
        ("extreme_occupancy_flag", "bool"),
        ("measure_transition_score", "float"),
    ]
    rows = []
    for key, fmt in fields:
        value = measure_stats.get(key)
        if fmt == "pct":
            rendered = fmt_pct(value)
        elif fmt == "float":
            rendered = fmt_float(value)
        elif fmt == "bool":
            rendered = badge(str(bool(value)).lower(), "ok" if not value else "warning")
        else:
            rendered = html_escape(value if value is not None else "n/a")
        rows.append(f"<tr><td><code>{html_escape(key)}</code></td><td>{rendered}</td></tr>")

    metrics_table = (
        '<table class="tbl mini">'
        "<thead><tr><th>Métrica</th><th>Valor</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )
    bands_table = render_band_occupancy_table(measure_stats.get("band_occupancy", {}))
    return f"<details><summary>Más info</summary><div class=\"details-grid\">{metrics_table}{bands_table}</div></details>"


def render_target_candidates_table(stats):
    per_measure = stats.get("per_measure", {}) or {}
    target_candidates = stats.get("target_candidates", {}) or {}
    rows = []

    for measure_name, measure_stats in per_measure.items():
        candidate_info = target_candidates.get(measure_name, {}) or {}
        high_info = candidate_info.get("high", {}) or {}
        low_info = candidate_info.get("low", {}) or {}
        high_candidate = bool(high_info.get("candidate", measure_stats.get("high_target_candidate", False)))
        low_candidate = bool(low_info.get("candidate", measure_stats.get("low_target_candidate", False)))
        high_count = high_info.get("extreme_event_count", measure_stats.get("high_rare_event_count", 0))
        low_count = low_info.get("extreme_event_count", measure_stats.get("low_rare_event_count", 0))
        high_ratio = high_info.get("extreme_event_ratio", measure_stats.get("high_rare_event_ratio", 0.0))
        low_ratio = low_info.get("extreme_event_ratio", measure_stats.get("low_rare_event_ratio", 0.0))

        rows.append(
            "<tr>"
            f"<td class=\"measure-name\">{html_escape(measure_name)}</td>"
            f"<td>{badge(str(high_candidate).lower(), 'ok' if high_candidate else 'reject')}</td>"
            f"<td>{html_escape(high_info.get('reason', 'n/a'))}</td>"
            f"<td>{html_escape(high_count)}</td>"
            f"<td>{fmt_pct(high_ratio)}</td>"
            f"<td>{badge(str(low_candidate).lower(), 'ok' if low_candidate else 'reject')}</td>"
            f"<td>{html_escape(low_info.get('reason', 'n/a'))}</td>"
            f"<td>{html_escape(low_count)}</td>"
            f"<td>{fmt_pct(low_ratio)}</td>"
            f"<td>{html_escape(measure_stats.get('n_events_generated', 'n/a'))}</td>"
            f"<td>{html_escape(measure_stats.get('n_unique_event_types_observed', 'n/a'))}</td>"
            f"<td>{render_measure_details(measure_stats)}</td>"
            "</tr>"
        )

    if not rows:
        return "<p>No hay candidatos calculados.</p>"

    return (
        '<table class="tbl target-table">'
        "<thead><tr>"
        "<th>measure_name</th><th>high_candidate</th><th>high_reason</th><th>high_rare_event_count</th><th>high_rare_event_ratio</th>"
        "<th>low_candidate</th><th>low_reason</th><th>low_rare_event_count</th><th>low_rare_event_ratio</th>"
        "<th>n_events_generated</th><th>n_unique_event_types_observed</th><th>Más info</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def compute_measure_stats(
    measure_cols,
    df_events,
    event_counts,
    event_metadata,
    band_assignments,
    strategy,
):
    per_measure = {}
    band_occupancy = {}

    row_measure_counts = {col: [] for col in measure_cols}
    for row_events in df_events["events"]:
        counts = {col: 0 for col in measure_cols}
        for event_id in row_events:
            meta = event_metadata.get(int(event_id))
            if not meta:
                continue
            measure = meta["measure_name"]
            counts[measure] = counts.get(measure, 0) + 1
        for col in measure_cols:
            row_measure_counts[col].append(int(counts.get(col, 0)))

    for col in measure_cols:
        measure_event_counts = {
            int(event_id): int(count)
            for event_id, count in event_counts.items()
            if event_metadata.get(int(event_id), {}).get("measure_name") == col
        }
        total_measure_events = int(sum(measure_event_counts.values()))
        observed_types = int(len(measure_event_counts))
        top1_ratio = (
            float(max(measure_event_counts.values()) / total_measure_events)
            if total_measure_events > 0 else 0.0
        )
        rare_count = int(sum(
            count for event_id, count in measure_event_counts.items()
            if event_metadata.get(int(event_id), {}).get("rare", False)
        ))
        rare_ratio = float(rare_count / total_measure_events) if total_measure_events > 0 else 0.0
        rare_event_type_count = int(sum(
            1 for event_id in measure_event_counts
            if event_metadata.get(int(event_id), {}).get("rare", False)
        ))
        high_rare_count = int(sum(
            count for event_id, count in measure_event_counts.items()
            if event_metadata.get(int(event_id), {}).get("kind") == "transition"
            and event_metadata.get(int(event_id), {}).get("rare_direction") == "high"
        ))
        low_rare_count = int(sum(
            count for event_id, count in measure_event_counts.items()
            if event_metadata.get(int(event_id), {}).get("kind") == "transition"
            and event_metadata.get(int(event_id), {}).get("rare_direction") == "low"
        ))
        high_rare_event_type_count = int(sum(
            1 for event_id in measure_event_counts
            if event_metadata.get(int(event_id), {}).get("kind") == "transition"
            and event_metadata.get(int(event_id), {}).get("rare_direction") == "high"
        ))
        low_rare_event_type_count = int(sum(
            1 for event_id in measure_event_counts
            if event_metadata.get(int(event_id), {}).get("kind") == "transition"
            and event_metadata.get(int(event_id), {}).get("rare_direction") == "low"
        ))
        high_rare_event_ratio = safe_ratio(high_rare_count, total_measure_events)
        low_rare_event_ratio = safe_ratio(low_rare_count, total_measure_events)

        jump_vals = []
        if strategy.lower() in ("transitions", "both"):
            for event_id, count in measure_event_counts.items():
                meta = event_metadata.get(int(event_id), {})
                if meta.get("kind") == "transition" and meta.get("jump_size") is not None:
                    jump_vals.extend([int(meta["jump_size"])] * int(count))

        band_counts = {}
        kind_arr = band_assignments[col]["kind"]
        label_arr = band_assignments[col]["label"]
        for label in band_assignments[col]["labels"]:
            band_counts[label] = int(np.sum((kind_arr == "band") & (label_arr == label)))
        band_metrics = compute_band_occupancy_metrics(band_counts)

        measure_entry = {
            "n_events_generated": total_measure_events,
            "n_unique_event_types_observed": observed_types,
            "top1_ratio": top1_ratio,
            "rare_event_count": rare_count,
            "rare_event_ratio": rare_ratio,
            "high_rare_event_count": high_rare_count,
            "low_rare_event_count": low_rare_count,
            "rare_event_type_count": rare_event_type_count,
            "high_rare_event_type_count": high_rare_event_type_count,
            "low_rare_event_type_count": low_rare_event_type_count,
            "high_rare_event_ratio": high_rare_event_ratio,
            "low_rare_event_ratio": low_rare_event_ratio,
            "mean_events_per_row_contributed": float(np.mean(row_measure_counts[col])) if row_measure_counts[col] else 0.0,
            "band_occupancy": band_counts,
            **band_metrics,
        }
        measure_entry["is_eventless_measure"] = bool(total_measure_events == 0)
        measure_entry["band_degeneracy_flag"] = bool(measure_entry["n_active_bands"] <= 1)
        measure_entry["extreme_occupancy_flag"] = bool(measure_entry["extreme_band_ratio"] >= 0.95)
        if strategy.lower() in ("transitions", "both"):
            measure_entry["jump_size_mean"] = float(np.mean(jump_vals)) if jump_vals else 0.0

        per_measure[col] = measure_entry
        band_occupancy[col] = band_counts

    per_measure = compute_measure_quality_scores(per_measure)

    return per_measure, band_occupancy


def compute_event_stats(df, df_events, epoch_col, measure_cols, bands, event_to_id, strategy, nan_mode, Tu):
    row_lengths = df_events["events"].apply(len).to_numpy(dtype=int)
    total_events_generated = int(row_lengths.sum())
    total_rows = int(len(df_events))
    flat_events = [int(event_id) for row in df_events["events"] for event_id in row]
    event_counts = Counter(flat_events)
    event_metadata, transition_catalog_count, level_catalog_count = build_event_metadata(event_to_id, bands)

    observed_types = int(len(event_counts))
    n_event_types_catalog = int(len(event_to_id))
    top_counts = [count for _, count in event_counts.most_common(5)]
    top1_event_ratio = float(top_counts[0] / total_events_generated) if top_counts and total_events_generated > 0 else 0.0
    top5_event_ratio = float(sum(top_counts) / total_events_generated) if total_events_generated > 0 else 0.0

    if total_events_generated > 0 and observed_types > 0:
        probs = np.array([count / total_events_generated for count in event_counts.values()], dtype=float)
        event_entropy = float(-(probs * np.log(probs)).sum())
        normalized_event_entropy = (
            float(event_entropy / math.log(observed_types))
            if observed_types > 1 else 0.0
        )
    else:
        event_entropy = 0.0
        normalized_event_entropy = 0.0

    rare_event_count = int(sum(
        count for event_id, count in event_counts.items()
        if event_metadata.get(int(event_id), {}).get("rare", False)
    ))
    rare_event_ratio = float(rare_event_count / total_events_generated) if total_events_generated > 0 else 0.0
    rare_event_types_observed = int(sum(
        1 for event_id in event_counts
        if event_metadata.get(int(event_id), {}).get("rare", False)
    ))
    rare_event_type_ratio = float(rare_event_types_observed / observed_types) if observed_types > 0 else 0.0

    epochs = df[epoch_col].to_numpy(dtype=np.int64)
    is_consecutive = np.zeros(len(epochs), dtype=bool)
    if len(epochs) > 1:
        is_consecutive[1:] = (np.diff(epochs) == Tu)
    n_steps = max(len(epochs) - 1, 0)
    n_consecutive_steps = int(is_consecutive[1:].sum()) if len(is_consecutive) > 1 else 0
    n_broken_steps = int(n_steps - n_consecutive_steps)
    consecutive_ratio = float(n_consecutive_steps / n_steps) if n_steps > 0 else 0.0
    broken_ratio = float(n_broken_steps / n_steps) if n_steps > 0 else 0.0

    band_assignments = {}
    for col in measure_cols:
        kind_arr, label_arr = assign_bands_to_column(
            df[col].to_numpy(),
            bands[col]["cuts"],
            bands[col]["labels"],
        )
        band_assignments[col] = {
            "kind": kind_arr,
            "label": label_arr,
            "labels": bands[col]["labels"],
        }

    per_measure, band_occupancy = compute_measure_stats(
        measure_cols=measure_cols,
        df_events=df_events,
        event_counts=event_counts,
        event_metadata=event_metadata,
        band_assignments=band_assignments,
        strategy=strategy,
    )

    transition_stats = {
        "n_transition_events": 0,
        "n_unique_transition_types_observed": 0,
        "transition_coverage_ratio": 0.0,
        "jump_size_mean": 0.0,
        "jump_size_std": 0.0,
        "pct_jump_eq_1": 0.0,
        "pct_jump_ge_2": 0.0,
        "pct_jump_ge_3": 0.0,
    }
    if strategy.lower() in ("transitions", "both"):
        transition_stats = compute_transition_stats(
            event_counts=event_counts,
            event_metadata=event_metadata,
            transition_catalog_count=transition_catalog_count,
        )

    n_level_events = int(sum(
        count for event_id, count in event_counts.items()
        if event_metadata.get(int(event_id), {}).get("kind") == "level"
    ))
    n_unique_level_types_observed = int(sum(
        1 for event_id in event_counts
        if event_metadata.get(int(event_id), {}).get("kind") == "level"
    ))

    top_events = []
    id_to_name = {int(event_id): name for name, event_id in event_to_id.items()}
    for event_id, count in event_counts.most_common(20):
        top_events.append({
            "event_id": int(event_id),
            "event_name": id_to_name.get(int(event_id), f"event_{event_id}"),
            "count": int(count),
            "ratio": float(count / total_events_generated) if total_events_generated > 0 else 0.0,
        })

    n_measures_total = int(len(measure_cols))
    n_eventless_measures = int(sum(
        1 for measure_stats in per_measure.values()
        if measure_stats["is_eventless_measure"]
    ))
    n_non_eventless_measures = int(n_measures_total - n_eventless_measures)
    n_measures_with_high_rare_events = int(sum(
        1 for measure_stats in per_measure.values()
        if int(measure_stats["high_rare_event_count"]) > 0
    ))
    n_measures_with_low_rare_events = int(sum(
        1 for measure_stats in per_measure.values()
        if int(measure_stats["low_rare_event_count"]) > 0
    ))
    high_rare_event_count = int(sum(
        int(measure_stats["high_rare_event_count"])
        for measure_stats in per_measure.values()
    ))
    low_rare_event_count = int(sum(
        int(measure_stats["low_rare_event_count"])
        for measure_stats in per_measure.values()
    ))

    global_stats = {
        "total_events_generated": total_events_generated,
        "mean_events_per_row": float(row_lengths.mean()) if total_rows > 0 else 0.0,
        "std_events_per_row": float(row_lengths.std()) if total_rows > 0 else 0.0,
        "max_events_per_row": int(row_lengths.max()) if total_rows > 0 else 0,
        "p95_events_per_row": float(np.percentile(row_lengths, 95)) if total_rows > 0 else 0.0,
        "empty_rows_ratio": float(np.mean(row_lengths == 0)) if total_rows > 0 else 0.0,
        "nonempty_rows_ratio": float(np.mean(row_lengths > 0)) if total_rows > 0 else 0.0,
        "n_event_types_catalog": n_event_types_catalog,
        "n_event_types_observed": observed_types,
        "catalog_coverage_ratio": float(observed_types / n_event_types_catalog) if n_event_types_catalog > 0 else 0.0,
        "effective_catalog_unused_ratio": 1.0 - (float(observed_types / n_event_types_catalog) if n_event_types_catalog > 0 else 0.0),
        "rare_event_count": rare_event_count,
        "rare_event_ratio": rare_event_ratio,
        "rare_event_types_observed": rare_event_types_observed,
        "rare_event_type_ratio": rare_event_type_ratio,
        "top1_event_ratio": top1_event_ratio,
        "top5_event_ratio": top5_event_ratio,
        "event_entropy": event_entropy,
        "normalized_event_entropy": normalized_event_entropy,
        "n_consecutive_steps": n_consecutive_steps,
        "consecutive_ratio": consecutive_ratio,
        "n_broken_steps": n_broken_steps,
        "broken_ratio": broken_ratio,
        "n_level_events": n_level_events,
        "n_unique_level_types_observed": n_unique_level_types_observed,
        "n_measures_total": n_measures_total,
        "n_eventless_measures": n_eventless_measures,
        "eventless_measure_ratio": safe_ratio(n_eventless_measures, n_measures_total),
        "n_non_eventless_measures": n_non_eventless_measures,
        "non_eventless_measure_ratio": safe_ratio(n_non_eventless_measures, n_measures_total),
        "n_measures_with_high_rare_events": n_measures_with_high_rare_events,
        "n_measures_with_low_rare_events": n_measures_with_low_rare_events,
        "high_rare_measure_ratio": safe_ratio(n_measures_with_high_rare_events, n_measures_total),
        "low_rare_measure_ratio": safe_ratio(n_measures_with_low_rare_events, n_measures_total),
        "high_rare_event_count": high_rare_event_count,
        "low_rare_event_count": low_rare_event_count,
        "high_rare_event_ratio": safe_ratio(high_rare_event_count, total_events_generated),
        "low_rare_event_ratio": safe_ratio(low_rare_event_count, total_events_generated),
        "events_per_million_rows": safe_ratio(total_events_generated * 1_000_000, total_rows),
        **transition_stats,
    }
    global_stats["f02_quality_score"] = compute_f02_quality_score(global_stats)
    global_stats.update(compute_global_gate_flags(global_stats))

    stats = {
        "global": global_stats,
        "event_frequency": {
            str(event_id): {
                "event_name": id_to_name.get(int(event_id), f"event_{event_id}"),
                "count": int(count),
            }
            for event_id, count in event_counts.most_common()
        },
        "per_measure": per_measure,
        "top_events": top_events,
        "band_occupancy": band_occupancy,
        "target_candidates": build_target_candidates(per_measure),
    }

    return stats


def build_outputs_metrics(stats, execution_time, n_rows_in, n_rows_out):
    global_stats = stats["global"]
    return {
        "execution_time": float(execution_time),
        "n_rows_in": int(n_rows_in),
        "n_rows_out": int(n_rows_out),
        "total_events_generated": int(global_stats["total_events_generated"]),
        "mean_events_per_row": float(global_stats["mean_events_per_row"]),
        "empty_rows_ratio": float(global_stats["empty_rows_ratio"]),
        "n_event_types_observed": int(global_stats["n_event_types_observed"]),
        "catalog_coverage_ratio": float(global_stats["catalog_coverage_ratio"]),
        "top1_event_ratio": float(global_stats["top1_event_ratio"]),
        "rare_event_ratio": float(global_stats["rare_event_ratio"]),
        "eventless_measure_ratio": float(global_stats["eventless_measure_ratio"]),
        "non_eventless_measure_ratio": float(global_stats["non_eventless_measure_ratio"]),
        "high_rare_measure_ratio": float(global_stats["high_rare_measure_ratio"]),
        "low_rare_measure_ratio": float(global_stats["low_rare_measure_ratio"]),
        "high_rare_event_ratio": float(global_stats["high_rare_event_ratio"]),
        "low_rare_event_ratio": float(global_stats["low_rare_event_ratio"]),
        "f02_quality_score": float(global_stats["f02_quality_score"]),
        "f02_gate_status": global_stats["f02_gate_status"],
        "event_entropy": float(global_stats["event_entropy"]),
        "normalized_event_entropy": float(global_stats["normalized_event_entropy"]),
        "n_transition_events": int(global_stats["n_transition_events"]),
        "jump_size_mean": float(global_stats["jump_size_mean"]),
    }


def _build_report_html_legacy(variant, parent_variant, strategy, bands_pct, nan_mode, stats):
    global_stats = stats["global"]

    top_events_df = pd.DataFrame(stats["top_events"])
    if not top_events_df.empty:
        top_events_df["ratio"] = top_events_df["ratio"].map(lambda x: f"{100 * float(x):.2f}%")
        top_events_html = top_events_df.to_html(index=False, classes="tbl", escape=False)
    else:
        top_events_html = "<p>No hay eventos observados.</p>"

    per_measure_rows = []
    for measure_name, measure_stats in stats["per_measure"].items():
        row = {
            "measure_name": measure_name,
            "n_events_generated": measure_stats["n_events_generated"],
            "n_unique_event_types_observed": measure_stats["n_unique_event_types_observed"],
            "top1_ratio": format_pct(measure_stats["top1_ratio"]),
            "rare_event_ratio": format_pct(measure_stats["rare_event_ratio"]),
            "high_rare_event_ratio": format_pct(measure_stats["high_rare_event_ratio"]),
            "low_rare_event_ratio": format_pct(measure_stats["low_rare_event_ratio"]),
            "n_active_bands": measure_stats["n_active_bands"],
            "max_band_ratio": format_pct(measure_stats["max_band_ratio"]),
            "extreme_band_ratio": format_pct(measure_stats["extreme_band_ratio"]),
            "occupancy_entropy": format_float(measure_stats["occupancy_entropy"]),
            "band_degeneracy_flag": measure_stats["band_degeneracy_flag"],
            "measure_transition_score": format_float(measure_stats["measure_transition_score"]),
            "mean_events_per_row_contributed": format_float(measure_stats["mean_events_per_row_contributed"]),
        }
        if "jump_size_mean" in measure_stats:
            row["jump_size_mean"] = format_float(measure_stats["jump_size_mean"])
        row["band_occupancy"] = ", ".join(
            f"{band}:{count}" for band, count in measure_stats["band_occupancy"].items()
        )
        per_measure_rows.append(row)

    per_measure_html = (
        pd.DataFrame(per_measure_rows).to_html(index=False, classes="tbl", escape=False)
        if per_measure_rows else "<p>No hay resumen por medida.</p>"
    )

    gate_rows = [
        {"gate": key, "status": global_stats[key]}
        for key in [
            "activity_flag",
            "diversity_flag",
            "catalog_flag",
            "dominance_flag",
            "continuity_flag",
            "measure_coverage_flag",
        ]
    ]
    gate_diagnosis_html = pd.DataFrame(gate_rows).to_html(index=False, classes="tbl", escape=False)

    target_candidate_rows = []
    for measure_name, target_info in stats.get("target_candidates", {}).items():
        for side in ("high", "low"):
            side_info = target_info[side]
            target_candidate_rows.append({
                "measure_name": measure_name,
                "side": side,
                "candidate": side_info["candidate"],
                "extreme_event_count": side_info["extreme_event_count"],
                "extreme_event_ratio": format_pct(side_info["extreme_event_ratio"]),
                "reason": side_info["reason"],
            })
    target_candidates_html = (
        pd.DataFrame(target_candidate_rows).to_html(index=False, classes="tbl", escape=False)
        if target_candidate_rows else "<p>No hay candidatos calculados.</p>"
    )

    high_candidate_measures = int(sum(
        1 for measure_stats in stats["per_measure"].values()
        if measure_stats["high_target_candidate"]
    ))
    low_candidate_measures = int(sum(
        1 for measure_stats in stats["per_measure"].values()
        if measure_stats["low_target_candidate"]
    ))

    summary_cards = f"""
    <div class="kpi-grid">
      <div class="card"><div class="k">Total events</div><div class="v">{global_stats['total_events_generated']:,}</div></div>
      <div class="card"><div class="k">Mean / row</div><div class="v">{global_stats['mean_events_per_row']:.3f}</div></div>
      <div class="card"><div class="k">Empty rows</div><div class="v">{100 * global_stats['empty_rows_ratio']:.2f}%</div></div>
      <div class="card"><div class="k">Observed types</div><div class="v">{global_stats['n_event_types_observed']}</div></div>
      <div class="card"><div class="k">Catalog coverage</div><div class="v">{100 * global_stats['catalog_coverage_ratio']:.2f}%</div></div>
      <div class="card"><div class="k">Rare event ratio</div><div class="v">{100 * global_stats['rare_event_ratio']:.2f}%</div></div>
      <div class="card"><div class="k">Gate status</div><div class="v">{global_stats['f02_gate_status']}</div></div>
      <div class="card"><div class="k">Quality score</div><div class="v">{global_stats['f02_quality_score']:.3f}</div></div>
      <div class="card"><div class="k">Non-eventless measures</div><div class="v">{global_stats['n_non_eventless_measures']}/{global_stats['n_measures_total']}</div></div>
      <div class="card"><div class="k">High candidate measures</div><div class="v">{high_candidate_measures}</div></div>
      <div class="card"><div class="k">Low candidate measures</div><div class="v">{low_candidate_measures}</div></div>
      <div class="card"><div class="k">Entropy</div><div class="v">{global_stats['event_entropy']:.3f}</div></div>
      <div class="card"><div class="k">Norm entropy</div><div class="v">{global_stats['normalized_event_entropy']:.3f}</div></div>
    </div>
    """

    global_table = pd.DataFrame(
        [{"metric": key, "value": value} for key, value in global_stats.items()]
    ).to_html(index=False, classes="tbl", escape=False)

    return f"""
    <!doctype html>
    <html lang="es">
    <head>
      <meta charset="utf-8">
      <title>F02 Events — {variant}</title>
      <style>
        body {{ font-family: Arial, sans-serif; margin: 24px; color: #1f2937; }}
        h1, h2, h3 {{ color: #111827; }}
        .lead {{ color: #4b5563; max-width: 980px; }}
        .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 20px 0; }}
        .card {{ border: 1px solid #e5e7eb; border-radius: 10px; padding: 14px; background: #f9fafb; }}
        .card .k {{ font-size: 12px; color: #6b7280; text-transform: uppercase; }}
        .card .v {{ font-size: 24px; font-weight: 700; margin-top: 6px; }}
        .tbl {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
        .tbl th, .tbl td {{ border: 1px solid #d1d5db; padding: 8px 10px; text-align: left; }}
        .tbl th {{ background: #f3f4f6; }}
        .panel {{ margin: 24px 0; }}
      </style>
    </head>
    <body>
      <h1>F02 Events — {variant}</h1>
      <p class="lead">
        Parent: <code>{parent_variant}</code> | strategy: <code>{strategy}</code> | bands: <code>{bands_pct}</code> | nan_mode: <code>{nan_mode}</code>.
        Este reporte resume la calidad y estructura del dataset de eventos generado sin alterar la lógica principal de F02.
      </p>

      {summary_cards}

      <section class="panel">
        <h2>Resumen global</h2>
        {global_table}
      </section>

      <section class="panel">
        <h2>Gate diagnosis</h2>
        {gate_diagnosis_html}
      </section>

      <section class="panel">
        <h2>Target candidates</h2>
        {target_candidates_html}
      </section>

      <section class="panel">
        <h2>Top events</h2>
        {top_events_html}
      </section>

      <section class="panel">
        <h2>Resumen por medida</h2>
        {per_measure_html}
      </section>
    </body>
    </html>
    """


def build_report_html(variant, parent_variant, strategy, bands_pct, nan_mode, stats):
    global_stats = stats.get("global", {})

    top_events_df = pd.DataFrame(stats.get("top_events", []))
    if not top_events_df.empty:
        if "ratio" in top_events_df.columns:
            top_events_df["ratio"] = top_events_df["ratio"].map(fmt_pct)
        top_events_html = top_events_df.to_html(index=False, classes="tbl", escape=True)
    else:
        top_events_html = "<p>No hay eventos observados.</p>"

    gate_status = str(global_stats.get("f02_gate_status", "n/a"))
    gate_kind = "ok" if gate_status == "candidate" else "warning" if gate_status == "warning" else "reject"
    total_events = global_stats.get("total_events_generated", 0)
    try:
        total_events_text = f"{int(total_events):,}"
    except (TypeError, ValueError):
        total_events_text = "n/a"

    kpis = [
        ("f02_gate_status", badge(gate_status, gate_kind)),
        ("f02_quality_score", fmt_float(global_stats.get("f02_quality_score"))),
        ("total_events_generated", html_escape(total_events_text)),
        ("normalized_event_entropy", fmt_float(global_stats.get("normalized_event_entropy"))),
        ("catalog_coverage_ratio", fmt_pct(global_stats.get("catalog_coverage_ratio"))),
        ("non_eventless_measure_ratio", fmt_pct(global_stats.get("non_eventless_measure_ratio"))),
        ("high_rare_measure_ratio", fmt_pct(global_stats.get("high_rare_measure_ratio"))),
        ("low_rare_measure_ratio", fmt_pct(global_stats.get("low_rare_measure_ratio"))),
    ]
    kpi_cards = "".join(
        f'<div class="card"><div class="k">{html_escape(label)}</div><div class="v">{value}</div></div>'
        for label, value in kpis
    )

    global_table = pd.DataFrame(
        [{"metric": key, "value": value} for key, value in global_stats.items()]
    ).to_html(index=False, classes="tbl", escape=True)
    gate_criteria_html = render_gate_criteria_table(global_stats)
    target_rules_html = render_target_rule_table()
    target_candidates_html = render_target_candidates_table(stats)

    return f"""
    <!doctype html>
    <html lang="es">
    <head>
      <meta charset="utf-8">
      <title>F02 Events - {html_escape(variant)}</title>
      <style>
        :root {{
          --bg: #f6f8fb;
          --panel: #ffffff;
          --ink: #172033;
          --muted: #667085;
          --line: #d9e0ea;
          --head: #eef3f8;
          --ok-bg: #dcfce7;
          --ok-fg: #166534;
          --warn-bg: #fef3c7;
          --warn-fg: #92400e;
          --bad-bg: #fee2e2;
          --bad-fg: #991b1b;
          --code: #26364f;
        }}
        * {{ box-sizing: border-box; }}
        body {{
          margin: 0;
          background: var(--bg);
          color: var(--ink);
          font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
          line-height: 1.45;
        }}
        main {{ max-width: 1480px; margin: 0 auto; padding: 28px; }}
        h1, h2, h3 {{ margin: 0 0 10px; color: var(--ink); }}
        h1 {{ font-size: 30px; letter-spacing: 0; }}
        h2 {{ font-size: 19px; margin-top: 4px; }}
        p {{ margin: 8px 0 0; }}
        code {{ color: var(--code); background: #eef3f8; border-radius: 4px; padding: 1px 4px; }}
        .hero {{
          background: linear-gradient(180deg, #ffffff 0%, #f9fbfd 100%);
          border: 1px solid var(--line);
          border-radius: 8px;
          padding: 22px;
          box-shadow: 0 10px 24px rgba(23, 32, 51, 0.06);
        }}
        .meta {{
          display: flex;
          flex-wrap: wrap;
          gap: 8px 14px;
          color: var(--muted);
          font-size: 13px;
          margin-top: 10px;
        }}
        .lead {{ color: var(--muted); max-width: 1120px; }}
        .kpi-grid {{
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
          gap: 12px;
          margin-top: 18px;
        }}
        .card {{
          border: 1px solid var(--line);
          border-radius: 8px;
          padding: 14px;
          background: var(--panel);
        }}
        .card .k {{
          min-height: 32px;
          color: var(--muted);
          font-size: 11px;
          font-weight: 700;
          text-transform: uppercase;
          overflow-wrap: anywhere;
        }}
        .card .v {{ margin-top: 7px; font-size: 23px; font-weight: 800; overflow-wrap: anywhere; }}
        .panel {{
          margin-top: 22px;
          padding: 18px;
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 8px;
        }}
        .table-wrap {{ overflow-x: auto; margin-top: 12px; }}
        .tbl {{
          border-collapse: collapse;
          width: 100%;
          min-width: 760px;
          font-size: 13px;
        }}
        .tbl th, .tbl td {{
          border: 1px solid var(--line);
          padding: 8px 10px;
          text-align: left;
          vertical-align: top;
        }}
        .tbl th {{
          position: sticky;
          top: 0;
          z-index: 1;
          background: var(--head);
          color: #344054;
          font-size: 11px;
          text-transform: uppercase;
          letter-spacing: 0;
        }}
        .tbl tr:nth-child(even) td {{ background: #fbfdff; }}
        .target-table {{ min-width: 1360px; }}
        .compact {{ max-width: 720px; min-width: 520px; }}
        .mini {{ min-width: 260px; font-size: 12px; }}
        .mini th {{ position: static; }}
        .measure-name {{ font-weight: 700; color: #111827; }}
        .badge {{
          display: inline-flex;
          align-items: center;
          min-height: 22px;
          padding: 2px 8px;
          border-radius: 999px;
          font-size: 12px;
          font-weight: 800;
          white-space: nowrap;
        }}
        .badge.ok, .badge.candidate, .badge.true {{ background: var(--ok-bg); color: var(--ok-fg); }}
        .badge.warning {{ background: var(--warn-bg); color: var(--warn-fg); }}
        .badge.reject, .badge.false {{ background: var(--bad-bg); color: var(--bad-fg); }}
        details {{ margin: 0; }}
        details > summary {{
          cursor: pointer;
          color: #2563eb;
          font-weight: 700;
          white-space: nowrap;
        }}
        details[open] > summary {{ margin-bottom: 10px; }}
        .details-grid {{
          display: grid;
          grid-template-columns: minmax(280px, 1fr) minmax(220px, 0.8fr);
          gap: 12px;
          min-width: 560px;
        }}
        .muted {{ color: var(--muted); }}
        .global-details summary {{ font-size: 16px; }}
        @media (max-width: 760px) {{
          main {{ padding: 14px; }}
          .hero, .panel {{ padding: 14px; }}
          .details-grid {{ grid-template-columns: 1fr; min-width: 0; }}
        }}
      </style>
    </head>
    <body>
      <main>
        <section class="hero">
          <h1>F02 Events - {html_escape(variant)}</h1>
          <div class="meta">
            <span>Parent: <code>{html_escape(parent_variant)}</code></span>
            <span>Strategy: <code>{html_escape(strategy)}</code></span>
            <span>Bands: <code>{html_escape(bands_pct)}</code></span>
            <span>NaN mode: <code>{html_escape(nan_mode)}</code></span>
          </div>
          <div class="kpi-grid">{kpi_cards}</div>
        </section>

        <section class="panel">
          <h2>Criterio de decisión F02 → F03</h2>
          <p class="lead">
            La variante F02 se evalúa antes de construir ventanas para evitar pasar a F03 discretizaciones degeneradas.
            No busca elegir la mejor variante, sino descartar las que no generan una representación de eventos mínimamente útil.
            El criterio se aplica en dos niveles: validación global de la variante y validación por medida/dirección para posibles targets F04.
          </p>
          <div class="table-wrap">{gate_criteria_html}</div>
        </section>

        <section class="panel">
          <h2>Decisión por medida/dirección</h2>
          <p class="lead">
            Una variante F02 puede pasar globalmente aunque algunas medidas no sean útiles.
            Para decidir si una medida puede generar un target high o low en F04, se comprueba el soporte de eventos extremos en la dirección correspondiente.
          </p>
          <div class="table-wrap">{target_rules_html}</div>
        </section>

        <section class="panel">
          <h2>Target candidates</h2>
          <div class="table-wrap">{target_candidates_html}</div>
        </section>

        <section class="panel">
          <h2>Top events</h2>
          <div class="table-wrap">{top_events_html}</div>
        </section>

        <section class="panel">
          <details class="global-details">
            <summary>Global metrics completas</summary>
            <div class="table-wrap">{global_table}</div>
          </details>
        </section>
      </main>
    </body>
    </html>
    """


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", required=True)
    args = parser.parse_args()

    variant = args.variant
    variant_dir = get_variant_dir(PHASE, variant)

    params_data = load_params(PHASE, variant)
    params = params_data["parameters"]
    parent_variant = params_data["parent"]

    print(f"\n===== INICIO {PHASE} / {variant} =====")

    start_time = time.perf_counter()

    # --------------------------------------------------------
    # Resolver parent F01
    # --------------------------------------------------------

    parent_phase = "f01_explore"
    parent_outputs, parent_dir = load_phase_outputs(
        PROJECT_ROOT,
        parent_phase,
        parent_variant,
        "F02",
    )

    parent_dataset_path = resolve_artifact_path(
        parent_dir,
        parent_outputs,
        ["dataset"],
        "F02",
    )

    df = pq.read_table(parent_dataset_path, memory_map=True).to_pandas()

    Tu = params["Tu"]
    strategy = params["strategy"]
    bands_pct = params["bands"]
    nan_mode = params["nan_mode"]

    # --------------------------------------------------------
    # Determinar columna temporal 'segs'
    # --------------------------------------------------------

    if "segs" in df.columns:
        epoch_col = "segs"
    elif df.index.name == "segs":
        df = df.reset_index()
        epoch_col = "segs"
    else:
        raise RuntimeError(
            "No se encontró 'segs' ni como columna ni como índice en el dataset padre"
        )

    # --------------------------------------------------------
    # Columnas de medida: vienen de F01 (exports.measure_cols)
    # --------------------------------------------------------

    exports_parent = parent_outputs.get("exports", {})
    measure_cols = exports_parent.get("measure_cols")

    if not measure_cols:
        raise RuntimeError(
            "El parent no exporta 'measure_cols' en outputs.yaml (F01 incompleto)"
        )

    # Verificación de coherencia
    missing = [c for c in measure_cols if c not in df.columns]
    if missing:
        raise RuntimeError(
            f"Columnas de medida declaradas en F01 no están en el dataset padre: {missing}"
        )
    
    # --------------------------------------------------------
    # Generar eventos
    # --------------------------------------------------------

    minmax_stats = compute_minmax(df, measure_cols)
    bands = compute_cuts_and_labels(minmax_stats, bands_pct)
    event_to_id = build_event_catalog(bands, strategy, nan_mode)

    df_events = generate_events(
        df=df,
        epoch_col=epoch_col,
        measure_cols=measure_cols,
        bands=bands,
        event_to_id=event_to_id,
        strategy=strategy,
        nan_mode=nan_mode,
        Tu=Tu,
    )

    # --------------------------------------------------------
    # Guardar artefactos
    # --------------------------------------------------------

    events_path = variant_dir / "02_events.parquet"
    catalog_path = variant_dir / "02_events_catalog.json"
    stats_path = variant_dir / "02_events_stats.json"
    report_path = variant_dir / "02_events_report.html"

    df_events.to_parquet(events_path, index=False)

    save_json(catalog_path, event_to_id)

    stats = compute_event_stats(
        df=df,
        df_events=df_events,
        epoch_col=epoch_col,
        measure_cols=measure_cols,
        bands=bands,
        event_to_id=event_to_id,
        strategy=strategy,
        nan_mode=nan_mode,
        Tu=Tu,
    )
    save_json(stats_path, stats)

    report_html = build_report_html(
        variant=variant,
        parent_variant=parent_variant,
        strategy=strategy,
        bands_pct=bands_pct,
        nan_mode=nan_mode,
        stats=stats,
    )

    report_path.write_text(report_html, encoding="utf-8")

    execution_time = float(time.perf_counter() - start_time)

    # --------------------------------------------------------
    # Construir outputs.yaml
    # --------------------------------------------------------

    outputs_content = {
        "phase": PHASE,
        "variant": variant,
        "artifacts": {
            "events": {
                "path": events_path.name,
                "sha256": sha256_of_file(events_path),
            },
            "catalog": {
                "path": catalog_path.name,
                "sha256": sha256_of_file(catalog_path),
            },
            "stats": {
                "path": stats_path.name,
                "sha256": sha256_of_file(stats_path),
            },
            "report": {
                "path": report_path.name,
                "sha256": sha256_of_file(report_path),
            },
        },
        "exports": {
            "Tu": int(Tu),
            "n_events": int(len(df_events)),
            "n_types": int(len(event_to_id)),
            "n_types_observed": int(stats["global"]["n_event_types_observed"]),
            "target_candidates": stats.get("target_candidates", {}),
        },
        "metrics": build_outputs_metrics(
            stats=stats,
            execution_time=execution_time,
            n_rows_in=len(df),
            n_rows_out=len(df_events),
        ),
        "provenance": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }

    save_outputs_yaml(variant_dir, outputs_content)
    validate_outputs(PHASE, outputs_content)

    print(f"\n===== FASE {PHASE} COMPLETADA =====")


if __name__ == "__main__":
    main()
