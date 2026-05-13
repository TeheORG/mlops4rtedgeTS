#!/usr/bin/env python3

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

from scripts.runtime_analysis.parse import parse_log_enriched
from scripts.runtime_analysis.metrics_models import compute_model_metrics
from scripts.runtime_analysis.metrics_memory import compute_memory_summary
from scripts.runtime_analysis.metrics_timing import compute_system_summary
from scripts.runtime_analysis.window_fingerprint import (
    fnv1a_32 as _fnv1a_32,
    parse_events_cell as _parse_ow_events_cell,
)


PHASE = "f08_sysval"
PARENT_PHASE = "f07_modval"


class _NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def _yaml_dump_no_alias(data: dict) -> str:
    return yaml.dump(data, Dumper=_NoAliasDumper, sort_keys=False)


# ============================================================
# HELPERS
# ============================================================

def _rate(num, den):
    if den is None or den == 0:
        return None
    return float(num) / float(den)


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


def _load_yaml(path: Path, label: str):
    if not path.exists():
        raise RuntimeError(f"[F084] {label} no encontrado: {path}")
    return yaml.safe_load(path.read_text()) or {}


def _load_yaml_if_exists(path: Path):
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text()) or {}


def _resolve_variant_root(variant: str) -> Path:
    root = Path("executions") / PHASE / variant
    if not root.exists():
        raise RuntimeError(f"[F084] Variant directory not found: {root}")
    return root


def _load_model_name_map_from_cfg(edge_cfg: dict) -> dict[int, str]:
    model_map = {}
    models = edge_cfg.get("models")
    if isinstance(models, list):
        for m in models:
            if not isinstance(m, dict):
                continue
            mid = m.get("id")
            name = m.get("name")
            if mid is None or name is None:
                continue
            model_map[int(mid)] = str(name)
    return model_map


def _apply_model_name_map(df: pd.DataFrame, model_name_map: dict[int, str]):
    if df.empty or not model_name_map:
        return df
    if "model_id" not in df.columns or "model_name" not in df.columns:
        return df

    for model_id, model_name in model_name_map.items():
        df.loc[df["model_id"] == int(model_id), "model_name"] = str(model_name)
    return df


def _extract_runtime_predictions(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    pred = df[df["event_name"] == "FUNC_PRED_RESULT"].copy()
    if pred.empty:
        return pred

    required_cols = ["model_name", "fingerprint"]
    for col in required_cols:
        if col not in pred.columns:
            raise RuntimeError(f"[F084] El log parseado no contiene la columna requerida: {col}")

    pred["fingerprint"] = pd.to_numeric(pred["fingerprint"], errors="coerce")
    pred = pred.dropna(subset=["model_name", "fingerprint"]).copy()
    if pred.empty:
        return pred

    pred["fingerprint"] = pred["fingerprint"].astype("int64")

    # Intentar resolver y_pred de forma robusta.
    ypred_col = None
    for c in ["y_pred", "predicted", "predicted_label", "prediction", "pred_class", "result"]:
        if c in pred.columns:
            ypred_col = c
            break

    if ypred_col is None:
        # fallback: si hay score + threshold ya vendrá tratado en otra fase, pero aquí no lo forzamos
        raise RuntimeError(
            "[F084] No se encontró columna de predicción binaria en FUNC_PRED_RESULT. "
            "Se esperaba una de: y_pred, predicted, predicted_label, prediction, pred_class, result"
        )

    pred["y_pred"] = pd.to_numeric(pred[ypred_col], errors="coerce")
    pred = pred.dropna(subset=["y_pred"]).copy()
    pred["y_pred"] = pred["y_pred"].astype(int)

    keep = ["model_name", "fingerprint", "y_pred"]
    if "timestamp_ms" in pred.columns:
        keep.append("timestamp_ms")

    pred = pred[keep].copy()

    # Una predicción por (modelo, fingerprint). Si hay varias, nos quedamos con la última.
    sort_cols = [c for c in ["timestamp_ms"] if c in pred.columns]
    if sort_cols:
        pred = pred.sort_values(sort_cols)

    pred = pred.drop_duplicates(subset=["model_name", "fingerprint"], keep="last")
    return pred


def _build_fp_from_events(series: pd.Series) -> pd.Series:
    return series.apply(lambda cell: int(_fnv1a_32(_parse_ow_events_cell(cell))))


def _evaluate_single_model(runtime_preds: pd.DataFrame, model_cfg: dict) -> dict:
    runtime_model_name = str(model_cfg["runtime_model_name"])
    eval_csv = model_cfg.get("evaluation_dataset_csv")

    if not eval_csv:
        return {
            "model_name": runtime_model_name,
            "N_total": None,
            "tp": None,
            "fp": None,
            "tn": None,
            "fn": None,
            "accuracy": None,
            "precision": None,
            "recall": None,
            "f1": None,
            "false_negative_rate": None,
            "skipped_predictions": None,
            "confusion_matrix": None,
            "quality_score": None,
        }

    eval_path = Path(eval_csv)
    if not eval_path.is_absolute():
        eval_path = (Path.cwd() / eval_path).resolve()

    if not eval_path.exists():
        raise RuntimeError(f"[F084] evaluation_dataset_csv no encontrado para {runtime_model_name}: {eval_path}")

    df_eval = pd.read_csv(eval_path, sep=";")
    if "OW_events" not in df_eval.columns:
        raise RuntimeError(f"[F084] El dataset de evaluación de {runtime_model_name} no contiene OW_events")
    if "label" not in df_eval.columns:
        raise RuntimeError(f"[F084] El dataset de evaluación de {runtime_model_name} no contiene label")

    df_eval = df_eval.copy()
    df_eval["fingerprint"] = _build_fp_from_events(df_eval["OW_events"])
    df_eval["label"] = pd.to_numeric(df_eval["label"], errors="coerce")
    df_eval = df_eval.dropna(subset=["label"]).copy()
    df_eval["label"] = df_eval["label"].astype(int)

    pred_m = runtime_preds[runtime_preds["model_name"] == runtime_model_name].copy()
    merged = df_eval.merge(
        pred_m[["fingerprint", "y_pred"]],
        on="fingerprint",
        how="left",
    )

    N_total = int(len(merged))
    skipped = int(merged["y_pred"].isna().sum())

    valid = merged.dropna(subset=["y_pred"]).copy()
    if valid.empty:
        return {
            "model_name": runtime_model_name,
            "N_total": N_total,
            "tp": 0,
            "fp": 0,
            "tn": 0,
            "fn": 0,
            "accuracy": None,
            "precision": None,
            "recall": None,
            "f1": None,
            "false_negative_rate": None,
            "skipped_predictions": skipped,
            "confusion_matrix": None,
            "quality_score": None,
        }

    valid["y_pred"] = valid["y_pred"].astype(int)

    tp = int(((valid["label"] == 1) & (valid["y_pred"] == 1)).sum())
    fp = int(((valid["label"] == 0) & (valid["y_pred"] == 1)).sum())
    tn = int(((valid["label"] == 0) & (valid["y_pred"] == 0)).sum())
    fn = int(((valid["label"] == 1) & (valid["y_pred"] == 0)).sum())

    denom = tp + tn + fp + fn
    accuracy = _rate(tp + tn, denom)
    precision = _rate(tp, tp + fp)
    recall = _rate(tp, tp + fn)
    f1 = None if (precision is None or recall is None or (precision + recall) == 0) else (2.0 * precision * recall / (precision + recall))
    fnr = _rate(fn, tp + fn)

    confusion_matrix = f"[[TN={tn}, FP={fp}], [FN={fn}, TP={tp}]]"
    quality_score = f1 if f1 is not None else (recall if recall is not None else accuracy)

    return {
        "model_name": runtime_model_name,
        "N_total": N_total,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_negative_rate": fnr,
        "skipped_predictions": skipped,
        "confusion_matrix": confusion_matrix,
        "quality_score": quality_score,
    }


def _evaluate_predictions(runtime_preds: pd.DataFrame, model_plan: list[dict]) -> pd.DataFrame:
    rows = []
    for model_cfg in model_plan:
        rows.append(_evaluate_single_model(runtime_preds, model_cfg))
    return pd.DataFrame(rows)


def _build_quality_metrics(models_df: pd.DataFrame, prediction_df: pd.DataFrame | None = None):
    if models_df is None or models_df.empty:
        return pd.DataFrame()

    qdf = models_df.copy()

    if "model_id" in qdf.columns:
        qdf = qdf[qdf["model_id"] >= 0].copy()

    if qdf.empty:
        return qdf

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

    if prediction_df is not None and not prediction_df.empty and "model_name" in prediction_df.columns:
        pred_cols = [
            "model_name",
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
            "quality_score",
        ]
        pred_cols = [c for c in pred_cols if c in prediction_df.columns]
        qdf = qdf.merge(prediction_df[pred_cols], on="model_name", how="left")

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
        "quality_score",
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
        "quality_score",
    ]
    cols = [c for c in preferred_order if c in df.columns]
    return df[cols]


def _resolve_system_metrics(models_report_df: pd.DataFrame, system_summary: dict) -> dict:
    row = _first_row_dict(pd.DataFrame([system_summary] if system_summary else []))

    if models_report_df is None or models_report_df.empty:
        row["system_quality_score"] = None
        row["mean_model_quality_score"] = None
        row["ok_rate"] = row.get("ok_rate")
        row["offload_rate"] = row.get("offload_rate")
        row["watchdog_rate"] = row.get("wd_late_rate")
        return row

    mdf = models_report_df.copy()

    if "quality_score" in mdf.columns:
        qs = pd.to_numeric(mdf["quality_score"], errors="coerce").dropna()
        row["mean_model_quality_score"] = float(qs.mean()) if not qs.empty else None
        row["system_quality_score"] = float(qs.mean()) if not qs.empty else None
    else:
        row["mean_model_quality_score"] = None
        row["system_quality_score"] = None

    attempts = pd.to_numeric(mdf.get("n_attempts"), errors="coerce").fillna(0)
    n_ok = pd.to_numeric(mdf.get("n_ok"), errors="coerce").fillna(0)
    n_offload = pd.to_numeric(mdf.get("n_offload"), errors="coerce").fillna(0)
    n_wd_late = pd.to_numeric(mdf.get("n_wd_late"), errors="coerce").fillna(0)

    den = float(attempts.sum()) if len(attempts) > 0 else 0.0
    row["ok_rate"] = _rate(float(n_ok.sum()), den)
    row["offload_rate"] = _rate(float(n_offload.sum()), den)
    row["watchdog_rate"] = _rate(float(n_wd_late.sum()), den)

    return row


def _update_system_profile(
    root: Path,
    *,
    selected_cfg: dict,
    system_profile: dict,
    models_report_df: pd.DataFrame,
    memory_row: dict,
    system_row: dict,
    run_completed: bool = True,
):
    profile = system_profile or {}

    run_block = profile.get("run", {}) or {}
    run_block.update(
        {
            "esp_run_completed": bool(run_completed),
            "n_inferences": int(models_report_df["n_inferences"].fillna(0).sum()) if "n_inferences" in models_report_df.columns else None,
            "ok_rate": system_row.get("ok_rate"),
            "offload_rate": system_row.get("offload_rate"),
            "watchdog_rate": system_row.get("watchdog_rate"),
        }
    )
    profile["run"] = run_block

    timing_block = profile.get("timing", {}) or {}
    timing_block.update(
        {
            "esp_mean_latency_ms": system_row.get("process_mean_ms"),
            "esp_max_latency_ms": system_row.get("process_max_ms"),
            "esp_jitter_ms": system_row.get("process_jitter_ms"),
        }
    )
    profile["timing"] = timing_block

    memory_block = profile.get("memory", {}) or {}
    memory_block.update(
        {
            "esp_memory_peak_bytes": memory_row.get("mem_used_max_bytes"),
            "heap_free_min_bytes": memory_row.get("heap_free_min_bytes"),
            "heap_total_ref": memory_row.get("heap_total_ref"),
        }
    )
    profile["memory"] = memory_block

    quality_block = profile.get("quality", {}) or {}
    quality_block.update(
        {
            "system_quality_score": system_row.get("system_quality_score"),
            "mean_model_quality_score": system_row.get("mean_model_quality_score"),
        }
    )
    profile["quality"] = quality_block

    outcome_block = profile.get("outcomes", {}) or {}
    outcome_block.update(
        {
            "ok_rate": system_row.get("ok_rate"),
            "offload_rate": system_row.get("offload_rate"),
            "watchdog_rate": system_row.get("watchdog_rate"),
        }
    )
    profile["outcomes"] = outcome_block

    system_block = profile.get("system", {}) or {}
    current_viable = bool(system_block.get("system_viable", False))
    current_edge_capable = bool(system_block.get("configuration_edge_capable", False))
    run_completed = bool(run_block.get("esp_run_completed", False))
    total_models_selected = int(((selected_cfg.get("aggregates", {}) or {}).get("total_models_selected", 0)) or 0)

    final_viable = current_edge_capable and current_viable and run_completed
    system_block["system_viable"] = bool(final_viable)

    phase_status = "completed"
    phase_status_reason = None
    selection_reason = selected_cfg.get("selection_reason")
    if not selection_reason:
        selection_reason = ((selected_cfg.get("selection_report", {}) or {}).get("reason"))

    if not bool(selected_cfg.get("selection_completed", False)):
        phase_status = "selection_incomplete"
        phase_status_reason = "selection_completed_false"
    elif not current_edge_capable:
        phase_status = "skipped_inviable"
        phase_status_reason = selection_reason or "configuration_edge_capable_false"
    elif total_models_selected <= 0:
        phase_status = "skipped_inviable"
        phase_status_reason = selection_reason or "no_models_selected"
    elif not run_completed:
        monitor_log = root / "08_esp_monitor_log.txt"
        phase_status = "partial_no_runtime"
        phase_status_reason = "monitor_log_missing" if not monitor_log.exists() else "edge_run_not_completed"

    run_block["phase_status"] = phase_status
    run_block["phase_status_reason"] = phase_status_reason
    system_block["phase_status"] = phase_status
    system_block["phase_status_reason"] = phase_status_reason

    profile["run"] = run_block
    profile["system"] = system_block

    # resumen por modelo
    profile["models_runtime_summary"] = []
    for _, row in models_report_df.iterrows():
        profile["models_runtime_summary"].append(
            {
                "model_id": _safe_scalar(row.get("model_id")),
                "model_name": _safe_scalar(row.get("model_name")),
                "n_attempts": _safe_scalar(row.get("n_attempts")),
                "n_inferences": _safe_scalar(row.get("n_inferences")),
                "ok_rate": _safe_scalar(row.get("ok_rate")),
                "offload_rate": _safe_scalar(row.get("offload_rate")),
                "infer_worst_ms": _safe_scalar(row.get("infer_worst_ms")),
                "accuracy": _safe_scalar(row.get("accuracy")),
                "precision": _safe_scalar(row.get("precision")),
                "recall": _safe_scalar(row.get("recall")),
                "f1": _safe_scalar(row.get("f1")),
                "quality_score": _safe_scalar(row.get("quality_score")),
                "tp": _safe_scalar(row.get("tp")),
                "fp": _safe_scalar(row.get("fp")),
                "tn": _safe_scalar(row.get("tn")),
                "fn": _safe_scalar(row.get("fn")),
            }
        )

    profile_path = root / "08_system_profile.yaml"
    profile_path.write_text(_yaml_dump_no_alias(profile))
    return profile


def _write_outputs_yaml(
    root: Path,
    *,
    selected_cfg: dict,
    updated_profile: dict,
    models_report_df: pd.DataFrame,
    memory_row: dict,
    system_row: dict,
):
    artifacts = [
        str(root / "08_selected_configuration.yaml"),
        str(root / "08_selection_report.yaml"),
        str(root / "08_candidate_summary.csv"),
        str(root / "08_unique_windows.csv"),
        str(root / "08_system_profile.yaml"),
        str(root / "08_edge_run_config.yaml"),
        str(root / "08_input_dataset.csv"),
        str(root / "08_model_execution_plan.yaml"),
        str(root / "08_edge_predictions.csv"),
        str(root / "08_edge_runtime_metrics_raw.json"),
        str(root / "metrics_models.csv"),
        str(root / "metrics_memory.csv"),
        str(root / "metrics_system_timing.csv"),
        str(root / "metrics_outcomes.csv"),
        str(root / "metrics_system_summary.yaml"),
        str(root / "08_report.html"),
        str(root / "08_esp_build_log.txt"),
        str(root / "08_esp_flash_log.txt"),
        str(root / "08_esp_monitor_log.txt"),
    ]

    if (root / "sdkconfig").exists():
        artifacts.append(str(root / "sdkconfig"))
    elif list(root.glob("*_project/sdkconfig")):
        artifacts.extend(str(p) for p in root.glob("*_project/sdkconfig"))

    if (root / "application_image.bin").exists():
        artifacts.append(str(root / "application_image.bin"))
    if (root / "bootloader_image.bin").exists():
        artifacts.append(str(root / "bootloader_image.bin"))
    if (root / "partition_table_image.bin").exists():
        artifacts.append(str(root / "partition_table_image.bin"))
    if (root / "platform_build_bundle").exists():
        artifacts.append(str(root / "platform_build_bundle"))

    exports = {
        "selection_mode": selected_cfg.get("selection_mode"),
        "objective": ((selected_cfg.get("selection_report", {}) or {}).get("objective")),
        "solver_status": ((selected_cfg.get("selection_report", {}) or {}).get("solver_status")),
        "solver_iterations": ((selected_cfg.get("selection_report", {}) or {}).get("iterations")),
        "solver_objective_value": ((selected_cfg.get("selection_report", {}) or {}).get("objective_value")),
        "solver_lambda_last": ((selected_cfg.get("selection_report", {}) or {}).get("lambda_last")),
        "solver_gap_last": ((selected_cfg.get("selection_report", {}) or {}).get("gap_last")),
        "parent_variants": (selected_cfg.get("parent", {}) or {}).get("variants", []),
        "requested_parent_variants": selected_cfg.get("requested_parent_variants", []),
        "selected_variants": selected_cfg.get("selected_variants", []),
        "excluded_parents": selected_cfg.get("excluded_parents", []),
        "platform": selected_cfg.get("platform"),
        "Tu": ((selected_cfg.get("common_input_signature", {}) or {}).get("Tu")),
        "OW": ((selected_cfg.get("common_input_signature", {}) or {}).get("OW")),
        "LT": ((selected_cfg.get("common_input_signature", {}) or {}).get("LT")),
        "PW": ((selected_cfg.get("common_input_signature", {}) or {}).get("PW")),
        "event_type_count": ((selected_cfg.get("common_input_signature", {}) or {}).get("event_type_count")),
        "model_ids": [m.get("model_id") for m in (selected_cfg.get("models", []) or [])],
        "runtime_model_names": [m.get("runtime_model_name") for m in (selected_cfg.get("models", []) or [])],
        "MTI_MS": ((selected_cfg.get("system_limits", {}) or {}).get("MTI_MS")),
        "total_models_requested": ((selected_cfg.get("aggregates", {}) or {}).get("total_models_requested")),
        "total_models_declared": ((selected_cfg.get("aggregates", {}) or {}).get("total_models_declared")),
        "total_models_selected": ((selected_cfg.get("aggregates", {}) or {}).get("total_models_selected")),
        "total_model_size_bytes": ((selected_cfg.get("aggregates", {}) or {}).get("total_model_size_bytes")),
        "required_arena_bytes": ((selected_cfg.get("aggregates", {}) or {}).get("required_arena_bytes")),
        "operators_union": ((selected_cfg.get("aggregates", {}) or {}).get("operators_union", [])),
        "compatible_input_signature": bool(selected_cfg.get("compatible_input_signature", False)),
        "configuration_edge_capable": bool(selected_cfg.get("configuration_edge_capable", False)),
        "selection_completed": bool(selected_cfg.get("selection_completed", False)),
        "phase_status": ((updated_profile.get("run", {}) or {}).get("phase_status")),
        "phase_status_reason": ((updated_profile.get("run", {}) or {}).get("phase_status_reason")),
        "esp_run_completed": bool((updated_profile.get("run", {}) or {}).get("esp_run_completed", False)),
        "edge_run_completed": bool((updated_profile.get("run", {}) or {}).get("esp_run_completed", False)),
        "selection_global_precision": ((selected_cfg.get("aggregates", {}) or {}).get("global_precision")),
        "selection_global_recall": ((selected_cfg.get("aggregates", {}) or {}).get("global_recall")),
        "selection_sum_effective_time_ms": ((selected_cfg.get("aggregates", {}) or {}).get("sum_effective_time_ms")),
        "selection_max_exec_time_ms": ((selected_cfg.get("aggregates", {}) or {}).get("max_exec_time_ms")),
        "max_exec_time_ms": ((selected_cfg.get("aggregates", {}) or {}).get("max_exec_time_ms")),
        "system_viable": bool((updated_profile.get("system", {}) or {}).get("system_viable", False)),
        "unique_windows_count": ((selected_cfg.get("aggregates", {}) or {}).get("unique_windows_count")),
        "duplicate_windows_removed": ((selected_cfg.get("aggregates", {}) or {}).get("duplicate_windows_removed")),
        "exec_time_policy": selected_cfg.get("exec_time_policy"),
    }

    metrics = {
        "execution_time": None,
        "n_inferences": int(models_report_df["n_inferences"].fillna(0).sum()) if "n_inferences" in models_report_df.columns else None,
        "unique_windows_count": int(((selected_cfg.get("aggregates", {}) or {}).get("unique_windows_count", 0)) or 0),
        "evaluated_rows_total": int(((selected_cfg.get("aggregates", {}) or {}).get("unique_windows_count", 0)) or 0),
        "models_evaluated": int(len(models_report_df)) if models_report_df is not None else 0,
        "throughput_inf_per_sec": None,
        "edge_mean_latency_ms": system_row.get("process_mean_ms"),
        "edge_max_latency_ms": system_row.get("process_max_ms"),
        "edge_jitter_ms": system_row.get("process_jitter_ms"),
        "esp_mean_latency_ms": system_row.get("process_mean_ms"),
        "esp_max_latency_ms": system_row.get("process_max_ms"),
        "esp_jitter_ms": system_row.get("process_jitter_ms"),
        "ok_rate": system_row.get("ok_rate"),
        "offload_rate": system_row.get("offload_rate"),
        "watchdog_rate": system_row.get("watchdog_rate"),
        "system_quality_score": system_row.get("system_quality_score"),
        "mean_model_quality_score": system_row.get("mean_model_quality_score"),
        "edge_memory_peak_bytes": memory_row.get("mem_used_max_bytes"),
        "esp_memory_peak_bytes": memory_row.get("mem_used_max_bytes"),
        "pc_esp_agreement": None,
    }

    outputs = {
        "generated_at": datetime.utcnow().isoformat(),
        "phase": PHASE,
        "parent": {
            "phase": PARENT_PHASE,
            "variants": (selected_cfg.get("parent", {}) or {}).get("variants", []),
        },
        "artifacts": artifacts,
        "exports": exports,
        "metrics": metrics,
    }

    (root / "outputs.yaml").write_text(_yaml_dump_no_alias(outputs))


def _write_runtime_aux_artifacts(
    root: Path,
    *,
    runtime_preds: pd.DataFrame | None,
    raw_metrics_payload: dict | None,
    models_report_df: pd.DataFrame,
    system_row: dict,
):
    preds_path = root / "08_edge_predictions.csv"
    if runtime_preds is None or runtime_preds.empty:
        pd.DataFrame(columns=["model_name", "fingerprint", "y_pred", "timestamp_ms"]).to_csv(preds_path, index=False)
    else:
        runtime_preds.to_csv(preds_path, index=False)

    raw_path = root / "08_edge_runtime_metrics_raw.json"
    with raw_path.open("w", encoding="utf-8") as f:
        json.dump(raw_metrics_payload or {}, f, ensure_ascii=False, indent=2)

    outcomes_cols = [
        "model_id",
        "model_name",
        "n_attempts",
        "n_ok",
        "n_fail",
        "n_offload",
        "n_wd_late",
        "ok_rate",
        "offload_rate",
        "wd_late_rate",
        "fail_rate",
    ]
    outcomes_cols = [c for c in outcomes_cols if c in models_report_df.columns]
    outcomes_df = models_report_df[outcomes_cols].copy() if outcomes_cols else pd.DataFrame()
    outcomes_df.to_csv(root / "metrics_outcomes.csv", index=False)

    (root / "metrics_system_summary.yaml").write_text(_yaml_dump_no_alias(system_row or {}))


def _write_html_report(root: Path, selected_cfg: dict, models_report_df: pd.DataFrame, memory_df: pd.DataFrame, timing_df: pd.DataFrame):
    def _df_to_html(df: pd.DataFrame, index=False):
        if df is None or df.empty:
            return "<p><em>No data</em></p>"
        return df.to_html(index=index, border=0)

    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>F08 report</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 24px; }}
h1, h2 {{ color: #222; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 24px; }}
th, td {{ border: 1px solid #ccc; padding: 6px 8px; font-size: 13px; text-align: left; }}
th {{ background: #f5f5f5; }}
code {{ background: #f2f2f2; padding: 2px 4px; }}
</style>
</head>
<body>
<h1>F08 — System Validation Report</h1>
<p><strong>Generated at:</strong> {datetime.utcnow().isoformat()}</p>
<p><strong>Selection mode:</strong> {selected_cfg.get("selection_mode")}</p>
<p><strong>Platform:</strong> {selected_cfg.get("platform")}</p>
<p><strong>Selected variants:</strong> {selected_cfg.get("selected_variants", [])}</p>

<h2>System summary</h2>
<pre>{_yaml_dump_no_alias({
    "configuration_edge_capable": selected_cfg.get("configuration_edge_capable"),
    "compatible_input_signature": selected_cfg.get("compatible_input_signature"),
    "system_viable_initial": selected_cfg.get("system_viable"),
    "MTI_MS": (selected_cfg.get("system_limits", {}) or {}).get("MTI_MS"),
    "required_arena_bytes": (selected_cfg.get("aggregates", {}) or {}).get("required_arena_bytes"),
    "total_model_size_bytes": (selected_cfg.get("aggregates", {}) or {}).get("total_model_size_bytes"),
})}</pre>

<h2>Metrics by model</h2>
{_df_to_html(models_report_df)}

<h2>Memory summary</h2>
{_df_to_html(memory_df)}

<h2>System timing summary</h2>
{_df_to_html(timing_df)}

</body>
</html>
"""
    (root / "08_report.html").write_text(html, encoding="utf-8")


# ============================================================
# MAIN ANALYSIS
# ============================================================

def run_analysis(variant: str):
    root = _resolve_variant_root(variant)

    # limpieza de legacy opcional
    for legacy in [
        "metrics_raw.json",
        "metrics_inference_records.csv",
        "metrics_prediction.csv",
        "metrics_quality_models.csv",
    ]:
        p = root / legacy
        if p.exists():
            p.unlink()

    selected_cfg = _load_yaml(root / "08_selected_configuration.yaml", "08_selected_configuration.yaml")
    system_profile = _load_yaml_if_exists(root / "08_system_profile.yaml") or {}
    edge_cfg = {}
    model_plan = []

    if not bool(selected_cfg.get("selection_completed", False)):
        raise RuntimeError("[F084] selection_completed=false en 08_selected_configuration.yaml")

    if not bool(selected_cfg.get("configuration_edge_capable", False)):
        print("[F084] configuration_edge_capable=false. Se generan salidas sin análisis de runtime edge.")

        models_report_df = pd.DataFrame()
        models_csv = root / "metrics_models.csv"
        models_report_df.to_csv(models_csv, index=False)

        memory_df = pd.DataFrame()
        memory_csv = root / "metrics_memory.csv"
        memory_df.to_csv(memory_csv, index=False)

        timing_df = pd.DataFrame()
        timing_csv = root / "metrics_system_timing.csv"
        timing_df.to_csv(timing_csv, index=False)

        memory_row = _first_row_dict(memory_df)
        system_row = _resolve_system_metrics(models_report_df, {})

        _write_runtime_aux_artifacts(
            root,
            runtime_preds=pd.DataFrame(),
            raw_metrics_payload={
                "reason": "configuration_edge_capable_false",
                "runtime_events": 0,
            },
            models_report_df=models_report_df,
            system_row=system_row,
        )

        updated_profile = _update_system_profile(
            root,
            selected_cfg=selected_cfg,
            system_profile=system_profile,
            models_report_df=models_report_df,
            memory_row=memory_row,
            system_row=system_row,
            run_completed=False,
        )

        _write_outputs_yaml(
            root,
            selected_cfg=selected_cfg,
            updated_profile=updated_profile,
            models_report_df=models_report_df,
            memory_row=memory_row,
            system_row=system_row,
        )

        _write_html_report(
            root,
            selected_cfg=selected_cfg,
            models_report_df=models_report_df,
            memory_df=memory_df,
            timing_df=timing_df,
        )

        print("")
        print("[F084] Analysis completed (configuration_edge_capable=false)")
        print(f" metrics_models.csv        : {models_csv}")
        print(f" metrics_memory.csv        : {memory_csv}")
        print(f" metrics_system_timing.csv : {timing_csv}")
        print(f" outputs.yaml              : {root / 'outputs.yaml'}")
        print(f" 08_system_profile.yaml    : {root / '08_system_profile.yaml'}")
        print(f" 08_report.html            : {root / '08_report.html'}")
        return

    edge_cfg = _load_yaml(root / "08_edge_run_config.yaml", "08_edge_run_config.yaml")
    execution_plan = _load_yaml(root / "08_model_execution_plan.yaml", "08_model_execution_plan.yaml")
    model_plan = execution_plan.get("models", []) or []

    log_path = root / "08_esp_monitor_log.txt"
    if not log_path.exists():
        print(f"[F084] No monitor log found: {log_path}. Se generan salidas parciales sin análisis de runtime.")

        models_report_df = pd.DataFrame()
        models_csv = root / "metrics_models.csv"
        models_report_df.to_csv(models_csv, index=False)

        memory_df = pd.DataFrame()
        memory_csv = root / "metrics_memory.csv"
        memory_df.to_csv(memory_csv, index=False)

        timing_df = pd.DataFrame()
        timing_csv = root / "metrics_system_timing.csv"
        timing_df.to_csv(timing_csv, index=False)

        memory_row = _first_row_dict(memory_df)
        system_row = _resolve_system_metrics(models_report_df, {})

        _write_runtime_aux_artifacts(
            root,
            runtime_preds=pd.DataFrame(),
            raw_metrics_payload={
                "reason": "monitor_log_missing",
                "runtime_events": 0,
            },
            models_report_df=models_report_df,
            system_row=system_row,
        )

        updated_profile = _update_system_profile(
            root,
            selected_cfg=selected_cfg,
            system_profile=system_profile,
            models_report_df=models_report_df,
            memory_row=memory_row,
            system_row=system_row,
            run_completed=False,
        )

        _write_outputs_yaml(
            root,
            selected_cfg=selected_cfg,
            updated_profile=updated_profile,
            models_report_df=models_report_df,
            memory_row=memory_row,
            system_row=system_row,
        )

        _write_html_report(
            root,
            selected_cfg=selected_cfg,
            models_report_df=models_report_df,
            memory_df=memory_df,
            timing_df=timing_df,
        )

        print("")
        print("[F084] Analysis completed (sin monitor log)")
        print(f" metrics_models.csv        : {models_csv}")
        print(f" metrics_memory.csv        : {memory_csv}")
        print(f" metrics_system_timing.csv : {timing_csv}")
        print(f" outputs.yaml              : {root / 'outputs.yaml'}")
        print(f" 08_system_profile.yaml    : {root / '08_system_profile.yaml'}")
        print(f" 08_report.html            : {root / '08_report.html'}")
        return

    print(f"[F084] Using log file: {log_path}")
    print(f"[F084] Parsing log {log_path}")

    df = parse_log_enriched(log_path)
    model_name_map = _load_model_name_map_from_cfg(edge_cfg)
    df = _apply_model_name_map(df, model_name_map)

    print("[F084] Computing system summary")
    system_summary = compute_system_summary(df)

    print("[F084] Computing model metrics")
    models_df = compute_model_metrics(df)

    print("[F084] Extracting runtime predictions")
    runtime_preds = _extract_runtime_predictions(df)

    print("[F084] Evaluating predictions by model")
    prediction_df = _evaluate_predictions(runtime_preds, model_plan)

    print("[F084] Building quality metrics")
    quality_df = _build_quality_metrics(models_df, prediction_df)

    key_cols = [c for c in ["model_id", "model_name"] if c in quality_df.columns and c in models_df.columns]
    extra_cols = [c for c in quality_df.columns if c not in models_df.columns]

    if key_cols and extra_cols:
        merged_df = models_df.merge(quality_df[key_cols + extra_cols], on=key_cols, how="left")
        models_report_df = _compact_models_report(merged_df)
    else:
        models_report_df = _compact_models_report(models_df)

    models_csv = root / "metrics_models.csv"
    models_report_df.to_csv(models_csv, index=False)

    print("[F084] Computing memory summary")
    memory_summary = compute_memory_summary(df)
    memory_df = pd.DataFrame([memory_summary] if memory_summary else [])
    memory_csv = root / "metrics_memory.csv"
    memory_df.to_csv(memory_csv, index=False)

    print("[F084] Writing timing summary")
    timing_df = pd.DataFrame([system_summary] if system_summary else [])
    timing_csv = root / "metrics_system_timing.csv"
    timing_df.to_csv(timing_csv, index=False)

    memory_row = _first_row_dict(memory_df)
    system_row = _resolve_system_metrics(models_report_df, system_summary)

    _write_runtime_aux_artifacts(
        root,
        runtime_preds=runtime_preds,
        raw_metrics_payload={
            "runtime_events": int(len(df)) if df is not None else 0,
            "parse_columns": list(df.columns) if df is not None else [],
            "system_summary": system_summary or {},
            "memory_summary": memory_summary or {},
            "models_metrics_rows": int(len(models_report_df)) if models_report_df is not None else 0,
            "prediction_rows": int(len(runtime_preds)) if runtime_preds is not None else 0,
        },
        models_report_df=models_report_df,
        system_row=system_row,
    )

    updated_profile = _update_system_profile(
        root,
        selected_cfg=selected_cfg,
        system_profile=system_profile,
        models_report_df=models_report_df,
        memory_row=memory_row,
        system_row=system_row,
        run_completed=True,
    )

    _write_outputs_yaml(
        root,
        selected_cfg=selected_cfg,
        updated_profile=updated_profile,
        models_report_df=models_report_df,
        memory_row=memory_row,
        system_row=system_row,
    )

    _write_html_report(
        root,
        selected_cfg=selected_cfg,
        models_report_df=models_report_df,
        memory_df=memory_df,
        timing_df=timing_df,
    )

    print("")
    print("[F084] Analysis completed")
    print(f" metrics_models.csv        : {models_csv}")
    print(f" metrics_memory.csv        : {memory_csv}")
    print(f" metrics_system_timing.csv : {timing_csv}")
    print(f" outputs.yaml              : {root / 'outputs.yaml'}")
    print(f" 08_system_profile.yaml    : {root / '08_system_profile.yaml'}")
    print(f" 08_report.html            : {root / '08_report.html'}")


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", required=True)
    args = parser.parse_args()
    run_analysis(args.variant)

    