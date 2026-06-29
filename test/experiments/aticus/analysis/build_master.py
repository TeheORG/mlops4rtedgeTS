#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import hashlib
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import yaml


import matplotlib.pyplot as plt
import numpy as np



def seq_hash(seq: Any) -> str:
    return hashlib.md5(str(tuple(seq)).encode("utf-8")).hexdigest()


def stable_seq_hash(seq: Any) -> str:
    arr = np.asarray(seq, dtype=np.int32)
    if arr.size == 0:
        return "EMPTY"
    return hashlib.md5(arr.tobytes()).hexdigest()


def deduplicate_labeled_windows(df: pd.DataFrame, mode: str):
    if mode == "none":
        stats = {
            "dedup_mode_effective": "none",
            "n_before": int(len(df)),
            "n_after": int(len(df)),
            "n_removed": 0,
            "removed_ratio": 0.0,
        }
        return df.copy(), stats

    work = df.copy()
    work["_ow_hash"] = work["OW_events"].apply(stable_seq_hash)

    n_before = int(len(work))

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
    }
    return deduped, stats


def generate_f03_hashmap_image(
    parquet_path: Path,
    output_path: Path,
    *,
    max_cols: int = 2000,
    title: str | None = None,
) -> dict[str, Any]:
    """
    Genera una imagen-resumen de hashes para una variante F03.

    La imagen tiene 2 filas:
      - fila superior: PW hashes
      - fila inferior: OW hashes

    Cada hash distinto recibe un color distinto.
    Si hay demasiadas ventanas, se hace muestreo uniforme.

    Parámetros
    ----------
    parquet_path : Path
        Ruta a 03_windows.parquet
    output_path : Path
        Ruta al PNG de salida
    max_cols : int
        Nº máximo de columnas a dibujar
    title : str | None
        Título opcional de la figura

    Returns
    -------
    dict
        Estadísticas útiles para el report
    """
    if not parquet_path.exists():
        raise FileNotFoundError(f"No existe parquet: {parquet_path}")

    df = pd.read_parquet(parquet_path)

    if "OW_events" not in df.columns or "PW_events" not in df.columns:
        raise RuntimeError(
            f"{parquet_path} debe contener columnas OW_events y PW_events"
        )

    n_total = len(df)
    if n_total == 0:
        raise RuntimeError(f"Parquet vacío: {parquet_path}")

    # --------------------------------------------------------
    # Muestreo uniforme si hace falta
    # --------------------------------------------------------
    if n_total <= max_cols:
        sampled = df.copy()
        sampled_indices = np.arange(n_total)
    else:
        sampled_indices = np.linspace(0, n_total - 1, max_cols, dtype=int)
        sampled = df.iloc[sampled_indices].copy()

    # --------------------------------------------------------
    # Hashes
    # --------------------------------------------------------
    ow_hashes = sampled["OW_events"].apply(seq_hash).tolist()
    pw_hashes = sampled["PW_events"].apply(seq_hash).tolist()

    # Diccionario global hash -> entero color
    all_hashes = list(dict.fromkeys(pw_hashes + ow_hashes))
    hash_to_id = {h: i for i, h in enumerate(all_hashes)}

    pw_ids = np.array([hash_to_id[h] for h in pw_hashes], dtype=int)
    ow_ids = np.array([hash_to_id[h] for h in ow_hashes], dtype=int)

    img = np.vstack([pw_ids, ow_ids])

    # --------------------------------------------------------
    # Stats globales del sample
    # --------------------------------------------------------
    ow_counter = Counter(ow_hashes)
    pw_counter = Counter(pw_hashes)

    n_unique_ow_sample = len(ow_counter)
    n_unique_pw_sample = len(pw_counter)

    ow_unique_ratio_sample = n_unique_ow_sample / len(ow_hashes)
    pw_unique_ratio_sample = n_unique_pw_sample / len(pw_hashes)

    top1_ow_freq_sample = ow_counter.most_common(1)[0][1] if ow_counter else 0
    top1_pw_freq_sample = pw_counter.most_common(1)[0][1] if pw_counter else 0

    top5_ow_coverage_sample = (
        sum(freq for _, freq in ow_counter.most_common(5)) / len(ow_hashes)
        if ow_hashes else 0.0
    )
    top5_pw_coverage_sample = (
        sum(freq for _, freq in pw_counter.most_common(5)) / len(pw_hashes)
        if pw_hashes else 0.0
    )

    # --------------------------------------------------------
    # Plot
    # --------------------------------------------------------
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig_w = max(10, min(24, len(sampled) / 80))
    fig, ax = plt.subplots(figsize=(fig_w, 2.8))

    im = ax.imshow(img, aspect="auto", interpolation="nearest")

    ax.set_yticks([0, 1])
    ax.set_yticklabels(["PW", "OW"])
    ax.set_xticks([])

    final_title = title if title else parquet_path.stem
    ax.set_title(final_title)

    # línea separadora visual entre filas
    ax.axhline(0.5, color="white", linewidth=1.2)

    # Texto resumen abajo
    subtitle = (
        f"sampled_windows={len(sampled)} / total_windows={n_total} | "
        f"unique_pw={n_unique_pw_sample} ({pw_unique_ratio_sample:.3f}) | "
        f"unique_ow={n_unique_ow_sample} ({ow_unique_ratio_sample:.3f}) | "
        f"top5_pw_cov={top5_pw_coverage_sample:.3f} | "
        f"top5_ow_cov={top5_ow_coverage_sample:.3f}"
    )
    fig.text(0.5, 0.01, subtitle, ha="center", va="bottom", fontsize=9)

    plt.tight_layout(rect=[0, 0.06, 1, 1])
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)

    return {
        "hashmap_path": str(output_path),
        "sampled_windows": int(len(sampled)),
        "total_windows": int(n_total),
        "sampled_fraction": float(len(sampled) / n_total),
        "n_unique_ow_sample": int(n_unique_ow_sample),
        "n_unique_pw_sample": int(n_unique_pw_sample),
        "ow_unique_ratio_sample": float(ow_unique_ratio_sample),
        "pw_unique_ratio_sample": float(pw_unique_ratio_sample),
        "top1_ow_freq_sample": int(top1_ow_freq_sample),
        "top1_pw_freq_sample": int(top1_pw_freq_sample),
        "top5_ow_coverage_sample": float(top5_ow_coverage_sample),
        "top5_pw_coverage_sample": float(top5_pw_coverage_sample),
    }


def _build_hash_color_mapping(hash_values: List[str]) -> tuple[dict[str, int], np.ndarray]:
    unique_hashes = list(dict.fromkeys(hash_values))
    hash_to_id = {h: i for i, h in enumerate(unique_hashes)}
    ids = np.array([hash_to_id[h] for h in hash_values], dtype=int)
    return hash_to_id, ids


def _format_label_hash_summary(df_label: pd.DataFrame, label_value: int) -> str:
    n_windows = int(len(df_label))
    n_unique = int(df_label["_ow_hash"].nunique()) if not df_label.empty else 0
    ratio = (n_unique / n_windows) if n_windows else 0.0
    return (
        f"label {label_value}: windows={n_windows:,} | "
        f"hashes_unicos={n_unique:,} | unique_ratio={ratio:.3f}"
    )


def generate_f04_label_hash_image(
    dataset_path: Optional[Path],
    output_path: Path,
    *,
    title: str,
    df_input: Optional[pd.DataFrame] = None,
    dedup_stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if df_input is not None:
        df = df_input.copy().reset_index(drop=True)
    else:
        if dataset_path is None or not dataset_path.exists():
            raise FileNotFoundError(f"No existe parquet F04: {dataset_path}")
        df = pd.read_parquet(dataset_path).reset_index(drop=True)
    needed = {"OW_events", "label"}
    if not needed.issubset(df.columns):
        raise RuntimeError(f"{dataset_path} debe contener columnas {sorted(needed)}")
    if df.empty:
        raise RuntimeError(f"Parquet F04 vacío: {dataset_path}")

    df["_ow_hash"] = df["OW_events"].apply(stable_seq_hash)
    if "window_index" not in df.columns:
        df["window_index"] = np.arange(len(df), dtype=int)

    label0 = df[df["label"] == 0].copy()
    label1 = df[df["label"] == 1].copy()
    if label0.empty and label1.empty:
        raise RuntimeError(f"{dataset_path} no contiene filas con label 0/1")

    combined_hashes = label0["_ow_hash"].tolist() + label1["_ow_hash"].tolist()
    hash_to_id, _ = _build_hash_color_mapping(combined_hashes if combined_hashes else ["EMPTY"])

    fig, axes = plt.subplots(
        2,
        1,
        figsize=(20, 8.8),
        sharex=True,
        gridspec_kw={"height_ratios": [1, 1]},
    )

    label_frames = [
        (axes[0], label0, 0, "Negative windows (label = 0)"),
        (axes[1], label1, 1, "Positive windows (label = 1)"),
    ]

    max_index = int(df["window_index"].max()) if not df.empty else 0

    for ax, frame, label_value, subtitle in label_frames:
        if not frame.empty:
            x = frame["window_index"].to_numpy(dtype=float)
            y = np.zeros(len(frame), dtype=float)
            color_ids = np.array([hash_to_id[h] for h in frame["_ow_hash"]], dtype=int)
            ax.scatter(
                x,
                y,
                c=color_ids,
                cmap="tab20",
                marker="|",
                s=700,
                linewidths=1.5,
            )
        ax.set_xlim(-max(1, max_index * 0.01), max_index * 1.01 if max_index > 0 else 1)
        ax.set_ylim(-0.4, 0.4)
        ax.set_yticks([0])
        ax.set_yticklabels([f"label {label_value}"])
        ax.set_title(subtitle, fontsize=16, pad=8)
        ax.grid(axis="x", alpha=0.25)
        ax.text(
            0.01,
            1.02,
            _format_label_hash_summary(frame, label_value),
            transform=ax.transAxes,
            ha="left",
            va="bottom",
            fontsize=10,
            bbox=dict(boxstyle="round,pad=0.25", facecolor="white", alpha=0.9, edgecolor="#d0d0d0"),
        )

    axes[1].set_xlabel("Window index", fontsize=14)
    fig.suptitle(title, fontsize=18, y=0.98)

    if dedup_stats:
        stats_lines = [
            f"dedup_mode_effective={dedup_stats.get('dedup_mode_effective')}",
            f"n_before={int(dedup_stats.get('n_before', 0)):,}",
            f"n_after={int(dedup_stats.get('n_after', 0)):,}",
            f"n_removed={int(dedup_stats.get('n_removed', 0)):,}",
            f"removed_ratio={float(dedup_stats.get('removed_ratio', 0.0)):.3f}",
        ]
        fig.text(
            0.995,
            0.5,
            "\n".join(stats_lines),
            ha="right",
            va="center",
            fontsize=10,
            bbox=dict(boxstyle="round,pad=0.35", facecolor="white", alpha=0.95, edgecolor="#d0d0d0"),
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout(rect=[0, 0, 0.965 if dedup_stats else 1, 0.96])
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)

    return {
        "image_path": str(output_path),
        "n_total": int(len(df)),
        "n_label_0": int(len(label0)),
        "n_label_1": int(len(label1)),
        "n_unique_label_0": int(label0["_ow_hash"].nunique()) if not label0.empty else 0,
        "n_unique_label_1": int(label1["_ow_hash"].nunique()) if not label1.empty else 0,
    }


def generate_all_f04_hash_images(project_root: Path, manifest: pd.DataFrame) -> int:
    manifest_f04 = manifest[manifest["phase"].astype(str).str.contains("f04", case=False, na=False)].copy()
    generated = 0

    for _, row_manifest in manifest_f04.iterrows():
        variant_f04 = str(row_manifest["variant"])
        try:
            f04 = load_outputs(project_root, "f04_targets", variant_f04)
            f04_exports = f04.get("exports", {}) or {}
            f04_artifacts = f04.get("artifacts", {}) or {}

            dataset_rel = safe_get(f04_artifacts, "dataset", "path")
            if not dataset_rel:
                raise RuntimeError("outputs.yaml de F04 no incluye artifacts.dataset.path")

            dataset_path = resolve_artifact_path(project_root, "f04_targets", variant_f04, dataset_rel)
            window_strategy = str(f04_exports.get("window_strategy", ""))
            parent_f03 = str(f04_exports.get("parent_f03", ""))

            out_base = figures_dir(project_root) / "f04" / "hash_by_label"
            base_title = (
                f"F04 {variant_f04} - window hashes by label | "
                f"strategy={window_strategy} | parent_f03={parent_f03}"
            )
            base_output = out_base / f"{variant_f04}__hash_by_label.png"
            generate_f04_label_hash_image(dataset_path, base_output, title=base_title)
            generated += 1

            if window_strategy == "synchro":
                df = pd.read_parquet(dataset_path)
                deduped, stats = deduplicate_labeled_windows(df, mode="auto")
                auto_output = out_base / f"{variant_f04}__hash_by_label__dedup_auto.png"
                auto_title = (
                    f"F04 {variant_f04} - window hashes by label | "
                    f"strategy={window_strategy} | dedup=auto"
                )
                generate_f04_label_hash_image(
                    dataset_path=None,
                    output_path=auto_output,
                    title=auto_title,
                    df_input=deduped,
                    dedup_stats=stats,
                )
                generated += 1

        except Exception as exc:
            print(f"[WARN] Saltando hash F04 {variant_f04}: {exc}")

    return generated

# ============================================================
# HELPERS
# ============================================================


def load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML inválido: {path}")
    return data


def safe_get(d: Dict[str, Any], *keys: str, default=None):
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def discover_project_root(cli_project_root: Optional[Path]) -> Path:
    if cli_project_root is not None:
        return cli_project_root.resolve()
    return Path(__file__).resolve().parents[4]


def analysis_root(project_root: Path) -> Path:
    return project_root / "test" / "experiments" / "aticus" / "analysis"


def outputs_dir(project_root: Path) -> Path:
    return analysis_root(project_root) / "outputs"


def figures_dir(project_root: Path) -> Path:
    return analysis_root(project_root) / "figures"



def get_outputs_path(project_root: Path, phase_dir: str, variant: str) -> Path:
    return project_root / "executions" / phase_dir / variant / "outputs.yaml"


def load_outputs(project_root: Path, phase_dir: str, variant: str) -> Dict[str, Any]:
    path = get_outputs_path(project_root, phase_dir, variant)
    if not path.exists():
        raise FileNotFoundError(f"No existe outputs.yaml: {path}")
    return load_yaml(path)


def resolve_artifact_path(project_root: Path, phase_dir: str, variant: str, rel_path: str) -> Path:
    return project_root / "executions" / phase_dir / variant / rel_path


def seq_hash(seq: Any) -> str:
    return hashlib.md5(str(tuple(seq)).encode("utf-8")).hexdigest()


def safe_int(x: Any) -> Optional[int]:
    if x is None or pd.isna(x):
        return None
    return int(x)


def safe_float(x: Any) -> Optional[float]:
    if x is None or pd.isna(x):
        return None
    return float(x)


# ============================================================
# F03 PARQUET ANALYSIS
# ============================================================

def analyze_f03_parquet(dataset_path: Path) -> Dict[str, Any]:
    if not dataset_path.exists():
        raise FileNotFoundError(f"No existe parquet F03: {dataset_path}")

    df = pd.read_parquet(dataset_path)

    if "OW_events" not in df.columns or "PW_events" not in df.columns:
        raise RuntimeError(
            f"{dataset_path} debe contener columnas OW_events y PW_events"
        )

    n_rows = len(df)

    ow_lengths = df["OW_events"].apply(len)
    pw_lengths = df["PW_events"].apply(len)

    n_ow_nonempty = int((ow_lengths > 0).sum())
    n_pw_nonempty = int((pw_lengths > 0).sum())

    ow_hashes = df["OW_events"].apply(seq_hash)
    pw_hashes = df["PW_events"].apply(seq_hash)

    ow_counter = Counter(ow_hashes)
    pw_counter = Counter(pw_hashes)

    n_unique_ow = len(ow_counter)
    n_unique_pw = len(pw_counter)

    ow_unique_ratio = (n_unique_ow / n_rows) if n_rows else 0.0
    pw_unique_ratio = (n_unique_pw / n_rows) if n_rows else 0.0

    ow_common = ow_counter.most_common(5)
    pw_common = pw_counter.most_common(5)

    top1_ow_hash_freq = int(ow_common[0][1]) if ow_common else 0
    top1_pw_hash_freq = int(pw_common[0][1]) if pw_common else 0

    top5_ow_hash_coverage = (
        sum(freq for _, freq in ow_common) / n_rows if n_rows else 0.0
    )
    top5_pw_hash_coverage = (
        sum(freq for _, freq in pw_common) / n_rows if n_rows else 0.0
    )

    return {
        "n_rows_parquet": int(n_rows),
        "n_ow_nonempty": n_ow_nonempty,
        "n_pw_nonempty": n_pw_nonempty,
        "ow_unique_ratio": float(ow_unique_ratio),
        "pw_unique_ratio": float(pw_unique_ratio),
        "top1_ow_hash_freq": top1_ow_hash_freq,
        "top1_pw_hash_freq": top1_pw_hash_freq,
        "top5_ow_hash_coverage": float(top5_ow_hash_coverage),
        "top5_pw_hash_coverage": float(top5_pw_hash_coverage),
    }


# ============================================================
# F03 MASTER
# ============================================================

def build_f03_row(project_root: Path, manifest_row: pd.Series) -> Dict[str, Any]:
    variant_f03 = str(manifest_row["variant"])
    f03 = load_outputs(project_root, "f03_windows", variant_f03)

    f03_exports = f03.get("exports", {}) or {}
    f03_metrics = f03.get("metrics", {}) or {}
    f03_artifacts = f03.get("artifacts", {}) or {}

    dataset_rel = safe_get(f03_artifacts, "dataset", "path")
    dataset_path = (
        resolve_artifact_path(project_root, "f03_windows", variant_f03, dataset_rel)
        if dataset_rel else None
    )
    hashmap_path = (
        figures_dir(project_root)
        / "f03"
        / "hashmaps"
        / f"{variant_f03}.png"
    )

    hashmap_stats = generate_f03_hashmap_image(
        parquet_path=dataset_path,
        output_path=hashmap_path,
        max_cols=2000,
        title=f"F03 {variant_f03} | {f03_exports.get('window_strategy')} | "
            f"OW={f03_exports.get('OW')} PW={f03_exports.get('PW')} LT={f03_exports.get('LT')}",
    )

    parquet_stats = analyze_f03_parquet(dataset_path) if dataset_path else {}

    row = {
        # manifest
        "job_id": manifest_row.get("job_id"),
        "variant_f03": variant_f03,
        "variant_f02": manifest_row.get("parent_f02"),
        "manifest_strategy": manifest_row.get("strategy"),
        "manifest_ow": manifest_row.get("ow"),
        "manifest_pw": manifest_row.get("pw"),
        "manifest_lt": manifest_row.get("lt"),

        # config
        "window_strategy": f03_exports.get("window_strategy"),
        "Tu": f03_exports.get("Tu"),
        "OW": f03_exports.get("OW"),
        "PW": f03_exports.get("PW"),
        "LT": f03_exports.get("LT"),
        "nan_mode": f03_exports.get("nan_mode"),
        "parent_f02": f03_exports.get("parent_f02"),
        "OW/PW": f03_exports.get("OW") / f03_exports.get("PW") if f03_exports.get("PW") else None,

        # exports.yaml
        "n_windows": f03_exports.get("n_windows"),
        "n_unique_ow_hash": f03_exports.get("n_unique_ow_hash"),
        "n_unique_pw_hash": f03_exports.get("n_unique_pw_hash"),
        "dup_ratio_ow": f03_exports.get("dup_ratio_ow"),
        "dup_ratio_pw": f03_exports.get("dup_ratio_pw"),
        "seq_len_mean_ow": f03_exports.get("seq_len_mean_ow"),
        "seq_len_mean_pw": f03_exports.get("seq_len_mean_pw"),
        "seq_len_std_ow": f03_exports.get("seq_len_std_ow"),
        "seq_len_std_pw": f03_exports.get("seq_len_std_pw"),

        # metrics
        "execution_time": f03_metrics.get("execution_time"),
        "n_events_in": f03_metrics.get("n_events_in"),
        "n_windows_out": f03_metrics.get("n_windows_out"),

        # parquet recalculated
        **parquet_stats,

        # traceability
        "generated_at": safe_get(f03, "provenance", "generated_at"),
        "dataset_path": str(dataset_path) if dataset_path else None,
    }
    row.update({
        "hashmap_path": hashmap_stats["hashmap_path"],
        "sampled_windows": hashmap_stats["sampled_windows"],
        "sampled_fraction": hashmap_stats["sampled_fraction"],
        "n_unique_ow_sample": hashmap_stats["n_unique_ow_sample"],
        "n_unique_pw_sample": hashmap_stats["n_unique_pw_sample"],
        "ow_unique_ratio_sample": hashmap_stats["ow_unique_ratio_sample"],
        "pw_unique_ratio_sample": hashmap_stats["pw_unique_ratio_sample"],
        "top1_ow_freq_sample": hashmap_stats["top1_ow_freq_sample"],
        "top1_pw_freq_sample": hashmap_stats["top1_pw_freq_sample"],
        "top5_ow_coverage_sample": hashmap_stats["top5_ow_coverage_sample"],
        "top5_pw_coverage_sample": hashmap_stats["top5_pw_coverage_sample"],
    })

    return row


def build_master_f03(project_root: Path, manifest: pd.DataFrame) -> pd.DataFrame:
    manifest_f03 = manifest[manifest["phase"] == "f03"].copy()

    rows: List[Dict[str, Any]] = []
    for _, row_manifest in manifest_f03.iterrows():
        try:
            rows.append(build_f03_row(project_root, row_manifest))
        except Exception as exc:
            print(f"[WARN] Saltando F03 {row_manifest.get('variant')}: {exc}")

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    sort_cols = [c for c in ["window_strategy", "OW", "PW", "LT", "variant_f03"] if c in df.columns]
    return df.sort_values(sort_cols).reset_index(drop=True)


# ============================================================
# F04 + F05 MASTER
# ============================================================

def build_f045_row(project_root: Path, manifest_row: pd.Series) -> Dict[str, Any]:
    variant_f05 = str(manifest_row["variant"])

    f05 = load_outputs(project_root, "f05_modeling", variant_f05)

    f05_exports = f05.get("exports", {}) or {}
    f05_metrics = f05.get("metrics", {}) or {}
    f05_prov = f05.get("provenance", {}) or {}
    f05_mlflow = f05.get("mlflow_registration", {}) or {}
    f05_hp = f05_mlflow.get("params", {}) or {}

    variant_f04 = f05_exports.get("parent_f04") or f05_prov.get("parent_variant")
    variant_f03 = f05_exports.get("parent_f03")
    variant_f02 = f05_exports.get("parent_f02")

    f04 = load_outputs(project_root, "f04_targets", variant_f04) if variant_f04 else {}
    f03 = load_outputs(project_root, "f03_windows", variant_f03) if variant_f03 else {}

    f04_exports = f04.get("exports", {}) or {}
    f04_metrics = f04.get("metrics", {}) or {}

    f03_exports = f03.get("exports", {}) or {}
    f03_metrics = f03.get("metrics", {}) or {}

    dedup_stats = f04_exports.get("deduplication_stats", {}) or {}

    row = {
        # manifest
        "job_id": manifest_row.get("job_id"),
        "manifest_pipeline": manifest_row.get("pipeline"),
        "manifest_direction": manifest_row.get("direction"),
        "manifest_measure": manifest_row.get("measure"),
        "manifest_strategy": manifest_row.get("strategy"),
        "manifest_dedup": manifest_row.get("dedup"),
        "manifest_seed": manifest_row.get("seed"),
        "manifest_ow": manifest_row.get("ow"),
        "manifest_pw": manifest_row.get("pw"),
        "manifest_lt": manifest_row.get("lt"),

        # ids
        "variant_f05": variant_f05,
        "variant_f04": variant_f04,
        "variant_f03": variant_f03,
        "variant_f02": variant_f02,

        # config
        "measure_name": f05_exports.get("measure_name"),
        "prediction_name": f05_exports.get("prediction_name"),
        "direction": manifest_row.get("direction"),
        "window_strategy": f05_exports.get("window_strategy"),
        "pipeline": manifest_row.get("pipeline"),
        "deduplication_mode": f05_exports.get("deduplication_mode"),
        "deduplication_mode_effective": f05_exports.get("deduplication_mode_effective"),
        "seed": f05_exports.get("seed"),
        "model_family": f05_exports.get("model_family"),
        "Tu": f05_exports.get("Tu"),
        "OW": f05_exports.get("OW"),
        "PW": f05_exports.get("PW"),
        "LT": f05_exports.get("LT"),

        # F03 inherited
        "f03_n_windows": f03_exports.get("n_windows"),
        "f03_dup_ratio_ow": f03_exports.get("dup_ratio_ow"),
        "f03_dup_ratio_pw": f03_exports.get("dup_ratio_pw"),
        "f03_seq_len_mean_ow": f03_exports.get("seq_len_mean_ow"),
        "f03_seq_len_mean_pw": f03_exports.get("seq_len_mean_pw"),
        "f03_execution_time": f03_metrics.get("execution_time"),

        # F04
        "f04_target_operator": f04_exports.get("target_operator"),
        "f04_target_event_count": f04_exports.get("target_event_count"),
        "f04_n_windows": f04_exports.get("n_windows"),
        "f04_n_windows_pos": f04_exports.get("n_windows_pos"),
        "f04_n_windows_neg": f04_exports.get("n_windows_neg"),
        "f04_class_balance_ratio": f04_exports.get("class_balance_ratio"),
        "f04_positive_ratio": f04_metrics.get("positive_ratio"),
        "f04_total_sequences": dedup_stats.get("total_sequences"),
        "f04_unique_ow_sequences": dedup_stats.get("unique_ow_sequences"),
        "f04_num_duplicate_sequences": dedup_stats.get("num_duplicate_sequences"),
        "f04_duplicate_ratio": dedup_stats.get("duplicate_ratio"),
        "f04_ambiguous_sequences": dedup_stats.get("ambiguous_sequences"),
        "f04_ambiguous_samples": dedup_stats.get("ambiguous_samples"),
        "f04_ambiguous_ratio": dedup_stats.get("ambiguous_ratio"),
        "f04_avg_label_consistency_per_ow": dedup_stats.get("avg_label_consistency_per_ow"),
        "f04_unique_ratio": f04_exports.get("unique_ratio"),
        "f04_execution_time": f04_metrics.get("execution_time"),

        # F05
        "f05_trainable": f05_exports.get("trainable"),
        "f05_decision_threshold": f05_exports.get("decision_threshold"),
        "f05_best_f1_threshold": f05_exports.get("best_f1_threshold"),
        "f05_best_recall_threshold": f05_exports.get("best_recall_threshold"),
        "f05_best_val_recall": f05_exports.get("best_val_recall"),
        "f05_test_precision": f05_exports.get("test_precision"),
        "f05_test_recall": f05_exports.get("test_recall"),
        "f05_test_f1": f05_exports.get("test_f1"),
        "f05_imbalance_strategy": f05_exports.get("imbalance_strategy"),
        "f05_execution_time": f05_metrics.get("execution_time"),
        "f05_n_train": f05_metrics.get("n_train"),
        "f05_n_val": f05_metrics.get("n_val"),
        "f05_n_test": f05_metrics.get("n_test"),
        "f05_positive_ratio_train": f05_metrics.get("positive_ratio_train"),
        "f05_positive_ratio_val": f05_metrics.get("positive_ratio_val"),
        "f05_positive_ratio_test": f05_metrics.get("positive_ratio_test"),
        "f05_tp": f05_metrics.get("tp"),
        "f05_tn": f05_metrics.get("tn"),
        "f05_fp": f05_metrics.get("fp"),
        "f05_fn": f05_metrics.get("fn"),
        "f05_n_samples_before_dedup": f05_metrics.get("n_samples_before_dedup"),
        "f05_n_samples_after_dedup": f05_metrics.get("n_samples_after_dedup"),
        "f05_n_removed_by_dedup": f05_metrics.get("n_removed_by_dedup"),
        "f05_removed_ratio_by_dedup": f05_metrics.get("removed_ratio_by_dedup"),

        # HP
        "hp_batch_size": f05_hp.get("batch_size"),
        "hp_learning_rate": f05_hp.get("learning_rate"),
        "hp_n_layers": f05_hp.get("n_layers"),
        "hp_units": f05_hp.get("units"),
        "hp_dropout": f05_hp.get("dropout"),
        "hp_embed_dim": f05_hp.get("embed_dim"),
        "hp_filters": f05_hp.get("filters"),
        "hp_kernel_size": f05_hp.get("kernel_size"),

        # traceability
        "f05_generated_at": safe_get(f05, "provenance", "generated_at"),
        "f04_generated_at": safe_get(f04, "provenance", "generated_at"),
        "f03_generated_at": safe_get(f03, "provenance", "generated_at"),
    }

    return row


def build_master_f045(project_root: Path, manifest: pd.DataFrame) -> pd.DataFrame:
    manifest_f05 = manifest[manifest["phase"] == "f05"].copy()

    rows: List[Dict[str, Any]] = []
    for _, row_manifest in manifest_f05.iterrows():
        try:
            rows.append(build_f045_row(project_root, row_manifest))
        except Exception as exc:
            print(f"[WARN] Saltando F05 {row_manifest.get('variant')}: {exc}")

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    sort_cols = [
        c for c in [
            "measure_name",
            "direction",
            "window_strategy",
            "deduplication_mode",
            "OW",
            "PW",
            "LT",
            "seed",
            "variant_f05",
        ] if c in df.columns
    ]
    return df.sort_values(sort_cols).reset_index(drop=True)


# ============================================================
# CLI
# ============================================================

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Construye masters de análisis para Aticus")
    p.add_argument("--manifest", type=Path, required=True, help="Ruta a manifest.csv")
    p.add_argument("--project-root", type=Path, default=None, help="Root del proyecto")
    p.add_argument(
        "--mode",
        choices=["f03", "f045", "hash04", "all"],
        default="all",
        help="Qué master generar",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    project_root = discover_project_root(args.project_root)
    print(f"[INFO] Project root: {project_root}")
    manifest_path = args.manifest.resolve()

    if not manifest_path.exists():
        raise FileNotFoundError(f"No existe manifest.csv: {manifest_path}")

    out_dir = outputs_dir(project_root)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = pd.read_csv(manifest_path)

    if args.mode in {"f03", "all"}:
        df_f03 = build_master_f03(project_root, manifest)
        out_f03 = out_dir / "master_f03.csv"
        df_f03.to_csv(out_f03, index=False, encoding="utf-8")
        print(f"[OK] master_f03.csv generado en: {out_f03}")
        print(f"[OK] filas F03: {len(df_f03)}")

    if args.mode in {"f045", "all"}:
        df_f045 = build_master_f045(project_root, manifest)
        out_f045 = out_dir / "master_f045.csv"
        df_f045.to_csv(out_f045, index=False, encoding="utf-8")
        print(f"[OK] master_f045.csv generado en: {out_f045}")
        print(f"[OK] filas F045: {len(df_f045)}")

    if args.mode in {"hash04", "all"}:
        n_hash04 = generate_all_f04_hash_images(project_root, manifest)
        print(f"[OK] imágenes hash F04 generadas: {n_hash04}")
        print(f"[OK] figuras F04 en: {figures_dir(project_root) / 'f04' / 'hash_by_label'}")

    if args.mode == "all":
        print(f"[OK] Todos los masters generados en: {out_dir}")

if __name__ == "__main__":
    main()


# python test/experiments/aticus/analysis/build_master.py \
#   --manifest test/experiments/aticus/manifests/manifest_all.csv \
#   --mode all
