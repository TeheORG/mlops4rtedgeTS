#!/usr/bin/env python3
"""
F08 — SYSTEM VALIDATION (MULTI-MODEL EDGE) — SELECT CONFIG

Modos soportados:
- manual
- auto_ilp

Notas de diseño:
- La arena NO se cuenta por modelo. Se usa arena global fija = max(arena_bytes)
  sobre el conjunto de candidatos factibles (tras filtros de calidad/edge).
- La restricción temporal usa effective_time_ms = itmax_ms + 5.0
- El objetivo por defecto en auto_ilp es maximizar recall global exacto:
      sum(TP_i x_i) / sum((TP_i + FN_i) x_i)
  usando una resolución MILP iterativa tipo Dinkelbach.
"""

import argparse
import math
from pathlib import Path

import pandas as pd
import yaml

from scripts.runtime_analysis.window_fingerprint import (
    fnv1a_32 as _fnv1a_32,
    parse_events_cell as _parse_ow_events_cell,
)
from scripts.core.artifacts import PROJECT_ROOT, get_variant_dir
from scripts.core.edge_prepare_common import (
    load_phase_outputs,
    load_variant_params,
    load_yaml_file,
    resolve_platform,
)

try:
    import pulp
except Exception:
    pulp = None


PHASE = "f08_sysval"
PARENT_PHASE = "f07_modval"
MEMORY_GUARD_BYTES_DEFAULT = 32768
EXEC_TIME_POLICY = "effective_time_ms = ceil(itmax_ms + 5.0)"
DEFAULT_OBJECTIVE = "max_global_recall"
DEFAULT_SOLVER_TIME_LIMIT_SEC = 30
DEFAULT_DINKELBACH_MAX_ITER = 40
DEFAULT_DINKELBACH_TOL = 1e-9


class _NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def _yaml_dump_no_alias(data: dict) -> str:
    return yaml.dump(data, Dumper=_NoAliasDumper, sort_keys=False)


# ============================================================
# GENERIC HELPERS
# ============================================================

def _safe_float(v, default=0.0) -> float:
    try:
        if v is None:
            return float(default)
        if isinstance(v, float) and (v != v):
            return float(default)
        return float(v)
    except Exception:
        return float(default)


def _safe_int(v, default=0) -> int:
    try:
        if v is None:
            return int(default)
        if isinstance(v, float) and (v != v):
            return int(default)
        return int(float(v))
    except Exception:
        return int(default)


def _first_non_null(*values):
    for v in values:
        if v is not None:
            if isinstance(v, float) and (v != v):
                continue
            return v
    return None


def _nested_get(d: dict, path: list[str], default=None):
    cur = d
    for key in path:
        if not isinstance(cur, dict):
            return default
        if key not in cur:
            return default
        cur = cur[key]
    return cur


def _read_csv_if_exists(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.read_csv(path)
    except Exception:
        return None


def _solver_status_to_str(status_code) -> str:
    try:
        return str(pulp.LpStatus.get(status_code, status_code))
    except Exception:
        return str(status_code)


# ============================================================
# WINDOW / DATASET HELPERS
# ============================================================

def normalize_window(window):
    if hasattr(window, "tolist"):
        return window.tolist()
    if isinstance(window, (list, tuple)):
        return list(window)
    if hasattr(window, "item"):
        return [window.item()]
    return [window]


def compute_window_key(window) -> str:
    return str(int(_fnv1a_32(_parse_ow_events_cell(window))))


def build_unique_windows_from_dataset(dataset_path: Path, max_rows: int | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not dataset_path.exists():
        raise RuntimeError(f"[F08] Dataset no encontrado: {dataset_path}")

    if dataset_path.suffix.lower() == ".parquet":
        df = pd.read_parquet(dataset_path)
    else:
        df = pd.read_csv(dataset_path, sep=";")

    if "OW_events" not in df.columns:
        raise RuntimeError(f"[F08] El dataset no contiene columna OW_events: {dataset_path}")

    if max_rows is not None:
        df = df.head(int(max_rows)).copy()
    else:
        df = df.copy()

    df["window_key"] = df["OW_events"].apply(compute_window_key)

    df_unique = (
        df[["window_key", "OW_events"]]
        .drop_duplicates(subset=["window_key"])
        .reset_index(drop=True)
    )

    return df_unique, df


def build_unique_windows_from_datasets(
    dataset_paths: list[Path],
    max_rows: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not dataset_paths:
        raise RuntimeError("[F08] No hay datasets de evaluación para construir ventanas únicas")

    frames: list[pd.DataFrame] = []
    rows_loaded = 0

    for dataset_path in dataset_paths:
        if not dataset_path.exists():
            raise RuntimeError(f"[F08] Dataset no encontrado: {dataset_path}")

        if dataset_path.suffix.lower() == ".parquet":
            df = pd.read_parquet(dataset_path)
        else:
            df = pd.read_csv(dataset_path, sep=";")

        if "OW_events" not in df.columns:
            raise RuntimeError(f"[F08] El dataset no contiene columna OW_events: {dataset_path}")

        if max_rows is not None:
            remaining = int(max_rows) - rows_loaded
            if remaining <= 0:
                break
            df = df.head(remaining)

        df = df.copy()
        df["window_key"] = df["OW_events"].apply(compute_window_key)

        rows_loaded += int(len(df))
        frames.append(df)

    if not frames:
        raise RuntimeError("[F08] No se pudieron cargar filas para construir ventanas únicas")

    df_full = pd.concat(frames, ignore_index=True)
    df_unique = (
        df_full[["window_key", "OW_events"]]
        .drop_duplicates(subset=["window_key"])
        .reset_index(drop=True)
    )

    return df_unique, df_full


# ============================================================
# PARAMS / PARENTS
# ============================================================

def resolve_parent_variants(params_data: dict) -> list[str]:
    parameters = params_data.get("parameters", {}) or {}
    raw = parameters.get("parent_variant") or parameters.get("parents")

    if raw is None:
        raise RuntimeError(
            "[F08] parent_variant requerido. "
            "Define PARENTS=v7XX,v7YY,... en make variant8"
        )

    if isinstance(raw, str):
        normalized = raw.replace("[", " ").replace("]", " ")
        normalized = normalized.replace(",", " ")
        parents = [p.strip() for p in normalized.split() if p.strip()]
    elif isinstance(raw, list):
        parents = []
        for item in raw:
            token = str(item).strip()
            if not token:
                continue
            normalized = token.replace("[", " ").replace("]", " ")
            normalized = normalized.replace(",", " ")
            parents.extend([p.strip() for p in normalized.split() if p.strip()])
    else:
        raise RuntimeError("[F08] parents debe ser lista o string CSV")

    if not parents:
        raise RuntimeError("[F08] parents vacío")

    if len(set(parents)) != len(parents):
        raise RuntimeError("[F08] parents contiene duplicados")

    return parents


# ============================================================
# SIGNATURE / COMPATIBILITY
# ============================================================

def compute_union_operators(model_profiles: list[dict]) -> list[str]:
    ops = set()
    for prof in model_profiles:
        build = prof.get("build", {}) or {}
        ops |= set(build.get("operators", []) or [])
    return sorted(ops)


def _signature_from_profile(profile: dict) -> dict:
    sig = profile.get("input_signature", {}) or {}
    model = profile.get("model", {}) or {}
    return {
        "platform": model.get("platform"),
        "Tu": sig.get("Tu"),
        "OW": sig.get("OW"),
        "LT": sig.get("LT"),
        "PW": sig.get("PW"),
        "input_dtype": sig.get("input_dtype"),
        "output_dtype": sig.get("output_dtype"),
        "input_shape": sig.get("input_shape"),
        "output_shape": sig.get("output_shape"),
        "input_bytes": sig.get("input_bytes"),
        "output_bytes": sig.get("output_bytes"),
        "input_max_len": sig.get("input_max_len"),
        "normalization_mean": sig.get("normalization_mean"),
        "normalization_std": sig.get("normalization_std"),
        "input_quant_scale": sig.get("input_quant_scale"),
        "input_quant_zero_point": sig.get("input_quant_zero_point"),
    }


def _signature_incompatibility_reason(base: dict, candidate: dict, expected_platform: str) -> str | None:
    platform = str(candidate.get("platform") or "").strip().lower()
    if platform != expected_platform:
        return (
            "platform incompatible: "
            f"{candidate.get('platform')!r} != {expected_platform!r}"
        )

    keys_to_match = [
        "platform",
        "Tu",
        "OW",
        "LT",
        "PW",
        "input_dtype",
        "output_dtype",
        "output_shape",
        "output_bytes",
        "input_max_len",
        "normalization_mean",
        "normalization_std",
        "input_quant_scale",
        "input_quant_zero_point",
    ]

    for key in keys_to_match:
        if candidate.get(key) != base.get(key):
            return (
                f"signature mismatch in {key}: "
                f"base={base.get(key)!r}, candidate={candidate.get(key)!r}"
            )

    return None


def validate_common_signature(selected_profiles: list[dict], expected_platform: str) -> dict:
    if not selected_profiles:
        raise RuntimeError("[F08] No hay perfiles seleccionados")

    base = _signature_from_profile(selected_profiles[0])

    reason = _signature_incompatibility_reason(base, base, expected_platform)
    if reason is not None:
        raise RuntimeError(f"[F08] {reason}")

    for idx, prof in enumerate(selected_profiles[1:], start=1):
        cur = _signature_from_profile(prof)
        reason = _signature_incompatibility_reason(base, cur, expected_platform)
        if reason is not None:
            raise RuntimeError(f"[F08] Incompatibilidad de firma con model[{idx}]: {reason}")

    return base


# ============================================================
# METRIC EXTRACTION
# ============================================================

def _extract_confusion_from_profile_or_metrics(profile: dict, parent_dir: Path) -> dict:
    """
    Intenta recuperar TP/TN/FP/FN, precision y recall desde:
    1) 07_model_profile.yaml / quality
    2) metrics_quality_models.csv
    3) metrics_prediction.csv

    Se soportan varios nombres de columnas para robustez.
    """
    quality = profile.get("quality", {}) or {}
    model = profile.get("model", {}) or {}
    runtime_model_name = model.get("runtime_model_name")
    prediction_name = model.get("prediction_name")

    tp = _first_non_null(
        quality.get("tp"),
        quality.get("TP"),
        quality.get("true_positives"),
        quality.get("tp_count"),
    )
    tn = _first_non_null(
        quality.get("tn"),
        quality.get("TN"),
        quality.get("true_negatives"),
        quality.get("tn_count"),
    )
    fp = _first_non_null(
        quality.get("fp"),
        quality.get("FP"),
        quality.get("false_positives"),
        quality.get("fp_count"),
    )
    fn = _first_non_null(
        quality.get("fn"),
        quality.get("FN"),
        quality.get("false_negatives"),
        quality.get("fn_count"),
    )

    precision = _first_non_null(
        quality.get("precision"),
        quality.get("Precision"),
        quality.get("prec"),
    )
    recall = _first_non_null(
        quality.get("recall"),
        quality.get("Recall"),
        quality.get("tpr"),
        quality.get("sensitivity"),
    )

    def _row_match(df: pd.DataFrame) -> pd.Series | None:
        if df is None or df.empty:
            return None

        if runtime_model_name and "model_name" in df.columns:
            matches = df[df["model_name"] == runtime_model_name]
            if not matches.empty:
                return matches.iloc[0]

        if prediction_name and "prediction_name" in df.columns:
            matches = df[df["prediction_name"] == prediction_name]
            if not matches.empty:
                return matches.iloc[0]

        return df.iloc[0]

    qdf = _read_csv_if_exists(parent_dir / "metrics_quality_models.csv")
    row = _row_match(qdf)
    if row is not None:
        tp = _first_non_null(
            tp,
            row.get("tp"),
            row.get("TP"),
            row.get("true_positives"),
            row.get("tp_count"),
        )
        tn = _first_non_null(
            tn,
            row.get("tn"),
            row.get("TN"),
            row.get("true_negatives"),
            row.get("tn_count"),
        )
        fp = _first_non_null(
            fp,
            row.get("fp"),
            row.get("FP"),
            row.get("false_positives"),
            row.get("fp_count"),
        )
        fn = _first_non_null(
            fn,
            row.get("fn"),
            row.get("FN"),
            row.get("false_negatives"),
            row.get("fn_count"),
        )
        precision = _first_non_null(
            precision,
            row.get("precision"),
            row.get("Precision"),
            row.get("prec"),
        )
        recall = _first_non_null(
            recall,
            row.get("recall"),
            row.get("Recall"),
            row.get("tpr"),
            row.get("sensitivity"),
        )

    pdf = _read_csv_if_exists(parent_dir / "metrics_prediction.csv")
    row = _row_match(pdf)
    if row is not None:
        tp = _first_non_null(
            tp,
            row.get("tp"),
            row.get("TP"),
            row.get("true_positives"),
            row.get("tp_count"),
        )
        tn = _first_non_null(
            tn,
            row.get("tn"),
            row.get("TN"),
            row.get("true_negatives"),
            row.get("tn_count"),
        )
        fp = _first_non_null(
            fp,
            row.get("fp"),
            row.get("FP"),
            row.get("false_positives"),
            row.get("fp_count"),
        )
        fn = _first_non_null(
            fn,
            row.get("fn"),
            row.get("FN"),
            row.get("false_negatives"),
            row.get("fn_count"),
        )
        precision = _first_non_null(
            precision,
            row.get("precision"),
            row.get("Precision"),
            row.get("prec"),
        )
        recall = _first_non_null(
            recall,
            row.get("recall"),
            row.get("Recall"),
            row.get("tpr"),
            row.get("sensitivity"),
        )

    tp = _safe_int(tp, 0)
    tn = _safe_int(tn, 0)
    fp = _safe_int(fp, 0)
    fn = _safe_int(fn, 0)

    if precision is None:
        precision = (tp / (tp + fp)) if (tp + fp) > 0 else None
    else:
        precision = _safe_float(precision, None)

    if recall is None:
        recall = (tp / (tp + fn)) if (tp + fn) > 0 else None
    else:
        recall = _safe_float(recall, None)

    return {
        "tp": int(tp),
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "precision": None if precision is None else float(precision),
        "recall": None if recall is None else float(recall),
        "positive_support": int(tp + fn),
        "total_support": int(tp + tn + fp + fn),
    }


# ============================================================
# MODEL BUILD
# ============================================================

def build_selected_model(
    parent_variant: str,
    parent_dir: Path,
    profile: dict,
    user_mti_ms: float,
) -> dict:
    def _load_management_latencies_ms(parent_dir: Path, runtime_model_name: str | None) -> tuple[float, float]:
        infer_mgmt_max_ms = 0.0
        cycle_mgmt_max_ms = 0.0

        models_csv = parent_dir / "metrics_models.csv"
        if models_csv.exists():
            try:
                mdf = pd.read_csv(models_csv)
                if not mdf.empty and "infer_overhead_max_ms" in mdf.columns:
                    row = None
                    if runtime_model_name and "model_name" in mdf.columns:
                        matches = mdf[mdf["model_name"] == runtime_model_name]
                        if not matches.empty:
                            row = matches.iloc[0]
                    if row is None:
                        row = mdf.iloc[0]
                    infer_mgmt_max_ms = _safe_float(row.get("infer_overhead_max_ms"), 0.0)
            except Exception:
                pass

        system_csv = parent_dir / "metrics_system_timing.csv"
        if system_csv.exists():
            try:
                sdf = pd.read_csv(system_csv)
                if not sdf.empty:
                    row = sdf.iloc[0]
                    cycle_mgmt_max_ms = _safe_float(
                        row.get("sys_cycle_process_max_ms", row.get("sys_cycle_max_ms")),
                        0.0,
                    )
            except Exception:
                pass

        return infer_mgmt_max_ms, cycle_mgmt_max_ms

    model = profile.get("model", {}) or {}
    build = profile.get("build", {}) or {}
    limits = profile.get("limits", {}) or {}
    timing = profile.get("timing", {}) or {}
    artifacts = profile.get("artifacts", {}) or {}
    run = profile.get("run", {}) or {}
    compat = profile.get("compatibility", {}) or {}
    sig = profile.get("input_signature", {}) or {}
    quality = profile.get("quality", {}) or {}

    model_tflite_rel = artifacts.get("model_tflite")
    if not model_tflite_rel:
        raise RuntimeError(f"[F08] model_tflite no definido en 07_model_profile de {parent_variant}")

    evaluation_dataset_rel = artifacts.get("evaluation_dataset_csv")
    if not evaluation_dataset_rel:
        raise RuntimeError(f"[F08] evaluation_dataset_csv no definido en 07_model_profile de {parent_variant}")

    input_dataset_rel = artifacts.get("input_dataset_csv")
    if not input_dataset_rel:
        raise RuntimeError(f"[F08] input_dataset_csv no definido en 07_model_profile de {parent_variant}")

    model_tflite_path = Path(model_tflite_rel)
    evaluation_dataset_path = Path(evaluation_dataset_rel)
    input_dataset_path = Path(input_dataset_rel)
    if not model_tflite_path.is_absolute():
        model_tflite_path = (PROJECT_ROOT / model_tflite_path).resolve()
    if not evaluation_dataset_path.is_absolute():
        evaluation_dataset_path = (PROJECT_ROOT / evaluation_dataset_path).resolve()
    if not input_dataset_path.is_absolute():
        input_dataset_path = (PROJECT_ROOT / input_dataset_path).resolve()

    if not input_dataset_path.exists():
        raise RuntimeError(f"[F08] input_dataset_csv no encontrado para {parent_variant}: {input_dataset_path}")
    if not model_tflite_path.exists():
        raise RuntimeError(f"[F08] model_tflite no encontrado para {parent_variant}: {model_tflite_path}")
    if not evaluation_dataset_path.exists():
        raise RuntimeError(f"[F08] evaluation_dataset_csv no encontrado para {parent_variant}: {evaluation_dataset_path}")

    itmax_ms = timing.get("itmax_ms")
    if itmax_ms is None:
        itmax_ms = limits.get("itmax_ms")
    if itmax_ms is None:
        itmax_ms = limits.get("ITmax")
    if itmax_ms is None:
        raise RuntimeError(f"[F08] itmax_ms no definido en 07_model_profile de {parent_variant}")

    infer_mgmt_max_ms, cycle_mgmt_max_ms = _load_management_latencies_ms(
        parent_dir,
        model.get("runtime_model_name"),
    )

    it_max_ms = float(itmax_ms)
    effective_time_ms = float(math.ceil(it_max_ms + 5.0))
    exec_time_ms = effective_time_ms

    confusion = _extract_confusion_from_profile_or_metrics(profile, parent_dir)

    return {
        "parent_variant": parent_variant,
        "model_id": model.get("model_id"),
        "runtime_model_name": model.get("runtime_model_name"),
        "prediction_name": model.get("prediction_name"),
        "platform": model.get("platform"),
        "edge_capable": bool(compat.get("edge_capable", False)),
        "edge_run_completed": bool(run.get("edge_run_completed", run.get("esp_run_completed", False))),
        "threshold": build.get("decision_threshold"),
        "it_max_ms": float(it_max_ms),
        "itmax_ms": float(it_max_ms),
        "infer_mgmt_latency_max_ms": float(infer_mgmt_max_ms),
        "cycle_mgmt_latency_max_ms": float(cycle_mgmt_max_ms),
        "management_overhead_ms": 5.0,
        "effective_time_ms": float(effective_time_ms),
        "exec_time_ms": float(exec_time_ms),
        "ITmax": limits.get("ITmax"),
        "MTI_MS": int(round(float(user_mti_ms))),
        "arena_bytes": int(build.get("arena_bytes") or 0),
        "arena_global_bytes": int(build.get("arena_global_bytes") or 0),
        "model_size_bytes": int(build.get("model_size_bytes") or 0),
        "operators": build.get("operators", []) or [],
        "quality_score": quality.get("quality_score"),
        "precision": confusion["precision"],
        "recall": confusion["recall"],
        "tp": int(confusion["tp"]),
        "tn": int(confusion["tn"]),
        "fp": int(confusion["fp"]),
        "fn": int(confusion["fn"]),
        "positive_support": int(confusion["positive_support"]),
        "total_support": int(confusion["total_support"]),
        "Tu": sig.get("Tu"),
        "OW": sig.get("OW"),
        "LT": sig.get("LT"),
        "PW": sig.get("PW"),
        "input_dtype": sig.get("input_dtype"),
        "output_dtype": sig.get("output_dtype"),
        "input_shape": sig.get("input_shape"),
        "output_shape": sig.get("output_shape"),
        "input_bytes": sig.get("input_bytes"),
        "output_bytes": sig.get("output_bytes"),
        "input_max_len": sig.get("input_max_len"),
        "normalization_mean": sig.get("normalization_mean"),
        "normalization_std": sig.get("normalization_std"),
        "input_quant_scale": sig.get("input_quant_scale"),
        "input_quant_zero_point": sig.get("input_quant_zero_point"),
        "model_tflite": str(model_tflite_path),
        "evaluation_dataset_csv": str(evaluation_dataset_path),
        "input_dataset_csv": str(input_dataset_path),
        "source_profile": str((parent_dir / "07_model_profile.yaml").resolve()),
    }


def build_selected_models(
    parent_variants: list[str],
    parent_dirs: list[Path],
    model_profiles: list[dict],
    user_mti_ms: float,
) -> list[dict]:
    return [
        build_selected_model(parent_variant, parent_dir, profile, user_mti_ms)
        for parent_variant, parent_dir, profile in zip(parent_variants, parent_dirs, model_profiles)
    ]


# ============================================================
# MEMORY HELPERS
# ============================================================

def _load_heap_total_ref_bytes(parent_dir: Path) -> int | None:
    metrics_path = parent_dir / "metrics_memory.csv"
    if not metrics_path.exists():
        return None

    try:
        df = pd.read_csv(metrics_path)
    except Exception:
        return None

    if df.empty or "heap_total_ref" not in df.columns:
        return None

    try:
        raw = df.iloc[0].get("heap_total_ref")
        if pd.isna(raw):
            return None
        value = int(float(raw))
    except Exception:
        return None

    return value if value > 0 else None


# ============================================================
# CANDIDATE FILTERING
# ============================================================

def filter_candidates_for_selection(
    models: list[dict],
    min_precision: float | None = None,
    min_recall: float | None = None,
    min_quality_score: float | None = None,
) -> tuple[list[dict], list[dict]]:
    feasible = []
    excluded = []

    for m in models:
        reason = None

        if not bool(m.get("edge_capable", False)):
            reason = "edge_capable=false"
        elif min_quality_score is not None:
            q = m.get("quality_score")
            if q is None or float(q) < float(min_quality_score):
                reason = f"quality_score<{min_quality_score}"
        if reason is None and min_precision is not None:
            p = m.get("precision")
            if p is None or float(p) < float(min_precision):
                reason = f"precision<{min_precision}"
        if reason is None and min_recall is not None:
            r = m.get("recall")
            if r is None or float(r) < float(min_recall):
                reason = f"recall<{min_recall}"
        if reason is None and int(m.get("positive_support") or 0) <= 0:
            reason = "positive_support<=0"

        if reason is None:
            feasible.append(m)
        else:
            excluded.append(
                {
                    "parent_variant": m.get("parent_variant"),
                    "runtime_model_name": m.get("runtime_model_name"),
                    "reason": reason,
                }
            )

    return feasible, excluded


# ============================================================
# ILP / MILP SELECTION
# ============================================================

def _build_base_problem(
    name: str,
    candidates: list[dict],
    memory_models_budget_bytes: int | None,
    mti_ms: float,
    max_models: int | None,
):
    prob = pulp.LpProblem(name, pulp.LpMaximize)
    x = {
        idx: pulp.LpVariable(f"x_{idx}", lowBound=0, upBound=1, cat=pulp.LpBinary)
        for idx in range(len(candidates))
    }

    prob += pulp.lpSum(x[idx] * float(candidates[idx].get("effective_time_ms") or 0.0) for idx in x) <= float(mti_ms), "time_budget"

    if memory_models_budget_bytes is not None:
        prob += (
            pulp.lpSum(x[idx] * int(candidates[idx].get("model_size_bytes") or 0) for idx in x)
            <= int(memory_models_budget_bytes)
        ), "memory_budget_models"

    if max_models is not None:
        prob += pulp.lpSum(x[idx] for idx in x) <= int(max_models), "max_models"

    prob += pulp.lpSum(x[idx] for idx in x) >= 1, "min_one_model"

    return prob, x


def _extract_selected_indices(x_vars: dict[int, "pulp.LpVariable"]) -> list[int]:
    selected = []
    for idx, var in x_vars.items():
        val = var.value()
        if val is not None and float(val) > 0.5:
            selected.append(idx)
    return selected


def solve_selection_max_tp(
    candidates: list[dict],
    memory_models_budget_bytes: int | None,
    mti_ms: float,
    max_models: int | None,
    time_limit_sec: int,
) -> dict:
    prob, x = _build_base_problem(
        name="F08_SelectConfig_MaxTP",
        candidates=candidates,
        memory_models_budget_bytes=memory_models_budget_bytes,
        mti_ms=mti_ms,
        max_models=max_models,
    )

    prob += pulp.lpSum(x[idx] * int(candidates[idx].get("tp") or 0) for idx in x), "maximize_tp"

    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=int(time_limit_sec))
    status = prob.solve(solver)
    status_str = _solver_status_to_str(status)

    if status_str not in {"Optimal", "Integer Feasible"}:
        return {
            "solver_status": status_str,
            "selected_indices": [],
            "objective_value": None,
            "iterations": 1,
        }

    selected_indices = _extract_selected_indices(x)
    total_tp = sum(int(candidates[i].get("tp") or 0) for i in selected_indices)
    total_fn = sum(int(candidates[i].get("fn") or 0) for i in selected_indices)
    recall_global = (total_tp / (total_tp + total_fn)) if (total_tp + total_fn) > 0 else None

    return {
        "solver_status": status_str,
        "selected_indices": selected_indices,
        "objective_value": float(total_tp),
        "objective_name": "max_tp",
        "recall_global": recall_global,
        "iterations": 1,
    }


def solve_selection_max_global_recall(
    candidates: list[dict],
    memory_models_budget_bytes: int | None,
    mti_ms: float,
    max_models: int | None,
    time_limit_sec: int,
    max_iter: int = DEFAULT_DINKELBACH_MAX_ITER,
    tol: float = DEFAULT_DINKELBACH_TOL,
) -> dict:
    """
    Maximiza exactamente el cociente:
        sum(tp_i x_i) / sum((tp_i + fn_i) x_i)
    usando iteración de Dinkelbach con MILP binario.
    """
    lam = 0.0
    best = None
    last_status = "NotSolved"

    for it in range(1, int(max_iter) + 1):
        prob, x = _build_base_problem(
            name=f"F08_SelectConfig_MaxRecall_iter{it}",
            candidates=candidates,
            memory_models_budget_bytes=memory_models_budget_bytes,
            mti_ms=mti_ms,
            max_models=max_models,
        )

        prob += pulp.lpSum(
            x[idx] * (
                float(int(candidates[idx].get("tp") or 0))
                - float(lam) * float(int(candidates[idx].get("positive_support") or 0))
            )
            for idx in x
        ), f"maximize_tp_minus_lambda_support_iter{it}"

        solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=int(time_limit_sec))
        status = prob.solve(solver)
        status_str = _solver_status_to_str(status)
        last_status = status_str

        if status_str not in {"Optimal", "Integer Feasible"}:
            break

        selected_indices = _extract_selected_indices(x)
        if not selected_indices:
            break

        total_tp = sum(int(candidates[i].get("tp") or 0) for i in selected_indices)
        total_pos = sum(int(candidates[i].get("positive_support") or 0) for i in selected_indices)
        total_fn = sum(int(candidates[i].get("fn") or 0) for i in selected_indices)
        if total_pos <= 0:
            break

        recall_val = float(total_tp) / float(total_pos)
        objective_gap = float(total_tp) - float(lam) * float(total_pos)

        best = {
            "solver_status": status_str,
            "selected_indices": selected_indices,
            "objective_value": float(recall_val),
            "objective_name": "max_global_recall",
            "recall_global": float(recall_val),
            "total_tp": int(total_tp),
            "total_fn": int(total_fn),
            "total_positive_support": int(total_pos),
            "iterations": int(it),
            "lambda_last": float(lam),
            "gap_last": float(objective_gap),
        }

        if abs(objective_gap) <= float(tol):
            return best

        lam = recall_val

    if best is None:
        return {
            "solver_status": last_status,
            "selected_indices": [],
            "objective_value": None,
            "objective_name": "max_global_recall",
            "recall_global": None,
            "iterations": 0,
        }

    return best


def run_auto_selector(
    candidates: list[dict],
    objective_name: str,
    memory_models_budget_bytes: int | None,
    mti_ms: float,
    max_models: int | None,
    time_limit_sec: int,
) -> dict:
    if pulp is None:
        raise RuntimeError(
            "[F08] El modo auto_ilp requiere la librería 'pulp'. "
            "Instálala en el entorno: pip install pulp"
        )

    objective_name = str(objective_name or DEFAULT_OBJECTIVE).strip().lower()

    if objective_name == "max_tp":
        return solve_selection_max_tp(
            candidates=candidates,
            memory_models_budget_bytes=memory_models_budget_bytes,
            mti_ms=mti_ms,
            max_models=max_models,
            time_limit_sec=time_limit_sec,
        )

    if objective_name in {"max_global_recall", "global_recall", "recall_global"}:
        return solve_selection_max_global_recall(
            candidates=candidates,
            memory_models_budget_bytes=memory_models_budget_bytes,
            mti_ms=mti_ms,
            max_models=max_models,
            time_limit_sec=time_limit_sec,
        )

    raise RuntimeError(f"[F08] objective no soportado en auto_ilp: {objective_name}")


# ============================================================
# CANDIDATE SUMMARY / REPORT
# ============================================================

def write_candidate_summary(variant_dir: Path, selected_models: list[dict], feasible_parent_variants: set[str] | None = None):
    rows = []
    feasible_parent_variants = feasible_parent_variants or set()

    for m in selected_models:
        rows.append(
            {
                "parent_variant": m.get("parent_variant"),
                "model_id": m.get("model_id"),
                "runtime_model_name": m.get("runtime_model_name"),
                "prediction_name": m.get("prediction_name"),
                "platform": m.get("platform"),
                "quality_score": m.get("quality_score"),
                "precision": m.get("precision"),
                "recall": m.get("recall"),
                "tp": m.get("tp"),
                "tn": m.get("tn"),
                "fp": m.get("fp"),
                "fn": m.get("fn"),
                "positive_support": m.get("positive_support"),
                "total_support": m.get("total_support"),
                "itmax_ms": m.get("itmax_ms"),
                "effective_time_ms": m.get("effective_time_ms"),
                "cycle_mgmt_latency_max_ms": m.get("cycle_mgmt_latency_max_ms"),
                "management_overhead_ms": m.get("management_overhead_ms"),
                "exec_time_ms": m.get("exec_time_ms"),
                "arena_bytes": m.get("arena_bytes"),
                "model_size_bytes": m.get("model_size_bytes"),
                "edge_capable": m.get("edge_capable"),
                "edge_run_completed": m.get("edge_run_completed"),
                "feasible_after_filters": m.get("parent_variant") in feasible_parent_variants,
                "selected": bool(m.get("_selected", False)),
                "evaluation_dataset_csv": m.get("evaluation_dataset_csv"),
                "input_dataset_csv": m.get("input_dataset_csv"),
            }
        )

    out_path = variant_dir / "08_candidate_summary.csv"
    pd.DataFrame(rows).to_csv(out_path, index=False)


def write_selection_report(variant_dir: Path, report: dict):
    out_path = variant_dir / "08_selection_report.yaml"
    out_path.write_text(_yaml_dump_no_alias(report))


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", required=True)
    args = parser.parse_args()

    variant = args.variant
    variant_dir = get_variant_dir(PHASE, variant)

    params_data = load_variant_params(get_variant_dir, PHASE, variant, "F08")
    params = params_data.get("parameters", {})

    selection_mode = str(params.get("selection_mode", "manual")).strip().lower()
    if selection_mode not in {"manual", "auto_ilp"}:
        raise RuntimeError(f"[F08] selection_mode no soportado: {selection_mode}")

    platform = resolve_platform(params, "F08")
    parent_variants_resolution_error = None
    try:
        parent_variants = resolve_parent_variants(params_data)
    except Exception as exc:
        parent_variants = []
        parent_variants_resolution_error = str(exc)

    mti_ms = params.get("MTI_MS")
    if mti_ms is None:
        raise RuntimeError("[F08] MTI_MS requerido")
    try:
        mti_ms = float(mti_ms)
    except Exception:
        raise RuntimeError("[F08] MTI_MS debe ser numérico (ms)")
    if mti_ms <= 0:
        raise RuntimeError("[F08] MTI_MS debe ser > 0 (ms)")

    max_rows = params.get("max_rows")
    memory_budget_bytes = params.get("memory_budget_bytes")
    max_models = params.get("max_models")
    min_quality_score = params.get("min_quality_score")
    min_precision = params.get("min_precision")
    min_recall = params.get("min_recall")
    objective_name = str(params.get("objective", DEFAULT_OBJECTIVE)).strip().lower()
    solver_time_limit_sec = _safe_int(params.get("solver_time_limit_sec", DEFAULT_SOLVER_TIME_LIMIT_SEC), DEFAULT_SOLVER_TIME_LIMIT_SEC)

    try:
        time_scale_factor = float(params.get("time_scale_factor", 1.0))
    except Exception:
        raise RuntimeError("[F08] time_scale_factor debe ser numérico")
    if time_scale_factor <= 0:
        raise RuntimeError("[F08] time_scale_factor debe ser > 0")

    if max_rows is not None:
        max_rows = int(max_rows)
        if max_rows < 1:
            raise RuntimeError("[F08] max_rows debe ser >= 1")

    if memory_budget_bytes is not None:
        memory_budget_bytes = int(memory_budget_bytes)

    if max_models is not None:
        max_models = int(max_models)
        if max_models < 1:
            raise RuntimeError("[F08] max_models debe ser >= 1")

    if min_quality_score is not None:
        min_quality_score = float(min_quality_score)

    if min_precision is not None:
        min_precision = float(min_precision)

    if min_recall is not None:
        min_recall = float(min_recall)

    parent_dirs: list[Path] = []
    model_profiles: list[dict] = []
    edge_parent_variants: list[str] = []
    non_edge_parent_variants: list[str] = []
    excluded_parents: list[dict] = []

    def exclude_parent(parent_variant: str | None, reason: str, stage: str):
        excluded_parents.append(
            {
                "parent_variant": parent_variant,
                "stage": stage,
                "reason": str(reason),
            }
        )

    if parent_variants_resolution_error is not None:
        exclude_parent(None, parent_variants_resolution_error, "resolve_parent_variants")

    def write_inviable_selection_result(
        *,
        reason: str,
        solver_status: str,
        common_sig: dict | None = None,
        total_models_declared: int = 0,
        operators_union: list[str] | None = None,
        all_models: list[dict] | None = None,
        feasible_parent_variants: set[str] | None = None,
        plate_available_heap_bytes: int | None = None,
        effective_memory_budget_bytes: int | None = None,
        extra_selection_report: dict | None = None,
    ):
        unique_windows_path = variant_dir / "08_unique_windows.csv"
        pd.DataFrame(columns=["window_key", "OW_events"]).to_csv(unique_windows_path, index=False)

        all_models = all_models or []
        feasible_parent_variants = feasible_parent_variants or set()
        operators_union = operators_union or []

        for model in all_models:
            model["_selected"] = False

        write_candidate_summary(
            variant_dir,
            all_models,
            feasible_parent_variants=feasible_parent_variants,
        )

        selection_report = {
            "selection_mode": selection_mode,
            "objective": objective_name,
            "solver_status": solver_status,
            "reason": reason,
            "candidates_considered": len(all_models) if all_models else len(parent_variants),
            "candidates_feasible_after_filters": len(feasible_parent_variants),
            "selected_count": 0,
            "selected_variants": [],
            "excluded_parents": excluded_parents,
        }
        if extra_selection_report:
            selection_report.update(extra_selection_report)
        write_selection_report(variant_dir, selection_report)

        signature = common_sig or {}
        selected_configuration = {
            "phase": PHASE,
            "variant": variant,
            "selection_mode": selection_mode,
            "selection_completed": True,
            "selection_reason": reason,
            "configuration_edge_capable": False,
            "compatible_input_signature": bool(common_sig),
            "system_viable": False,
            "exec_time_policy": EXEC_TIME_POLICY,
            "parent": {"phase": PARENT_PHASE, "variants": []},
            "requested_parent_variants": parent_variants,
            "selected_variants": [],
            "non_edge_parent_variants": non_edge_parent_variants,
            "excluded_parents": excluded_parents,
            "platform": platform,
            "time_scale_factor": float(time_scale_factor),
            "system_limits": {
                "MTI_MS": int(round(mti_ms)),
                "memory_budget_bytes": int(memory_budget_bytes) if memory_budget_bytes is not None else None,
                "max_models": int(max_models) if max_models is not None else None,
                "min_quality_score": float(min_quality_score) if min_quality_score is not None else None,
                "min_precision": float(min_precision) if min_precision is not None else None,
                "min_recall": float(min_recall) if min_recall is not None else None,
                "objective": objective_name,
            },
            "common_input_signature": {
                "Tu": signature.get("Tu"),
                "OW": signature.get("OW"),
                "LT": signature.get("LT"),
                "PW": signature.get("PW"),
                "input_dtype": signature.get("input_dtype"),
                "output_dtype": signature.get("output_dtype"),
                "input_shape": signature.get("input_shape"),
                "output_shape": signature.get("output_shape"),
                "input_bytes": signature.get("input_bytes"),
                "output_bytes": signature.get("output_bytes"),
                "input_max_len": signature.get("input_max_len"),
                "normalization_mean": signature.get("normalization_mean"),
                "normalization_std": signature.get("normalization_std"),
                "input_quant_scale": signature.get("input_quant_scale"),
                "input_quant_zero_point": signature.get("input_quant_zero_point"),
            },
            "aggregates": {
                "total_models_requested": len(parent_variants),
                "total_models_declared": int(total_models_declared),
                "total_models_selected": 0,
                "required_arena_bytes": 0,
                "total_model_size_bytes": 0,
                "model_memory_payload_bytes": 0,
                "model_memory_required_bytes": 0,
                "operators_union": operators_union,
                "unique_windows_count": 0,
                "duplicate_windows_removed": 0,
                "max_exec_time_ms": 0.0,
                "sum_effective_time_ms": 0.0,
                "total_tp": 0,
                "total_tn": 0,
                "total_fp": 0,
                "total_fn": 0,
                "global_precision": None,
                "global_recall": None,
            },
            "memory_check": {
                "source": "f07.metrics_memory.heap_total_ref",
                "plate_available_heap_bytes": int(plate_available_heap_bytes) if plate_available_heap_bytes is not None else None,
                "effective_memory_budget_bytes": int(effective_memory_budget_bytes) if effective_memory_budget_bytes is not None else None,
                "memory_guard_bytes": int(MEMORY_GUARD_BYTES_DEFAULT),
                "arena_global_bytes": 0,
                "models_memory_budget_bytes": None,
                "model_memory_payload_bytes": 0,
                "model_memory_required_bytes": 0,
                "fit_margin_bytes": None,
                "fits": False,
            },
            "selection_report": selection_report,
            "datasets": {
                "base_evaluation_dataset_csv": None,
                "source_evaluation_datasets_csv": [],
                "unique_windows_csv": str(unique_windows_path),
                "max_rows": int(max_rows) if max_rows is not None else None,
                "full_rows_count": 0,
                "unique_windows_count": 0,
            },
            "models": [],
        }

        out_path = variant_dir / "08_selected_configuration.yaml"
        out_path.write_text(_yaml_dump_no_alias(selected_configuration))

    loaded_edge_parent_records: list[tuple[str, Path, dict]] = []

    for parent_variant in parent_variants:
        try:
            outputs, parent_dir = load_phase_outputs(PROJECT_ROOT, PARENT_PHASE, parent_variant, "F08")
        except Exception as exc:
            exclude_parent(parent_variant, exc, "load_outputs")
            continue

        exports = outputs.get("exports", {}) or {}
        if not bool(exports.get("edge_capable", False)):
            non_edge_parent_variants.append(parent_variant)
            exclude_parent(
                parent_variant,
                str(exports.get("incompatibility_reason") or "edge_capable=false en F07 outputs"),
                "edge_capable_check",
            )
            continue

        profile_path = parent_dir / "07_model_profile.yaml"
        try:
            profile = load_yaml_file(profile_path, f"07_model_profile de {parent_variant}", "F08")
        except Exception as exc:
            exclude_parent(parent_variant, exc, "load_model_profile")
            continue

        loaded_edge_parent_records.append((parent_variant, parent_dir, profile))

    common_sig = None
    compatible_parent_records: list[tuple[str, Path, dict]] = []
    for parent_variant, parent_dir, profile in loaded_edge_parent_records:
        candidate_sig = _signature_from_profile(profile)
        if common_sig is None:
            reason = _signature_incompatibility_reason(candidate_sig, candidate_sig, platform)
            if reason is not None:
                exclude_parent(parent_variant, reason, "validate_signature")
                continue
            common_sig = candidate_sig
            compatible_parent_records.append((parent_variant, parent_dir, profile))
            continue

        reason = _signature_incompatibility_reason(common_sig, candidate_sig, platform)
        if reason is not None:
            exclude_parent(parent_variant, reason, "validate_signature")
            continue
        compatible_parent_records.append((parent_variant, parent_dir, profile))

    for parent_variant, parent_dir, profile in compatible_parent_records:
        try:
            build_selected_model(parent_variant, parent_dir, profile, user_mti_ms=float(mti_ms))
        except Exception as exc:
            exclude_parent(parent_variant, exc, "build_candidate")
            continue

        parent_dirs.append(parent_dir)
        model_profiles.append(profile)
        edge_parent_variants.append(parent_variant)

    if not edge_parent_variants:
        unique_windows_path = variant_dir / "08_unique_windows.csv"
        pd.DataFrame(columns=["window_key", "OW_events"]).to_csv(unique_windows_path, index=False)

        write_candidate_summary(variant_dir, [])
        write_selection_report(
            variant_dir,
            {
                "selection_mode": selection_mode,
                "objective": objective_name,
                "solver_status": "NoCandidates",
                "reason": "no_edge_capable_parents",
                "candidates_considered": len(parent_variants),
                "candidates_feasible_after_filters": 0,
                "selected_count": 0,
                "selected_variants": [],
                "excluded_parents": excluded_parents,
            },
        )

        selected_configuration = {
            "phase": PHASE,
            "variant": variant,
            "selection_mode": selection_mode,
            "selection_completed": True,
            "configuration_edge_capable": False,
            "compatible_input_signature": False,
            "system_viable": False,
            "exec_time_policy": EXEC_TIME_POLICY,
            "parent": {"phase": PARENT_PHASE, "variants": []},
            "requested_parent_variants": parent_variants,
            "selected_variants": [],
            "non_edge_parent_variants": non_edge_parent_variants,
            "excluded_parents": excluded_parents,
            "platform": platform,
            "time_scale_factor": float(time_scale_factor),
            "system_limits": {
                "MTI_MS": int(round(mti_ms)),
                "memory_budget_bytes": int(memory_budget_bytes) if memory_budget_bytes is not None else None,
                "max_models": int(max_models) if max_models is not None else None,
                "min_quality_score": float(min_quality_score) if min_quality_score is not None else None,
                "min_precision": float(min_precision) if min_precision is not None else None,
                "min_recall": float(min_recall) if min_recall is not None else None,
                "objective": objective_name,
            },
            "common_input_signature": {
                "Tu": None,
                "OW": None,
                "LT": None,
                "PW": None,
                "input_dtype": None,
                "output_dtype": None,
                "input_shape": None,
                "output_shape": None,
                "input_bytes": None,
                "output_bytes": None,
                "input_max_len": None,
                "normalization_mean": None,
                "normalization_std": None,
                "input_quant_scale": None,
                "input_quant_zero_point": None,
            },
            "aggregates": {
                "total_models_requested": len(parent_variants),
                "total_models_declared": 0,
                "total_models_selected": 0,
                "required_arena_bytes": 0,
                "total_model_size_bytes": 0,
                "model_memory_payload_bytes": 0,
                "model_memory_required_bytes": 0,
                "operators_union": [],
                "unique_windows_count": 0,
                "duplicate_windows_removed": 0,
                "max_exec_time_ms": 0.0,
                "sum_effective_time_ms": 0.0,
                "total_tp": 0,
                "total_tn": 0,
                "total_fp": 0,
                "total_fn": 0,
                "global_precision": None,
                "global_recall": None,
            },
            "memory_check": {
                "source": "f07.metrics_memory.heap_total_ref",
                "plate_available_heap_bytes": None,
                "effective_memory_budget_bytes": int(memory_budget_bytes) if memory_budget_bytes is not None else None,
                "memory_guard_bytes": int(MEMORY_GUARD_BYTES_DEFAULT),
                "arena_global_bytes": 0,
                "models_memory_budget_bytes": None,
                "model_memory_payload_bytes": 0,
                "model_memory_required_bytes": 0,
                "fit_margin_bytes": None,
                "fits": False,
            },
            "selection_report": {
                "solver_status": "NoCandidates",
                "objective": objective_name,
                "reason": "no_edge_capable_parents",
            },
            "selection_reason": "no_edge_capable_parents",
            "datasets": {
                "base_evaluation_dataset_csv": None,
                "source_evaluation_datasets_csv": [],
                "unique_windows_csv": str(unique_windows_path),
                "max_rows": int(max_rows) if max_rows is not None else None,
                "full_rows_count": 0,
                "unique_windows_count": 0,
            },
            "models": [],
        }

        out_path = variant_dir / "08_selected_configuration.yaml"
        out_path.write_text(_yaml_dump_no_alias(selected_configuration))

        print(f"[F08] selectconfig OK — {variant}")
        print("[F08] No hay modelos edge_capable seleccionables. Se genera configuración no-edge.")
        print(f"[F08] Parents excluidos: {len(excluded_parents)}")
        return

    if common_sig is None:
        raise RuntimeError("[F08] common_sig no disponible con parents edge_capable")
    operators_union = compute_union_operators(model_profiles)

    all_edge_models = build_selected_models(
        edge_parent_variants,
        parent_dirs,
        model_profiles,
        user_mti_ms=float(mti_ms),
    )

    # Heap total ref común para encaje real
    heap_total_refs = []
    for parent_dir in parent_dirs:
        heap_total_ref = _load_heap_total_ref_bytes(parent_dir)
        if heap_total_ref is not None:
            heap_total_refs.append(heap_total_ref)
    plate_available_heap_bytes = min(heap_total_refs) if heap_total_refs else None

    # Filtro por umbrales
    feasible_candidates, filtered_out_candidates = filter_candidates_for_selection(
        all_edge_models,
        min_precision=min_precision,
        min_recall=min_recall,
        min_quality_score=min_quality_score,
    )
    excluded_parents.extend(filtered_out_candidates)

    if not feasible_candidates:
        unique_windows_path = variant_dir / "08_unique_windows.csv"
        pd.DataFrame(columns=["window_key", "OW_events"]).to_csv(unique_windows_path, index=False)

        for m in all_edge_models:
            m["_selected"] = False
        write_candidate_summary(variant_dir, all_edge_models, feasible_parent_variants=set())
        write_selection_report(
            variant_dir,
            {
                "selection_mode": selection_mode,
                "objective": objective_name,
                "solver_status": "NoFeasibleCandidatesAfterFilters",
                "reason": "no_feasible_candidates_after_filters",
                "filters": {
                    "min_quality_score": min_quality_score,
                    "min_precision": min_precision,
                    "min_recall": min_recall,
                },
                "excluded_parents": excluded_parents,
            },
        )

        selected_configuration = {
            "phase": PHASE,
            "variant": variant,
            "selection_mode": selection_mode,
            "selection_completed": True,
            "configuration_edge_capable": False,
            "compatible_input_signature": True,
            "system_viable": False,
            "exec_time_policy": EXEC_TIME_POLICY,
            "parent": {"phase": PARENT_PHASE, "variants": []},
            "requested_parent_variants": parent_variants,
            "selected_variants": [],
            "non_edge_parent_variants": non_edge_parent_variants,
            "excluded_parents": excluded_parents,
            "platform": platform,
            "time_scale_factor": float(time_scale_factor),
            "system_limits": {
                "MTI_MS": int(round(mti_ms)),
                "memory_budget_bytes": int(memory_budget_bytes) if memory_budget_bytes is not None else None,
                "max_models": int(max_models) if max_models is not None else None,
                "min_quality_score": float(min_quality_score) if min_quality_score is not None else None,
                "min_precision": float(min_precision) if min_precision is not None else None,
                "min_recall": float(min_recall) if min_recall is not None else None,
                "objective": objective_name,
            },
            "common_input_signature": common_sig,
            "aggregates": {
                "total_models_requested": len(parent_variants),
                "total_models_declared": len(edge_parent_variants),
                "total_models_selected": 0,
                "required_arena_bytes": 0,
                "total_model_size_bytes": 0,
                "model_memory_payload_bytes": 0,
                "model_memory_required_bytes": 0,
                "operators_union": operators_union,
                "unique_windows_count": 0,
                "duplicate_windows_removed": 0,
                "max_exec_time_ms": 0.0,
                "sum_effective_time_ms": 0.0,
                "total_tp": 0,
                "total_tn": 0,
                "total_fp": 0,
                "total_fn": 0,
                "global_precision": None,
                "global_recall": None,
            },
            "memory_check": {
                "source": "f07.metrics_memory.heap_total_ref",
                "plate_available_heap_bytes": int(plate_available_heap_bytes) if plate_available_heap_bytes is not None else None,
                "effective_memory_budget_bytes": int(memory_budget_bytes) if memory_budget_bytes is not None else None,
                "memory_guard_bytes": int(MEMORY_GUARD_BYTES_DEFAULT),
                "arena_global_bytes": 0,
                "models_memory_budget_bytes": None,
                "model_memory_payload_bytes": 0,
                "model_memory_required_bytes": 0,
                "fit_margin_bytes": None,
                "fits": False,
            },
            "selection_report": {
                "solver_status": "NoFeasibleCandidatesAfterFilters",
                "objective": objective_name,
                "reason": "no_feasible_candidates_after_filters",
            },
            "selection_reason": "no_feasible_candidates_after_filters",
            "datasets": {
                "base_evaluation_dataset_csv": None,
                "source_evaluation_datasets_csv": [],
                "unique_windows_csv": str(unique_windows_path),
                "max_rows": int(max_rows) if max_rows is not None else None,
                "full_rows_count": 0,
                "unique_windows_count": 0,
            },
            "models": [],
        }

        out_path = variant_dir / "08_selected_configuration.yaml"
        out_path.write_text(_yaml_dump_no_alias(selected_configuration))
        print(f"[F08] selectconfig OK — {variant}")
        print("[F08] No hay candidatos factibles tras filtros.")
        return

    # Arena global fija sobre candidatos factibles
    required_arena_bytes = max(int(m.get("arena_bytes") or 0) for m in feasible_candidates)
    memory_guard_bytes = int(MEMORY_GUARD_BYTES_DEFAULT)

    effective_memory_budget_bytes = None
    if memory_budget_bytes is not None and plate_available_heap_bytes is not None:
        effective_memory_budget_bytes = min(int(memory_budget_bytes), int(plate_available_heap_bytes))
    elif memory_budget_bytes is not None:
        effective_memory_budget_bytes = int(memory_budget_bytes)
    elif plate_available_heap_bytes is not None:
        effective_memory_budget_bytes = int(plate_available_heap_bytes)

    models_memory_budget_bytes = None
    if effective_memory_budget_bytes is not None:
        models_memory_budget_bytes = int(effective_memory_budget_bytes - required_arena_bytes - memory_guard_bytes)
        if models_memory_budget_bytes < 0:
            write_inviable_selection_result(
                reason="insufficient_memory_budget_for_arena_guard",
                solver_status="NoSolutionBeforeSelection",
                common_sig=common_sig,
                total_models_declared=len(edge_parent_variants),
                operators_union=operators_union,
                all_models=all_edge_models,
                feasible_parent_variants={m["parent_variant"] for m in feasible_candidates},
                plate_available_heap_bytes=plate_available_heap_bytes,
                effective_memory_budget_bytes=effective_memory_budget_bytes,
                extra_selection_report={
                    "required_arena_bytes": int(required_arena_bytes),
                    "memory_guard_bytes": int(memory_guard_bytes),
                    "models_memory_budget_bytes": int(models_memory_budget_bytes),
                },
            )
            print(f"[F08] selectconfig OK — {variant}")
            print("[F08] Presupuesto de memoria insuficiente antes de la selección.")
            return

    # Selección
    if selection_mode == "manual":
        selected_models = list(feasible_candidates)

        if max_models is not None and len(selected_models) > max_models:
            write_inviable_selection_result(
                reason="manual_exceeds_max_models",
                solver_status="ManualConstraintViolation",
                common_sig=common_sig,
                total_models_declared=len(edge_parent_variants),
                operators_union=operators_union,
                all_models=all_edge_models,
                feasible_parent_variants={m["parent_variant"] for m in feasible_candidates},
                plate_available_heap_bytes=plate_available_heap_bytes,
                effective_memory_budget_bytes=effective_memory_budget_bytes,
                extra_selection_report={
                    "selected_count_requested": len(selected_models),
                    "max_models": int(max_models),
                },
            )
            print(f"[F08] selectconfig OK — {variant}")
            print("[F08] Selección manual inviable: supera max_models.")
            return

        total_effective_time_ms = sum(float(m.get("effective_time_ms") or 0.0) for m in selected_models)
        if total_effective_time_ms > float(mti_ms):
            write_inviable_selection_result(
                reason="manual_exceeds_time_budget",
                solver_status="ManualConstraintViolation",
                common_sig=common_sig,
                total_models_declared=len(edge_parent_variants),
                operators_union=operators_union,
                all_models=all_edge_models,
                feasible_parent_variants={m["parent_variant"] for m in feasible_candidates},
                plate_available_heap_bytes=plate_available_heap_bytes,
                effective_memory_budget_bytes=effective_memory_budget_bytes,
                extra_selection_report={
                    "selected_sum_effective_time_ms": float(total_effective_time_ms),
                    "MTI_MS": float(mti_ms),
                },
            )
            print(f"[F08] selectconfig OK — {variant}")
            print("[F08] Selección manual inviable: supera el presupuesto temporal.")
            return

        total_model_size_bytes = sum(int(m.get("model_size_bytes") or 0) for m in selected_models)
        if models_memory_budget_bytes is not None and total_model_size_bytes > models_memory_budget_bytes:
            write_inviable_selection_result(
                reason="manual_exceeds_memory_budget",
                solver_status="ManualConstraintViolation",
                common_sig=common_sig,
                total_models_declared=len(edge_parent_variants),
                operators_union=operators_union,
                all_models=all_edge_models,
                feasible_parent_variants={m["parent_variant"] for m in feasible_candidates},
                plate_available_heap_bytes=plate_available_heap_bytes,
                effective_memory_budget_bytes=effective_memory_budget_bytes,
                extra_selection_report={
                    "selected_total_model_size_bytes": int(total_model_size_bytes),
                    "models_memory_budget_bytes": int(models_memory_budget_bytes),
                },
            )
            print(f"[F08] selectconfig OK — {variant}")
            print("[F08] Selección manual inviable: supera el presupuesto de memoria.")
            return

        selection_report = {
            "selection_mode": selection_mode,
            "objective": "manual_all_feasible",
            "solver_status": "Manual",
            "candidates_considered": len(all_edge_models),
            "candidates_feasible_after_filters": len(feasible_candidates),
            "selected_count": len(selected_models),
        }

    else:
        auto_result = run_auto_selector(
            candidates=feasible_candidates,
            objective_name=objective_name,
            memory_models_budget_bytes=models_memory_budget_bytes,
            mti_ms=float(mti_ms),
            max_models=max_models,
            time_limit_sec=solver_time_limit_sec,
        )

        selected_indices = auto_result.get("selected_indices", [])
        if not selected_indices:
            write_inviable_selection_result(
                reason="no_solution_under_constraints",
                solver_status=str(auto_result.get("solver_status") or "NotSolved"),
                common_sig=common_sig,
                total_models_declared=len(edge_parent_variants),
                operators_union=operators_union,
                all_models=all_edge_models,
                feasible_parent_variants={m["parent_variant"] for m in feasible_candidates},
                plate_available_heap_bytes=plate_available_heap_bytes,
                effective_memory_budget_bytes=effective_memory_budget_bytes,
                extra_selection_report={
                    "objective_value": auto_result.get("objective_value"),
                    "iterations": auto_result.get("iterations"),
                    "lambda_last": auto_result.get("lambda_last"),
                    "gap_last": auto_result.get("gap_last"),
                },
            )
            print(f"[F08] selectconfig OK — {variant}")
            print("[F08] auto_ilp no encontró solución bajo las restricciones activas.")
            return

        selected_models = [feasible_candidates[i] for i in selected_indices]
        selection_report = {
            "selection_mode": selection_mode,
            "objective": auto_result.get("objective_name", objective_name),
            "solver_status": auto_result.get("solver_status"),
            "objective_value": auto_result.get("objective_value"),
            "iterations": auto_result.get("iterations"),
            "lambda_last": auto_result.get("lambda_last"),
            "gap_last": auto_result.get("gap_last"),
            "candidates_considered": len(all_edge_models),
            "candidates_feasible_after_filters": len(feasible_candidates),
            "selected_count": len(selected_models),
        }

    selected_variants = [m["parent_variant"] for m in selected_models]
    selected_variant_set = set(selected_variants)

    # Marcado para CSV
    feasible_parent_variants = {m["parent_variant"] for m in feasible_candidates}
    for m in all_edge_models:
        m["_selected"] = (m["parent_variant"] in selected_variant_set)

    # Cálculos agregados reales
    configuration_edge_capable = (
        len(selected_models) > 0
        and all(bool(m.get("edge_capable", False)) for m in selected_models)
    )
    compatible_input_signature = True

    total_model_size_bytes = sum(int(m.get("model_size_bytes") or 0) for m in selected_models)
    model_memory_payload_bytes = int(required_arena_bytes + total_model_size_bytes)
    model_memory_required_bytes = int(model_memory_payload_bytes + memory_guard_bytes)

    fit_margin_bytes = (
        None if effective_memory_budget_bytes is None
        else int(effective_memory_budget_bytes - model_memory_required_bytes)
    )

    if effective_memory_budget_bytes is not None and fit_margin_bytes is not None and fit_margin_bytes < 0:
        raise RuntimeError(
            "[F08] Configuración no cabe en memoria efectiva: "
            f"efectiva={effective_memory_budget_bytes} B, "
            f"requerida={model_memory_required_bytes} B"
        )

    source_eval_datasets: list[Path] = []
    seen_eval_datasets: set[str] = set()
    for m in selected_models:
        eval_path = Path(str(m["evaluation_dataset_csv"]))
        key = str(eval_path.resolve()) if eval_path.exists() else str(eval_path)
        if key in seen_eval_datasets:
            continue
        seen_eval_datasets.add(key)
        source_eval_datasets.append(eval_path)

    base_eval_dataset = source_eval_datasets[0]
    df_unique, df_full = build_unique_windows_from_datasets(source_eval_datasets, max_rows=max_rows)
    unique_windows_count = int(len(df_unique))
    full_rows_count = int(len(df_full))
    duplicate_windows_removed = int(full_rows_count - unique_windows_count)

    unique_windows_path = variant_dir / "08_unique_windows.csv"
    df_unique.to_csv(unique_windows_path, index=False)

    max_exec_time_ms = max(float(m.get("exec_time_ms") or 0.0) for m in selected_models)
    sum_effective_time_ms = sum(float(m.get("effective_time_ms") or 0.0) for m in selected_models)

    total_tp = sum(int(m.get("tp") or 0) for m in selected_models)
    total_tn = sum(int(m.get("tn") or 0) for m in selected_models)
    total_fp = sum(int(m.get("fp") or 0) for m in selected_models)
    total_fn = sum(int(m.get("fn") or 0) for m in selected_models)

    global_precision = (total_tp / (total_tp + total_fp)) if (total_tp + total_fp) > 0 else None
    global_recall = (total_tp / (total_tp + total_fn)) if (total_tp + total_fn) > 0 else None

    system_viable = bool(configuration_edge_capable)

    write_candidate_summary(
        variant_dir,
        all_edge_models,
        feasible_parent_variants=feasible_parent_variants,
    )

    selection_report["selected_variants"] = selected_variants
    selection_report["excluded_parents"] = excluded_parents
    selection_report["memory"] = {
        "effective_memory_budget_bytes": int(effective_memory_budget_bytes) if effective_memory_budget_bytes is not None else None,
        "arena_global_bytes": int(required_arena_bytes),
        "memory_guard_bytes": int(memory_guard_bytes),
        "models_memory_budget_bytes": int(models_memory_budget_bytes) if models_memory_budget_bytes is not None else None,
        "selected_total_model_size_bytes": int(total_model_size_bytes),
        "selected_model_memory_required_bytes": int(model_memory_required_bytes),
        "fit_margin_bytes": int(fit_margin_bytes) if fit_margin_bytes is not None else None,
    }
    selection_report["timing"] = {
        "MTI_MS": float(mti_ms),
        "selected_sum_effective_time_ms": float(sum_effective_time_ms),
        "selected_max_exec_time_ms": float(max_exec_time_ms),
    }
    selection_report["quality_aggregates"] = {
        "total_tp": int(total_tp),
        "total_tn": int(total_tn),
        "total_fp": int(total_fp),
        "total_fn": int(total_fn),
        "global_precision": None if global_precision is None else float(global_precision),
        "global_recall": None if global_recall is None else float(global_recall),
    }
    write_selection_report(variant_dir, selection_report)

    selected_configuration = {
        "phase": PHASE,
        "variant": variant,
        "selection_mode": selection_mode,
        "selection_completed": True,
        "selection_reason": None,
        "configuration_edge_capable": bool(configuration_edge_capable),
        "compatible_input_signature": bool(compatible_input_signature),
        "system_viable": bool(system_viable),
        "exec_time_policy": EXEC_TIME_POLICY,
        "parent": {
            "phase": PARENT_PHASE,
            "variants": selected_variants,
        },
        "requested_parent_variants": parent_variants,
        "selected_variants": selected_variants,
        "non_edge_parent_variants": non_edge_parent_variants,
        "excluded_parents": excluded_parents,
        "platform": platform,
        "time_scale_factor": float(time_scale_factor),
        "system_limits": {
            "MTI_MS": int(round(mti_ms)),
            "memory_budget_bytes": int(memory_budget_bytes) if memory_budget_bytes is not None else None,
            "plate_available_heap_bytes": int(plate_available_heap_bytes) if plate_available_heap_bytes is not None else None,
            "effective_memory_budget_bytes": int(effective_memory_budget_bytes) if effective_memory_budget_bytes is not None else None,
            "max_models": int(max_models) if max_models is not None else None,
            "min_quality_score": float(min_quality_score) if min_quality_score is not None else None,
            "min_precision": float(min_precision) if min_precision is not None else None,
            "min_recall": float(min_recall) if min_recall is not None else None,
            "objective": objective_name,
        },
        "common_input_signature": {
            "Tu": common_sig["Tu"],
            "OW": common_sig["OW"],
            "LT": common_sig["LT"],
            "PW": common_sig["PW"],
            "input_dtype": common_sig["input_dtype"],
            "output_dtype": common_sig["output_dtype"],
            "input_shape": common_sig["input_shape"],
            "output_shape": common_sig["output_shape"],
            "input_bytes": common_sig["input_bytes"],
            "output_bytes": common_sig["output_bytes"],
            "input_max_len": common_sig["input_max_len"],
            "normalization_mean": common_sig["normalization_mean"],
            "normalization_std": common_sig["normalization_std"],
            "input_quant_scale": common_sig["input_quant_scale"],
            "input_quant_zero_point": common_sig["input_quant_zero_point"],
        },
        "aggregates": {
            "total_models_requested": len(parent_variants),
            "total_models_declared": len(edge_parent_variants),
            "total_models_selected": len(selected_models),
            "required_arena_bytes": int(required_arena_bytes),
            "total_model_size_bytes": int(total_model_size_bytes),
            "model_memory_payload_bytes": int(model_memory_payload_bytes),
            "model_memory_required_bytes": int(model_memory_required_bytes),
            "operators_union": operators_union,
            "unique_windows_count": int(unique_windows_count),
            "duplicate_windows_removed": int(duplicate_windows_removed),
            "max_exec_time_ms": float(max_exec_time_ms),
            "sum_effective_time_ms": float(sum_effective_time_ms),
            "total_tp": int(total_tp),
            "total_tn": int(total_tn),
            "total_fp": int(total_fp),
            "total_fn": int(total_fn),
            "global_precision": None if global_precision is None else float(global_precision),
            "global_recall": None if global_recall is None else float(global_recall),
        },
        "memory_check": {
            "source": "min(memory_budget_bytes, f07.metrics_memory.heap_total_ref) if both available",
            "plate_available_heap_bytes": int(plate_available_heap_bytes) if plate_available_heap_bytes is not None else None,
            "effective_memory_budget_bytes": int(effective_memory_budget_bytes) if effective_memory_budget_bytes is not None else None,
            "memory_guard_bytes": int(memory_guard_bytes),
            "arena_global_bytes": int(required_arena_bytes),
            "models_memory_budget_bytes": int(models_memory_budget_bytes) if models_memory_budget_bytes is not None else None,
            "model_memory_payload_bytes": int(model_memory_payload_bytes),
            "model_memory_required_bytes": int(model_memory_required_bytes),
            "fit_margin_bytes": int(fit_margin_bytes) if fit_margin_bytes is not None else None,
            "fits": (fit_margin_bytes is None or fit_margin_bytes >= 0),
        },
        "selection_report": selection_report,
        "datasets": {
            "base_evaluation_dataset_csv": str(base_eval_dataset),
            "source_evaluation_datasets_csv": [str(p) for p in source_eval_datasets],
            "unique_windows_csv": str(unique_windows_path),
            "max_rows": int(max_rows) if max_rows is not None else None,
            "full_rows_count": int(full_rows_count),
            "unique_windows_count": int(unique_windows_count),
        },
        "models": selected_models,
    }

    out_path = variant_dir / "08_selected_configuration.yaml"
    out_path.write_text(_yaml_dump_no_alias(selected_configuration))

    print(f"[F08] selectconfig OK — {variant}")
    print(f"[F08] selection_mode: {selection_mode}")
    print(f"[F08] objective: {objective_name}")
    print(f"[F08] Platform: {platform}")
    print(f"[F08] Parent variants requested: {len(parent_variants)}")
    print(f"[F08] Parents edge_capable declarados: {len(edge_parent_variants)}")
    print(f"[F08] Candidates feasible after filters: {len(feasible_candidates)}")
    print(f"[F08] Models selected: {len(selected_models)}")
    print(f"[F08] Parents excluded: {len(excluded_parents)}")
    print(f"[F08] Unique windows: {unique_windows_count}")
    print(f"[F08] Duplicate windows removed: {duplicate_windows_removed}")
    print(f"[F08] Required arena (global): {required_arena_bytes} bytes")
    print(f"[F08] Total model size: {total_model_size_bytes} bytes")
    print(f"[F08] Model memory payload (arena+models): {model_memory_payload_bytes} bytes")
    print(f"[F08] Memory guard: {memory_guard_bytes} bytes")
    print(f"[F08] Model memory required: {model_memory_required_bytes} bytes")
    if effective_memory_budget_bytes is not None:
        print(f"[F08] Effective memory budget: {effective_memory_budget_bytes} bytes")
        print(f"[F08] Memory fit margin: {fit_margin_bytes} bytes")
    print(f"[F08] Sum effective time: {sum_effective_time_ms} ms")
    print(f"[F08] Max exec time: {max_exec_time_ms} ms")
    print(f"[F08] Global precision: {global_precision}")
    print(f"[F08] Global recall: {global_recall}")
    print(f"[F08] Operators union: {len(operators_union)}")


if __name__ == "__main__":
    main()
