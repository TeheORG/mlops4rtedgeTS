#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd



# ============================================================
# CLI
# ============================================================

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Genera report.html para Aticus")
    p.add_argument("--project-root", type=Path, default=None, help="Root del proyecto")
    p.add_argument("--master-f03", type=Path, default=None, help="Ruta a master_f03.csv")
    p.add_argument("--output-html", type=Path, default=None, help="Ruta de salida del HTML")
    return p.parse_args()


# ============================================================
# PATHS
# ============================================================

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


# ============================================================
# HELPERS
# ============================================================

def fmt_float(x: Any, ndigits: int = 4) -> str:
    if x is None or pd.isna(x):
        return ""
    return f"{float(x):.{ndigits}f}"


def fmt_sci(x: Any) -> str:
    if x is None or pd.isna(x):
        return ""
    return f"{float(x):.6e}"


def human_time(raw: Any, tu: int = 10) -> str:
    if raw is None or pd.isna(raw):
        return ""
    seconds = float(raw) * float(tu)
    if seconds % 3600 == 0:
        return f"{int(seconds // 3600)}h"
    if seconds % 60 == 0:
        return f"{int(seconds // 60)}min"
    return f"{int(seconds)}s"


def sanitize_filename(text: str) -> str:
    return (
        str(text)
        .strip()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
        .replace("[", "")
        .replace("]", "")
        .replace(":", "_")
        .replace("|", "_")
    )


def save_current_figure(path: Path, *, use_tight_layout: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if use_tight_layout:
        plt.tight_layout()
    plt.savefig(path, dpi=170, bbox_inches="tight")
    plt.close()


def table_html(df: pd.DataFrame) -> str:
    if df.empty:
        return "<p>No hay datos.</p>"
    return df.to_html(index=False, classes="tbl", escape=False)


def metric_to_color(val: Any, vmin: float, vmax: float, invert: bool = False) -> str:
    if val is None or pd.isna(val):
        return "#f0f0f0"

    if vmax <= vmin:
        t = 0.5
    else:
        t = (float(val) - vmin) / (vmax - vmin)

    t = max(0.0, min(1.0, t))
    if invert:
        t = 1.0 - t

    if t < 0.5:
        a = t / 0.5
        r1, g1, b1 = (220, 53, 69)
        r2, g2, b2 = (255, 193, 7)
    else:
        a = (t - 0.5) / 0.5
        r1, g1, b1 = (255, 193, 7)
        r2, g2, b2 = (25, 135, 84)

    r = int(r1 + a * (r2 - r1))
    g = int(g1 + a * (g2 - g1))
    b = int(b1 + a * (b2 - b1))
    return f"rgb({r},{g},{b})"


# ============================================================
# AGGREGATIONS
# ============================================================

def build_f03_summary(master_f03: pd.DataFrame) -> pd.DataFrame:
    if master_f03.empty:
        return pd.DataFrame()

    group_cols = ["window_strategy", "OW", "PW", "LT"]

    summary = (
        master_f03.groupby(group_cols, dropna=False)
        .agg(
            n_variants=("variant_f03", "count"),
            n_windows_mean=("n_windows", "mean"),
            dup_ratio_ow_mean=("dup_ratio_ow", "mean"),
            dup_ratio_pw_mean=("dup_ratio_pw", "mean"),
            seq_len_mean_ow_mean=("seq_len_mean_ow", "mean"),
            seq_len_mean_pw_mean=("seq_len_mean_pw", "mean"),
            seq_len_std_ow_mean=("seq_len_std_ow", "mean"),
            seq_len_std_pw_mean=("seq_len_std_pw", "mean"),
            ow_unique_ratio_mean=("ow_unique_ratio", "mean"),
            pw_unique_ratio_mean=("pw_unique_ratio", "mean"),
            top5_ow_hash_coverage_mean=("top5_ow_hash_coverage", "mean"),
            top5_pw_hash_coverage_mean=("top5_pw_hash_coverage", "mean"),
            execution_time_mean=("execution_time", "mean"),
        )
        .reset_index()
    )

    return summary


# ============================================================
# PLOTS — COMMON
# ============================================================



def make_dual_strategy_heatmap(
    df: pd.DataFrame,
    metric_col: str,
    metric_title: str,
    output_path: Path,
    *,
    strategy_col: str = "window_strategy",
    index_col: str = "OW",
    column_col: str = "PW",
    strategies: Tuple[str, str] = ("synchro", "asynOW"),
    time_axes: bool = True,
    cmap: str = "viridis",
    annotate: bool = True,
    value_fmt: str = ".3f",
) -> Optional[Path]:
    """
    Genera una figura con dos heatmaps comparables (uno por estrategia)
    usando exactamente la misma escala de color.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame con una fila por configuración.
    metric_col : str
        Columna de la métrica a representar.
    metric_title : str
        Título general de la figura.
    output_path : Path
        Ruta del PNG de salida.
    strategy_col : str
        Nombre de la columna de estrategia.
    index_col : str
        Columna para eje Y (normalmente OW).
    column_col : str
        Columna para eje X (normalmente PW).
    strategies : tuple[str, str]
        Estrategias a comparar.
    time_axes : bool
        Si True, usa human_time en los ejes.
    cmap : str
        Colormap de matplotlib.
    annotate : bool
        Si True, escribe el valor en cada celda.
    value_fmt : str
        Formato numérico, por ejemplo ".3f" o ".0f".
    """
    needed = [strategy_col, index_col, column_col, metric_col]
    if df.empty or not all(c in df.columns for c in needed):
        return None

    sub = df[needed].dropna().copy()
    if sub.empty:
        return None

    # Mantener solo estrategias presentes
    strategies_present = [s for s in strategies if s in set(sub[strategy_col].astype(str))]
    if not strategies_present:
        return None

    # Construir pivots
    pivots: Dict[str, pd.DataFrame] = {}
    all_index_vals = set()
    all_col_vals = set()

    for strategy in strategies_present:
        ssub = sub[sub[strategy_col].astype(str) == strategy].copy()
        if ssub.empty:
            continue

        pivot = ssub.pivot_table(
            index=index_col,
            columns=column_col,
            values=metric_col,
            aggfunc="mean",
        )
        if pivot.empty:
            continue

        pivots[strategy] = pivot
        all_index_vals.update([x for x in pivot.index if not pd.isna(x)])
        all_col_vals.update([x for x in pivot.columns if not pd.isna(x)])

    if not pivots:
        return None

    # Orden común en ambos heatmaps
    common_index = sorted(all_index_vals, reverse=True)
    common_cols = sorted(all_col_vals)

    for strategy in list(pivots.keys()):
        pivots[strategy] = pivots[strategy].reindex(index=common_index, columns=common_cols)

    # Escala global compartida
    all_values = []
    for pivot in pivots.values():
        arr = pivot.values.astype(float).ravel()
        arr = arr[~np.isnan(arr)]
        if len(arr):
            all_values.extend(arr.tolist())

    if not all_values:
        return None

    vmin = float(np.min(all_values))
    vmax = float(np.max(all_values))

    # Evitar problemas si todos los valores coinciden
    if np.isclose(vmin, vmax):
        vmax = vmin + 1e-9

    fig, axes = plt.subplots(
        1,
        len(strategies_present),
        figsize=(6.8 * len(strategies_present), 5.4),
        squeeze=False,
    )
    axes = axes[0]

    im = None
    for ax, strategy in zip(axes, strategies_present):
        pivot = pivots[strategy]
        arr = pivot.values.astype(float)

        im = ax.imshow(arr, aspect="auto", cmap=cmap, vmin=vmin, vmax=vmax)

        ax.set_title(strategy)
        ax.set_xlabel(column_col)
        ax.set_ylabel(index_col)

        ax.set_xticks(np.arange(len(pivot.columns)))
        ax.set_yticks(np.arange(len(pivot.index)))

        if time_axes:
            ax.set_xticklabels([human_time(x) for x in pivot.columns], rotation=20, ha="right")
            ax.set_yticklabels([human_time(x) for x in pivot.index])
        else:
            ax.set_xticklabels([str(x) for x in pivot.columns], rotation=20, ha="right")
            ax.set_yticklabels([str(x) for x in pivot.index])

        if annotate:
            for i in range(arr.shape[0]):
                for j in range(arr.shape[1]):
                    val = arr[i, j]
                    if np.isnan(val):
                        continue
                    txt = format(val, value_fmt)
                    ax.text(j, i, txt, ha="center", va="center", fontsize=9, color="black")

    fig.suptitle(metric_title, fontsize=16, y=0.98)
    fig.subplots_adjust(top=0.84, right=0.90, wspace=0.30)

    cbar = fig.colorbar(im, ax=axes.tolist(), fraction=0.035, pad=0.06)
    cbar.set_label(metric_col)

    save_current_figure(output_path, use_tight_layout=False)
    return output_path

def make_correlation_heatmap(
    df: pd.DataFrame,
    columns: list[str],
    title: str,
    output_path: Path,
    method: str = "spearman",
) -> Optional[Path]:
    """
    Genera un heatmap de correlación para las columnas indicadas.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame de entrada.
    columns : list[str]
        Columnas numéricas a analizar.
    title : str
        Título de la figura.
    output_path : Path
        Ruta del PNG de salida.
    method : str
        'pearson' o 'spearman'. Para tu caso recomiendo spearman.

    Returns
    -------
    Optional[Path]
        Ruta si se generó la figura, None si no había datos suficientes.
    """
    valid_cols = [c for c in columns if c in df.columns]
    if len(valid_cols) < 2:
        return None

    sub = df[valid_cols].copy()

    # convertir a numérico por seguridad
    for c in valid_cols:
        sub[c] = pd.to_numeric(sub[c], errors="coerce")

    # quitar columnas constantes o totalmente vacías
    keep_cols = []
    for c in valid_cols:
        series = sub[c].dropna()
        if len(series) >= 2 and series.nunique() >= 2:
            keep_cols.append(c)

    if len(keep_cols) < 2:
        return None

    sub = sub[keep_cols].dropna(axis=0, how="any")
    if len(sub) < 3:
        return None

    corr = sub.corr(method=method)

    plt.figure(figsize=(max(8, len(corr) * 0.8), max(6, len(corr) * 0.7)))
    ax = plt.gca()

    arr = corr.values
    im = ax.imshow(arr, vmin=-1.0, vmax=1.0, aspect="auto")

    ax.set_xticks(np.arange(len(corr.columns)))
    ax.set_yticks(np.arange(len(corr.index)))
    ax.set_xticklabels(corr.columns, rotation=45, ha="right")
    ax.set_yticklabels(corr.index)

    ax.set_title(title)

    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            val = arr[i, j]
            txt = "" if np.isnan(val) else f"{val:.2f}"
            ax.text(j, i, txt, ha="center", va="center", fontsize=8, color="black")

    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    save_current_figure(output_path)
    return output_path

def get_top_correlations(
    df: pd.DataFrame,
    target_col: str,
    candidate_cols: list[str],
    method: str = "spearman",
    top_k: int = 8,
) -> pd.DataFrame:
    valid_cols = [c for c in candidate_cols if c in df.columns]
    if target_col not in df.columns:
        return pd.DataFrame(columns=["feature", "correlation"])

    sub = df[[target_col] + valid_cols].copy()

    for c in sub.columns:
        sub[c] = pd.to_numeric(sub[c], errors="coerce")

    # quitar columnas constantes
    keep_cols = [target_col]
    for c in valid_cols:
        s = sub[c].dropna()
        if len(s) >= 2 and s.nunique() >= 2:
            keep_cols.append(c)

    sub = sub[keep_cols].dropna(axis=0, how="any")
    if len(sub) < 3:
        return pd.DataFrame(columns=["feature", "correlation"])

    corr = sub.corr(method=method)[target_col].drop(labels=[target_col], errors="ignore")
    corr = corr.dropna()

    if corr.empty:
        return pd.DataFrame(columns=["feature", "correlation"])

    out = (
        corr.abs()
        .sort_values(ascending=False)
        .head(top_k)
        .index.to_series()
        .rename("feature")
        .to_frame()
    )
    out["correlation"] = out["feature"].map(corr)
    return out.reset_index(drop=True)

def make_heatmap_from_df(
    df: pd.DataFrame,
    index_col: str,
    column_col: str,
    value_col: str,
    title: str,
    xlabel: str,
    ylabel: str,
    output_path: Path,
    time_axes: bool = True,
) -> Optional[Path]:
    if df.empty or value_col not in df.columns:
        return None

    pivot = df.pivot_table(index=index_col, columns=column_col, values=value_col, aggfunc="mean")
    if pivot.empty:
        return None

    # Orden OW desc, PW asc
    idx_sorted = sorted([x for x in pivot.index if not pd.isna(x)], reverse=True)
    col_sorted = sorted([x for x in pivot.columns if not pd.isna(x)])

    pivot = pivot.reindex(index=idx_sorted, columns=col_sorted)

    arr = pivot.values.astype(float)

    plt.figure(figsize=(8, 5.5))
    ax = plt.gca()
    im = ax.imshow(arr, aspect="auto")

    ax.set_xticks(np.arange(len(pivot.columns)))
    ax.set_yticks(np.arange(len(pivot.index)))

    if time_axes:
        ax.set_xticklabels([human_time(c) for c in pivot.columns])
        ax.set_yticklabels([human_time(i) for i in pivot.index])
    else:
        ax.set_xticklabels([str(c) for c in pivot.columns], rotation=20, ha="right")
        ax.set_yticklabels([str(i) for i in pivot.index])

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)

    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            val = arr[i, j]
            txt = "" if np.isnan(val) else f"{val:.3f}"
            ax.text(j, i, txt, ha="center", va="center", fontsize=9, color="black")

    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    save_current_figure(output_path)
    return output_path


def make_bar_from_series(
    series: pd.Series,
    title: str,
    ylabel: str,
    output_path: Path,
    rotation: int = 20,
) -> Optional[Path]:
    if series.empty:
        return None

    plt.figure(figsize=(8, 5))
    x = np.arange(len(series))
    plt.bar(x, series.values)
    plt.xticks(x, series.index, rotation=rotation, ha="right")
    plt.ylabel(ylabel)
    plt.title(title)
    save_current_figure(output_path)
    return output_path


def make_scatter(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    label_cols: List[str],
    title: str,
    xlabel: str,
    ylabel: str,
    output_path: Path,
) -> Optional[Path]:
    needed = [x_col, y_col] + label_cols
    sub = df[needed].dropna().copy() if all(c in df.columns for c in needed) else pd.DataFrame()
    if sub.empty:
        return None

    plt.figure(figsize=(7, 6))
    plt.scatter(sub[x_col], sub[y_col], alpha=0.7)

    for _, r in sub.iterrows():
        label = " | ".join(str(r[c]) for c in label_cols)
        plt.annotate(label, (r[x_col], r[y_col]), fontsize=7, alpha=0.8)

    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title(title)
    save_current_figure(output_path)
    return output_path


def make_f03_dup_config_comparison(
    master_f03: pd.DataFrame,
    output_path: Path,
  ) -> Optional[Path]:
    needed = ["window_strategy", "OW", "PW", "dup_ratio_ow", "dup_ratio_pw"]
    if master_f03.empty or not all(c in master_f03.columns for c in needed):
      return None

    sub = master_f03.copy()
    sub = sub[sub["window_strategy"].isin(["synchro", "asynOW"])].copy()
    if sub.empty:
      return None

    # Mantener una fila por combinación para evitar duplicados accidentales.
    dedup_cols = ["window_strategy", "OW", "PW", "dup_ratio_ow", "dup_ratio_pw"]
    if "generated_at" in sub.columns:
      sub = sub.sort_values("generated_at").drop_duplicates(
        subset=["window_strategy", "OW", "PW"],
        keep="last",
      )
    else:
      sub = sub.drop_duplicates(subset=dedup_cols, keep="first")

    if sub.empty:
      return None

    config_df = (
      sub[["OW", "PW"]]
      .drop_duplicates()
      .sort_values(["OW", "PW"], ascending=[False, True])
    )
    if config_df.empty:
      return None

    config_pairs = [tuple(x) for x in config_df[["OW", "PW"]].to_numpy()]
    config_labels = [f"OW={human_time(ow)} | PW={human_time(pw)}" for ow, pw in config_pairs]

    strategies = [s for s in ["synchro", "asynOW"] if s in set(sub["window_strategy"])]
    if not strategies:
      return None

    fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
    x = np.arange(len(config_pairs))
    width = 0.38 if len(strategies) == 2 else 0.6

    metric_specs = [
      ("dup_ratio_ow", "Duplicación OW"),
      ("dup_ratio_pw", "Duplicación PW"),
    ]

    for ax, (metric, title) in zip(axes, metric_specs):
      for i, strategy in enumerate(strategies):
        vals: List[float] = []
        for ow, pw in config_pairs:
          row = sub[
            (sub["window_strategy"] == strategy)
            & (sub["OW"] == ow)
            & (sub["PW"] == pw)
          ]
          vals.append(float(row.iloc[0][metric]) if not row.empty else np.nan)

        offset = (i - (len(strategies) - 1) / 2.0) * width
        bars = ax.bar(x + offset, vals, width=width, label=strategy)

        labels = ["" if np.isnan(v) else f"{v:.4f}" for v in vals]
        ax.bar_label(bars, labels=labels, padding=3, fontsize=8)

      ax.set_title(title)
      ax.set_xticks(x)
      ax.set_xticklabels(config_labels, rotation=20, ha="right")
      ax.set_xlabel("Configuración OW/PW")
      ax.grid(axis="y", alpha=0.2)
      ax.margins(y=0.15)

    axes[0].set_ylabel("Ratio de duplicación")
    axes[-1].legend(title="Estrategia")
    fig.suptitle("F03: Duplicación por configuración OW/PW (sin medias)")

    save_current_figure(output_path)
    return output_path


# ============================================================
# PLOTS — F03
# ============================================================

def _make_f03_dup_grouped_by_strategy_plot(
    master_f03: pd.DataFrame,
    output_path: Path,
) -> Optional[Path]:
    needed = ["window_strategy", "OW", "PW", "dup_ratio_ow", "dup_ratio_pw"]
    if master_f03.empty or not all(c in master_f03.columns for c in needed):
        return None

    sub = master_f03.copy()
    sub = sub[sub["window_strategy"].isin(["synchro", "asynOW"])].copy()
    if sub.empty:
        return None

    if "generated_at" in sub.columns:
        sub = (
            sub.sort_values("generated_at")
            .drop_duplicates(subset=["window_strategy", "OW", "PW"], keep="last")
        )
    else:
        sub = sub.drop_duplicates(subset=["window_strategy", "OW", "PW"], keep="last")

    if sub.empty:
        return None

    config_df = (
        sub[["OW", "PW"]]
        .drop_duplicates()
        .sort_values(["OW", "PW"], ascending=[False, True])
    )
    if config_df.empty:
        return None

    config_pairs = [tuple(x) for x in config_df[["OW", "PW"]].to_numpy()]
    config_labels = [f"OW={human_time(ow)}\nPW={human_time(pw)}" for ow, pw in config_pairs]

    strategies = ["synchro", "asynOW"]
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), sharey=True)
    bar_width = 0.34

    for ax, strategy in zip(axes, strategies):
        ssub = sub[sub["window_strategy"] == strategy].copy()

        ow_vals = []
        pw_vals = []

        for ow, pw in config_pairs:
            row = ssub[(ssub["OW"] == ow) & (ssub["PW"] == pw)]
            if row.empty:
                ow_vals.append(np.nan)
                pw_vals.append(np.nan)
            else:
                ow_vals.append(float(row.iloc[0]["dup_ratio_ow"]))
                pw_vals.append(float(row.iloc[0]["dup_ratio_pw"]))

        x = np.arange(len(config_pairs))

        bars_ow = ax.bar(x - bar_width / 2, ow_vals, width=bar_width, label="OW")
        bars_pw = ax.bar(x + bar_width / 2, pw_vals, width=bar_width, label="PW")

        ax.set_title(strategy)
        ax.set_xticks(x)
        ax.set_xticklabels(config_labels)
        ax.set_xlabel("Configuración")
        ax.grid(axis="y", alpha=0.2)
        ax.margins(y=0.18)

        ax.bar_label(
            bars_ow,
            labels=[("" if np.isnan(v) else f"{v:.4f}") for v in ow_vals],
            padding=3,
            fontsize=8,
        )
        ax.bar_label(
            bars_pw,
            labels=[("" if np.isnan(v) else f"{v:.4f}") for v in pw_vals],
            padding=3,
            fontsize=8,
        )

    axes[0].set_ylabel("Ratio de duplicación")
    axes[1].legend(title="Ventana")
    fig.suptitle("Comparación de duplicación OW/PW por configuración y estrategia")

    save_current_figure(output_path)
    return output_path

def make_f03_dup_grouped_by_strategy(
    project_root: Path,
    master_f03: pd.DataFrame,
) -> Dict[str, Path]:
    fig_root = figures_dir(project_root) / "f03"
    fig_root.mkdir(parents=True, exist_ok=True)

    figure_paths: Dict[str, Path] = {}

    output_path = fig_root / "grouped_dup_ow_pw_by_config_and_strategy.png"
    p = _make_f03_dup_grouped_by_strategy_plot(master_f03, output_path)

    if p is not None:
        figure_paths["f03_grouped_dup_ow_pw_by_config_and_strategy"] = p

    return figure_paths

def generate_f03_comparison_heatmaps(
    project_root: Path,
    master_f03: pd.DataFrame,
) -> Dict[str, Path]:
    fig_root = figures_dir(project_root) / "f03"
    fig_root.mkdir(parents=True, exist_ok=True)
    out = fig_root / "grouped_dup_ow_pw_by_config_and_strategy.png"
    figure_paths: Dict[str, Path] = {}

    if master_f03.empty:
        return figure_paths

    metric_specs: List[Tuple[str, str, str]] = [
        ("execution_time", "Comparación de tiempo de ejecución", ".3f"),
        ("n_windows", "Comparación de número de ventanas", ".0f"),
        ("dup_ratio_ow", "Comparación de duplicación OW", ".3f"),
        ("dup_ratio_pw", "Comparación de duplicación PW", ".3f"),
        ("ow_unique_ratio", "Comparación de unicidad OW", ".3f"),
        ("pw_unique_ratio", "Comparación de unicidad PW", ".3f"),
        ("n_unique_ow_hash", "Comparación de hashes únicos OW", ".0f"),
        ("n_unique_pw_hash", "Comparación de hashes únicos PW", ".0f"),
        ("seq_len_mean_ow", "Comparación de longitud media OW", ".1f"),
        ("seq_len_mean_pw", "Comparación de longitud media PW", ".1f"),
        ("seq_len_std_ow", "Comparación de dispersión longitud OW", ".1f"),
        ("seq_len_std_pw", "Comparación de dispersión longitud PW", ".1f"),
        ("top5_ow_hash_coverage", "Comparación de cobertura top5 OW", ".3f"),
        ("top5_pw_hash_coverage", "Comparación de cobertura top5 PW", ".3f"),
    ]

    for metric_col, metric_title, value_fmt in metric_specs:
        if metric_col not in master_f03.columns:
            continue

        out = fig_root / f"dual_heatmap__{metric_col}.png"
        p = make_dual_strategy_heatmap(
            master_f03,
            metric_col=metric_col,
            metric_title=metric_title,
            output_path=out,
            strategy_col="window_strategy",
            index_col="OW",
            column_col="PW",
            strategies=("synchro", "asynOW"),
            time_axes=True,
            cmap="viridis",
            annotate=True,
            value_fmt=value_fmt,
        )
        if p is not None:
            figure_paths[f"f03_dual_heatmap__{metric_col}"] = p

    return figure_paths


def generate_f03_figures(
    project_root: Path,
    f03_summary: pd.DataFrame,
    master_f03: pd.DataFrame,
) -> Dict[str, Path]:
    fig_root = figures_dir(project_root) / "f03"
    fig_root.mkdir(parents=True, exist_ok=True)

    figure_paths: Dict[str, Path] = {}

    if not f03_summary.empty and "window_strategy" in f03_summary.columns:
        bar_specs = [
            ("ow_unique_ratio_mean", "Unicidad OW media por estrategia", "Ratio medio de unicidad", "f03_bar_ow_unique_ratio_by_strategy"),
            ("execution_time_mean", "Tiempo medio de ejecución por estrategia", "Tiempo medio (s)", "f03_bar_execution_time_by_strategy"),
        ]

        for metric_col, title, ylabel, key in bar_specs:
            if metric_col not in f03_summary.columns:
                continue
            series = (
                f03_summary.groupby("window_strategy", dropna=False)[metric_col]
                .mean()
                .sort_index()
            )
            out = fig_root / f"{key}.png"
            p = make_bar_from_series(series, title=title, ylabel=ylabel, output_path=out)
            if p is not None:
                figure_paths[key] = p

    p = make_f03_dup_config_comparison(
        master_f03,
        fig_root / "f03_bar_dup_ratio_ow_pw_by_config_synchro_asynOW.png",
    )
    if p is not None:
        figure_paths["f03_bar_dup_ratio_ow_pw_by_config_synchro_asynOW"] = p

    figure_paths.update(make_f03_dup_grouped_by_strategy(project_root, master_f03))
    figure_paths.update(generate_f03_comparison_heatmaps(project_root, master_f03))
    return figure_paths


def build_hash_concentration_explanation(row: pd.Series) -> str:
    def get_float(col: str) -> Optional[float]:
        try:
            return float(row[col]) if col in row and not pd.isna(row[col]) else None
        except Exception:
            return None

    def get_int(col: str) -> Optional[int]:
        try:
            return int(float(row[col])) if col in row and not pd.isna(row[col]) else None
        except Exception:
            return None

    def pct(x: Optional[float]) -> str:
        return "N/A" if x is None else f"{100*x:.1f}%"

    def explain(name: str, dup: Optional[float], top1: Optional[int], top5: Optional[float]) -> str:
        if dup is None or top5 is None:
            return ""

        if top5 < 0.05:
            concentration = "muy baja"
            verdict = (
                "Los 5 patrones más frecuentes representan una fracción mínima del dataset, "
                "lo que indica una distribución muy dispersa y alta diversidad estructural."
            )

        elif top5 < 0.15:
            concentration = "baja"
            verdict = (
                "Existe cierta recurrencia en algunos patrones, pero la mayor parte del dataset "
                "sigue distribuida entre muchos hashes (secuencias) distintos."
            )

        elif top5 < 0.30:
            concentration = "moderada"
            verdict = (
        "Los patrones más frecuentes ya concentran una parte relevante del dataset, "
        "indicando que ciertas estructuras empiezan a repetirse con notable frecuencia. "
        "No obstante, la distribución aún conserva diversidad suficiente y no puede considerarse colapsada."
    )

        else:
            concentration = "alta"
            verdict = (
            "Los hashes dominantes concentran una fracción excesiva del dataset, "
            "indicando que gran parte de las muestras pertenece a un conjunto muy reducido de patrones repetidos. "
            "Esto sugiere pérdida relevante de diversidad y posible colapso estructural parcial."
                )

        if dup < 0.20:
            dup_text = "duplicación baja"
        elif dup < 0.50:
            dup_text = "duplicación moderada"
        elif dup < 0.75:
            dup_text = "duplicación alta"
        else:
            dup_text = "duplicación muy alta"

        return f"""
        <div class="hash-insight-block">
          <div class="hash-insight-title">{name}</div>
          <ul>
            <li><strong>Duplicación:</strong> {pct(dup)} ({dup_text})</li>
            <li><strong>Hash más frecuente:</strong> {top1:,} apariciones</li>
            <li><strong>Top 5 hashes:</strong> {pct(top5)} del dataset</li>
            <li><strong>Concentración:</strong> {concentration}</li>
          </ul>
          <p class="hash-insight-verdict">{verdict}</p>
        </div>
        """

    return f"""
    <div class="hash-insight-wrapper">
      {explain(
          "OW",
          get_float("dup_ratio_ow"),
          get_int("top1_ow_hash_freq"),
          get_float("top5_ow_hash_coverage"),
      )}
      {explain(
          "PW",
          get_float("dup_ratio_pw"),
          get_int("top1_pw_hash_freq"),
          get_float("top5_pw_hash_coverage"),
      )}
    </div>
    """


def make_seq_len_distribution_plot(
    row: pd.Series,
    output_path: Path,
) -> Optional[Path]:
    needed = [
        "variant_f03",
        "seq_len_mean_ow",
        "seq_len_mean_pw",
        "seq_len_std_ow",
        "seq_len_std_pw",
    ]
    if not all(c in row.index for c in needed):
        return None

    try:
        mean_ow = float(row["seq_len_mean_ow"])
        mean_pw = float(row["seq_len_mean_pw"])
        std_ow = float(row["seq_len_std_ow"])
        std_pw = float(row["seq_len_std_pw"])
    except Exception:
        return None

    labels = ["OW", "PW"]
    means = [mean_ow, mean_pw]
    stds = [std_ow, std_pw]
    lefts = [max(0.0, m - s) for m, s in zip(means, stds)]
    rights = [m + s for m, s in zip(means, stds)]

    max_right = max(rights) if rights else 1.0
    x_max = max_right * 1.18 if max_right > 0 else 1.0

    fig, ax = plt.subplots(figsize=(7.6, 3.8))
    y_positions = np.array([1, 0], dtype=float)

    # Carril de fondo
    for y in y_positions:
        ax.barh(y, x_max, left=0, height=0.26, alpha=0.08, edgecolor="none", zorder=0)

    # Rango aproximado [max(0, mean-std), mean+std]
    widths = [r - l for l, r in zip(lefts, rights)]
    ax.barh(
        y_positions,
        widths,
        left=lefts,
        height=0.26,
        alpha=0.75,
        edgecolor="none",
        zorder=2,
    )

    # Punto de media
    ax.scatter(means, y_positions, s=110, zorder=3)

    # Línea guía vertical en la media
    for y, m in zip(y_positions, means):
        ax.vlines(m, y - 0.18, y + 0.18, linewidth=2, zorder=4)

    # Etiquetas compactas a la derecha, sin montarse sobre la figura
    label_x = x_max * 0.985
    for y, m, s, l, r in zip(y_positions, means, stds, lefts, rights):
        ax.text(
            label_x,
            y,
            f"μ={m:.1f}   σ={s:.1f}   [{l:.1f}, {r:.1f}]",
            va="center",
            ha="right",
            fontsize=9,
            bbox=dict(
                boxstyle="round,pad=0.25",
                facecolor="white",
                alpha=0.95,
                edgecolor="#d9d9d9",
            ),
            zorder=5,
        )

    ax.set_yticks(y_positions)
    ax.set_yticklabels(labels, fontsize=12)
    ax.set_xlabel("Eventos por ventana")
    ax.set_title(f"{row.get('variant_f03', '')} — Longitud de secuencias", pad=10)

    ax.set_xlim(0, x_max)
    ax.set_ylim(-0.5, 1.5)
    ax.grid(axis="x", alpha=0.22)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    save_current_figure(output_path)
    return output_path

def make_f03_window_occupancy_plot(
    row: pd.Series,
    output_path: Path,
) -> Optional[Path]:
    needed = ["variant_f03", "n_windows", "n_ow_nonempty", "n_pw_nonempty"]
    if not all(c in row.index for c in needed):
        return None

    try:
        total = float(row["n_windows"])
        ow_nonempty = float(row["n_ow_nonempty"])
        pw_nonempty = float(row["n_pw_nonempty"])
    except Exception:
        return None

    if total <= 0:
        return None

    labels = [ "OW no vacía", "PW no vacía"]
    values = [ ow_nonempty, pw_nonempty]

    plt.figure(figsize=(6.5, 3.8))
    ax = plt.gca()
    x = np.arange(len(labels))
    bars = ax.bar(x, values)

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Número de ventanas")
    ax.set_title(f"{row.get('variant_f03', '')} — ocupación de ventanas")
    ax.grid(axis="y", alpha=0.2)

    # El máximo del eje Y debe ser el total de ventanas de la variante.
    ax.set_ylim(0, total)

    bar_labels = [
        f"{int(v):,}\n({(v / total) * 100:.1f}%)"
        for v in values
    ]
    ax.bar_label(
        bars,
        labels=bar_labels,
        label_type="center",
        fontsize=9,
        color="white",
    )

    save_current_figure(output_path)
    return output_path



# ============================================================
# TABLE STYLING
# ============================================================

def styled_f03_table(f03_summary: pd.DataFrame) -> str:
    if f03_summary.empty:
        return "<p>No hay configuraciones F03.</p>"

    df = f03_summary.copy()
    df["OW_h"] = df["OW"].map(human_time)
    df["PW_h"] = df["PW"].map(human_time)
    df["LT_h"] = df["LT"].map(human_time)

    for c in [
        "dup_ratio_ow_mean",
        "dup_ratio_pw_mean",
        "ow_unique_ratio_mean",
        "pw_unique_ratio_mean",
        "top5_ow_hash_coverage_mean",
        "top5_pw_hash_coverage_mean",
        "seq_len_mean_ow_mean",
        "seq_len_mean_pw_mean",
        "execution_time_mean",
    ]:
        if c in df.columns:
            df[c] = df[c].map(fmt_float)

    cols = [
        "window_strategy",
        "OW_h",
        "PW_h",
        "LT_h",
        "n_windows_mean",
        "dup_ratio_ow_mean",
        "dup_ratio_pw_mean",
        "ow_unique_ratio_mean",
        "pw_unique_ratio_mean",
        "seq_len_mean_ow_mean",
        "execution_time_mean",
    ]
    cols = [c for c in cols if c in df.columns]
    return table_html(df[cols])


def styled_f045_table(f045_summary: pd.DataFrame) -> str:
    if f045_summary.empty:
        return "<p>No hay configuraciones F04+F05.</p>"

    df = f045_summary.copy()
    df["OW_h"] = df["OW"].map(human_time)
    df["PW_h"] = df["PW"].map(human_time)
    df["LT_h"] = df["LT"].map(human_time)

    for c in [
        "f05_test_f1_mean",
        "f05_test_recall_mean",
        "f05_test_precision_mean",
        "f05_best_val_recall_mean",
        "f03_dup_ratio_ow_mean",
        "f04_duplicate_ratio_mean",
        "f04_ambiguous_ratio_mean",
        "f05_execution_time_mean",
    ]:
        if c in df.columns:
            df[c] = df[c].map(fmt_float)

    if "f04_positive_ratio_mean" in df.columns:
        df["f04_positive_ratio_mean"] = df["f04_positive_ratio_mean"].map(fmt_sci)

    cols = [
        "measure_direction",
        "pipeline",
        "OW_h",
        "PW_h",
        "LT_h",
        "f05_test_f1_mean",
        "f05_test_recall_mean",
        "f05_test_precision_mean",
        "f04_positive_ratio_mean",
        "f04_ambiguous_ratio_mean",
        "decision",
    ]
    cols = [c for c in cols if c in df.columns]
    return table_html(df[cols])


# ============================================================
# HTML
# ============================================================


def build_html(
    project_root: Path,
    master_f03: pd.DataFrame,
    f03_summary: pd.DataFrame,
    fig_f03: Dict[str, Path],
) -> str:
    analysis_base = analysis_root(project_root)

    def safe_val(row: pd.Series, col: str, default: str = "") -> Any:
        if col not in row or pd.isna(row[col]):
            return default
        return row[col]

    def fmt_int(x: Any) -> str:
        if x is None or x == "" or pd.isna(x):
            return ""
        return f"{int(float(x)):,}"

    def fmt_ratio(x: Any, nd: int = 4) -> str:
        if x is None or x == "" or pd.isna(x):
            return ""
        return f"{float(x):.{nd}f}"

    def kv_item(label: str, value: str) -> str:
        if value in ["", None]:
            return ""
        return f"""
        <div class="kv-item">
          <div class="kv-label">{label}</div>
          <div class="kv-value">{value}</div>
        </div>
        """
    
    
    occupancy_fig_dir = figures_dir(project_root) / "f03" / "occupancy_cards"
    occupancy_fig_dir.mkdir(parents=True, exist_ok=True)

    occupancy_fig_paths: Dict[str, Path] = {}

    if not master_f03.empty and "variant_f03" in master_f03.columns:
        tmp_df = master_f03.drop_duplicates(subset=["variant_f03"], keep="last").copy()
        for _, r in tmp_df.iterrows():
            variant = str(r.get("variant_f03", "")).strip()
            if not variant:
                continue
            out = occupancy_fig_dir / f"{sanitize_filename(variant)}__occupancy.png"
            p = make_f03_window_occupancy_plot(r, out)
            if p is not None:
                occupancy_fig_paths[variant] = p

    def hashmap_variant_card(row: pd.Series) -> str:
        hashmap_path = safe_val(row, "hashmap_path", "")
        if not hashmap_path:
            return ""

        img_path = Path(str(hashmap_path))
        if not img_path.exists():
            return ""

        rel = rel_to_analysis(img_path)

        variant = str(safe_val(row, "variant_f03", ""))
        strategy = str(safe_val(row, "window_strategy", ""))
        ow = human_time(safe_val(row, "OW", None))
        pw = human_time(safe_val(row, "PW", None))
        lt = human_time(safe_val(row, "LT", None))

        n_windows = fmt_int(safe_val(row, "n_windows", None))
        dup_ratio_ow = fmt_ratio(safe_val(row, "dup_ratio_ow", None))
        dup_ratio_pw = fmt_ratio(safe_val(row, "dup_ratio_pw", None))
        execution_time = fmt_ratio(safe_val(row, "execution_time", None), 3)
        n_events_in = fmt_int(safe_val(row, "n_events_in", None))
            
        occupancy_rel = None
        occupancy_path = occupancy_fig_paths.get(variant)
        if occupancy_path is not None and occupancy_path.exists():
            occupancy_rel = rel_to_analysis(occupancy_path)

        seq_dist_path = make_seq_len_distribution_plot(row, figures_dir(project_root) / "f03" / "seq_len_distributions" / f"{sanitize_filename(variant)}__seq_len_distribution.png")
        hash_explanation_html = build_hash_concentration_explanation(row)

        return f"""
        <section class="panel hashmap-card">
          <div class="hashmap-head">
            <h4>{variant}</h4>
            <div class="hashmap-subtitle">
              strategy=<strong>{strategy}</strong> · OW=<strong>{ow}</strong> · PW=<strong>{pw}</strong> · LT=<strong>{lt}</strong>
            </div>
          </div>

          <div class="hashmap-image-wrap">
            <img class="hashmap-image" src="{rel}" alt="Hashmap {variant}">
          </div>

          <div class="hashmap-main-kpi">
            <div class="hashmap-main-kpi-label">Número de ventanas</div>
            <div class="hashmap-main-kpi-value">{n_windows}</div>
          </div>

          <div class="hashmap-meta-grid">
            {kv_item("manifest_strategy", str(safe_val(row, "manifest_strategy", "")))}
            {kv_item("dup_ratio_ow", dup_ratio_ow)}
            {kv_item("dup_ratio_pw", dup_ratio_pw)}
            {kv_item("n_events_in", n_events_in)}
            {kv_item("execution_time", execution_time + " s" if execution_time else "")}
          </div>
          {
            f'''
            <div class="hashmap-explanation">
                <h5 class="subpanel-title">Interpretación de concentración y duplicación</h5>
                {hash_explanation_html}
            </div>
            
            <div class="hashmap-subgrid">
                <div class="panel hashmap-subpanel">
                    <h5 class="subpanel-title">Ocupación de ventanas</h5>
                    <img class="hashmap-occupancy-image" src="{occupancy_rel}" alt="Occupancy {variant}">
                </div>
                <div class="panel hashmap-subpanel">
                    <h5 class="subpanel-title">Longitud de la secuencia</h5>
                    <img class="hashmap-occupancy-image" src="{seq_dist_path}" alt="Sequence Length {variant}">
                </div>

            '''
            if occupancy_rel else ""
          }
        </section>
        """

    def rel_to_analysis(path: Optional[Path]) -> Optional[str]:
        if path is None:
            return None
        return "../" + path.relative_to(analysis_base).as_posix()

    def rel_from_master_path(path_str: Optional[str]) -> Optional[str]:
        if not path_str or pd.isna(path_str):
            return None

        p = Path(str(path_str))
        if not p.is_absolute():
            return str(p).replace("\\", "/")

        try:
            return "../" + p.resolve().relative_to(analysis_base.resolve()).as_posix()
        except Exception:
            # Fallback para rutas fuera del árbol de analysis.
            return p.as_posix()

    def img_block(path: Optional[Path], title: str, subtitle: str = "") -> str:
        if path is None:
            return ""
        rel = rel_to_analysis(path)
        subtitle_html = f"<p class='caption'>{subtitle}</p>" if subtitle else ""
        return f"""
        <section class='panel'>
          <h4>{title}</h4>
          {subtitle_html}
          <img class='plot' src='{rel}'>
        </section>
        """

    def metric_card(label: str, value: str) -> str:
        return f"""
        <div class="metric-card">
          <div class="metric-label">{label}</div>
          <div class="metric-value">{value}</div>
        </div>
        """

    def two_col_block(*blocks: str) -> str:
        rendered = [b for b in blocks if b]
        if not rendered:
            return ""
        return """
  <div class="two-col">
{content}
  </div>
""".format(content="\n".join(rendered))

    def panel_block(title: str, body: str) -> str:
        return f"""
  <section class="panel">
    <h3>{title}</h3>
    {body}
  </section>
"""



    # KPIs F03
    f03_total = len(master_f03)
    f03_strategies = master_f03["window_strategy"].nunique() if not master_f03.empty and "window_strategy" in master_f03.columns else 0
    f03_configs = (
        master_f03[["OW", "PW", "LT"]].drop_duplicates().shape[0]
        if not master_f03.empty and all(c in master_f03.columns for c in ["OW", "PW", "LT"])
        else 0
    )
    fig_f03_compare = generate_f03_comparison_heatmaps(project_root, master_f03)
    fig_f03.update(fig_f03_compare)

    dup_ow_mean = f03_summary["dup_ratio_ow_mean"].mean() if not f03_summary.empty and "dup_ratio_ow_mean" in f03_summary.columns else None
    unique_ow_mean = f03_summary["ow_unique_ratio_mean"].mean() if not f03_summary.empty and "ow_unique_ratio_mean" in f03_summary.columns else None
    windows_mean = f03_summary["n_windows_mean"].mean() if not f03_summary.empty and "n_windows_mean" in f03_summary.columns else None
    exec_mean = f03_summary["execution_time_mean"].mean() if not f03_summary.empty and "execution_time_mean" in f03_summary.columns else None

    def fmt(x, pct=False, nd=3):
        if x is None or pd.isna(x):
            return "N/A"
        if pct:
            return f"{100*x:.1f}%"
        return f"{x:,.{nd}f}"

    summary_text = """
    <p>
      Esta sección analiza el comportamiento estructural de las configuraciones F03 en términos de
      redundancia, diversidad, tamaño del conjunto generado y coste de ejecución. El objetivo es
      identificar qué estrategia de apertura de ventanas produce configuraciones más eficientes y diversas.
    </p>
    <p>
      La lectura recomendada es la siguiente: primero se comparan las estrategias de forma global,
      después se estudia el efecto de cada configuración OW–PW, y finalmente se observan los
      trade-offs entre duplicación, unicidad, volumen de ventanas y concentración de patrones.
    </p>
    """

    hashmap_gallery_html = ""
    if not master_f03.empty and all(c in master_f03.columns for c in ["variant_f03", "hashmap_path"]):
        variants_df = master_f03.copy()
        sort_cols = [c for c in ["window_strategy", "OW", "PW", "variant_f03"] if c in variants_df.columns]
        if sort_cols:
            variants_df = variants_df.sort_values(sort_cols)

        variants_df = variants_df.drop_duplicates(subset=["variant_f03"], keep="last")
        cards = [hashmap_variant_card(r) for _, r in variants_df.iterrows()]
        cards = [c for c in cards if c]
        if cards:
            hashmap_gallery_html = "\n".join(cards)

    kpi_html = "\n".join([
        metric_card("Ejecuciones F03", str(f03_total)),
        metric_card("Estrategias", str(f03_strategies)),
        metric_card("Configuraciones OW–PW–LT", str(f03_configs)),
        metric_card("Duplicación OW media", fmt(dup_ow_mean, pct=True)),
        metric_card("Unicidad OW media", fmt(unique_ow_mean, pct=True)),
        metric_card("Ventanas medias", fmt(windows_mean, pct=False, nd=0)),
        metric_card("Tiempo medio ejecución", fmt(exec_mean, pct=False, nd=3) + " s"),
    ])

    global_compare_plot = img_block(
        fig_f03.get("f03_grouped_dup_ow_pw_by_config_and_strategy"),
        "Duplicación OW/PW por configuración y estrategia",
        "Cada subplot corresponde a una estrategia; dentro de cada configuración se comparan las tasas de duplicación en OW y PW.",
    )
    global_compare_row = two_col_block(
        img_block(
            fig_f03.get("f03_bar_ow_unique_ratio_by_strategy"),
            "Unicidad OW media por estrategia",
            "Indica qué fracción de ventanas aporta contenido no repetido.",
        ),
        img_block(
            fig_f03.get("f03_bar_execution_time_by_strategy"),
            "Tiempo medio de ejecución por estrategia",
            "Resume el coste computacional asociado a cada política de apertura.",
        ),
    )
    direct_compare_plot = img_block(
        fig_f03.get("f03_bar_dup_ratio_ow_pw_by_config_synchro_asynOW"),
        "Duplicación OW/PW por configuración",
        "Comparación directa entre configuraciones OW–PW para las estrategias synchro y asynOW, sin agregación.",
    )
    direct_heatmap_rows = "\n".join(
        block for block in [
            two_col_block(
                img_block(fig_f03.get("f03_dual_heatmap__execution_time"), "Tiempo de ejecución"),
                img_block(fig_f03.get("f03_dual_heatmap__n_windows"), "Número medio de ventanas"),
            ),
            two_col_block(
                img_block(fig_f03.get("f03_dual_heatmap__n_unique_ow_hash"), "Hashes únicos OW"),
                img_block(fig_f03.get("f03_dual_heatmap__n_unique_pw_hash"), "Hashes únicos PW"),
            ),
            two_col_block(
                img_block(fig_f03.get("f03_dual_heatmap__top5_ow_hash_coverage"), "Cobertura top5 OW"),
                img_block(fig_f03.get("f03_dual_heatmap__top5_pw_hash_coverage"), "Cobertura top5 PW"),
            ),
        ]
        if block
    )

    executive_summary_html = panel_block("Resumen ejecutivo", summary_text)
    final_reading_html = panel_block(
        "Cómo interpretar el bloque F03",
        """
    <p>
      Una configuración es estructuralmente preferible cuando combina una <strong>baja duplicación</strong>,
      una <strong>alta unicidad</strong>, una <strong>concentración moderada de patrones</strong> y un
      <strong>coste de ejecución razonable</strong>. Ninguna métrica por sí sola basta: el análisis debe
      leerse siempre en conjunto.
    </p>
    <p>
      En general, las gráficas de barras permiten detectar el patrón medio por estrategia, los heatmaps
      muestran en qué regiones OW–PW aparecen los mejores y peores comportamientos, y el conjunto del
      bloque ayuda a entender los trade-offs que hay detrás de esos resultados.
    </p>
    <p class="muted">
      Recomendación práctica: empezar la lectura por las barras globales, continuar con los heatmaps de
      duplicación y unicidad, y terminar con el detalle por variante para validar si las mejoras observadas
      se sostienen también en términos de volumen y concentración.
    </p>
""",
    )

    variant_detail_html = (
        hashmap_gallery_html
        if hashmap_gallery_html
        else "<section class='panel'><p class='muted'>No se encontraron hashmaps válidos en master_f03.</p></section>"
    )

    html = f"""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>Informe de análisis F03</title>
    <link rel="stylesheet" href="../report.css">
</head>
<body>

  <h1>Análisis F03 — generación de ventanas</h1>
  <p class="lead">
    Evaluación estructural de las configuraciones de windowing para comparar redundancia,
    diversidad, volumen de datos y coste computacional.
  </p>

  <div class="kpi-grid">
    {kpi_html}
  </div>

  {executive_summary_html}

  <h2>1. Comparación global entre estrategias</h2>
  <p class="section-note">
    Esta primera sección permite comparar de forma agregada el comportamiento medio de cada estrategia.
    Aquí se observa el patrón general antes de entrar en el detalle por configuración.
  </p>

  {global_compare_plot}

  {global_compare_row}

  <h3> Comparación por configuración OW–PW</h3>
  <p class="section-note">
    Una vez visto el patrón global, esta sección baja al nivel de configuración concreta para analizar
    cómo influyen el tamaño de la ventana de observación y la ventana de predicción sobre la redundancia.
  </p>

  {direct_compare_plot}
  <p class="section-note">
  La figura muestra que, bajo la estrategia <code>asynOW</code>, la duplicación en la ventana de predicción (PW)
  permanece sistemáticamente muy superior a la duplicación en la ventana de observación (OW)
  para todas las configuraciones analizadas. Este comportamiento se debe a que <code>asynOW</code>
  abre ventanas únicamente cuando existe actividad en OW, sin exigir actividad futura en PW.
  Como resultado, múltiples ventanas con observaciones distintas terminan asociándose a contenidos
  de predicción idénticos —frecuentemente PW vacías o con muy baja variabilidad—, lo que provoca
  una fuerte concentración y repetición de patrones en PW.
  </p>

  <h4>Heatmaps de comparación directa</h4>

  <p class="section-note">
    Cada figura muestra la misma métrica para <code>synchro</code> y <code>asynOW</code>
    usando exactamente la misma escala de color, lo que permite comparar visualmente
    ambas estrategias sin sesgos de representación.
  </p>

  {direct_heatmap_rows}


  <h3>2.1 Detalle por variante F03</h3>
  <p class="section-note">
    Se muestran los hashmaps de todas las variantes de la fase 3 usando el campo <b>hashmap_path</b> de master_f03.
  </p>
  {variant_detail_html}



  <h2>5. Lectura final</h2>
  {final_reading_html}

</body>
</html>
"""
    return html


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    args = parse_args()
    project_root = discover_project_root(args.project_root)

    out_dir = outputs_dir(project_root)
    fig_dir = figures_dir(project_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    master_f03_path = (
        args.master_f03.resolve()
        if args.master_f03
        else out_dir / "master_f03.csv"
    )

    if not master_f03_path.exists():
        raise FileNotFoundError(f"No existe master_f03.csv: {master_f03_path}")

    master_f03 = pd.read_csv(master_f03_path)

    f03_summary = build_f03_summary(master_f03)


    # guardar summaries
    f03_summary.to_csv(out_dir / "config_summary_f03.csv", index=False, encoding="utf-8")


    fig_f03 = generate_f03_figures(project_root, f03_summary, master_f03)



    output_html = (
        args.output_html.resolve()
        if args.output_html
        else out_dir / "reportf03.html"
    )
    output_html.write_text(
        build_html(
            project_root=project_root,
            master_f03=master_f03,
            f03_summary=f03_summary,
            fig_f03=fig_f03,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

# python test/experiments/aticus/analysis/build_report.py
