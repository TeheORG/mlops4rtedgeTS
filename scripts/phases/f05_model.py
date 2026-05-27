#!/usr/bin/env python3
"""
F05 — MODELING

Lee:
  - params.yaml de f05_modeling (incluye model_family, automl, search_space, evaluation, training, etc.)
  - outputs.yaml del parent f04_targets (dataset etiquetado, prediction_name, Tu/OW/LT/PW…)

Entrena un modelo binario con AutoML simple (random search sobre search_space),
selecciona el mejor por recall en validación, calcula métricas en test,
calcula umbral óptimo (por F1), guarda el modelo y genera outputs.yaml
conforme a traceability_schema.yaml.

Este código está diseñado para:
  - encajar con el patrón de F01–F04,
  - dejar todo listo para F06 (cuantización y edge unit),
  - mantener MLflow en Makefile (solo se deja bloque mlflow_registration).
"""

import argparse
import json
import time
from datetime import datetime, timezone
import shutil
import random
import hashlib
from collections import Counter
from html import escape

import numpy as np
import pandas as pd
import tensorflow as tf
import pyarrow as pa
import pyarrow.parquet as pq
from sklearn.metrics import (
    confusion_matrix,
    precision_score,
    recall_score,
    f1_score,
    precision_recall_curve,
)
from sklearn.model_selection import train_test_split
import yaml

from scripts.core.artifacts import (
    PROJECT_ROOT,
    get_variant_dir,
    save_outputs_yaml,
    sha256_of_file,
)
from scripts.core.phase_io import load_phase_outputs, load_variant_params
from scripts.core.traceability import validate_outputs

# ============================================================
# CONSTANTES
# ============================================================

PHASE = "f05_modeling"
PARENT_PHASE = "f04_targets"
FAST_MAX_MAJORITY_SAMPLES = 20_000
INPUT_SEQUENCE_COLUMN = "OW_values"

# ── Análisis opcionales (desactivar para acelerar ejecución) ──────────────────
ENABLE_EXACT_DUPLICATE_ANALYSIS    = False   # set operations, rápido
ENABLE_UNORDERED_DUPLICATE_ANALYSIS = False  # set operations, rápido
ENABLE_NEAR_DUPLICATE_ANALYSIS     = False  # O(n²) Jaccard, muy lento en datasets grandes


def build_adam_optimizer(learning_rate: float):
    # Ruta única para todos los OS: evita divergencias por elegir optimizadores distintos.
    return tf.keras.optimizers.Adam(learning_rate=learning_rate)


def configure_reproducibility(seed: int, strict_cross_os: bool = False):
    """Configura semillas globales y, opcionalmente, modo determinista estricto.

    strict_cross_os=True intenta minimizar diferencias entre SOs:
      - activa operaciones deterministas de TensorFlow cuando están disponibles,
      - fija paralelismo a 1 hilo intra/inter-op para reducir no determinismo.
    """
    random.seed(seed)
    np.random.seed(seed)
    tf.keras.utils.set_random_seed(seed)

    if strict_cross_os:
        try:
            tf.config.experimental.enable_op_determinism()
        except Exception as exc:
            print(f"[WARN] No se pudo activar enable_op_determinism(): {exc}")

        try:
            tf.config.threading.set_intra_op_parallelism_threads(1)
            tf.config.threading.set_inter_op_parallelism_threads(1)
        except Exception as exc:
            print(f"[WARN] No se pudo fijar threading determinista: {exc}")


# ============================================================
# HELPERS DE MODELADO
# ============================================================

def stable_seq_hash(seq) -> str:
    arr = np.asarray(seq, dtype=np.float64)
    if arr.size == 0:
        return "EMPTY"
    return hashlib.md5(arr.tobytes()).hexdigest()


def find_observation_hash_column(df: pd.DataFrame) -> str | None:
    preferred_cols = [
        "OW_hash",
        "ow_hash",
        "hash_window",
        "window_hash",
        "observation_window_hash",
        "window_observation_hash",
    ]
    for col in preferred_cols:
        if col in df.columns:
            return col

    for col in df.columns:
        col_norm = str(col).strip().lower()
        if "hash" in col_norm and ("ow" in col_norm or "window" in col_norm):
            return col

    return None


def ensure_observation_hash_series(df: pd.DataFrame) -> tuple[pd.Series, str]:
    hash_col = find_observation_hash_column(df)
    if hash_col is not None:
        hash_series = df[hash_col].astype(str).fillna("MISSING_HASH")
        return hash_series.reset_index(drop=True), str(hash_col)

    if "OW_values" not in df.columns:
        raise RuntimeError(
            "No se encontró columna hash de observación (OW_hash/hash_window/...) "
            "ni la columna OW_values para calcularla."
        )

    hash_series = df["OW_values"].apply(stable_seq_hash).astype(str)
    return hash_series.reset_index(drop=True), "computed_from_OW_values"


def deduplicate_labeled_windows(df: pd.DataFrame, mode: str):
    """
    mode:
      - none: no deduplicar
      - all: deduplicar todas las ventanas por OW_values
      - neg_only: deduplicar solo las negativas
      - auto: usa neg_only por defecto; si hay suficientes positivos únicos,
              puede pasar a all
    """
    if mode == "none":
        stats = {
            "dedup_mode_effective": "none",
            "n_before": int(len(df)),
            "n_after": int(len(df)),
            "n_removed": 0,
            "removed_ratio": 0.0,
            "n_ambiguous_sequences_removed": 0,
            "n_ambiguous_rows_removed": 0,
            "n_majority_resolved_sequences": 0,
        }
        return df.copy(), stats

    work = df.copy()
    work["_ow_hash"] = work["OW_values"].apply(stable_seq_hash)

    n_before = int(len(work))

    """
    Ambiguity handling:
    If the same OW_values sequence appears with conflicting labels,
    this indicates instability or noise in the target.

    We apply a strict consistency threshold (>= 0.995):
    - Highly consistent sequences → resolved via majority voting
    - Low consistency sequences → removed entirely

    This avoids corrupting the model with contradictory supervision.
    """
    label_stats = (
        work.groupby("_ow_hash")["label"]
        .agg(n_total="size", n_pos="sum")
    )
    label_stats["n_pos"] = label_stats["n_pos"].astype(int)
    label_stats["n_neg"] = (label_stats["n_total"] - label_stats["n_pos"]).astype(int)
    label_stats["consistency"] = (
        label_stats[["n_pos", "n_neg"]].max(axis=1) / label_stats["n_total"]
    )
    label_stats["majority_label"] = (label_stats["n_pos"] >= label_stats["n_neg"]).astype(int)

    consistent_mask = label_stats["consistency"] >= 0.995
    conflicting_mask = (label_stats["n_pos"] > 0) & (label_stats["n_neg"] > 0)

    ambiguous_hashes = label_stats.index[~consistent_mask]
    n_ambiguous_sequences_removed = int((~consistent_mask).sum())
    n_ambiguous_rows_removed = int(
        label_stats.loc[~consistent_mask, "n_total"].sum()
    )
    n_majority_resolved_sequences = int((consistent_mask & conflicting_mask).sum())

    # Majority voting is only safe for highly consistent hashes; weaker agreement means
    # the same observation window has contradictory supervision and should not train.
    majority_label_by_hash = label_stats.loc[consistent_mask, "majority_label"]
    work = work[~work["_ow_hash"].isin(ambiguous_hashes)].copy()
    work["label"] = work["_ow_hash"].map(majority_label_by_hash).astype(int)

    if mode == "all":
        deduped = work.drop_duplicates(subset=["_ow_hash"], keep="first").copy()
        effective = "all"

    elif mode == "neg_only":
        pos = work[work["label"] == 1].copy()
        neg = work[work["label"] == 0].copy()
        neg = neg.drop_duplicates(subset=["_ow_hash"], keep="first")
        deduped = pd.concat([pos, neg], axis=0).copy()
        effective = "neg_only"

    elif mode == "auto":
        pos = work[work["label"] == 1].copy()
        neg = work[work["label"] == 0].copy()

        n_pos = len(pos)
        n_pos_unique = pos["_ow_hash"].nunique()

        # Heurística simple: si hay muy pocos positivos o demasiados duplicados positivos,
        # no tocar positivos y deduplicar solo negativos.
        if n_pos < 50 or n_pos_unique < max(10, int(0.5 * n_pos)):
            neg = neg.drop_duplicates(subset=["_ow_hash"], keep="first")
            deduped = pd.concat([pos, neg], axis=0).copy()
            effective = "neg_only"
        else:
            deduped = work.drop_duplicates(subset=["_ow_hash"], keep="first").copy()
            effective = "all"
    else:
        raise ValueError(f"deduplication_mode no soportado: {mode}")

    deduped = deduped.drop(columns=["_ow_hash"]).reset_index(drop=True)

    n_after = int(len(deduped))
    n_removed = n_before - n_after
    removed_ratio = float(n_removed / n_before) if n_before else 0.0

    stats = {
        "dedup_mode_effective": effective,
        "n_before": n_before,
        "n_after": n_after,
        "n_removed": n_removed,
        "removed_ratio": removed_ratio,
        "n_ambiguous_sequences_removed": n_ambiguous_sequences_removed,
        "n_ambiguous_rows_removed": n_ambiguous_rows_removed,
        "n_majority_resolved_sequences": n_majority_resolved_sequences,
    }
    return deduped, stats



def compute_class_weights(y):
    pos = int(np.sum(y == 1))
    neg = int(np.sum(y == 0))
    if pos == 0:
        return None
    return {0: 1.0, 1: float(neg / pos)}


def convert_to_native_types(obj):
    if isinstance(obj, dict):
        return {k: convert_to_native_types(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_to_native_types(item) for item in obj]
    if isinstance(obj, (np.integer, np.int32, np.int64)):
        return int(obj)
    if isinstance(obj, (np.floating, np.float32, np.float64)):
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def split_dataset_indices(y, eval_cfg: dict):
    split = eval_cfg.get("split", {})
    train_ratio = float(split.get("train", 0.7))
    val_ratio = float(split.get("val", 0.15))
    test_ratio = float(split.get("test", 0.15))

    if not np.isclose(train_ratio + val_ratio + test_ratio, 1.0, atol=1e-6):
        raise ValueError(
            f"Las proporciones train/val/test no suman 1: "
            f"{train_ratio} + {val_ratio} + {test_ratio}"
        )

    indices = np.arange(len(y), dtype=np.int64)
    idx_temp, idx_test, y_temp, _ = train_test_split(
        indices, y, test_size=test_ratio, stratify=y, random_state=42
    )

    tv_total = train_ratio + val_ratio
    val_rel = val_ratio / tv_total if tv_total > 0 else 0.0

    idx_train, idx_val, _, _ = train_test_split(
        idx_temp, y_temp, test_size=val_rel, stratify=y_temp, random_state=43
    )

    return idx_train, idx_val, idx_test


def apply_rare_events_to_train_indices(
    y,
    idx_train: np.ndarray,
    max_majority_samples: int | None,
    random_state: int = 123,
) -> tuple[np.ndarray, int]:
    max_maj = FAST_MAX_MAJORITY_SAMPLES if max_majority_samples is None else int(max_majority_samples)
    max_maj = min(max_maj, FAST_MAX_MAJORITY_SAMPLES)

    y_train = y[idx_train]
    pos_idx = idx_train[y_train == 1]
    neg_idx = idx_train[y_train == 0]

    rng = np.random.default_rng(random_state)
    if len(neg_idx) > max_maj:
        neg_idx = rng.choice(neg_idx, size=max_maj, replace=False)

    sampled = np.concatenate([pos_idx, neg_idx]).astype(np.int64)
    rng.shuffle(sampled)
    return sampled, int(max_maj)


def sample_rare_events_full_indices(
    y,
    max_majority_samples: int | None,
    random_state: int = 123,
) -> tuple[np.ndarray, int]:
    max_maj = FAST_MAX_MAJORITY_SAMPLES if max_majority_samples is None else int(max_majority_samples)
    max_maj = min(max_maj, FAST_MAX_MAJORITY_SAMPLES)

    indices = np.arange(len(y), dtype=np.int64)
    pos_idx = indices[y == 1]
    neg_idx = indices[y == 0]

    rng = np.random.default_rng(random_state)
    if len(neg_idx) > max_maj:
        neg_idx = rng.choice(neg_idx, size=max_maj, replace=False)

    sampled = np.concatenate([pos_idx, neg_idx]).astype(np.int64)
    rng.shuffle(sampled)
    return sampled, int(max_maj)


def split_vectorized_dataset(X, y, eval_cfg: dict):
    idx_train, idx_val, idx_test = split_dataset_indices(y, eval_cfg)
    X_train = X[idx_train]
    y_train = y[idx_train]
    X_val = X[idx_val]
    y_val = y[idx_val]
    X_test = X[idx_test]
    y_test = y[idx_test]
    return X_train, y_train, X_val, y_val, X_test, y_test



def build_hash_leakage_report(
    observation_hashes: pd.Series,
    labels: pd.Series,
    split_indices: dict[str, np.ndarray],
) -> dict:
    split_hashes_unique: dict[str, set[str]] = {}
    split_hashes_counts: dict[str, pd.Series] = {}
    split_hash_label_counts: dict[str, pd.DataFrame] = {}
    split_label_summary: dict[str, dict[str, int]] = {}

    for split_name, idx in split_indices.items():
        cur_hashes = observation_hashes.iloc[idx].astype(str).reset_index(drop=True)
        cur_labels = labels.iloc[idx].astype("int32").reset_index(drop=True)
        split_hashes_unique[split_name] = set(cur_hashes.tolist())
        split_hashes_counts[split_name] = cur_hashes.value_counts()
        hash_label_counts = (
            pd.DataFrame({"hash": cur_hashes, "label": cur_labels})
            .groupby(["hash", "label"])
            .size()
            .unstack(fill_value=0)
        )
        split_hash_label_counts[split_name] = hash_label_counts

        pos_col = hash_label_counts[1] if 1 in hash_label_counts.columns else pd.Series(0, index=hash_label_counts.index)
        neg_col = hash_label_counts[0] if 0 in hash_label_counts.columns else pd.Series(0, index=hash_label_counts.index)
        split_label_summary[split_name] = {
            "n_hash_negative": int(((neg_col > 0) & (pos_col == 0)).sum()),
            "n_hash_positive": int(((pos_col > 0) & (neg_col == 0)).sum()),
            "n_hash_mixed_labels": int(((pos_col > 0) & (neg_col > 0)).sum()),
        }

    train_hashes = split_hashes_unique["train"]
    val_hashes = split_hashes_unique["val"]
    test_hashes = split_hashes_unique["test"]

    train_val = train_hashes & val_hashes
    train_test = train_hashes & test_hashes
    val_test = val_hashes & test_hashes
    all_three = train_hashes & val_hashes & test_hashes

    split_sizes = {
        "train": len(train_hashes),
        "val": len(val_hashes),
        "test": len(test_hashes),
    }

    def pct(shared: int, base: int) -> float:
        return float(shared / base) if base > 0 else 0.0

    intersections = {
        "train_val": {
            "count": int(len(train_val)),
            "pct_of_train": pct(len(train_val), split_sizes["train"]),
            "pct_of_val": pct(len(train_val), split_sizes["val"]),
        },
        "train_test": {
            "count": int(len(train_test)),
            "pct_of_train": pct(len(train_test), split_sizes["train"]),
            "pct_of_test": pct(len(train_test), split_sizes["test"]),
        },
        "val_test": {
            "count": int(len(val_test)),
            "pct_of_val": pct(len(val_test), split_sizes["val"]),
            "pct_of_test": pct(len(val_test), split_sizes["test"]),
        },
        "all_three": {
            "count": int(len(all_three)),
            "pct_of_train": pct(len(all_three), split_sizes["train"]),
            "pct_of_val": pct(len(all_three), split_sizes["val"]),
            "pct_of_test": pct(len(all_three), split_sizes["test"]),
        },
    }

    summary_rows = [
        {
            "pair": "train_val",
            "shared_hashes": intersections["train_val"]["count"],
            "pct_of_left": intersections["train_val"]["pct_of_train"],
            "pct_of_right": intersections["train_val"]["pct_of_val"],
            "left_split": "train",
            "right_split": "val",
        },
        {
            "pair": "train_test",
            "shared_hashes": intersections["train_test"]["count"],
            "pct_of_left": intersections["train_test"]["pct_of_train"],
            "pct_of_right": intersections["train_test"]["pct_of_test"],
            "left_split": "train",
            "right_split": "test",
        },
        {
            "pair": "val_test",
            "shared_hashes": intersections["val_test"]["count"],
            "pct_of_left": intersections["val_test"]["pct_of_val"],
            "pct_of_right": intersections["val_test"]["pct_of_test"],
            "left_split": "val",
            "right_split": "test",
        },
        {
            "pair": "all_three",
            "shared_hashes": intersections["all_three"]["count"],
            "pct_of_left": intersections["all_three"]["pct_of_train"],
            "pct_of_right": intersections["all_three"]["pct_of_test"],
            "left_split": "train",
            "right_split": "test",
        },
    ]

    shared_union = sorted(train_val | train_test | val_test)
    top_shared_rows = []
    for hash_value in shared_union[:]:
        train_count = int(split_hashes_counts["train"].get(hash_value, 0))
        val_count = int(split_hashes_counts["val"].get(hash_value, 0))
        test_count = int(split_hashes_counts["test"].get(hash_value, 0))
        train_neg_count = int(split_hash_label_counts["train"].get(0, pd.Series(dtype=int)).get(hash_value, 0))
        train_pos_count = int(split_hash_label_counts["train"].get(1, pd.Series(dtype=int)).get(hash_value, 0))
        val_neg_count = int(split_hash_label_counts["val"].get(0, pd.Series(dtype=int)).get(hash_value, 0))
        val_pos_count = int(split_hash_label_counts["val"].get(1, pd.Series(dtype=int)).get(hash_value, 0))
        test_neg_count = int(split_hash_label_counts["test"].get(0, pd.Series(dtype=int)).get(hash_value, 0))
        test_pos_count = int(split_hash_label_counts["test"].get(1, pd.Series(dtype=int)).get(hash_value, 0))
        total_count = train_count + val_count + test_count
        n_splits_present = int(sum(v > 0 for v in [train_count, val_count, test_count]))
        total_neg_count = train_neg_count + val_neg_count + test_neg_count
        total_pos_count = train_pos_count + val_pos_count + test_pos_count
        if total_pos_count > 0 and total_neg_count == 0:
            label_profile = "positive"
        elif total_neg_count > 0 and total_pos_count == 0:
            label_profile = "negative"
        else:
            label_profile = "mixed"
        top_shared_rows.append(
            {
                "hash": hash_value,
                "label_profile": label_profile,
                "train_count": train_count,
                "train_neg_count": train_neg_count,
                "train_pos_count": train_pos_count,
                "val_count": val_count,
                "val_neg_count": val_neg_count,
                "val_pos_count": val_pos_count,
                "test_count": test_count,
                "test_neg_count": test_neg_count,
                "test_pos_count": test_pos_count,
                "total_neg_count": total_neg_count,
                "total_pos_count": total_pos_count,
                "total_count": total_count,
                "n_splits_present": n_splits_present,
            }
        )

    top_shared_rows = sorted(
        top_shared_rows,
        key=lambda row: (
            -row["n_splits_present"],
            -row["total_count"],
            row["hash"],
        ),
    )[:20]

    max_overlap_pct = max(
        intersections["train_val"]["pct_of_train"],
        intersections["train_val"]["pct_of_val"],
        intersections["train_test"]["pct_of_train"],
        intersections["train_test"]["pct_of_test"],
        intersections["val_test"]["pct_of_val"],
        intersections["val_test"]["pct_of_test"],
        intersections["all_three"]["pct_of_train"],
        intersections["all_three"]["pct_of_val"],
        intersections["all_three"]["pct_of_test"],
    )
    possible_leakage = bool(
        intersections["train_val"]["count"] > 0
        or intersections["train_test"]["count"] > 0
        or intersections["val_test"]["count"] > 0
    )
    high_leakage_warning = bool(
        intersections["all_three"]["count"] > 0
        or max_overlap_pct >= 0.01
    )

    return {
        "split_sizes_unique_hashes": {
            "n_hash_train": int(split_sizes["train"]),
            "n_hash_val": int(split_sizes["val"]),
            "n_hash_test": int(split_sizes["test"]),
        },
        "split_label_summary": split_label_summary,
        "intersections": intersections,
        "summary_rows": summary_rows,
        "top_shared_hashes": top_shared_rows,
        "possible_leakage": possible_leakage,
        "high_leakage_warning": high_leakage_warning,
        "max_overlap_pct": float(max_overlap_pct),
    }


def print_hash_leakage_report(leakage_report: dict, hash_source: str) -> None:
    sizes = leakage_report["split_sizes_unique_hashes"]
    split_label_summary = leakage_report.get("split_label_summary", {})
    print("[INFO] Leakage audit por hashes de ventana")
    print(f"[INFO] hash_source={hash_source}")
    print(
        f"[INFO] unique_hashes train={sizes['n_hash_train']} | "
        f"val={sizes['n_hash_val']} | test={sizes['n_hash_test']}"
    )

    if split_label_summary:
        label_df = pd.DataFrame.from_dict(split_label_summary, orient="index").reset_index()
        label_df = label_df.rename(columns={"index": "split"})
        print("[INFO] Resumen de hashes por label:")
        print(label_df.to_string(index=False))

    summary_df = pd.DataFrame(leakage_report["summary_rows"]).copy()
    if not summary_df.empty:
        summary_df["pct_of_left"] = summary_df["pct_of_left"].map(lambda v: f"{100.0 * float(v):.2f}%")
        summary_df["pct_of_right"] = summary_df["pct_of_right"].map(lambda v: f"{100.0 * float(v):.2f}%")
        summary_df = summary_df.rename(
            columns={
                "pair": "pair",
                "shared_hashes": "shared_hashes",
                "pct_of_left": "% left",
                "pct_of_right": "% right",
                "left_split": "left_split",
                "right_split": "right_split",
            }
        )
        print(summary_df.to_string(index=False))

    top_shared = leakage_report.get("top_shared_hashes", [])
    if top_shared:
        print("[INFO] Top 20 hashes compartidos:")
        print(pd.DataFrame(top_shared).to_string(index=False))

    if leakage_report.get("high_leakage_warning", False):
        print("⚠️ Posible leakage entre splits")
    elif leakage_report.get("possible_leakage", False):
        print("[WARN] Hay hashes compartidos entre splits, aunque el solape es bajo.")
    else:
        print("[INFO] No se detectó solape de hashes entre train/val/test.")

def canonicalize_events_sequence(seq) -> tuple[float, ...]:
    if isinstance(seq, np.ndarray):
        return tuple(float(v) for v in seq.tolist())
    if isinstance(seq, (list, tuple)):
        return tuple(float(v) for v in seq)
    if pd.isna(seq):
        return tuple()
    return tuple(float(v) for v in list(seq))


def build_unordered_key(seq: tuple[int, ...]) -> str:
    counter = Counter(seq)
    return "|".join(f"{event}:{counter[event]}" for event in sorted(counter))


def build_sequence_preview(seq: tuple[int, ...], max_items: int = 12) -> str:
    if not seq:
        return "[]"
    values = [str(v) for v in seq[:max_items]]
    suffix = ", ..." if len(seq) > max_items else ""
    return "[" + ", ".join(values) + suffix + "]"


def label_profile_from_counts(neg_count: int, pos_count: int) -> str:
    if pos_count > 0 and neg_count == 0:
        return "only_positive"
    if neg_count > 0 and pos_count == 0:
        return "only_negative"
    return "mixed_labels"


def pair_name(left_split: str, right_split: str) -> str:
    return f"{left_split}_{right_split}"


def pct_shared(shared: int, base: int) -> float:
    return float(shared / base) if base > 0 else 0.0


def summarize_key_labels(
    split_key_label_counts: dict[str, pd.DataFrame],
    split_name: str,
    key_value: str,
) -> tuple[int, int]:
    counts_df = split_key_label_counts[split_name]
    neg_count = int(counts_df.get(0, pd.Series(dtype=int)).get(key_value, 0))
    pos_count = int(counts_df.get(1, pd.Series(dtype=int)).get(key_value, 0))
    return neg_count, pos_count


def summarize_intersection_label_profiles(
    shared_keys: set[str],
    split_key_label_counts: dict[str, pd.DataFrame],
    involved_splits: list[str],
) -> dict[str, int]:
    counts = {
        "only_negative": 0,
        "only_positive": 0,
        "mixed_labels": 0,
    }
    for key_value in shared_keys:
        total_neg = 0
        total_pos = 0
        for split_name in involved_splits:
            neg_count, pos_count = summarize_key_labels(split_key_label_counts, split_name, key_value)
            total_neg += neg_count
            total_pos += pos_count
        counts[label_profile_from_counts(total_neg, total_pos)] += 1
    return counts


def build_pair_intersection_report(
    left_split: str,
    right_split: str,
    split_keys_unique: dict[str, set[str]],
    split_key_label_counts: dict[str, pd.DataFrame],
) -> dict:
    shared_keys = split_keys_unique[left_split] & split_keys_unique[right_split]
    label_breakdown = summarize_intersection_label_profiles(
        shared_keys,
        split_key_label_counts,
        [left_split, right_split],
    )
    return {
        "shared_keys_count": int(len(shared_keys)),
        "shared_keys": sorted(shared_keys),
        "pct_of_left": pct_shared(len(shared_keys), len(split_keys_unique[left_split])),
        "pct_of_right": pct_shared(len(shared_keys), len(split_keys_unique[right_split])),
        "label_breakdown": label_breakdown,
        "left_split": left_split,
        "right_split": right_split,
    }


def build_triple_intersection_report(
    split_keys_unique: dict[str, set[str]],
    split_key_label_counts: dict[str, pd.DataFrame],
) -> dict:
    shared_keys = (
        split_keys_unique["train"]
        & split_keys_unique["val"]
        & split_keys_unique["test"]
    )
    label_breakdown = summarize_intersection_label_profiles(
        shared_keys,
        split_key_label_counts,
        ["train", "val", "test"],
    )
    return {
        "shared_keys_count": int(len(shared_keys)),
        "shared_keys": sorted(shared_keys),
        "pct_of_train": pct_shared(len(shared_keys), len(split_keys_unique["train"])),
        "pct_of_val": pct_shared(len(shared_keys), len(split_keys_unique["val"])),
        "pct_of_test": pct_shared(len(shared_keys), len(split_keys_unique["test"])),
        "label_breakdown": label_breakdown,
    }


def build_key_overlap_section(
    metadata_df: pd.DataFrame,
    key_col: str,
    split_names: list[str],
    key_name: str,
) -> dict:
    split_keys_unique: dict[str, set[str]] = {}
    split_keys_counts: dict[str, pd.Series] = {}
    split_key_label_counts: dict[str, pd.DataFrame] = {}
    split_label_summary: dict[str, dict[str, int]] = {}

    for split_name in split_names:
        cur = metadata_df[metadata_df["split"] == split_name].copy()
        cur_keys = cur[key_col].astype(str).reset_index(drop=True)
        cur_labels = cur["label"].astype("int32").reset_index(drop=True)
        split_keys_unique[split_name] = set(cur_keys.tolist())
        split_keys_counts[split_name] = cur_keys.value_counts()
        key_label_counts = (
            pd.DataFrame({"key": cur_keys, "label": cur_labels})
            .groupby(["key", "label"])
            .size()
            .unstack(fill_value=0)
        )
        split_key_label_counts[split_name] = key_label_counts
        pos_col = key_label_counts[1] if 1 in key_label_counts.columns else pd.Series(0, index=key_label_counts.index)
        neg_col = key_label_counts[0] if 0 in key_label_counts.columns else pd.Series(0, index=key_label_counts.index)
        split_label_summary[split_name] = {
            "only_negative": int(((neg_col > 0) & (pos_col == 0)).sum()),
            "only_positive": int(((pos_col > 0) & (neg_col == 0)).sum()),
            "mixed_labels": int(((pos_col > 0) & (neg_col > 0)).sum()),
        }

    pair_reports = {}
    summary_rows = []
    for left_split, right_split in [("train", "val"), ("train", "test"), ("val", "test")]:
        report = build_pair_intersection_report(
            left_split,
            right_split,
            split_keys_unique,
            split_key_label_counts,
        )
        pair_reports[pair_name(left_split, right_split)] = report
        summary_rows.append(
            {
                "pair": pair_name(left_split, right_split),
                "shared_keys": report["shared_keys_count"],
                "pct_of_left": report["pct_of_left"],
                "pct_of_right": report["pct_of_right"],
                "left_split": left_split,
                "right_split": right_split,
                **report["label_breakdown"],
            }
        )

    triple_report = build_triple_intersection_report(split_keys_unique, split_key_label_counts)
    summary_rows.append(
        {
            "pair": "train_val_test",
            "shared_keys": triple_report["shared_keys_count"],
            "pct_of_left": triple_report["pct_of_train"],
            "pct_of_right": triple_report["pct_of_test"],
            "left_split": "train",
            "right_split": "test",
            **triple_report["label_breakdown"],
        }
    )

    shared_union = sorted(
        set(
            pair_reports["train_val"]["shared_keys"]
            + pair_reports["train_test"]["shared_keys"]
            + pair_reports["val_test"]["shared_keys"]
        )
    )
    top_shared_rows = []
    for key_value in shared_union:
        train_count = int(split_keys_counts["train"].get(key_value, 0))
        val_count = int(split_keys_counts["val"].get(key_value, 0))
        test_count = int(split_keys_counts["test"].get(key_value, 0))
        train_neg_count, train_pos_count = summarize_key_labels(split_key_label_counts, "train", key_value)
        val_neg_count, val_pos_count = summarize_key_labels(split_key_label_counts, "val", key_value)
        test_neg_count, test_pos_count = summarize_key_labels(split_key_label_counts, "test", key_value)
        total_neg_count = train_neg_count + val_neg_count + test_neg_count
        total_pos_count = train_pos_count + val_pos_count + test_pos_count
        preview_values = metadata_df.loc[metadata_df[key_col] == key_value, "events_preview"]
        example_preview = preview_values.iloc[0] if not preview_values.empty else ""
        top_shared_rows.append(
            {
                "key": key_value,
                "key_type": key_name,
                "label_profile": label_profile_from_counts(total_neg_count, total_pos_count),
                "train_count": train_count,
                "train_neg_count": train_neg_count,
                "train_pos_count": train_pos_count,
                "val_count": val_count,
                "val_neg_count": val_neg_count,
                "val_pos_count": val_pos_count,
                "test_count": test_count,
                "test_neg_count": test_neg_count,
                "test_pos_count": test_pos_count,
                "total_count": train_count + val_count + test_count,
                "n_splits_present": int(sum(v > 0 for v in [train_count, val_count, test_count])),
                "events_preview": example_preview,
            }
        )

    top_shared_rows = sorted(
        top_shared_rows,
        key=lambda row: (-row["n_splits_present"], -row["total_count"], row["key"]),
    )[:20]

    max_overlap_pct = max(
        pair_reports["train_val"]["pct_of_left"],
        pair_reports["train_val"]["pct_of_right"],
        pair_reports["train_test"]["pct_of_left"],
        pair_reports["train_test"]["pct_of_right"],
        pair_reports["val_test"]["pct_of_left"],
        pair_reports["val_test"]["pct_of_right"],
        triple_report["pct_of_train"],
        triple_report["pct_of_val"],
        triple_report["pct_of_test"],
    )

    return {
        "key_name": key_name,
        "split_sizes_unique_keys": {
            f"n_{key_name}_train": int(len(split_keys_unique["train"])),
            f"n_{key_name}_val": int(len(split_keys_unique["val"])),
            f"n_{key_name}_test": int(len(split_keys_unique["test"])),
        },
        "split_label_summary": split_label_summary,
        "pair_intersections": pair_reports,
        "triple_intersection": triple_report,
        "summary_rows": summary_rows,
        "top_shared_keys": top_shared_rows,
        "possible_leakage": bool(any(report["shared_keys_count"] > 0 for report in pair_reports.values())),
        "high_leakage_warning": bool(
            triple_report["shared_keys_count"] > 0 or max_overlap_pct >= 0.01
        ),
        "max_overlap_pct": float(max_overlap_pct),
    }


def multiset_jaccard_similarity(counter_a: Counter, counter_b: Counter) -> float:
    keys = set(counter_a) | set(counter_b)
    if not keys:
        return 1.0
    intersection = sum(min(counter_a.get(key, 0), counter_b.get(key, 0)) for key in keys)
    union = sum(max(counter_a.get(key, 0), counter_b.get(key, 0)) for key in keys)
    return float(intersection / union) if union else 0.0


def build_near_duplicate_section(
    metadata_df: pd.DataFrame,
    threshold: float = 0.80,
    top_k_examples: int = 20,
) -> dict:
    unique_df = (
        metadata_df[
            [
                "split",
                "label",
                "exact_key",
                "unordered_key",
                "seq_len",
                "events_counter",
                "events_preview",
            ]
        ]
        .drop_duplicates(subset=["split", "exact_key", "label"])
        .reset_index(drop=True)
    )

    near_pairs = []
    pair_summaries = {}
    for left_split, right_split in [("train", "val"), ("train", "test"), ("val", "test")]:
        left_df = unique_df[unique_df["split"] == left_split].reset_index(drop=True)
        right_df = unique_df[unique_df["split"] == right_split].reset_index(drop=True)
        candidate_pairs = []

        for seq_len, left_group in left_df.groupby("seq_len"):
            right_group = right_df[right_df["seq_len"] == seq_len]
            if right_group.empty:
                continue
            left_records = left_group.to_dict("records")
            right_records = right_group.to_dict("records")
            for left_row in left_records:
                for right_row in right_records:
                    if left_row["unordered_key"] == right_row["unordered_key"]:
                        continue
                    similarity = multiset_jaccard_similarity(
                        left_row["events_counter"],
                        right_row["events_counter"],
                    )
                    if similarity < threshold:
                        continue
                    candidate_pairs.append(
                        {
                            "left_split": left_split,
                            "right_split": right_split,
                            "left_label": int(left_row["label"]),
                            "right_label": int(right_row["label"]),
                            "label_profile": (
                                "only_positive"
                                if int(left_row["label"]) == 1 and int(right_row["label"]) == 1
                                else "only_negative"
                                if int(left_row["label"]) == 0 and int(right_row["label"]) == 0
                                else "mixed_labels"
                            ),
                            "similarity_score": float(similarity),
                            "seq_len": int(seq_len),
                            "left_exact_key": left_row["exact_key"],
                            "right_exact_key": right_row["exact_key"],
                            "left_preview": left_row["events_preview"],
                            "right_preview": right_row["events_preview"],
                        }
                    )

        candidate_pairs = sorted(
            candidate_pairs,
            key=lambda row: (-row["similarity_score"], row["left_exact_key"], row["right_exact_key"]),
        )
        pair_key = pair_name(left_split, right_split)
        pair_summaries[pair_key] = {
            "n_pairs": int(len(candidate_pairs)),
            "n_only_negative": int(sum(row["label_profile"] == "only_negative" for row in candidate_pairs)),
            "n_only_positive": int(sum(row["label_profile"] == "only_positive" for row in candidate_pairs)),
            "n_mixed_labels": int(sum(row["label_profile"] == "mixed_labels" for row in candidate_pairs)),
            "examples": candidate_pairs[:top_k_examples],
        }
        near_pairs.extend(candidate_pairs)

    max_similarity = max((row["similarity_score"] for row in near_pairs), default=0.0)
    return {
        "threshold": float(threshold),
        "similarity_definition": "sum(min(count_a[e], count_b[e])) / sum(max(count_a[e], count_b[e]))",
        "candidate_strategy": {
            "base_unit": "unique exact sequences per split+label",
            "same_length_only": True,
            "unordered_duplicates_excluded": True,
        },
        "pairwise": pair_summaries,
        "n_total_pairs": int(len(near_pairs)),
        "max_similarity": float(max_similarity),
    }


def build_split_leakage_report(
    events: pd.Series,
    labels: pd.Series,
    split_indices: dict[str, np.ndarray],
) -> dict:
    split_frames = []
    for split_name, idx in split_indices.items():
        print(f"[INFO] Processing split '{split_name}' ({len(idx)} rows) for leakage detection...")
        start_time = time.time()
        
        cur_events = events.iloc[idx].reset_index(drop=True)
        cur_labels = labels.iloc[idx].astype("int32").reset_index(drop=True)
        
        print(f"      [1/6] Canonicalizing event sequences...")
        cur_df = pd.DataFrame(
            {
                "split": split_name,
                "label": cur_labels,
                "sequence": cur_events.apply(canonicalize_events_sequence),
            }
        )
        
        print(f"      [2/6] Computing exact keys...")
        cur_df["exact_key"] = cur_df["sequence"].apply(lambda seq: json.dumps(list(seq), separators=(",", ":")))
        
        print(f"      [3/6] Computing unordered keys...")
        cur_df["unordered_key"] = cur_df["sequence"].apply(build_unordered_key)
        
        print(f"      [4/6] Computing event counters...")
        cur_df["events_counter"] = cur_df["sequence"].apply(Counter)
        
        print(f"      [5/6] Computing sequence lengths...")
        cur_df["seq_len"] = cur_df["sequence"].apply(len)
        
        print(f"      [6/6] Building sequence previews...")
        cur_df["events_preview"] = cur_df["sequence"].apply(build_sequence_preview)
        
        elapsed = time.time() - start_time
        print(f"[INFO] Split '{split_name}' processed in {elapsed:.2f}s")
        split_frames.append(cur_df)

    metadata_df = pd.concat(split_frames, axis=0).reset_index(drop=True)
    print(f"[INFO] Merged all splits: {len(metadata_df)} total rows")
    
    _SKIPPED = {"skipped": True, "possible_leakage": False, "high_leakage_warning": False, "max_overlap_pct": 0.0}
    _SKIPPED_NEAR = {"skipped": True, "n_total_pairs": 0, "max_similarity": 0.0, "pairwise": {}}

    if ENABLE_EXACT_DUPLICATE_ANALYSIS:
        print("[INFO] Analyzing exact duplicate keys...")
        exact_duplicates = build_key_overlap_section(metadata_df, "exact_key", ["train", "val", "test"], "exact_key")
    else:
        print("[INFO] Exact duplicate analysis disabled")
        exact_duplicates = _SKIPPED

    if ENABLE_UNORDERED_DUPLICATE_ANALYSIS:
        print("[INFO] Analyzing unordered duplicate keys...")
        unordered_duplicates = build_key_overlap_section(metadata_df, "unordered_key", ["train", "val", "test"], "unordered_key")
    else:
        print("[INFO] Unordered duplicate analysis disabled")
        unordered_duplicates = _SKIPPED

    if ENABLE_NEAR_DUPLICATE_ANALYSIS:
        print("[INFO] Analyzing near duplicates (similarity >= 0.80)...")
        near_duplicates = build_near_duplicate_section(metadata_df, threshold=0.80, top_k_examples=20)
    else:
        print("[INFO] Near duplicate analysis disabled (O(n²) — activate with ENABLE_NEAR_DUPLICATE_ANALYSIS=True)")
        near_duplicates = _SKIPPED_NEAR

    print("[INFO] Leakage report generation complete")

    return {
        "exact_duplicates": exact_duplicates,
        "unordered_duplicates": unordered_duplicates,
        "near_duplicates": near_duplicates,
        "possible_leakage": bool(
            exact_duplicates.get("possible_leakage", False)
            or unordered_duplicates.get("possible_leakage", False)
            or near_duplicates["n_total_pairs"] > 0
        ),
        "high_leakage_warning": bool(
            exact_duplicates.get("high_leakage_warning", False)
            or unordered_duplicates.get("high_leakage_warning", False)
            or near_duplicates["n_total_pairs"] > 0
        ),
        "max_overlap_pct": float(
            max(
                exact_duplicates.get("max_overlap_pct", 0.0),
                unordered_duplicates.get("max_overlap_pct", 0.0),
                near_duplicates["max_similarity"],
            )
        ),
    }


def print_overlap_section(section_name: str, section: dict) -> None:
    if section.get("skipped"):
        print(f"[INFO] Leakage audit: {section_name} — skipped")
        return
    sizes = section["split_sizes_unique_keys"]
    train_size = next(v for k, v in sizes.items() if k.endswith("_train"))
    val_size = next(v for k, v in sizes.items() if k.endswith("_val"))
    test_size = next(v for k, v in sizes.items() if k.endswith("_test"))
    print(f"[INFO] Leakage audit: {section_name}")
    print(f"[INFO] unique_keys train={train_size} | val={val_size} | test={test_size}")

    split_label_summary = section.get("split_label_summary", {})
    if split_label_summary:
        label_df = pd.DataFrame.from_dict(split_label_summary, orient="index").reset_index()
        label_df = label_df.rename(columns={"index": "split"})
        print("[INFO] Resumen por label:")
        print(label_df.to_string(index=False))

    summary_df = pd.DataFrame(section["summary_rows"]).copy()
    if not summary_df.empty:
        summary_df["pct_of_left"] = summary_df["pct_of_left"].map(lambda v: f"{100.0 * float(v):.2f}%")
        summary_df["pct_of_right"] = summary_df["pct_of_right"].map(lambda v: f"{100.0 * float(v):.2f}%")
        print(summary_df.to_string(index=False))

    top_shared = section.get("top_shared_keys", [])
    if top_shared:
        print("[INFO] Top shared keys:")
        print(pd.DataFrame(top_shared).to_string(index=False))


def print_split_leakage_report(leakage_report: dict) -> None:
    print("[INFO] Leakage audit por OW_values")
    print_overlap_section("exact_duplicates", leakage_report["exact_duplicates"])
    print_overlap_section("unordered_duplicates", leakage_report["unordered_duplicates"])

    near_duplicates = leakage_report.get("near_duplicates", {})
    if near_duplicates.get("skipped"):
        print("[INFO] Leakage audit: near_duplicates — skipped")
        return
    print("[INFO] Leakage audit: near_duplicates")
    print(f"[INFO] similarity_definition={near_duplicates.get('similarity_definition')}")
    pairwise = near_duplicates.get("pairwise", {})
    if pairwise:
        near_summary = [
            {
                "pair": pair,
                "n_pairs": pair_data["n_pairs"],
                "n_only_negative": pair_data["n_only_negative"],
                "n_only_positive": pair_data["n_only_positive"],
                "n_mixed_labels": pair_data["n_mixed_labels"],
            }
            for pair, pair_data in pairwise.items()
        ]
        print(pd.DataFrame(near_summary).to_string(index=False))
        top_examples = []
        for pair, pair_data in pairwise.items():
            for example in pair_data.get("examples", [])[:5]:
                top_examples.append({"pair": pair, **example})
        if top_examples:
            print("[INFO] Near duplicate examples:")
            print(pd.DataFrame(top_examples[:15]).to_string(index=False))

    if leakage_report.get("high_leakage_warning", False):
        print("[WARN] Posible leakage entre splits.")
    elif leakage_report.get("possible_leakage", False):
        print("[WARN] Hay solape entre splits, aunque el solape es bajo.")
    else:
        print("[INFO] No se detecto solape entre train/val/test.")


def render_overlap_html(section_title: str, section: dict) -> str:
    if section.get("skipped"):
        return f"<h3>{escape(section_title)}</h3><p><em>Análisis desactivado.</em></p>"
    summary_html = pd.DataFrame(section["summary_rows"]).to_html(index=False, escape=True)
    top_shared = section.get("top_shared_keys", [])
    top_shared_html = (
        pd.DataFrame(top_shared).to_html(index=False, escape=True)
        if top_shared
        else "<p>No shared keys.</p>"
    )
    sizes_html = "".join(
        f"<li>{escape(str(key))} = {int(value)}</li>"
        for key, value in section["split_sizes_unique_keys"].items()
    )
    split_label_summary = pd.DataFrame.from_dict(
        section.get("split_label_summary", {}),
        orient="index",
    ).reset_index().rename(columns={"index": "split"})
    label_html = (
        split_label_summary.to_html(index=False, escape=True)
        if not split_label_summary.empty
        else "<p>No label summary.</p>"
    )
    return f"""
      <h3>{escape(section_title)}</h3>
      <ul>{sizes_html}</ul>
      <h4>Label summary</h4>
      {label_html}
      <h4>Intersections</h4>
      {summary_html}
      <h4>Top shared keys</h4>
      {top_shared_html}
    """


def render_near_duplicates_html(near_duplicates: dict) -> str:
    if near_duplicates.get("skipped"):
        return "<h3>near_duplicates</h3><p><em>Análisis desactivado.</em></p>"
    pairwise = near_duplicates.get("pairwise", {})
    summary_rows = []
    example_rows = []
    for pair, pair_data in pairwise.items():
        summary_rows.append(
            {
                "pair": pair,
                "n_pairs": pair_data["n_pairs"],
                "n_only_negative": pair_data["n_only_negative"],
                "n_only_positive": pair_data["n_only_positive"],
                "n_mixed_labels": pair_data["n_mixed_labels"],
            }
        )
        for example in pair_data.get("examples", [])[:5]:
            example_rows.append({"pair": pair, **example})
    summary_html = (
        pd.DataFrame(summary_rows).to_html(index=False, escape=True)
        if summary_rows
        else "<p>No near duplicates.</p>"
    )
    examples_html = (
        pd.DataFrame(example_rows[:15]).to_html(index=False, escape=True)
        if example_rows
        else "<p>No examples.</p>"
    )
    return f"""
      <h3>near_duplicates</h3>
      <ul>
        <li>threshold = {near_duplicates.get('threshold', 0.0):.2f}</li>
        <li>similarity_definition = {escape(str(near_duplicates.get('similarity_definition', '')))}</li>
        <li>n_total_pairs = {int(near_duplicates.get('n_total_pairs', 0))}</li>
        <li>max_similarity = {float(near_duplicates.get('max_similarity', 0.0)):.4f}</li>
      </ul>
      <h4>Pairwise summary</h4>
      {summary_html}
      <h4>Examples</h4>
      {examples_html}
    """


def sample_hyperparams(search_space: dict, model_family: str, rng: np.random.Generator):
    """
    Genera una configuración de hiperparámetros a partir de search_space:

    search_space:
      common:
        batch_size: [128, 256]
        learning_rate: [0.001, 0.0005]
        n_layers: [1, 2]
        units: [64, 128]
        dropout: [0.0, 0.2]
      dense_bow: {}
      sequence_embedding: { ... }
      cnn1d: { ... }

    Aquí solo usamos 'common' y, opcionalmente, bloque específico de la familia.
    """
    common = search_space.get("common", {})
    family_space = search_space.get(model_family, {})

    hp = {}

    def pick(key, space):
        values = space.get(key)
        if isinstance(values, list) and values:
            return rng.choice(values)
        return None

    # Common
    hp["batch_size"] = int(pick("batch_size", common) or 128)
    hp["learning_rate"] = float(pick("learning_rate", common) or 1e-3)
    hp["n_layers"] = int(pick("n_layers", common) or 1)
    hp["units"] = int(pick("units", common) or 64)
    hp["dropout"] = float(pick("dropout", common) or 0.0)

    # Podrías extender con params específicos de la familia si quieres
    for key, values in family_space.items():
        if isinstance(values, list) and values:
            hp[key] = rng.choice(values)

    return hp


def build_dense_bow_model(aux: dict, hp: dict) -> tf.keras.Model:
    n_layers = int(hp.get("n_layers", 1))
    units = int(hp.get("units", 64))
    dropout = float(hp.get("dropout", 0.0))

    model = tf.keras.Sequential(name="dense_bow_binary_classifier")
    model.add(tf.keras.layers.Input(shape=(int(aux["input_dim"]),)))

    for _ in range(n_layers):
        model.add(tf.keras.layers.Dense(units, activation="relu"))
        if dropout > 0:
            model.add(tf.keras.layers.Dropout(dropout))

    model.add(tf.keras.layers.Dense(1, activation="sigmoid"))

    return model


def build_sequence_embedding_model(aux: dict, hp: dict) -> tf.keras.Model:
    n_layers = int(hp.get("n_layers", 1))
    units = int(hp.get("units", 64))
    dropout = float(hp.get("dropout", 0.0))
    embed_dim = int(hp.get("embed_dim", 32))

    model = tf.keras.Sequential(name="sequence_embedding_binary_classifier")
    model.add(tf.keras.layers.Input(shape=(int(aux["max_len"]),)))
    model.add(
        tf.keras.layers.Embedding(
            input_dim=int(aux["vocab_size"]) + 1,
            output_dim=embed_dim,
            mask_zero=True,
        )
    )
    model.add(tf.keras.layers.GlobalAveragePooling1D())

    for _ in range(n_layers):
        model.add(tf.keras.layers.Dense(units, activation="relu"))
        if dropout > 0:
            model.add(tf.keras.layers.Dropout(dropout))

    model.add(tf.keras.layers.Dense(1, activation="sigmoid"))

    return model


def build_cnn1d_model(aux: dict, hp: dict) -> tf.keras.Model:
    n_layers = int(hp.get("n_layers", 1))
    units = int(hp.get("units", 64))
    dropout = float(hp.get("dropout", 0.0))
    embed_dim = int(hp.get("embed_dim", 32))
    filters = int(hp.get("filters", 64))
    kernel_size = int(hp.get("kernel_size", 3))

    model = tf.keras.Sequential(name="cnn1d_binary_classifier")
    model.add(tf.keras.layers.Input(shape=(int(aux["max_len"]),)))
    model.add(
        tf.keras.layers.Embedding(
            input_dim=int(aux["vocab_size"]) + 1,
            output_dim=embed_dim,
        )
    )
    model.add(
        tf.keras.layers.Conv1D(
            filters=filters,
            kernel_size=kernel_size,
            activation="relu",
            padding="same",
        )
    )
    model.add(tf.keras.layers.GlobalMaxPooling1D())

    for _ in range(n_layers):
        model.add(tf.keras.layers.Dense(units, activation="relu"))
        if dropout > 0:
            model.add(tf.keras.layers.Dropout(dropout))

    model.add(tf.keras.layers.Dense(1, activation="sigmoid"))

    return model


def build_model(
    model_family: str,
    hp: dict,
    aux: dict,
) -> tf.keras.Model:
    if model_family == "dense_bow":
        model = build_dense_bow_model(aux, hp)
    elif model_family == "sequence_embedding":
        model = build_sequence_embedding_model(aux, hp)
    elif model_family == "cnn1d":
        model = build_cnn1d_model(aux, hp)
    else:
        raise ValueError(
            f"model_family no soportada: {model_family}. "
            "Use una de: dense_bow, sequence_embedding, cnn1d"
        )

    lr = float(hp.get("learning_rate", 1e-3))

    model.compile(
        optimizer=build_adam_optimizer(lr),
        loss="binary_crossentropy",
        metrics=[
            tf.keras.metrics.Precision(name="precision"),
            tf.keras.metrics.Recall(name="recall"),
        ],
    )

    return model


def train_with_automl(
    X_train,
    y_train,
    X_val,
    y_val,
    model_family: str,
    aux: dict,
    search_space: dict,
    automl_cfg: dict,
    training_cfg: dict,
    class_weights=None,
    experiments_dir=None,
):
    """
    Bucle AutoML simple:
      - num_trials = automl.max_trials
      - en cada trial se muestrean hiperparametros
      - se entrena y se evalua con threshold fijo 0.5 en validacion
      - se queda con el modelo con mejor recall_val @0.5
    """
    enabled = bool(automl_cfg.get("enabled", True))
    max_trials = int(automl_cfg.get("max_trials", 5))
    seed = int(automl_cfg.get("seed", 42))

    epochs = int(training_cfg.get("epochs", 10))
    max_samples = training_cfg.get("max_samples", None)
    decision_threshold = 0.5

    rng = np.random.default_rng(seed)
    trials_summary = []

    if experiments_dir is not None:
        experiments_dir.mkdir(parents=True, exist_ok=True)

    num_trials = max_trials if enabled else 1

    if max_samples is not None:
        max_samples = int(max_samples)
        if max_samples < len(X_train):
            idx = rng.choice(len(X_train), size=max_samples, replace=False)
            X_train = X_train[idx]
            y_train = y_train[idx]

    if not enabled:
        print("[INFO] AutoML deshabilitado: se ejecutara 1 trial")

    best_model = None
    best_hp = None
    best_val_recall = -1.0
    best_val_f1 = -1.0
    best_history = None
    best_trial_id = 0
    best_by_f1 = None
    best_by_precision = None
    best_by_recall = None

    def _candidate_for_output(metrics):
        if metrics is None:
            return None
        return {
            "f1": float(metrics["f1"]),
            "recall": float(metrics["recall"]),
            "precision": float(metrics["precision"]),
        }

    def _is_better_candidate(current, candidate, primary_key, tie_key):
        if current is None:
            return True
        if candidate[primary_key] > current[primary_key]:
            return True
        return np.isclose(candidate[primary_key], current[primary_key]) and candidate[tie_key] > current[tie_key]

    def _format_candidate_metrics(metrics):
        if metrics is None:
            return "null"
        return (
            f"f1={metrics['f1']:.4f}, "
            f"recall={metrics['recall']:.4f}, "
            f"precision={metrics['precision']:.4f}"
        )

    if enabled:
        print(f"[INFO] AutoML habilitado: trials={num_trials}")

    for trial in range(num_trials):
        hp = sample_hyperparams(search_space, model_family, rng)
        model = build_model(model_family, hp, aux)

        print(
            f"[INFO] trial {trial + 1}/{num_trials} | family={model_family} | "
            f"batch={int(hp.get('batch_size', 128))} | epochs={epochs}"
        )

        history = model.fit(
            X_train,
            y_train,
            validation_data=(X_val, y_val),
            epochs=epochs,
            batch_size=int(hp.get("batch_size", 128)),
            class_weight=class_weights,
            verbose=0,
        )

        y_val_prob = sanitize_probabilities(model.predict(X_val, verbose=0).ravel(), "val")
        val_metrics = compute_metrics_at_threshold(y_val, y_val_prob, decision_threshold)
        val_precision = float(val_metrics["precision"])
        val_recall = float(val_metrics["recall"])
        val_f1 = float(val_metrics["f1"])

        candidate_metrics = {
            "f1": val_f1,
            "recall": val_recall,
            "precision": val_precision,
        }
        # Tie-breakers: F1/precision prefer recall; recall prefers F1.
        if _is_better_candidate(best_by_f1, candidate_metrics, "f1", "recall"):
            best_by_f1 = candidate_metrics
        if _is_better_candidate(best_by_precision, candidate_metrics, "precision", "recall"):
            best_by_precision = candidate_metrics
        if _is_better_candidate(best_by_recall, candidate_metrics, "recall", "f1"):
            best_by_recall = candidate_metrics

        hp_native = convert_to_native_types(hp)
        trial_result = {
            "trial_id": trial,
            "hyperparameters": hp_native,
            "decision_threshold": float(decision_threshold),
            "threshold_source": "fixed",
            "threshold_policy": "fixed_0_5",
            "val_precision": val_precision,
            "val_recall": val_recall,
            "val_f1": val_f1,
            "epochs": epochs,
            "batch_size": int(hp.get("batch_size", 128)),
        }
        trials_summary.append(trial_result)

        if experiments_dir is not None:
            exp_dir = experiments_dir / f"exp_{trial:03d}"
            exp_dir.mkdir(parents=True, exist_ok=True)
            model.save(exp_dir / "model.h5")
            (exp_dir / "metrics.json").write_text(
                json.dumps(trial_result, indent=2),
                encoding="utf-8",
            )

        print(
            f"[INFO] trial {trial + 1}/{num_trials} | "
            f"val_precision={val_precision:.4f} | val_recall={val_recall:.4f} | "
            f"val_f1={val_f1:.4f} | threshold={decision_threshold:.1f}"
        )

        if val_recall > best_val_recall or (np.isclose(val_recall, best_val_recall) and val_f1 > best_val_f1):
            best_val_recall = val_recall
            best_val_f1 = val_f1
            best_model = model
            best_hp = hp_native
            best_history = history.history
            best_trial_id = trial
            print(
                f"[INFO] Nuevo mejor trial: {best_trial_id} "
                f"(val_recall={best_val_recall:.4f}, val_f1={best_val_f1:.4f})"
            )

    best_validation_candidates = {
        "mejor_modelo_f1": _candidate_for_output(best_by_f1),
        "mejor_modelo_precision": _candidate_for_output(best_by_precision),
        "mejor_modelo_recall": _candidate_for_output(best_by_recall),
    }
    print("[INFO] Best validation candidates:")
    print(f"  by_f1: {_format_candidate_metrics(best_validation_candidates['mejor_modelo_f1'])}")
    print(f"  by_precision: {_format_candidate_metrics(best_validation_candidates['mejor_modelo_precision'])}")
    print(f"  by_recall: {_format_candidate_metrics(best_validation_candidates['mejor_modelo_recall'])}")

    return best_model, best_hp, best_val_recall, best_history, trials_summary, best_trial_id, best_validation_candidates


def compute_optimal_thresholds(y_true, y_prob):
    """
    Calcula:
      - threshold por F1 (global)
      - threshold por recall>=target_recall con máxima precisión
    """
    y_prob = sanitize_probabilities(y_prob, "threshold")
    precisions, recalls, thresholds = precision_recall_curve(y_true, y_prob)

    # Para F1
    f1_scores = 2 * (precisions * recalls) / (precisions + recalls + 1e-8)
    best_f1_idx = int(np.argmax(f1_scores))
    best_f1_threshold = float(thresholds[best_f1_idx]) if best_f1_idx < len(thresholds) else 0.5

    # Para recall objetivo (ejemplo: 0.9)
    target_recall = 0.9
    idx = np.where(recalls >= target_recall)[0]
    if len(idx) > 0:
        best_idx = idx[np.argmax(precisions[idx])]
        best_recall_threshold = float(thresholds[best_idx]) if best_idx < len(thresholds) else 0.5
    else:
        best_recall_threshold = 0.5

    return best_f1_threshold, best_recall_threshold



def compute_metrics_at_threshold(y_true, y_prob, threshold: float) -> dict:
    y_prob = sanitize_probabilities(y_prob, "metrics")
    y_pred = (y_prob >= float(threshold)).astype("int32")
    return {
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
    }


def get_optional_int(*values):
    for value in values:
        if value is not None:
            return int(value)
    return None


def stratified_cap_indices(indices, y_full, max_samples, seed: int):
    if max_samples is None or int(max_samples) <= 0 or len(indices) <= int(max_samples):
        return indices.astype(np.int64), False

    max_samples = int(max_samples)
    rng = np.random.default_rng(seed)
    selected_parts = []
    for label in np.unique(y_full[indices]):
        label_idx = indices[y_full[indices] == label]
        desired = int(round(max_samples * len(label_idx) / len(indices)))
        desired = min(len(label_idx), max(1, desired))
        selected_parts.append(rng.choice(label_idx, size=desired, replace=False))

    selected = np.concatenate(selected_parts).astype(np.int64)
    if len(selected) > max_samples:
        selected = rng.choice(selected, size=max_samples, replace=False).astype(np.int64)
    elif len(selected) < max_samples:
        missing_pool = np.setdiff1d(indices, selected, assume_unique=False)
        if len(missing_pool) > 0:
            extra = rng.choice(missing_pool, size=min(max_samples - len(selected), len(missing_pool)), replace=False)
            selected = np.concatenate([selected, extra]).astype(np.int64)

    rng.shuffle(selected)
    return selected.astype(np.int64), True


def sanitize_probabilities(y_prob, context=""):
    """Normaliza scores a un rango válido [0,1] y elimina NaN/Inf."""
    arr = np.asarray(y_prob, dtype=np.float64)
    non_finite = ~np.isfinite(arr)
    if non_finite.any():
        count = int(non_finite.sum())
        print(f"[WARN] Se detectaron {count} scores no finitos en {context}; se normalizan a 0.0")

    arr = np.nan_to_num(arr, nan=0.0, posinf=1.0, neginf=0.0)
    arr = np.clip(arr, 0.0, 1.0)
    return arr


def summarize_label_distribution(y) -> dict[int, int]:
    labels, counts = np.unique(y, return_counts=True)
    return {int(label): int(count) for label, count in zip(labels, counts)}


def explain_split_incompatibility(y) -> str | None:
    label_distribution = summarize_label_distribution(y)

    if len(y) < 3:
        return (
            f"Dataset con {len(y)} muestra(s): no alcanza para generar "
            "splits train/val/test no vacíos"
        )

    if len(label_distribution) < 2:
        only_label = next(iter(label_distribution.keys()), None)
        return (
            "Dataset monoclase: "
            f"solo contiene la clase {only_label} con {len(y)} muestra(s)"
        )

    min_class = min(label_distribution.values())
    if min_class < 2:
        return (
            f"La clase menos poblada tiene {min_class} muestra(s); "
            "train_test_split estratificado requiere al menos 2"
        )

    return None


def write_non_trainable_outputs(
    *,
    variant_dir,
    variant: str,
    parent_variant: str,
    training_dataset_path,
    prediction_name: str,
    model_family: str,
    Tu: int,
    OW: int,
    LT: int,
    PW: int,
    label_distribution: dict[int, int],
    reason: str,
    start_time: float,
):
    execution_time = float(time.perf_counter() - start_time)
    total_samples = int(sum(label_distribution.values()))
    positive_samples = int(label_distribution.get(1, 0))
    negative_samples = int(label_distribution.get(0, 0))

    report_path = variant_dir / "05_modeling_report.html"
    report_html = f"""
    <html>
    <body>
      <h1>F05 Modeling — {variant}</h1>
      <p><b>Parent F04:</b> {parent_variant}</p>
      <p><b>Prediction:</b> {prediction_name}</p>
      <p><b>Model family:</b> {model_family}</p>
      <h2>Status</h2>
      <ul>
        <li>trainable = False</li>
        <li>reason = {reason}</li>
      </ul>
      <h2>Dataset</h2>
      <ul>
        <li>n_samples_total = {total_samples}</li>
        <li>negative_samples = {negative_samples}</li>
        <li>positive_samples = {positive_samples}</li>
      </ul>
      <h2>Geometry</h2>
      <ul>
        <li>Tu = {Tu}</li>
        <li>OW = {OW}</li>
        <li>LT = {LT}</li>
        <li>PW = {PW}</li>
      </ul>
      <h2>Execution</h2>
      <p>execution_time = {execution_time:.1f} s</p>
    </body>
    </html>
    """
    report_path.write_text(report_html, encoding="utf-8")

    outputs_content = {
        "phase": PHASE,
        "variant": variant,
        "artifacts": {
            "labeled_dataset": {
                "path": training_dataset_path.name,
                "sha256": sha256_of_file(training_dataset_path),
            },
            "report": {
                "path": report_path.name,
                "sha256": sha256_of_file(report_path),
            },
        },
        "exports": {
            "Tu": int(Tu),
            "OW": int(OW),
            "LT": int(LT),
            "PW": int(PW),
            "prediction_name": str(prediction_name),
            "model_family": str(model_family),
            "trainable": False,
            "incompatibility_reason": str(reason),
        },
        "metrics": {
            "execution_time": float(execution_time),
            "mejor_modelo_f1": None,
            "mejor_modelo_precision": None,
            "mejor_modelo_recall": None,
            "n_train": 0,
            "n_val": 0,
            "n_test": 0,
            "positive_ratio_train": 0.0,
            "tp": 0,
            "tn": 0,
            "fp": 0,
            "fn": 0,
            "n_samples_total": total_samples,
            "positive_samples": positive_samples,
            "negative_samples": negative_samples,
        },
        "provenance": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "parent_phase": PARENT_PHASE,
            "parent_variant": parent_variant,
        },
    }

    save_outputs_yaml(variant_dir, outputs_content)
    validate_outputs(PHASE, outputs_content)

    print(f"[WARN] Modelo no entrenable para {variant}: {reason}")
    print(f"===== FASE {PHASE} COMPLETADA SIN ENTRENAMIENTO — variante {variant} =====")


# ============================================================
# NUMERIC-SEQUENCE OVERRIDES
# ============================================================

def load_labeled_dataset_for_training(
    dataset_path,
    label_col: str,
    strategy: str,
    max_majority_samples: int | None,
    random_state: int = 123,
) -> pd.DataFrame:
    columns = [INPUT_SEQUENCE_COLUMN, label_col]
    return pd.read_parquet(dataset_path, columns=columns)


def read_label_array_from_parquet(dataset_path, label_col: str) -> np.ndarray:
    return (
        pq.read_table(dataset_path, columns=[label_col], memory_map=True)
        .column(0)
        .to_numpy(zero_copy_only=False)
        .astype("int32")
    )


def load_labeled_dataset_rows(
    dataset_path,
    label_col: str,
    selected_indices: np.ndarray | None = None,
) -> pd.DataFrame:
    columns = [INPUT_SEQUENCE_COLUMN, label_col]
    if selected_indices is None:
        return pd.read_parquet(dataset_path, columns=columns)

    selected_indices = np.asarray(selected_indices, dtype=np.int64)
    if selected_indices.size == 0:
        return pd.DataFrame(columns=columns)

    order_by_index = pd.Series(
        np.arange(selected_indices.size, dtype=np.int64),
        index=selected_indices,
    )
    sorted_indices = np.sort(selected_indices)

    parquet_file = pq.ParquetFile(dataset_path, memory_map=True)
    frames = []
    row_offset = 0
    cursor = 0
    for batch in parquet_file.iter_batches(batch_size=50_000, columns=columns):
        batch_len = batch.num_rows
        batch_end = row_offset + batch_len
        start_cursor = cursor
        while cursor < sorted_indices.size and sorted_indices[cursor] < batch_end:
            cursor += 1
        if cursor > start_cursor:
            global_idx = sorted_indices[start_cursor:cursor]
            local_idx = global_idx - row_offset
            frame = batch.take(pa.array(local_idx)).to_pandas()
            frame["_source_index"] = global_idx
            frames.append(frame)
        row_offset = batch_end
        if cursor >= sorted_indices.size:
            break

    if not frames:
        return pd.DataFrame(columns=columns)

    df = pd.concat(frames, axis=0)
    df["_order"] = df["_source_index"].map(order_by_index)
    df = df.sort_values("_order").drop(columns=["_source_index", "_order"])
    return df.reset_index(drop=True)


def pad_numeric_sequences(sequences, max_len: int) -> np.ndarray:
    X = np.zeros((len(sequences), max_len), dtype=np.float32)
    for i, seq in enumerate(sequences):
        arr = np.asarray(seq, dtype=np.float32)
        if arr.size == 0:
            continue
        trunc = arr[-max_len:]
        X[i, -len(trunc):] = trunc
    return X


def vectorize_numeric_sequence(df: pd.DataFrame, label_col: str, model_family: str):
    if INPUT_SEQUENCE_COLUMN not in df.columns:
        raise RuntimeError(f"El dataset de F04 debe contener la columna '{INPUT_SEQUENCE_COLUMN}'")

    sequences = df[INPUT_SEQUENCE_COLUMN].tolist()
    y = df[label_col].astype("int32").values

    lengths = [len(seq) for seq in sequences]
    max_len = max(1, int(np.percentile(lengths, 95))) if lengths else 1
    X_2d = pad_numeric_sequences(sequences, max_len)

    mean = float(np.mean(X_2d)) if X_2d.size else 0.0
    std = float(np.std(X_2d)) if X_2d.size else 1.0
    if std <= 0.0:
        std = 1.0
    X_2d = ((X_2d - mean) / std).astype(np.float32)

    if model_family == "cnn1d":
        X = X_2d[..., np.newaxis]
        vectorization = "numeric_sequence_cnn1d"
    else:
        X = X_2d
        vectorization = "numeric_sequence_dense"

    return X, y, {
        "input_dim": int(X_2d.shape[1]),
        "max_len": int(max_len),
        "vectorization": vectorization,
        "sequence_column": INPUT_SEQUENCE_COLUMN,
        "normalization_mean": mean,
        "normalization_std": std,
    }


def vectorize_for_family(df: pd.DataFrame, label_col: str, model_family: str):
    if model_family in {"dense_bow", "cnn1d"}:
        return vectorize_numeric_sequence(df, label_col, model_family)

    if model_family == "sequence_embedding":
        raise ValueError(
            "sequence_embedding ya no aplica: OW_values contiene medidas continuas, "
            "no IDs categoricos de evento. Use cnn1d o dense_bow."
        )

    raise ValueError(
        f"model_family no soportada: {model_family}. "
        "Use una de: dense_bow, cnn1d"
    )


def build_cnn1d_model(aux: dict, hp: dict) -> tf.keras.Model:
    n_layers = int(hp.get("n_layers", 1))
    units = int(hp.get("units", 64))
    dropout = float(hp.get("dropout", 0.0))
    filters = int(hp.get("filters", 64))
    kernel_size = int(hp.get("kernel_size", 3))

    model = tf.keras.Sequential(name="cnn1d_numeric_binary_classifier")
    model.add(tf.keras.layers.Input(shape=(int(aux["max_len"]), 1)))
    model.add(
        tf.keras.layers.Conv1D(
            filters=filters,
            kernel_size=kernel_size,
            activation="relu",
            padding="same",
        )
    )
    model.add(tf.keras.layers.GlobalMaxPooling1D())

    for _ in range(n_layers):
        model.add(tf.keras.layers.Dense(units, activation="relu"))
        if dropout > 0:
            model.add(tf.keras.layers.Dropout(dropout))

    model.add(tf.keras.layers.Dense(1, activation="sigmoid"))
    return model


def build_model(
    model_family: str,
    hp: dict,
    aux: dict,
) -> tf.keras.Model:
    if model_family == "dense_bow":
        model = build_dense_bow_model(aux, hp)
    elif model_family == "cnn1d":
        model = build_cnn1d_model(aux, hp)
    else:
        raise ValueError(
            f"model_family no soportada: {model_family}. "
            "Use una de: dense_bow, cnn1d"
        )

    lr = float(hp.get("learning_rate", 1e-3))
    model.compile(
        optimizer=build_adam_optimizer(lr),
        loss="binary_crossentropy",
        metrics=[
            tf.keras.metrics.Precision(name="precision"),
            tf.keras.metrics.Recall(name="recall"),
        ],
    )
    return model


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", required=True, help="Variant id vY_XXXX for F05")
    args = parser.parse_args()

    variant = args.variant
    start_time = time.perf_counter()

    print(f"===== FASE {PHASE} — MODELING — variante {variant} =====")

    # ---------------------------------------------
    # 1. Cargar parámetros de F05 y parent F04
    # ---------------------------------------------
    params_data = load_variant_params(get_variant_dir, PHASE, variant, "F05")
    if not isinstance(params_data, dict):
        raise RuntimeError(f"params.yaml inválido para {PHASE}:{variant}")

    params = params_data.get("parameters", {})
    parent_variant = params_data.get("parent")

    if not parent_variant:
        raise RuntimeError("F05 requiere parent definido en params.yaml (f04_targets variant)")

    print(f"[INFO] Parent F04: {parent_variant}")

    parent_outputs, parent_dir = load_phase_outputs(PROJECT_ROOT, PARENT_PHASE, parent_variant, "F05")

    artifacts_parent = parent_outputs.get("artifacts", {})
    exports_parent = parent_outputs.get("exports", {})
    prediction_name = params.get("prediction_name") or exports_parent.get("prediction_name", "prediction")
    measure_name = exports_parent.get("measure_name")
    if measure_name is None:
        suffix = "_any-to-"
        measure_name = prediction_name.split(suffix, 1)[0] if suffix in prediction_name else prediction_name
    parent_f03 = exports_parent.get("parent_f03")
    parent_f02 = exports_parent.get("parent_f02")
    window_strategy = exports_parent.get("window_strategy")

    dataset_rel = artifacts_parent.get("dataset", {}).get("path")
    if not dataset_rel:
        raise RuntimeError("outputs.yaml de F04 no contiene artifacts.dataset.path")

    dataset_path = parent_dir / dataset_rel
    if not dataset_path.exists():
        raise FileNotFoundError(f"No se encuentra dataset etiquetado de F04 en {dataset_path}")

    # Label column: si F04 lo expone, lo usamos; si no, usamos 'target'
    label_col = exports_parent.get("target_column", "label")
    

    Tu = int(params.get("Tu", exports_parent.get("Tu", 0)))
    OW = int(params.get("OW", exports_parent.get("OW", 0)))
    LT = int(params.get("LT", exports_parent.get("LT", 0)))
    PW = int(params.get("PW", exports_parent.get("PW", 0)))

    model_family = params["model_family"]

    automl_cfg = params.get("automl", {})
    search_space = params.get("search_space", {})
    evaluation_cfg = params.get("evaluation", {})
    training_cfg = params.get("training", {})
    val_max_samples = get_optional_int(
        evaluation_cfg.get("val_max_samples"),
        evaluation_cfg.get("max_val_samples"),
    )
    test_max_samples = get_optional_int(
        evaluation_cfg.get("test_max_samples"),
        evaluation_cfg.get("max_test_samples"),
    )
    imbalance_cfg = params.get("imbalance", {})
    imbalance_strategy = params.get("imbalance_strategy")
    imbalance_max_majority = params.get("imbalance_max_majority_samples")
    dedup_mode = params.get("deduplication_mode", "none")


    if imbalance_strategy is None and isinstance(imbalance_cfg, dict):
        imbalance_strategy = imbalance_cfg.get("strategy", "none")
    if imbalance_strategy is None:
        imbalance_strategy = "none"

    if imbalance_max_majority is None and isinstance(imbalance_cfg, dict):
        imbalance_max_majority = imbalance_cfg.get("max_majority_samples")

    automl_seed = int(params.get("seed", automl_cfg.get("seed", 42)))
    configure_reproducibility(automl_seed, strict_cross_os=True)
    print(f"[INFO] reproducibility seed={automl_seed}, strict_cross_os=True")

    strategy = imbalance_strategy
    max_maj = imbalance_max_majority

    # ---------------------------------------------
    # 2. Cargar dataset etiquetado
    # ---------------------------------------------
    print(f"[INFO] Leyendo dataset etiquetado de F04: {dataset_path}")
    defer_full_dataset_load = strategy == "rare_events" and dedup_mode == "none"
    if defer_full_dataset_load:
        y_full_deferred = read_label_array_from_parquet(dataset_path, label_col)
        df = None
    else:
        y_full_deferred = None
        df = load_labeled_dataset_for_training(
            dataset_path,
            label_col,
            imbalance_strategy,
            imbalance_max_majority,
            random_state=123,
        )

    if df is not None and label_col not in df.columns:
        raise RuntimeError(f"La columna de etiqueta '{label_col}' no está en el dataset")
    

    if dedup_mode not in {"none", "all", "neg_only", "auto"}:
        raise ValueError(f"deduplication_mode no soportado: {dedup_mode}")

    # (Opcional) manejar imbalance de forma simple
    # Aquí solo aplicamos rare_events max_majority_samples
    strategy = imbalance_strategy
    max_maj = imbalance_max_majority

    if strategy == "rare_events":
        if max_maj is None:
            max_maj = FAST_MAX_MAJORITY_SAMPLES
        max_maj = min(int(max_maj), FAST_MAX_MAJORITY_SAMPLES)
        print(
            f"[INFO] imbalance=rare_events aplicado solo a train, max_majority_samples={max_maj} "
            f"(cap={FAST_MAX_MAJORITY_SAMPLES})"
        )

    # ---------------------------------------------
    # 2b. Preparar carpeta de salida y snapshot dataset usado
    # ---------------------------------------------
    variant_dir = get_variant_dir(PHASE, variant)
    variant_dir.mkdir(parents=True, exist_ok=True)

    training_dataset_path = variant_dir / "05_modeling_training_dataset.parquet"

    parent_dataset_snapshot_path = variant_dir / "05_modeling_parent_dataset.parquet"
    if dataset_path.resolve() != parent_dataset_snapshot_path.resolve():
        shutil.copy2(dataset_path, parent_dataset_snapshot_path)

    print(f"[INFO] dataset_parent={dataset_path}")
    print(f"[INFO] dataset_parent_snapshot={parent_dataset_snapshot_path}")

    # ---------------------------------------------
    # 3. Vectorización por familia + splits train/val/test
    # ---------------------------------------------
    y_full = y_full_deferred if defer_full_dataset_load else df[label_col].astype("int32").values
    label_distribution = summarize_label_distribution(y_full)
    split_incompatibility = explain_split_incompatibility(y_full)
    if split_incompatibility is not None:
        if df is None:
            df = load_labeled_dataset_rows(dataset_path, label_col)
        df.to_parquet(training_dataset_path)
        print(f"[INFO] dataset_training_used={training_dataset_path}")
        write_non_trainable_outputs(
            variant_dir=variant_dir,
            variant=variant,
            parent_variant=parent_variant,
            training_dataset_path=training_dataset_path,
            prediction_name=prediction_name,
            model_family=model_family,
            Tu=Tu,
            OW=OW,
            LT=LT,
            PW=PW,
            label_distribution=label_distribution,
            reason=split_incompatibility,
            start_time=start_time,
        )
        return

    try:
        idx_train_full, idx_val_full, idx_test_full = split_dataset_indices(y_full, evaluation_cfg)
    except ValueError as exc:
        if df is None:
            df = load_labeled_dataset_rows(dataset_path, label_col)
        df.to_parquet(training_dataset_path)
        print(f"[INFO] dataset_training_used={training_dataset_path}")
        write_non_trainable_outputs(
            variant_dir=variant_dir,
            variant=variant,
            parent_variant=parent_variant,
            training_dataset_path=training_dataset_path,
            prediction_name=prediction_name,
            model_family=model_family,
            Tu=Tu,
            OW=OW,
            LT=LT,
            PW=PW,
            label_distribution=label_distribution,
            reason=f"No se pudo generar split train/val/test: {exc}",
            start_time=start_time,
        )
        return

    print(f"[INFO] Split indices generated successfully")
    val_positive_ratio_before = float(y_full[idx_val_full].mean()) if len(idx_val_full) else 0.0
    test_positive_ratio_before = float(y_full[idx_test_full].mean()) if len(idx_test_full) else 0.0
    idx_val_full, val_cap_used = stratified_cap_indices(idx_val_full, y_full, val_max_samples, automl_seed + 101)
    idx_test_full, test_cap_used = stratified_cap_indices(idx_test_full, y_full, test_max_samples, automl_seed + 202)
    val_positive_ratio_after = float(y_full[idx_val_full].mean()) if len(idx_val_full) else 0.0
    test_positive_ratio_after = float(y_full[idx_test_full].mean()) if len(idx_test_full) else 0.0
    if val_cap_used:
        print(
            f"[INFO] Validation cap estratificado aplicado: n={len(idx_val_full)}, "
            f"positive_ratio {val_positive_ratio_before:.4f}->{val_positive_ratio_after:.4f}"
        )
    if test_cap_used:
        print(
            f"[INFO] Test cap estratificado aplicado: n={len(idx_test_full)}, "
            f"positive_ratio {test_positive_ratio_before:.4f}->{test_positive_ratio_after:.4f}"
        )

    if df is None:
        dedup_stats = {
            "dedup_mode_effective": "none",
            "n_before": int(len(idx_train_full)),
            "n_after": int(len(idx_train_full)),
            "n_removed": 0,
            "removed_ratio": 0.0,
            "n_ambiguous_sequences_removed": 0,
            "n_ambiguous_rows_removed": 0,
            "n_majority_resolved_sequences": 0,
        }
        idx_train_fit = idx_train_full
    else:
        df_train_full = df.iloc[idx_train_full].copy()
        df_train_full["_original_index"] = idx_train_full
        df_train_fit, dedup_stats = deduplicate_labeled_windows(df_train_full, dedup_mode)
        idx_train_fit = df_train_fit["_original_index"].to_numpy(dtype=np.int64)

    print(
        f"[INFO] dedup={dedup_mode} aplicado solo a train -> "
        f"effective={dedup_stats['dedup_mode_effective']} | "
        f"before={dedup_stats['n_before']} | after={dedup_stats['n_after']} | "
        f"removed={dedup_stats['n_removed']} ({dedup_stats['removed_ratio']:.4%})"
    )

    if strategy == "rare_events":
        idx_train_fit, max_maj = apply_rare_events_to_train_indices(
            y_full,
            idx_train_fit,
            max_maj,
            random_state=123,
        )

    selected_indices = np.concatenate([idx_train_fit, idx_val_full, idx_test_full]).astype(np.int64)
    if df is None:
        df_model = load_labeled_dataset_rows(dataset_path, label_col, selected_indices)
    else:
        df_model = df.iloc[selected_indices].reset_index(drop=True)
    df_model.to_parquet(training_dataset_path)
    print(f"[INFO] dataset_training_used={training_dataset_path}")

    n_train_fit = len(idx_train_fit)
    n_val = len(idx_val_full)
    n_test = len(idx_test_full)
    idx_train = np.arange(0, n_train_fit, dtype=np.int64)
    idx_val = np.arange(n_train_fit, n_train_fit + n_val, dtype=np.int64)
    idx_test = np.arange(n_train_fit + n_val, n_train_fit + n_val + n_test, dtype=np.int64)

    print(
        f"[INFO] Split sizes before train sampling: "
        f"train={len(idx_train_full)}, val={n_val}, test={n_test}"
    )
    if strategy == "rare_events":
        print(f"[INFO] Train after rare_events sampling: train={n_train_fit}")

    print(f"[INFO] Vectorizing dataset for model family '{model_family}'...")
    X, y, vectorization_info = vectorize_for_family(
        df_model,
        label_col,
        model_family,
    )
    print(f"[INFO] Vectorization complete: X.shape={X.shape}, y.shape={y.shape}")

    X_train = X[idx_train]
    y_train = y[idx_train]
    X_val = X[idx_val]
    y_val = y[idx_val]
    X_test = X[idx_test]
    y_test = y[idx_test]

    print(f"[INFO] Split sizes: train={len(y_train)}, val={len(y_val)}, test={len(y_test)}")
    print(f"[INFO] Starting leakage detection analysis (this may take a few minutes for large datasets)...")
    leakage_report = build_split_leakage_report(
        df_model["OW_values"],
        df_model[label_col],
        {
            "train": idx_train,
            "val": idx_val,
            "test": idx_test,
        },
    )
    print_split_leakage_report(leakage_report)
    print(f"[INFO] Leakage detection complete")

    class_weights = compute_class_weights(y_train) if strategy == "auto" else None

    print(f"[INFO] n_train={len(y_train)}, n_val={len(y_val)}, n_test={len(y_test)}")
    print(f"[INFO] positive_ratio_train={y_train.mean():.4f}")
    print(f"[INFO] vectorization={vectorization_info.get('vectorization')}")

    # ---------------------------------------------
    # 4. AutoML — entrenamiento y selección
    # ---------------------------------------------
    print(f"[INFO] Starting AutoML training...")
    experiments_dir = variant_dir / "experiments"

    best_model, best_hp, best_val_recall, history, trials_summary, best_trial_id, best_validation_candidates = train_with_automl(
        X_train,
        y_train,
        X_val,
        y_val,
        model_family,
        vectorization_info,
        search_space,
        automl_cfg,
        training_cfg,
        class_weights=class_weights,
        experiments_dir=experiments_dir,
    )
    print(f"[INFO] AutoML training complete (best trial: {best_trial_id}, best_val_recall: {best_val_recall:.4f})")

    # ---------------------------------------------
    # 5. Evaluación final en test + thresholds
    # ---------------------------------------------
    print(f"[INFO] Evaluating on test set...")
    decision_threshold = 0.5
    threshold_source = "fixed"
    threshold_policy = "fixed_0_5"

    y_val_prob = sanitize_probabilities(best_model.predict(X_val, verbose=0).ravel(), "val_final")
    val_metrics = compute_metrics_at_threshold(y_val, y_val_prob, decision_threshold)
    val_precision = float(val_metrics["precision"])
    val_recall = float(val_metrics["recall"])
    val_f1 = float(val_metrics["f1"])

    y_test_prob = sanitize_probabilities(best_model.predict(X_test, verbose=0).ravel(), "test")
    y_test_pred = (y_test_prob >= decision_threshold).astype("int32")
    test_precision = precision_score(y_test, y_test_pred, zero_division=0)
    test_recall = recall_score(y_test, y_test_pred, zero_division=0)
    test_f1 = f1_score(y_test, y_test_pred, zero_division=0)
    cm = confusion_matrix(y_test, y_test_pred, labels=[0, 1])
    tn, fp, fn, tp = [int(v) for v in cm.ravel()]

    execution_time = float(time.perf_counter() - start_time)

    print(f"[INFO] decision_threshold={decision_threshold:.1f} ({threshold_policy})")
    print(f"[INFO] val_precision={val_precision:.4f}, val_recall={val_recall:.4f}, val_f1={val_f1:.4f}")
    print(f"[INFO] test_precision={test_precision:.4f}, test_recall={test_recall:.4f}, test_f1={test_f1:.4f}")
    print(f"[INFO] confusion@0.5: tp={tp}, tn={tn}, fp={fp}, fn={fn}")
    print(f"[INFO] execution_time={execution_time:.1f}s")

    # ---------------------------------------------
    # 6. Guardar modelo + report + history (opcional)
    # ---------------------------------------------
    model_path = variant_dir / "05_modeling_model.h5"
    best_model.save(model_path)

    # history opcional
    history_path = variant_dir / "05_modeling_history.json"
    with history_path.open("w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

    trials_summary_path = variant_dir / "05_modeling_trials_summary.json"
    trials_summary_path.write_text(
        json.dumps(convert_to_native_types(trials_summary), indent=2),
        encoding="utf-8",
    )
    leakage_report_path = variant_dir / "05_modeling_split_hash_leakage.json"
    leakage_report_payload = convert_to_native_types(leakage_report)
    leakage_report_path.write_text(
        json.dumps(leakage_report_payload, indent=2),
        encoding="utf-8",
    )

    best_model_in_experiments = experiments_dir / f"exp_{best_trial_id:03d}" / "model.h5"

    print(f"[INFO] best_trial_id={best_trial_id}")
    print(f"[INFO] experiments_dir={experiments_dir}")
    print(f"[INFO] best_model_in_experiments={best_model_in_experiments}")
    print(f"[INFO] best_model_final={model_path}")

    # Report muy simple (puedes refinar luego)
    report_path = variant_dir / "05_modeling_report.html"
    report_html = f"""
    <html>
    <body>
      <h1>F05 Modeling — {variant}</h1>
      <p><b>Parent F04:</b> {parent_variant}</p>
      <p><b>Prediction:</b> {prediction_name}</p>
      <p><b>Model family:</b> {model_family}</p>
      <h2>Geometry</h2>
      <ul>
        <li>Tu = {Tu}</li>
        <li>OW = {OW}</li>
        <li>LT = {LT}</li>
        <li>PW = {PW}</li>
      </ul>
      <h2>AutoML</h2>
      <pre>{json.dumps(best_hp, indent=2)}</pre>
      <h2>Validation @0.5</h2>
      <p>val_precision = {val_precision:.4f}</p>
      <p>val_recall = {val_recall:.4f}</p>
      <p>val_f1 = {val_f1:.4f}</p>
      <h2>Test @0.5</h2>
      <ul>
        <li>precision = {test_precision:.4f}</li>
        <li>recall = {test_recall:.4f}</li>
        <li>f1 = {test_f1:.4f}</li>
                <li>tp = {tp}</li>
                <li>tn = {tn}</li>
                <li>fp = {fp}</li>
                <li>fn = {fn}</li>
      </ul>
      <h2>Threshold</h2>
      <ul>
        <li>decision_threshold = {decision_threshold:.1f}</li>
        <li>threshold_source = {threshold_source}</li>
        <li>threshold_policy = {threshold_policy}</li>
      </ul>
      <h2>Split Leakage Audit</h2>
      <ul>
        <li>possible_split_leakage = {str(leakage_report['possible_leakage'])}</li>
        <li>high_split_leakage_warning = {str(leakage_report['high_leakage_warning'])}</li>
        <li>max_overlap_pct = {float(leakage_report['max_overlap_pct']):.4f}</li>
      </ul>
      {render_overlap_html("exact_duplicates", leakage_report["exact_duplicates"])}
      {render_overlap_html("unordered_duplicates", leakage_report["unordered_duplicates"])}
      {render_near_duplicates_html(leakage_report["near_duplicates"])}
      <h2>Execution</h2>
      <p>execution_time = {execution_time:.1f} s</p>
    </body>
    </html>
    """
    report_path.write_text(report_html, encoding="utf-8")

    # ---------------------------------------------
    # 7. Construir outputs.yaml
    # ---------------------------------------------
    outputs_content = {
        "phase": PHASE,
        "variant": variant,
        "artifacts": {
            "model": {
                "path": model_path.name,
                "sha256": sha256_of_file(model_path),
            },
            "labeled_dataset": {
                "path": training_dataset_path.name,
                "sha256": sha256_of_file(training_dataset_path),
            },
            "history": {
                "path": history_path.name,
                "sha256": sha256_of_file(history_path),
            },
            "split_hash_leakage": {
                "path": leakage_report_path.name,
                "sha256": sha256_of_file(leakage_report_path),
            },
            "report": {
                "path": report_path.name,
                "sha256": sha256_of_file(report_path),
            },
        },
        "exports": {
            "Tu": int(Tu),
            "OW": int(OW),
            "LT": int(LT),
            "PW": int(PW),
            "prediction_name": str(prediction_name),
            "measure_name": str(measure_name),
            "model_family": str(model_family),
            "window_strategy": str(window_strategy),
            "deduplication_mode": str(dedup_mode),
            "deduplication_mode_effective": str(dedup_stats["dedup_mode_effective"]),
            "seed": int(automl_seed),
            "trainable": True,
            "possible_split_leakage": bool(leakage_report["possible_leakage"]),
            "high_split_leakage_warning": bool(leakage_report["high_leakage_warning"]),
            "decision_threshold": float(decision_threshold),
            "threshold_source": str(threshold_source),
            "threshold_policy": str(threshold_policy),
            "best_val_recall": float(val_recall),
            "val_precision": float(val_precision),
            "val_recall": float(val_recall),
            "val_f1": float(val_f1),
            "test_precision": float(test_precision),
            "test_recall": float(test_recall),
            "test_f1": float(test_f1),
            "imbalance_strategy": str(strategy),
            "parent_f04": str(parent_variant),
            "parent_f03": str(parent_f03),
            "parent_f02": str(parent_f02),
        },
        "metrics": {
            "execution_time": float(execution_time),
            "mejor_modelo_f1": best_validation_candidates.get("mejor_modelo_f1"),
            "mejor_modelo_precision": best_validation_candidates.get("mejor_modelo_precision"),
            "mejor_modelo_recall": best_validation_candidates.get("mejor_modelo_recall"),
            "n_train": int(len(y_train)),
            "n_val": int(len(y_val)),
            "n_test": int(len(y_test)),
            "n_exact_train": int(leakage_report["exact_duplicates"].get("split_sizes_unique_keys", {}).get("n_exact_key_train", 0)),
            "n_exact_val": int(leakage_report["exact_duplicates"].get("split_sizes_unique_keys", {}).get("n_exact_key_val", 0)),
            "n_exact_test": int(leakage_report["exact_duplicates"].get("split_sizes_unique_keys", {}).get("n_exact_key_test", 0)),
            "n_exact_intersection_train_val": int(leakage_report["exact_duplicates"].get("pair_intersections", {}).get("train_val", {}).get("shared_keys_count", 0)),
            "n_exact_intersection_train_test": int(leakage_report["exact_duplicates"].get("pair_intersections", {}).get("train_test", {}).get("shared_keys_count", 0)),
            "n_exact_intersection_val_test": int(leakage_report["exact_duplicates"].get("pair_intersections", {}).get("val_test", {}).get("shared_keys_count", 0)),
            "n_exact_intersection_all_three": int(leakage_report["exact_duplicates"].get("triple_intersection", {}).get("shared_keys_count", 0)),
            "n_unordered_train": int(leakage_report["unordered_duplicates"].get("split_sizes_unique_keys", {}).get("n_unordered_key_train", 0)),
            "n_unordered_val": int(leakage_report["unordered_duplicates"].get("split_sizes_unique_keys", {}).get("n_unordered_key_val", 0)),
            "n_unordered_test": int(leakage_report["unordered_duplicates"].get("split_sizes_unique_keys", {}).get("n_unordered_key_test", 0)),
            "n_unordered_intersection_train_val": int(leakage_report["unordered_duplicates"].get("pair_intersections", {}).get("train_val", {}).get("shared_keys_count", 0)),
            "n_unordered_intersection_train_test": int(leakage_report["unordered_duplicates"].get("pair_intersections", {}).get("train_test", {}).get("shared_keys_count", 0)),
            "n_unordered_intersection_val_test": int(leakage_report["unordered_duplicates"].get("pair_intersections", {}).get("val_test", {}).get("shared_keys_count", 0)),
            "n_unordered_intersection_all_three": int(leakage_report["unordered_duplicates"].get("triple_intersection", {}).get("shared_keys_count", 0)),
            "n_near_pairs_train_val": int(leakage_report["near_duplicates"].get("pairwise", {}).get("train_val", {}).get("n_pairs", 0)),
            "n_near_pairs_train_test": int(leakage_report["near_duplicates"].get("pairwise", {}).get("train_test", {}).get("n_pairs", 0)),
            "n_near_pairs_val_test": int(leakage_report["near_duplicates"].get("pairwise", {}).get("val_test", {}).get("n_pairs", 0)),
            "n_near_pairs_total": int(leakage_report["near_duplicates"]["n_total_pairs"]),
            "max_split_overlap_pct": float(leakage_report["max_overlap_pct"]),
            "positive_ratio_train": float(y_train.mean()),
            "positive_ratio_val": float(y_val.mean()),
            "positive_ratio_test": float(y_test.mean()),
            "val_positive_ratio": float(y_val.mean()),
            "test_positive_ratio": float(y_test.mean()),
            "val_cap_used": bool(val_cap_used),
            "test_cap_used": bool(test_cap_used),
            "val_max_samples": int(val_max_samples) if val_max_samples is not None else None,
            "test_max_samples": int(test_max_samples) if test_max_samples is not None else None,
            "val_positive_ratio_before": float(val_positive_ratio_before),
            "val_positive_ratio_after": float(val_positive_ratio_after),
            "test_positive_ratio_before": float(test_positive_ratio_before),
            "test_positive_ratio_after": float(test_positive_ratio_after),
            "tp": int(tp),
            "tn": int(tn),
            "fp": int(fp),
            "fn": int(fn),
            "n_samples_before_dedup": int(dedup_stats["n_before"]),
            "n_samples_after_dedup": int(dedup_stats["n_after"]),
            "n_removed_by_dedup": int(dedup_stats["n_removed"]),
            "removed_ratio_by_dedup": float(dedup_stats["removed_ratio"]),
            "train_n_samples_before_dedup": int(dedup_stats["n_before"]),
            "train_n_samples_after_dedup": int(dedup_stats["n_after"]),
            "train_n_removed_by_dedup": int(dedup_stats["n_removed"]),
            "train_removed_ratio_by_dedup": float(dedup_stats["removed_ratio"]),
        },
        "provenance": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "parent_phase": PARENT_PHASE,
            "parent_variant": parent_variant,
        },
        # Bloque para MLflow — Makefile se encarga
        "mlflow_registration": {
            "experiment_name": f"F05_{prediction_name}",
            "run_name": f"{prediction_name}__{variant}",
            "metrics": {
                "val_precision": float(val_precision),
                "val_recall": float(val_recall),
                "val_f1": float(val_f1),
                "test_precision": float(test_precision),
                "test_recall": float(test_recall),
                "test_f1": float(test_f1),
                "test_tp": int(tp),
                "test_tn": int(tn),
                "test_fp": int(fp),
                "test_fn": int(fn),
            },
            "params": {
                **convert_to_native_types(best_hp),
                "model_family": model_family,
                "decision_threshold": float(decision_threshold),
                "threshold_source": str(threshold_source),
                "threshold_policy": str(threshold_policy),
            },
            "artifacts": [
                str(model_path),
                str(history_path),
                str(trials_summary_path),
            ],
        },
    }

    save_outputs_yaml(variant_dir, outputs_content)
    validate_outputs(PHASE, outputs_content)

    print(f"===== FASE {PHASE} COMPLETADA — variante {variant} =====")


if __name__ == "__main__":
    main()
