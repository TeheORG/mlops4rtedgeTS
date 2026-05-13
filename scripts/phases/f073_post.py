#!/usr/bin/env python3

import yaml
import pandas as pd

from pathlib import Path
from datetime import datetime
import argparse

from scripts.runtime_analysis.parse import parse_log_enriched
from scripts.runtime_analysis.metrics_models import compute_model_metrics
from scripts.runtime_analysis.metrics_memory import compute_memory_summary
from scripts.runtime_analysis.metrics_timing import compute_system_summary
from scripts.runtime_analysis.metrics_prediction import compute_full_prediction_metrics
from scripts.runtime_analysis.window_fingerprint import (
    fnv1a_32 as _fnv1a_32,
    parse_events_cell as _parse_ow_events_cell,
)


def _rate(num, den):
    if den is None or den == 0:
        return None
    return float(num) / float(den)


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


def _build_fp_index_from_dataset(root: Path, model_name_map: dict) -> "pd.DataFrame | None":
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

    if "OW_events" not in df.columns or "label" not in df.columns:
        print(f"[F073] Warning: {csv_path} missing OW_events or label column.")
        return None

    df["_events"] = df["OW_events"].apply(_parse_ow_events_cell)
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
):
    profile_path = root / "07_model_profile.yaml"
    profile = _load_yaml_if_exists(profile_path)
    if profile is None:
        raise RuntimeError(f"[F073] 07_model_profile.yaml no encontrado: {profile_path}")

    quality_score = _build_quality_score(models_row)

    run_block = profile.get("run", {}) or {}
    run_block.update(
        {
            "edge_run_completed": True,
            "n_inferences": models_row.get("n_inferences"),
            "ok_rate": models_row.get("ok_rate"),
            "offload_rate": models_row.get("offload_rate"),
            "watchdog_rate": models_row.get("wd_late_rate"),
        }
    )
    profile["run"] = run_block

    timing_block = profile.get("timing", {}) or {}
    timing_block.update(
        {
            "edge_mean_latency_ms": system_row.get("process_mean_ms", models_row.get("infer_mean_ms")),
            "edge_max_latency_ms": system_row.get("process_max_ms", models_row.get("infer_max_ms")),
            "edge_jitter_ms": system_row.get("process_jitter_ms", models_row.get("infer_jitter_ms")),
            "itmax_ms": models_row.get("infer_worst_ms", models_row.get("infer_max_ms")),
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
):

    if artifacts is None:
        artifacts = [
            str(analysis / "07_model_profile.yaml"),
            str(analysis / "metrics_models.csv"),
            str(analysis / "metrics_memory.csv"),
            str(analysis / "metrics_system_timing.csv"),
        ]

    exports = dict(
        edge_capable=bool(parent_exports.get("edge_capable", False)),
        incompatibility_reason=parent_exports.get("incompatibility_reason"),
    )

    if model_profile:
        model_block = model_profile.get("model", {}) or {}
        sig_block = model_profile.get("input_signature", {}) or {}
        build_block = model_profile.get("build", {}) or {}
        limits_block = model_profile.get("limits", {}) or {}
        run_block = model_profile.get("run", {}) or {}
        quality_block = model_profile.get("quality", {}) or {}

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
                "event_type_count": sig_block.get("event_type_count"),
                "operators": build_block.get("operators"),
                "decision_threshold": build_block.get("decision_threshold"),
                "arena_bytes": build_block.get("arena_bytes"),
                "model_memory_bytes": (model_profile.get("memory", {}) or {}).get("model_memory_bytes"),
                "itmax_ms": (model_profile.get("timing", {}) or {}).get("itmax_ms", limits_block.get("itmax_ms")),
                "ITmax": limits_block.get("ITmax"),
                "MTI_MS": limits_block.get("MTI_MS"),
                "quality_score": quality_block.get("quality_score"),
                "n_inferences": run_block.get("n_inferences"),
                "ok_rate": run_block.get("ok_rate"),
                "offload_rate": run_block.get("offload_rate"),
                "watchdog_rate": run_block.get("watchdog_rate"),
                "edge_run_completed": bool(
                    run_block.get("edge_run_completed", run_block.get("esp_run_completed", False))
                ),
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

        run_block = model_profile.get("run", {}) or {}
        run_block.update(
            {
                "edge_run_completed": False,
                "n_inferences": None,
                "ok_rate": None,
                "offload_rate": None,
                "watchdog_rate": None,
            }
        )
        model_profile["run"] = run_block

        if profile_path.exists():
            profile_path.write_text(yaml.safe_dump(model_profile, sort_keys=False))

        artifacts = [str(profile_path)] if profile_path.exists() else []
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
            phase_status_reason="monitor_log_missing",
        )
        print("[F073] Partial outputs exported (no monitor log available).")
        return

    model_name_map = _load_model_name_map_from_cfg(root)

    print(f"[F073] Parsing log {log_path}")

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
        fp_index_df = _build_fp_index_from_dataset(root, model_name_map)

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

    model_profile = _update_model_profile(
        root,
        models_row=models_row,
        memory_row=memory_row,
        system_row=system_row,
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