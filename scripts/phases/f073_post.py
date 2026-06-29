#!/usr/bin/env python3

import yaml
import pandas as pd

from pathlib import Path
from datetime import datetime
import argparse
import math

from scripts.runtime_analysis.parse import parse_log_enriched
from scripts.runtime_analysis.metrics_models import compute_model_metrics
from scripts.runtime_analysis.metrics_memory import compute_memory_summary
from scripts.runtime_analysis.metrics_timing import compute_system_summary
from scripts.runtime_analysis.metrics_prediction import compute_full_prediction_metrics
from scripts.runtime_analysis.window_fingerprint import (
    fnv1a_32 as _fnv1a_32,
    parse_events_cell as _parse_ow_events_cell,
)
from scripts.core.edge_prepare_common import (
    parse_raw_input_sequence_cell as _parse_raw_input_sequence_cell,
    quantize_raw_input_sequence as _quantize_raw_input_sequence,
)


MIN_OK_RATE_FOR_VALID_EDGE_RUN = 0.95
MAX_FAIL_RATE_FOR_VALID_EDGE_RUN = 0.05
MAX_WATCHDOG_RATE_FOR_VALID_EDGE_RUN = 0.05
MAX_LATENCY_FACTOR_FOR_VALID_EDGE_RUN = 10.0
MIN_ATTEMPTS_FOR_VALID_EDGE_RUN = 1


def _rate(num, den):
    if den is None or den == 0:
        return None
    return float(num) / float(den)


def _as_float(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        v = float(value)
    except Exception:
        return None
    return v if math.isfinite(v) else None


def _as_int(value):
    v = _as_float(value)
    return int(v) if v is not None else None


def _dominant_failure_diagnosis(counts: dict, n_attempts: int) -> dict:
    failure_counts = {k: int(v or 0) for k, v in counts.items()}
    dominant_kind = None
    dominant_count = 0

    for kind, count in failure_counts.items():
        if count > dominant_count:
            dominant_kind = kind
            dominant_count = count

    if dominant_count <= 0:
        return {}

    dominant_rate = _rate(dominant_count, n_attempts)
    likely_causes = []

    if dominant_kind in {"urgent_fallback", "watchdog_deadline"}:
        likely_causes.extend(
            [
                "deadline_expired_before_or_during_inference",
                "effective_time_budget_too_small_for_runtime",
                "review_time_scale_factor_MTI_MS_ITmax_and_serial_period",
                "check_scheduler_backlog_or_stale_monitor_log_if_same_model_sometimes_passes",
            ]
        )
    elif dominant_kind == "inference_incomplete":
        likely_causes.extend(
            [
                "inference_started_but_did_not_emit_end_event",
                "possible_runtime_crash_reset_or_worker_task_interruption",
            ]
        )
    elif dominant_kind == "no_inference":
        likely_causes.extend(
            [
                "model_attempt_started_without_prediction_result",
                "check_event_sequence_and_monitor_log_completeness",
            ]
        )
    elif dominant_kind == "offload":
        likely_causes.append("firmware_reported_offload_result")

    return {
        "dominant_failure_kind": dominant_kind,
        "dominant_failure_count": dominant_count,
        "dominant_failure_rate": dominant_rate,
        "likely_causes": likely_causes,
        "failure_counts": failure_counts,
    }


def classify_edge_run(
    models_row: dict | None,
    *,
    monitor_present: bool = True,
    serial_open_failed: bool = False,
    runtime_crash: bool = False,
) -> dict:
    models_row = models_row or {}

    if not monitor_present:
        return {"phase_status_reason": "monitor_missing", "edge_run_completed": False}
    if serial_open_failed:
        return {"phase_status_reason": "serial_open_failed", "edge_run_completed": False}
    if runtime_crash:
        return {"phase_status_reason": "firmware_runtime_failed", "edge_run_completed": False}

    n_attempts = _as_int(models_row.get("n_attempts")) or 0
    n_ok = _as_int(models_row.get("n_ok")) or 0
    n_fail = _as_int(models_row.get("n_fail")) or 0
    n_wd_late = _as_int(models_row.get("n_wd_late")) or 0
    n_wd_early = _as_int(models_row.get("n_wd_early")) or 0
    n_inference_incomplete = _as_int(models_row.get("n_inference_incomplete")) or 0
    n_offload = _as_int(models_row.get("n_offload")) or 0
    n_urgent = _as_int(models_row.get("n_urgent")) or 0
    n_no_inference = _as_int(models_row.get("n_no_inference")) or 0
    ok_rate = _as_float(models_row.get("ok_rate"))
    fail_rate = _as_float(models_row.get("fail_rate"))
    wd_late_rate = _as_float(models_row.get("wd_late_rate")) or 0.0
    wd_early_rate = _as_float(models_row.get("wd_early_rate")) or 0.0
    watchdog_rate = wd_late_rate + wd_early_rate
    infer_mean_ms = _as_float(models_row.get("infer_mean_ms"))
    infer_max_ms = _as_float(models_row.get("infer_max_ms"))
    itmax_ms = _as_float(models_row.get("itmax_ms") or models_row.get("ITmax") or models_row.get("MTI_MS"))

    details = {
        "n_attempts": n_attempts,
        "n_ok": n_ok,
        "n_fail": n_fail,
        "ok_rate": ok_rate,
        "fail_rate": fail_rate,
        "watchdog_rate": watchdog_rate,
    }
    details.update(
        _dominant_failure_diagnosis(
            {
                "watchdog_deadline": n_wd_late + n_wd_early,
                "urgent_fallback": n_urgent,
                "inference_incomplete": n_inference_incomplete,
                "offload": n_offload,
                "no_inference": n_no_inference,
            },
            n_attempts,
        )
    )

    if n_attempts < MIN_ATTEMPTS_FOR_VALID_EDGE_RUN:
        return {
            "phase_status_reason": "no_edge_attempts",
            "edge_run_completed": False,
            "validation": details,
        }
    if n_ok <= 0:
        return {
            "phase_status_reason": "no_successful_inferences",
            "edge_run_completed": False,
            "validation": details,
        }
    if ok_rate is not None and ok_rate < MIN_OK_RATE_FOR_VALID_EDGE_RUN:
        return {
            "phase_status_reason": "low_ok_rate",
            "edge_run_completed": False,
            "validation": details,
        }
    if fail_rate is not None and fail_rate > MAX_FAIL_RATE_FOR_VALID_EDGE_RUN:
        return {
            "phase_status_reason": "high_fail_rate",
            "edge_run_completed": False,
            "validation": details,
        }
    if watchdog_rate > MAX_WATCHDOG_RATE_FOR_VALID_EDGE_RUN:
        return {
            "phase_status_reason": "high_watchdog_rate",
            "edge_run_completed": False,
            "validation": details,
        }
    if itmax_ms and infer_mean_ms and infer_mean_ms > itmax_ms * MAX_LATENCY_FACTOR_FOR_VALID_EDGE_RUN:
        return {
            "phase_status_reason": "invalid_latency",
            "edge_run_completed": False,
            "validation": {**details, "infer_mean_ms": infer_mean_ms, "itmax_ms": itmax_ms},
        }
    if itmax_ms and infer_max_ms and infer_max_ms > itmax_ms * MAX_LATENCY_FACTOR_FOR_VALID_EDGE_RUN:
        return {
            "phase_status_reason": "invalid_latency",
            "edge_run_completed": False,
            "validation": {**details, "infer_max_ms": infer_max_ms, "itmax_ms": itmax_ms},
        }

    warning_reasons = []
    if fail_rate and fail_rate > 0:
        warning_reasons.append("nonzero_fail_rate")
    if watchdog_rate > 0:
        warning_reasons.append("nonzero_watchdog_rate")

    if warning_reasons:
        return {
            "phase_status_reason": "completed_with_warnings",
            "edge_run_completed": True,
            "validation": {**details, "warnings": warning_reasons},
        }

    return {
        "phase_status_reason": "completed",
        "edge_run_completed": True,
        "validation": details,
    }


def _build_quality_metrics(models_df: pd.DataFrame, prediction_df: pd.DataFrame | None = None):

    if models_df is None or models_df.empty:
        return pd.DataFrame()

    qdf = models_df.copy()

    # Excluir fila de sistema.
    if "model_id" in qdf.columns:
        qdf = qdf[qdf["model_id"] >= 0].copy()

    if qdf.empty:
        return qdf

    # Garantizar columnas esperadas.
    defaults = {
        "n_attempts": 0,
        "n_ok": 0,
        "n_wd_late": 0,
        "n_wd_early": 0,
        "n_inference_incomplete": 0,
        "n_offload": 0,
        "n_urgent": 0,
        "n_no_inference": 0,
        "infer_n": 0,
    }
    for col, default in defaults.items():
        if col not in qdf.columns:
            qdf[col] = default

    qdf["n_fail"] = (
        qdf["n_wd_late"]
        + qdf["n_wd_early"]
        + qdf["n_inference_incomplete"]
        + qdf["n_offload"]
        + qdf["n_urgent"]
        + qdf["n_no_inference"]
    )

    qdf["n_inferences"] = qdf["infer_n"]
    qdf["ok_rate"] = qdf.apply(lambda r: _rate(r["n_ok"], r["n_attempts"]), axis=1)
    qdf["fail_rate"] = qdf.apply(lambda r: _rate(r["n_fail"], r["n_attempts"]), axis=1)
    qdf["wd_late_rate"] = qdf.apply(lambda r: _rate(r["n_wd_late"], r["n_attempts"]), axis=1)
    qdf["wd_early_rate"] = qdf.apply(lambda r: _rate(r["n_wd_early"], r["n_attempts"]), axis=1)
    qdf["incomplete_rate"] = qdf.apply(lambda r: _rate(r["n_inference_incomplete"], r["n_attempts"]), axis=1)
    qdf["offload_rate"] = qdf.apply(lambda r: _rate(r["n_offload"], r["n_attempts"]), axis=1)
    qdf["urgent_rate"] = qdf.apply(lambda r: _rate(r["n_urgent"], r["n_attempts"]), axis=1)
    qdf["no_inference_rate"] = qdf.apply(lambda r: _rate(r["n_no_inference"], r["n_attempts"]), axis=1)

    if "infer_max_ms" in qdf.columns:
        qdf["infer_worst_ms"] = qdf["infer_max_ms"]

    # Si hay métricas supervisadas disponibles, anexarlas por nombre de modelo.
    if prediction_df is not None and not prediction_df.empty and "model_name" in prediction_df.columns:
        keep_cols = [
            "model_name",
            "N_total",
            "TP",
            "FP",
            "TN",
            "FN",
            "accuracy",
            "precision",
            "recall",
            "f1",
            "false_negative_rate",
            "skipped_predictions",
            "confusion_matrix",
        ]
        pred_cols = [c for c in keep_cols if c in prediction_df.columns]
        qdf = qdf.merge(prediction_df[pred_cols], on="model_name", how="left")
        rename_map = {
            "TP": "tp",
            "FP": "fp",
            "TN": "tn",
            "FN": "fn",
        }
        qdf = qdf.rename(columns={k: v for k, v in rename_map.items() if k in qdf.columns})
        for col in ["tp", "fp", "tn", "fn"]:
            if col not in qdf.columns:
                qdf[col] = None

        def _cm_text(row):
            vals = [row.get("tn"), row.get("fp"), row.get("fn"), row.get("tp")]
            if any(pd.isna(v) for v in vals):
                return None
            return f"[[TN={int(row['tn'])}, FP={int(row['fp'])}], [FN={int(row['fn'])}, TP={int(row['tp'])}]]"

        qdf["confusion_matrix"] = qdf.apply(_cm_text, axis=1)

    preferred_order = [
        "model_id",
        "model_name",
        "n_attempts",
        "n_inferences",
        "n_ok",
        "n_fail",
        "ok_rate",
        "fail_rate",
        "n_wd_late",
        "wd_late_rate",
        "n_wd_early",
        "wd_early_rate",
        "n_inference_incomplete",
        "incomplete_rate",
        "n_offload",
        "offload_rate",
        "n_urgent",
        "urgent_rate",
        "n_no_inference",
        "no_inference_rate",
        "infer_worst_ms",
        "infer_max_ms",
        "infer_mean_ms",
        "infer_jitter_ms",
        "N_total",
        "tp",
        "fp",
        "tn",
        "fn",
        "accuracy",
        "precision",
        "recall",
        "f1",
        "false_negative_rate",
        "skipped_predictions",
        "confusion_matrix",
    ]
    cols = [c for c in preferred_order if c in qdf.columns]
    return qdf[cols]


def _compact_models_report(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    if "model_id" in df.columns:
        df = df[df["model_id"] >= 0].copy()
    if df.empty:
        return df

    preferred_order = [
        "model_id",
        "model_name",
        "n_attempts",
        "n_inferences",
        "n_ok",
        "n_fail",
        "ok_rate",
        "fail_rate",
        "n_wd_late",
        "wd_late_rate",
        "n_wd_early",
        "wd_early_rate",
        "n_inference_incomplete",
        "incomplete_rate",
        "n_offload",
        "offload_rate",
        "n_urgent",
        "urgent_rate",
        "n_no_inference",
        "no_inference_rate",
        "infer_worst_ms",
        "infer_overhead_max_ms",
        "infer_mean_ms",
        "infer_jitter_ms",
        "process_max_ms",
        "N_total",
        "tp",
        "fp",
        "tn",
        "fn",
        "accuracy",
        "precision",
        "recall",
        "f1",
        "false_negative_rate",
        "skipped_predictions",
        "confusion_matrix",
    ]

    cols = [c for c in preferred_order if c in df.columns]
    return df[cols]


def _validate_fp_index_schema(fp_df: pd.DataFrame):
    required = {"model_name", "fingerprint", "expected"}
    return required.issubset(set(fp_df.columns))


def _resolve_fp_index_path(root: Path, resolved_parent: str, fp_index: str | None):
    """
    Resolve fp_index path using:
      1) explicit --fp_index
      2) common filenames in F07 variant folder
      3) common filenames in parent F06 folder
    """
    candidates = []

    if fp_index:
        candidates.append(Path(fp_index))

    candidates.extend([
        root / "fp_index.csv",
        root / "07_fp_index.csv",
        root / "fingerprint_index.csv",
    ])

    f06_dir = Path("executions") / "f06_quant" / resolved_parent
    candidates.extend([
        f06_dir / "fp_index.csv",
        f06_dir / "fingerprint_index.csv",
    ])

    for p in candidates:
        if not p.exists():
            continue
        try:
            dfp = pd.read_csv(p)
        except Exception:
            continue
        if _validate_fp_index_schema(dfp):
            return p

    return None


def _write_fp_index_template(df: pd.DataFrame, out_path: Path):
    """
    Build a template from runtime prediction events:
      model_name, fingerprint, expected
    expected is intentionally left empty for user curation.
    """
    if df.empty:
        return None

    pred = df[df["event_name"] == "FUNC_PRED_RESULT"].copy()
    if pred.empty:
        return None

    # fingerprint may come as parsed field or raw payload.
    if "fingerprint" not in pred.columns:
        return None

    cols = [c for c in ["model_name", "fingerprint"] if c in pred.columns]
    if len(cols) < 2:
        return None

    tpl = pred[cols].dropna().copy()
    if tpl.empty:
        return None

    tpl["fingerprint"] = pd.to_numeric(tpl["fingerprint"], errors="coerce")
    tpl = tpl.dropna(subset=["fingerprint"])
    if tpl.empty:
        return None

    tpl["fingerprint"] = tpl["fingerprint"].astype("int64")
    tpl = tpl.drop_duplicates(subset=["model_name", "fingerprint"]).sort_values(["model_name", "fingerprint"])
    tpl["expected"] = ""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tpl.to_csv(out_path, index=False)
    return out_path


def _build_fp_index_from_dataset(
    root: Path,
    model_name_map: dict,
    event_dtype: str = "uint8",
) -> "pd.DataFrame | None":
    """
    Automatically build fp_index from 07_input_dataset.csv using the same FNV-1a 32-bit
    hash as the firmware (events_mgr_fingerprint in events_mgr.c).

    For fingerprints with ambiguous labels (same event sequence, mixed 0/1 labels in the
    dataset), applies majority-vote and logs a warning.

    Returns a DataFrame with columns [model_name, fingerprint, expected] for every model
    in model_name_map, or None if the dataset is missing / unreadable.
    """
    csv_path = root / "07_input_dataset.csv"
    if not csv_path.exists():
        return None

    try:
        df = pd.read_csv(csv_path, sep=";")
    except Exception as e:
        print(f"[F073] Warning: cannot read {csv_path}: {e}")
        return None

    if "label" not in df.columns:
        print(f"[F073] Warning: {csv_path} missing label column.")
        return None

    hash_dtype = event_dtype
    if "OW_events" in df.columns:
        df["_events"] = df["OW_events"].apply(_parse_ow_events_cell)
    elif "OW_values" in df.columns:
        profile = _load_yaml_if_exists(root / "07_model_profile.yaml") or {}
        sig = profile.get("input_signature", {}) or {}
        required = [
            "input_dtype",
            "input_max_len",
            "normalization_mean",
            "normalization_std",
            "input_quant_scale",
            "input_quant_zero_point",
        ]
        missing = [k for k in required if sig.get(k) is None]
        if missing:
            print(
                f"[F073] Warning: cannot auto-build fp_index from OW_values; "
                f"missing input_signature field(s): {', '.join(missing)}."
            )
            return None

        hash_dtype = str(sig.get("input_dtype") or event_dtype)

        def _quantized_events(cell):
            raw_values = _parse_raw_input_sequence_cell(cell)
            return _quantize_raw_input_sequence(
                raw_values,
                input_dtype=hash_dtype,
                input_max_len=int(sig["input_max_len"]),
                normalization_mean=float(sig["normalization_mean"]),
                normalization_std=float(sig["normalization_std"]),
                input_quant_scale=float(sig["input_quant_scale"]),
                input_quant_zero_point=int(sig["input_quant_zero_point"]),
            )

        df["_events"] = df["OW_values"].apply(_quantized_events)
    else:
        print(f"[F073] Warning: {csv_path} missing OW_events/OW_values column.")
        return None

    df["_fp"]     = df["_events"].apply(_fnv1a_32)
    df["_label"]  = pd.to_numeric(df["label"], errors="coerce").fillna(0).astype(int)

    fp_rows = []
    ambiguous = 0
    for fp_val, grp in df.groupby("_fp"):
        majority = int(grp["_label"].mode().iloc[0])
        if grp["_label"].nunique() > 1:
            ambiguous += 1
        fp_rows.append({"fingerprint": int(fp_val), "expected": majority})

    if ambiguous:
        print(
            f"[F073] fp_index auto-build: {ambiguous} ambiguous fingerprint(s) "
            "(same event sequence, mixed labels) — majority vote applied."
        )

    fp_df = pd.DataFrame(fp_rows)

    model_names = list(model_name_map.values())
    if not model_names:
        print("[F073] Warning: no model names available; skipping fp_index auto-build.")
        return None

    result = pd.concat(
        [fp_df.assign(model_name=mn) for mn in model_names],
        ignore_index=True,
    )[["model_name", "fingerprint", "expected"]]

    print(
        f"[F073] fp_index auto-built from {csv_path.name}: "
        f"{len(fp_df)} fingerprint(s) × {len(model_names)} model(s)."
    )
    return result


# --------------------------------------------------
# locate variant paths
# --------------------------------------------------

def locate_variant_dirs(variant: str):

    root = Path("executions/f07_modval") / variant

    if not root.exists():
        raise RuntimeError(f"Variant directory not found: {root}")

    artifacts = root 
    analysis = root 

    analysis.mkdir(exist_ok=True)

    # --------------------------------------------------
    # detect monitor log automatically
    # --------------------------------------------------

    log_candidates = list(artifacts.glob("07_esp_monitor_log.txt")) + list(artifacts.glob("*.log"))

    if not log_candidates:
        print(f"[F073] Warning: no monitor log found in {artifacts}. Exporting partial outputs.")
        log_path = None
    else:
        log_path = log_candidates[0]
        print(f"[F073] Using log file: {log_path}")

    return dict(
        root=root,
        artifacts=artifacts,
        analysis=analysis,
        log=log_path
    )


def _load_model_name_map_from_cfg(root: Path):

    cfg_path = root / "07_edge_run_config.yaml"

    if not cfg_path.exists():
        return {}

    try:
        cfg = yaml.safe_load(cfg_path.read_text()) or {}
    except Exception:
        return {}

    model_map: dict[int, str] = {}

    models = cfg.get("models")
    if isinstance(models, list):
        for m in models:
            if not isinstance(m, dict):
                continue
            mid = m.get("id")
            name = m.get("name")
            if mid is None or name is None:
                continue
            model_map[int(mid)] = str(name)

    if model_map:
        return model_map

    # Fallback legacy monomodelo
    pred = cfg.get("prediction", {})
    if isinstance(pred, dict):
        name = pred.get("name")
        if name is not None:
            model_map[0] = str(name)

    return model_map


def _apply_model_name_map(df: pd.DataFrame, model_name_map: dict[int, str]):

    if not model_name_map or df.empty:
        return df

    if "model_id" not in df.columns or "model_name" not in df.columns:
        return df

    for model_id, model_name in model_name_map.items():
        df.loc[df["model_id"] == int(model_id), "model_name"] = str(model_name)

    return df


def _resolve_parent_variant(root: Path, parent_variant: str | None):

    if parent_variant:
        return str(parent_variant)

    params_path = root / "params.yaml"
    if not params_path.exists():
        raise RuntimeError(f"params.yaml no encontrado en {root}")

    data = yaml.safe_load(params_path.read_text()) or {}
    resolved = data.get("parent")
    if not resolved:
        raise RuntimeError(f"No se pudo resolver parent en {params_path}")

    return str(resolved)


def _load_f06_exports(parent_variant: str):

    parent_outputs = Path("executions") / "f06_quant" / parent_variant / "outputs.yaml"
    if not parent_outputs.exists():
        raise RuntimeError(f"outputs.yaml de parent F06 no encontrado: {parent_outputs}")

    data = yaml.safe_load(parent_outputs.read_text()) or {}
    return data.get("exports", {}) or {}


def _load_yaml_if_exists(path: Path):
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text()) or {}


def _safe_scalar(value):
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def _first_row_dict(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {}
    row = df.iloc[0].to_dict()
    return {k: _safe_scalar(v) for k, v in row.items()}


def _detect_runtime_crash(log_path: Path) -> str | None:
    text = log_path.read_text(errors="ignore") if log_path.exists() else ""
    markers = [
        "Guru Meditation Error",
        "panic'ed",
        "Backtrace:",
        "SW_CPU_RESET",
    ]
    return "firmware_runtime_failed" if any(marker in text for marker in markers) else None


def _detect_serial_open_failed(root: Path) -> bool:
    patterns = [
        "could not open port",
        "permissionerror",
        "permission denied",
        "no se detecta ningún puerto serie",
        "no se detecta ningun puerto serie",
    ]
    for path in [
        root / "07_esp_flash_log.txt",
        root / "07_esp_monitor_log.txt",
        root / "07_esp_build_log.txt",
    ]:
        if not path.exists():
            continue
        text = path.read_text(errors="ignore").lower()
        if any(pattern in text for pattern in patterns):
            return True
    return False


def _resolve_single_model_row(models_df: pd.DataFrame) -> dict:
    if models_df is None or models_df.empty:
        return {}

    df = models_df.copy()

    if "model_id" in df.columns:
        df = df[df["model_id"] >= 0].copy()

    if df.empty:
        return {}

    return {k: _safe_scalar(v) for k, v in df.iloc[0].to_dict().items()}


def _build_quality_score(model_row: dict) -> float | None:
    """
    Calidad canónica simple para F08.
    Prioridad:
      1) f1
      2) recall
      3) accuracy
    """
    for key in ["f1", "recall", "accuracy"]:
        v = model_row.get(key)
        if v is not None:
            try:
                return float(v)
            except Exception:
                pass
    return None


def _update_model_profile(
    root: Path,
    *,
    models_row: dict,
    memory_row: dict,
    system_row: dict,
    time_scale_factor: float = 1.0,
    phase_status_reason: str | None = None,
    edge_run_completed: bool | None = None,
    validation_details: dict | None = None,
):
    profile_path = root / "07_model_profile.yaml"
    profile = _load_yaml_if_exists(profile_path)
    if profile is None:
        raise RuntimeError(f"[F073] 07_model_profile.yaml no encontrado: {profile_path}")

    quality_score = _build_quality_score(models_row)

    run_block = profile.get("run", {}) or {}
    if edge_run_completed is None:
        edge_run_completed = phase_status_reason in (None, "completed", "completed_with_warnings")
    run_block.update(
        {
            "edge_run_completed": bool(edge_run_completed),
            "phase_status_reason": phase_status_reason,
            "validation": validation_details,
            "n_inferences": models_row.get("n_inferences"),
            "ok_rate": models_row.get("ok_rate"),
            "offload_rate": models_row.get("offload_rate"),
            "watchdog_rate": models_row.get("wd_late_rate"),
        }
    )
    profile["run"] = run_block

    timing_block = profile.get("timing", {}) or {}
    _raw_itmax = models_row.get("infer_worst_ms", models_row.get("infer_max_ms"))
    if time_scale_factor < 1.0:
        _itmax_to_store = timing_block.get("itmax_ms")
    else:
        _itmax_to_store = _raw_itmax
    timing_block.update(
        {
            "edge_mean_latency_ms": system_row.get("process_mean_ms", models_row.get("infer_mean_ms")),
            "edge_max_latency_ms": system_row.get("process_max_ms", models_row.get("infer_max_ms")),
            "edge_jitter_ms": system_row.get("process_jitter_ms", models_row.get("infer_jitter_ms")),
            "itmax_ms": _itmax_to_store,
        }
    )
    profile["timing"] = timing_block

    memory_block = profile.get("memory", {}) or {}
    memory_block.update(
        {
            "edge_memory_peak_bytes": memory_row.get("mem_used_max_bytes"),
            "model_memory_bytes": profile.get("build", {}).get("model_size_bytes"),
            "arena_bytes": profile.get("build", {}).get("arena_bytes"),
        }
    )
    profile["memory"] = memory_block

    quality_block = profile.get("quality", {}) or {}
    quality_block.update(
        {
            "quality_score": quality_score,
            "tp": models_row.get("tp"),
            "fp": models_row.get("fp"),
            "tn": models_row.get("tn"),
            "fn": models_row.get("fn"),
            "confusion_matrix": models_row.get("confusion_matrix"),
            "accuracy": models_row.get("accuracy"),
            "precision": models_row.get("precision"),
            "recall": models_row.get("recall"),
            "f1": models_row.get("f1"),
            "false_negative_rate": models_row.get("false_negative_rate"),
            "pc_esp_agreement": system_row.get("pc_esp_agreement"),
        }
    )
    profile["quality"] = quality_block

    outcomes_block = profile.get("outcomes", {}) or {}
    outcomes_block.update(
        {
            "n_attempts": models_row.get("n_attempts"),
            "n_ok": models_row.get("n_ok"),
            "n_fail": models_row.get("n_fail"),
            "n_offload": models_row.get("n_offload"),
            "n_wd_late": models_row.get("n_wd_late"),
            "n_wd_early": models_row.get("n_wd_early"),
            "n_inference_incomplete": models_row.get("n_inference_incomplete"),
            "n_urgent": models_row.get("n_urgent"),
            "n_no_inference": models_row.get("n_no_inference"),
        }
    )
    profile["outcomes"] = outcomes_block

    profile_path.write_text(yaml.safe_dump(profile, sort_keys=False))
    return profile

def write_outputs_yaml(
    root,
    analysis,
    parent_variant: str,
    parent_exports: dict,
    *,
    artifacts=None,
    model_profile=None,
    models_row=None,
    memory_row=None,
    system_row=None,
    phase_status_reason: str | None = None,
    edge_capable_override: bool | None = None,
    incompatibility_reason_override: str | None = None,
    extra_exports: dict | None = None,
):

    if artifacts is None:
        artifacts = [
            str(analysis / "07_model_profile.yaml"),
            str(analysis / "metrics_models.csv"),
            str(analysis / "metrics_memory.csv"),
            str(analysis / "metrics_system_timing.csv"),
        ]

    exports = dict(
        edge_capable=(
            bool(edge_capable_override)
            if edge_capable_override is not None
            else bool(parent_exports.get("edge_capable", False))
        ),
        incompatibility_reason=(
            incompatibility_reason_override
            if incompatibility_reason_override is not None
            else parent_exports.get("incompatibility_reason")
        ),
    )

    if model_profile:
        model_block = model_profile.get("model", {}) or {}
        sig_block = model_profile.get("input_signature", {}) or {}
        build_block = model_profile.get("build", {}) or {}
        limits_block = model_profile.get("limits", {}) or {}
        run_block = model_profile.get("run", {}) or {}
        quality_block = model_profile.get("quality", {}) or {}

        timing_block = model_profile.get("timing", {}) or {}
        memory_block = model_profile.get("memory", {}) or {}
        outcomes_block = model_profile.get("outcomes", {}) or {}

        exports.update(
            {
                "model_id": model_block.get("model_id"),
                "runtime_model_name": model_block.get("runtime_model_name"),
                "prediction_name": model_block.get("prediction_name"),
                "platform": model_block.get("platform"),
                "Tu": sig_block.get("Tu"),
                "OW": sig_block.get("OW"),
                "LT": sig_block.get("LT"),
                "PW": sig_block.get("PW"),
                "operators": build_block.get("operators"),
                "decision_threshold": build_block.get("decision_threshold"),
                "arena_bytes": build_block.get("arena_bytes"),
                "model_memory_bytes": memory_block.get("model_memory_bytes"),
                "itmax_ms": timing_block.get("itmax_ms", limits_block.get("itmax_ms")),
                "ITmax": limits_block.get("ITmax"),
                "MTI_MS": limits_block.get("MTI_MS"),
                "edge_run_completed": bool(
                    run_block.get("edge_run_completed", run_block.get("esp_run_completed", False))
                ),
                "model_stats": {
                    "quality_score": quality_block.get("quality_score"),
                    "n_inferences": run_block.get("n_inferences"),
                    "ok_rate": run_block.get("ok_rate"),
                    "offload_rate": run_block.get("offload_rate"),
                    "watchdog_rate": run_block.get("watchdog_rate"),
                    "n_attempts": outcomes_block.get("n_attempts"),
                    "n_ok": outcomes_block.get("n_ok"),
                    "n_fail": outcomes_block.get("n_fail"),
                    "timing": {
                        "edge_mean_latency_ms": timing_block.get("edge_mean_latency_ms"),
                        "edge_max_latency_ms": timing_block.get("edge_max_latency_ms"),
                        "edge_jitter_ms": timing_block.get("edge_jitter_ms"),
                    },
                    "memory": {
                        "edge_memory_peak_bytes": memory_block.get("edge_memory_peak_bytes"),
                    },
                    "quality": {
                        "tp": quality_block.get("tp"),
                        "fp": quality_block.get("fp"),
                        "tn": quality_block.get("tn"),
                        "fn": quality_block.get("fn"),
                        "accuracy": quality_block.get("accuracy"),
                        "precision": quality_block.get("precision"),
                        "recall": quality_block.get("recall"),
                        "f1": quality_block.get("f1"),
                        "false_negative_rate": quality_block.get("false_negative_rate"),
                        "pc_esp_agreement": quality_block.get("pc_esp_agreement"),
                    },
                },
            }
        )

    edge_capable_flag = bool(exports.get("edge_capable", False))
    edge_run_completed_flag = bool(exports.get("edge_run_completed", False))
    resolved_reason = phase_status_reason
    if resolved_reason is None:
        if not edge_capable_flag:
            resolved_reason = "configuration_edge_capable_false"
        elif edge_run_completed_flag:
            resolved_reason = "completed"
        else:
            resolved_reason = "edge_run_not_completed"
    exports["phase_status_reason"] = resolved_reason
    exports["reason"] = resolved_reason
    if extra_exports:
        exports.update(extra_exports)

    outputs = dict(
        generated_at=datetime.utcnow().isoformat(),
        phase="f07_modval",
        parent=dict(
            phase="f06_quant",
            variant=parent_variant,
        ),
        artifacts=artifacts,
        exports=exports,
    )

    with open(root / "outputs.yaml", "w") as f:
        yaml.safe_dump(outputs, f, sort_keys=False)


# --------------------------------------------------
# main analysis
# --------------------------------------------------

def run_analysis(variant, parent_variant=None, fp_index=None):

    root = Path("executions/f07_modval") / variant
    if not root.exists():
        raise RuntimeError(f"Variant directory not found: {root}")

    analysis_dir = root
    analysis_dir.mkdir(exist_ok=True)

    # Limpieza de artefactos legacy para mantener un set mínimo de resultados.
    for legacy in [
        "metrics_raw.json",
        "metrics_inference_records.csv",
        "metrics_prediction.csv",
        "metrics_quality_models.csv",
    ]:
        legacy_path = analysis_dir / legacy
        if legacy_path.exists():
            legacy_path.unlink()

    resolved_parent = _resolve_parent_variant(root, parent_variant)
    parent_exports = _load_f06_exports(resolved_parent)

    _params_data = yaml.safe_load((root / "params.yaml").read_text()) if (root / "params.yaml").exists() else {}
    _time_scale_factor = float((_params_data.get("parameters") or _params_data).get("time_scale_factor", 1.0))

    if not bool(parent_exports.get("edge_capable", False)):
        write_outputs_yaml(
            root,
            analysis_dir,
            resolved_parent,
            parent_exports,
            artifacts=[],
            model_profile=None,
            models_row=None,
            memory_row=None,
            system_row=None,
            phase_status_reason="configuration_edge_capable_false",
        )
        print("[F073] Parent F06 no edge_capable: se omite análisis F07 y se exporta estado propagado.")
        return

    paths = locate_variant_dirs(variant)
    log_path = paths["log"]

    if log_path is None:
        profile_path = root / "07_model_profile.yaml"
        model_profile = _load_yaml_if_exists(profile_path)
        if model_profile is None:
            model_profile = {}

        build_status_path = root / "07_build_status.yaml"
        build_status = _load_yaml_if_exists(build_status_path) or {}
        status_reason = build_status.get("phase_status_reason") or "monitor_missing"
        if status_reason == "monitor_missing" and _detect_serial_open_failed(root):
            status_reason = "serial_open_failed"

        run_block = model_profile.get("run", {}) or {}
        run_block.update(
            {
                "edge_run_completed": False,
                "phase_status_reason": status_reason,
                "n_inferences": None,
                "ok_rate": None,
                "offload_rate": None,
                "watchdog_rate": None,
            }
        )
        model_profile["run"] = run_block

        if status_reason == "firmware_too_large_for_partition":
            compat_block = model_profile.get("compatibility", {}) or {}
            compat_block.update(
                {
                    "edge_capable": False,
                    "incompatibility_reason": "firmware_too_large_for_partition",
                }
            )
            model_profile["compatibility"] = compat_block

            build_block = model_profile.get("build", {}) or {}
            for key in [
                "firmware_bin_size_bytes",
                "app_partition_size_bytes",
                "app_partition_overflow_bytes",
                "configured_flash_size",
                "partition_name",
            ]:
                if key in build_status:
                    build_block[key] = build_status[key]
            model_profile["build"] = build_block

        if profile_path.exists():
            profile_path.write_text(yaml.safe_dump(model_profile, sort_keys=False))

        artifacts = [str(profile_path)] if profile_path.exists() else []
        if build_status_path.exists():
            artifacts.append(str(build_status_path))
        for artifact_name in [
            "metrics_models.csv",
            "metrics_memory.csv",
            "metrics_system_timing.csv",
        ]:
            artifact_path = root / artifact_name
            if artifact_path.exists():
                artifacts.append(str(artifact_path))

        write_outputs_yaml(
            root,
            analysis_dir,
            resolved_parent,
            parent_exports,
            artifacts=artifacts,
            model_profile=model_profile,
            models_row=None,
            memory_row=None,
            system_row=None,
            phase_status_reason=status_reason,
            edge_capable_override=False if status_reason == "firmware_too_large_for_partition" else None,
            incompatibility_reason_override=(
                "firmware_too_large_for_partition"
                if status_reason == "firmware_too_large_for_partition"
                else None
            ),
            extra_exports={
                k: build_status[k]
                for k in [
                    "firmware_bin_size_bytes",
                    "app_partition_size_bytes",
                    "app_partition_overflow_bytes",
                    "configured_flash_size",
                    "partition_name",
                ]
                if k in build_status
            },
        )
        print("[F073] Partial outputs exported (no monitor log available).")
        return

    model_name_map = _load_model_name_map_from_cfg(root)

    print(f"[F073] Parsing log {log_path}")

    runtime_crash_reason = _detect_runtime_crash(log_path)
    if runtime_crash_reason:
        print(f"[F073] Runtime crash detected: {runtime_crash_reason}")

    df = parse_log_enriched(log_path)
    df = _apply_model_name_map(df, model_name_map)

    # --------------------------------------------------
    # system timing
    # --------------------------------------------------

    system_summary = compute_system_summary(df)

    # --------------------------------------------------
    # model metrics (base)
    # --------------------------------------------------

    print("[F073] Computing model metrics")

    models_df = compute_model_metrics(df)

    # --------------------------------------------------
    # prediction metrics (optional)
    # Priority 1: explicit --fp_index argument
    # Priority 2: auto-build from 07_input_dataset.csv (FNV-1a replication)
    # Priority 3: discovered file (fp_index.csv etc. in variant/parent dirs)
    # Fallback: write template for user curation
    # --------------------------------------------------

    prediction_df = None
    fp_index_df = None
    fp_index_template_path = None

    # Priority 1 — explicit flag
    if fp_index:
        p = Path(fp_index)
        if p.exists():
            try:
                candidate = pd.read_csv(p)
                if _validate_fp_index_schema(candidate):
                    fp_index_df = candidate
                    print(f"[F073] Using explicit --fp_index: {p}")
                else:
                    print(f"[F073] Warning: --fp_index file missing required columns, ignored: {p}")
            except Exception as e:
                print(f"[F073] Warning: cannot load --fp_index {p}: {e}")
        else:
            print(f"[F073] Warning: --fp_index path not found: {p}")

    # Priority 2 — auto-build from dataset
    if fp_index_df is None:
        fp_index_df = _build_fp_index_from_dataset(
            root,
            model_name_map,
            event_dtype=str(parent_exports.get("input_dtype") or "uint8"),
        )

    # Priority 3 — file discovery (fp_index.csv / 07_fp_index.csv in variant or parent dir)
    if fp_index_df is None:
        discovered = _resolve_fp_index_path(root, resolved_parent, None)
        if discovered is not None:
            try:
                fp_index_df = pd.read_csv(discovered)
                print(f"[F073] Using discovered fp_index: {discovered}")
            except Exception as e:
                print(f"[F073] Warning: cannot load {discovered}: {e}")

    if fp_index_df is not None:
        print("[F073] Computing prediction metrics.")
        prediction_df = compute_full_prediction_metrics(df, fp_index_df)
    else:
        fp_index_template_path = _write_fp_index_template(
            df,
            analysis_dir / "fp_index_template.csv",
        )
        if fp_index_template_path is not None:
            print(f"[F073] No fp_index resolved. Created template: {fp_index_template_path}")
        else:
            print("[F073] No fp_index resolved and no prediction events for template.")

    # --------------------------------------------------
    # quality metrics (always, + supervised if fp_index)
    # --------------------------------------------------

    quality_df = _build_quality_metrics(models_df, prediction_df)

    # Combinar en un único reporte de modelos para reducir artefactos.
    key_cols = [c for c in ["model_id", "model_name"] if c in quality_df.columns and c in models_df.columns]
    extra_cols = [c for c in quality_df.columns if c not in models_df.columns]

    if key_cols and extra_cols:
        merged_df = models_df.merge(quality_df[key_cols + extra_cols], on=key_cols, how="left")
        models_report_df = _compact_models_report(merged_df)
    else:
        models_report_df = _compact_models_report(models_df)

    models_csv = analysis_dir / "metrics_models.csv"
    models_report_df.to_csv(models_csv, index=False)

    # --------------------------------------------------
    # memory summary
    # --------------------------------------------------

    memory_summary = compute_memory_summary(df)
    memory_csv = analysis_dir / "metrics_memory.csv"
    pd.DataFrame([memory_summary] if memory_summary else []).to_csv(memory_csv, index=False)

    # --------------------------------------------------
    # system timing summary
    # --------------------------------------------------

    system_csv = analysis_dir / "metrics_system_timing.csv"
    pd.DataFrame([system_summary] if system_summary else []).to_csv(system_csv, index=False)

    models_row = _resolve_single_model_row(models_report_df)
    memory_row = _first_row_dict(pd.DataFrame([memory_summary] if memory_summary else []))
    system_row = _first_row_dict(pd.DataFrame([system_summary] if system_summary else []))
    run_classification = classify_edge_run(
        models_row,
        monitor_present=True,
        runtime_crash=bool(runtime_crash_reason),
    )
    phase_status_reason = run_classification.get("phase_status_reason")
    edge_run_completed = bool(run_classification.get("edge_run_completed", False))
    validation_details = run_classification.get("validation")

    model_profile = _update_model_profile(
        root,
        models_row=models_row,
        memory_row=memory_row,
        system_row=system_row,
        time_scale_factor=_time_scale_factor,
        phase_status_reason=phase_status_reason,
        edge_run_completed=edge_run_completed,
        validation_details=validation_details,
    )

    artifacts = [
        str(root / "07_model_profile.yaml"),
        str(models_csv),
        str(memory_csv),
        str(system_csv),
    ]
    if fp_index_template_path is not None:
        artifacts.append(str(fp_index_template_path))

    # --------------------------------------------------
    # write outputs.yaml
    # --------------------------------------------------

    write_outputs_yaml(
        root,
        analysis_dir,
        resolved_parent,
        parent_exports,
        artifacts=artifacts,
        model_profile=model_profile,
        models_row=models_row,
        memory_row=memory_row,
        system_row=system_row,
        phase_status_reason=phase_status_reason,
        extra_exports={
            "edge_run_validation": validation_details,
        } if validation_details else None,
    )

    print("")
    print("[F073] Analysis completed")
    print(f" metrics_models.csv : {models_csv}")
    print(f" metrics_memory.csv            : {memory_csv}")
    print(f" metrics_system_timing.csv     : {system_csv}")
    if fp_index_template_path is not None:
        print(f" fp_index_template.csv         : {fp_index_template_path}")


# --------------------------------------------------
# CLI
# --------------------------------------------------

if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--variant",
        required=True
    )

    parser.add_argument(
        "--parent",
        default=None
    )

    parser.add_argument(
        "--fp_index",
        default=None
    )

    args = parser.parse_args()

    run_analysis(
        variant=args.variant,
        parent_variant=args.parent,
        fp_index=args.fp_index
    )
