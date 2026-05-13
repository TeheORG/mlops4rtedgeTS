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
from matplotlib.lines import Line2D
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.stats.anova import anova_lm




# ============================================================
# CLI
# ============================================================

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Genera report.html para Aticus")
    p.add_argument("--project-root", type=Path, default=None, help="Root del proyecto")
    p.add_argument("--master-f03", type=Path, default=None, help="Ruta a master_f03.csv")
    p.add_argument("--master-f045", type=Path, default=None, help="Ruta a master_f045.csv")
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


def pipeline_label(window_strategy: str, deduplication_mode: str) -> str:
    return f"{window_strategy} + {deduplication_mode}"


def measure_direction_label(measure_name: str, direction: str) -> str:
    direction = direction if direction not in [None, "", np.nan] else "na"
    return f"{measure_name} [{direction}]"


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
# DECISION RULES
# ============================================================

def infer_decision_f045(row: pd.Series) -> str:
    f1 = row.get("f05_test_f1_mean")
    recall = row.get("f05_test_recall_mean")
    f1_std = row.get("f05_test_f1_std")
    pos = row.get("f04_n_windows_pos_mean")
    ambiguous = row.get("f04_ambiguous_ratio_mean")

    if pd.isna(f1) or pd.isna(pos):
        return "revisar"

    if pos < 20 or (not pd.isna(ambiguous) and ambiguous > 0.20) or f1 < 0.10:
        return "descartar"

    if (
        f1 >= 0.40
        and (pd.isna(recall) or recall >= 0.20)
        and (pd.isna(f1_std) or f1_std <= 0.10)
        and (pd.isna(ambiguous) or ambiguous <= 0.15)
    ):
        return "finalista"

    if f1 >= 0.20:
        return "candidata"

    return "revisar"


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


def build_f045_summary(master_f045: pd.DataFrame) -> pd.DataFrame:
    if master_f045.empty:
        return pd.DataFrame()

    df = master_f045.copy()

    if "pipeline" not in df.columns:
        df["pipeline"] = df.apply(
            lambda r: pipeline_label(
                str(r.get("window_strategy", "")),
                str(r.get("deduplication_mode", "")),
            ),
            axis=1,
        )

    group_cols = [
        "measure_name",
        "direction",
        "window_strategy",
        "deduplication_mode",
        "pipeline",
        "OW",
        "PW",
        "LT",
        "model_family",
    ]

    summary = (
        df.groupby(group_cols, dropna=False)
        .agg(
            n_runs=("variant_f05", "count"),
            f05_test_f1_mean=("f05_test_f1", "mean"),
            f05_test_f1_std=("f05_test_f1", "std"),
            f05_test_recall_mean=("f05_test_recall", "mean"),
            f05_test_precision_mean=("f05_test_precision", "mean"),
            f05_best_val_recall_mean=("f05_best_val_recall", "mean"),
            f05_execution_time_mean=("f05_execution_time", "mean"),
            f03_dup_ratio_ow_mean=("f03_dup_ratio_ow", "mean"),
            f03_dup_ratio_pw_mean=("f03_dup_ratio_pw", "mean"),
            f04_positive_ratio_mean=("f04_positive_ratio", "mean"),
            f04_duplicate_ratio_mean=("f04_duplicate_ratio", "mean"),
            f04_ambiguous_ratio_mean=("f04_ambiguous_ratio", "mean"),
            f04_n_windows_pos_mean=("f04_n_windows_pos", "mean"),
            f05_removed_ratio_by_dedup_mean=("f05_removed_ratio_by_dedup", "mean"),
        )
        .reset_index()
    )

    summary["decision"] = summary.apply(infer_decision_f045, axis=1)
    summary["measure_direction"] = summary.apply(
        lambda r: measure_direction_label(r["measure_name"], r["direction"]),
        axis=1,
    )

    return summary


# ============================================================
# PLOTS Ã¢â‚¬â€ COMMON
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
        DataFrame con una fila por configuraciÃƒÂ³n.
    metric_col : str
        Columna de la mÃƒÂ©trica a representar.
    metric_title : str
        TÃƒÂ­tulo general de la figura.
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
        Formato numÃƒÂ©rico, por ejemplo ".3f" o ".0f".
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

    # Orden comÃƒÂºn en ambos heatmaps
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
    Genera un heatmap de correlaciÃƒÂ³n para las columnas indicadas.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame de entrada.
    columns : list[str]
        Columnas numÃƒÂ©ricas a analizar.
    title : str
        TÃƒÂ­tulo de la figura.
    output_path : Path
        Ruta del PNG de salida.
    method : str
        'pearson' o 'spearman'. Para tu caso recomiendo spearman.

    Returns
    -------
    Optional[Path]
        Ruta si se generÃƒÂ³ la figura, None si no habÃƒÂ­a datos suficientes.
    """
    valid_cols = [c for c in columns if c in df.columns]
    if len(valid_cols) < 2:
        return None

    sub = df[valid_cols].copy()

    # convertir a numÃƒÂ©rico por seguridad
    for c in valid_cols:
        sub[c] = pd.to_numeric(sub[c], errors="coerce")

    # quitar columnas constantes o totalmente vacÃƒÂ­as
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


def get_preferred_measure_order(df: pd.DataFrame) -> List[str]:
    preferred_measure_order = [
        "Battery_Active_Power",
        "FC_Active_Power",
        "Outlet_Temperature",
        "PVPCS_Active_Power",
    ]
    measures_present = [m for m in preferred_measure_order if m in set(df["measure_name"].dropna().astype(str))]
    remaining_measures = [
        m for m in sorted(df["measure_name"].dropna().astype(str).unique().tolist())
        if m not in measures_present
    ]
    return measures_present + remaining_measures


def compute_correlations_by_measure_feature(
    df: pd.DataFrame,
    *,
    target_col: str,
    feature_cols: List[str],
    method: str = "spearman",
) -> pd.DataFrame:
    if df.empty or "measure_name" not in df.columns or target_col not in df.columns:
        return pd.DataFrame(columns=["measure_name", "feature", "correlation"])

    rows: List[Dict[str, Any]] = []
    for measure_name in get_preferred_measure_order(df):
        sub = df[df["measure_name"].astype(str) == str(measure_name)].copy()
        if sub.empty:
            continue

        valid_cols = [c for c in feature_cols if c in sub.columns and c != target_col]
        if not valid_cols:
            continue

        work = sub[[target_col] + valid_cols].copy()
        for c in work.columns:
            work[c] = pd.to_numeric(work[c], errors="coerce")

        keep_cols = [target_col]
        for c in valid_cols:
            series = work[c].dropna()
            if len(series) >= 2 and series.nunique() >= 2:
                keep_cols.append(c)

        work = work[keep_cols].dropna(axis=0, how="any")
        if len(work) < 3:
            continue

        corr = work.corr(method=method)[target_col].drop(labels=[target_col], errors="ignore").dropna()
        for feature, correlation in corr.items():
            rows.append(
                {
                    "measure_name": str(measure_name),
                    "feature": str(feature),
                    "correlation": float(correlation),
                }
            )

    return pd.DataFrame(rows, columns=["measure_name", "feature", "correlation"])


def summarize_feature_correlations(corr_long: pd.DataFrame) -> pd.DataFrame:
    if corr_long.empty:
        return pd.DataFrame(
            columns=[
                "feature",
                "mean_corr",
                "std_corr",
                "min_corr",
                "max_corr",
                "same_sign",
                "strong_corr",
                "stable",
            ]
        )

    summary = (
        corr_long.groupby("feature", dropna=False)["correlation"]
        .agg(
            mean_corr="mean",
            std_corr="std",
            min_corr="min",
            max_corr="max",
        )
        .reset_index()
    )
    summary["std_corr"] = summary["std_corr"].fillna(0.0)

    sign_stats = corr_long.groupby("feature", dropna=False)["correlation"].agg(
        has_pos=lambda s: bool((s > 0).any()),
        has_neg=lambda s: bool((s < 0).any()),
    ).reset_index()
    summary = summary.merge(sign_stats, on="feature", how="left")
    summary["same_sign"] = ~(summary["has_pos"] & summary["has_neg"])
    summary["strong_corr"] = summary["mean_corr"].abs() > 0.3
    summary["stable"] = summary["std_corr"] < 0.15
    summary = summary.drop(columns=["has_pos", "has_neg"])

    summary = summary.sort_values("mean_corr", key=lambda s: s.abs(), ascending=False).reset_index(drop=True)
    return summary[
        [
            "feature",
            "mean_corr",
            "std_corr",
            "min_corr",
            "max_corr",
            "same_sign",
            "strong_corr",
            "stable",
        ]
    ]


def add_ow_pw_ratio_feature(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "OW" not in df.columns or "PW" not in df.columns:
        return df.copy()

    out = df.copy()
    ow = pd.to_numeric(out["OW"], errors="coerce")
    pw = pd.to_numeric(out["PW"], errors="coerce")
    out["OW/PW"] = np.where((pw > 0) & (~pw.isna()) & (~ow.isna()), ow / pw, np.nan)
    return out


def lowess_smooth(
    x: np.ndarray,
    y: np.ndarray,
    *,
    frac: float = 0.35,
    n_iter: int = 2,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    ImplementaciÃƒÂ³n ligera de LOWESS para evitar depender de statsmodels.
    Devuelve x ordenado y la estimaciÃƒÂ³n suavizada y_hat.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    valid = np.isfinite(x) & np.isfinite(y)
    x = x[valid]
    y = y[valid]
    if len(x) < 3:
        return x, y

    order = np.argsort(x)
    x = x[order]
    y = y[order]

    n = len(x)
    span = max(2, int(np.ceil(frac * n)))
    robust = np.ones(n, dtype=float)
    y_hat = np.zeros(n, dtype=float)

    for _ in range(max(1, n_iter + 1)):
        for i in range(n):
            distances = np.abs(x - x[i])
            bandwidth = np.partition(distances, span - 1)[span - 1]
            if bandwidth <= 0:
                weights = (distances == 0).astype(float)
            else:
                u = distances / bandwidth
                weights = np.where(u < 1, (1 - u**3) ** 3, 0.0)

            weights = weights * robust
            x_local = x - x[i]
            sw = weights.sum()
            if sw <= 0:
                y_hat[i] = y[i]
                continue

            sxx = np.sum(weights * x_local * x_local)
            if sxx <= 1e-12:
                beta0 = np.sum(weights * y) / sw
                y_hat[i] = beta0
                continue

            beta0 = np.sum(weights * y) / sw
            beta1 = np.sum(weights * x_local * (y - beta0)) / sxx
            y_hat[i] = beta0

        residuals = y - y_hat
        mad = np.median(np.abs(residuals))
        if mad <= 1e-12:
            break
        u = residuals / (6.0 * mad)
        robust = np.where(np.abs(u) < 1, (1 - u**2) ** 2, 0.0)

    return x, y_hat


def compute_xy_correlations(
    df: pd.DataFrame,
    *,
    x_col: str,
    y_col: str,
    group_col: str = "measure_name",
) -> pd.DataFrame:
    def spearman_corr_local(x: pd.Series, y: pd.Series) -> float:
        xr = x.rank(method="average")
        yr = y.rank(method="average")
        corr = xr.corr(yr, method="pearson")
        return float(corr) if pd.notna(corr) else np.nan

    def corr_row(scope: str, sub: pd.DataFrame) -> Optional[Dict[str, Any]]:
        work = sub[[x_col, y_col]].copy()
        for c in [x_col, y_col]:
            work[c] = pd.to_numeric(work[c], errors="coerce")
        work = work.dropna()
        if len(work) < 3 or work[x_col].nunique() < 2 or work[y_col].nunique() < 2:
            return None
        pearson = work[x_col].corr(work[y_col], method="pearson")
        spearman = spearman_corr_local(work[x_col], work[y_col])
        return {
            "scope": scope,
            "n": int(len(work)),
            "pearson": float(pearson) if pd.notna(pearson) else np.nan,
            "spearman": float(spearman) if pd.notna(spearman) else np.nan,
        }

    rows: List[Dict[str, Any]] = []
    global_row = corr_row("GLOBAL", df)
    if global_row is not None:
        rows.append(global_row)

    if group_col in df.columns:
        if group_col == "measure_name":
            group_values = get_preferred_measure_order(df)
        elif group_col == "pipeline":
            preferred_pipeline_order = ["synchro_auto", "synchro_all", "synchro_none", "asynOW_none"]
            present = set(df[group_col].dropna().astype(str))
            group_values = [p for p in preferred_pipeline_order if p in present]
            group_values += [p for p in sorted(present) if p not in group_values]
        else:
            group_values = sorted(df[group_col].dropna().astype(str).unique().tolist())

        for group_value in group_values:
            sub = df[df[group_col].astype(str) == str(group_value)].copy()
            row = corr_row(str(group_value), sub)
            if row is not None:
                rows.append(row)

    return pd.DataFrame(rows, columns=["scope", "n", "pearson", "spearman"])


def get_scatter_style_maps(df: pd.DataFrame) -> Tuple[List[str], Dict[str, str], List[str], Dict[str, str]]:
    pipeline_order = ["synchro_auto", "synchro_all", "synchro_none", "asynOW_none"]
    pipeline_colors = {
        "synchro_auto": "#1f77b4",
        "synchro_all": "#ff7f0e",
        "synchro_none": "#2ca02c",
        "asynOW_none": "#d62728",
    }
    fallback_colors = ["#9467bd", "#8c564b", "#e377c2", "#7f7f7f"]
    measure_markers = {
        "Battery_Active_Power": "o",
        "FC_Active_Power": "s",
        "Outlet_Temperature": "^",
        "PVPCS_Active_Power": "D",
    }
    fallback_markers = ["P", "X", "v", "<", ">", "*"]

    present_pipelines = [p for p in pipeline_order if p in set(df["pipeline"].astype(str))]
    for i, p in enumerate(sorted(set(df["pipeline"].astype(str)) - set(present_pipelines))):
        pipeline_colors[p] = fallback_colors[i % len(fallback_colors)]
        present_pipelines.append(p)

    present_measures = get_preferred_measure_order(df.rename(columns={"measure_name": "measure_name"}))
    for i, m in enumerate([m for m in present_measures if m not in measure_markers]):
        measure_markers[m] = fallback_markers[i % len(fallback_markers)]

    return present_pipelines, pipeline_colors, present_measures, measure_markers


def make_colored_marker_scatter_with_lowess(
    df: pd.DataFrame,
    *,
    x_col: str,
    y_col: str,
    output_path: Path,
    title: str,
    xlabel: str,
    ylabel: str,
    add_global_lowess: bool = True,
    add_pipeline_lowess: bool = False,
) -> Optional[Path]:
    needed = [x_col, y_col, "pipeline", "measure_name"]
    if df.empty or any(c not in df.columns for c in needed):
        return None

    sub = df[needed].copy()
    sub[x_col] = pd.to_numeric(sub[x_col], errors="coerce")
    sub[y_col] = pd.to_numeric(sub[y_col], errors="coerce")
    sub = sub.dropna(subset=[x_col, y_col, "pipeline", "measure_name"])
    if len(sub) < 3:
        return None

    present_pipelines, pipeline_colors, present_measures, measure_markers = get_scatter_style_maps(sub)

    def plot_measure_scatter(
        ax: Any,
        scatter_df: pd.DataFrame,
        *,
        use_pipeline_colors: bool,
    ) -> None:
        for measure_name in present_measures:
            cur = scatter_df[scatter_df["measure_name"].astype(str) == str(measure_name)].copy()
            if cur.empty:
                continue
            if use_pipeline_colors:
                colors = cur["pipeline"].astype(str).map(pipeline_colors).fillna("#555555")
            else:
                colors = [pipeline_colors[str(cur["pipeline"].iloc[0])]] * len(cur)
            ax.scatter(
                cur[x_col],
                cur[y_col],
                c=colors,
                marker=measure_markers.get(measure_name, "o"),
                s=58,
                alpha=0.82,
                edgecolors="white",
                linewidths=0.5,
            )

    def plot_lowess_line(
        ax: Any,
        line_df: pd.DataFrame,
        *,
        color: str,
        linewidth: float,
        frac: float,
        alpha: float = 1.0,
    ) -> bool:
        if len(line_df) < 3 or line_df[x_col].nunique() < 2:
            return False
        lowess_x, lowess_y = lowess_smooth(
            line_df[x_col].to_numpy(dtype=float),
            line_df[y_col].to_numpy(dtype=float),
            frac=frac,
            n_iter=2,
        )
        if len(lowess_x) < 3:
            return False
        ax.plot(lowess_x, lowess_y, color=color, linewidth=linewidth, alpha=alpha)
        return True

    n_pipelines = max(len(present_pipelines), 1)
    fig = plt.figure(figsize=(max(13.2, 4.9 * n_pipelines), 11.0))
    gs = fig.add_gridspec(2, n_pipelines, height_ratios=[1.15, 1.0], hspace=0.34, wspace=0.18)
    ax_global = fig.add_subplot(gs[0, :])

    plot_measure_scatter(ax_global, sub, use_pipeline_colors=True)

    pipeline_lowess_handles: List[Line2D] = []
    if add_global_lowess:
        plot_lowess_line(
            ax_global,
            sub,
            color="#111111",
            linewidth=2.4,
            frac=0.4,
        )

    if add_pipeline_lowess:
        for pipeline_name in present_pipelines:
            cur = sub[sub["pipeline"].astype(str) == pipeline_name].copy()
            added = plot_lowess_line(
                ax_global,
                cur,
                color=pipeline_colors[pipeline_name],
                linewidth=2.0,
                frac=0.45,
                alpha=0.95,
            )
            if added:
                pipeline_lowess_handles.append(
                    Line2D([0], [0], color=pipeline_colors[pipeline_name], linewidth=2.0, label=f"LOWESS {pipeline_name}")
                )

    ax_global.set_xlabel(xlabel)
    ax_global.set_ylabel(ylabel)
    ax_global.set_title(title)
    ax_global.grid(alpha=0.22)

    bottom_axes: List[Any] = []
    for idx, pipeline_name in enumerate(present_pipelines):
        sharey_ax = bottom_axes[0] if bottom_axes else None
        ax_pipeline = fig.add_subplot(gs[1, idx], sharey=sharey_ax)
        bottom_axes.append(ax_pipeline)
        cur = sub[sub["pipeline"].astype(str) == pipeline_name].copy()
        plot_measure_scatter(ax_pipeline, cur, use_pipeline_colors=False)
        plot_lowess_line(
            ax_pipeline,
            cur,
            color="#111111",
            linewidth=2.2,
            frac=0.45,
        )
        ax_pipeline.set_title(pipeline_name)
        ax_pipeline.set_xlabel(xlabel)
        ax_pipeline.grid(alpha=0.22)
        if idx == 0:
            ax_pipeline.set_ylabel(ylabel)
        else:
            ax_pipeline.tick_params(axis="y", labelleft=False)

    pipeline_handles = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor=pipeline_colors[p], markeredgecolor=pipeline_colors[p], markersize=8, label=p)
        for p in present_pipelines
    ]
    measure_handles = [
        Line2D([0], [0], marker=measure_markers[m], color="#444444", linestyle="None", markersize=8, label=m)
        for m in present_measures
    ]
    extra_handles: List[Line2D] = []
    if add_global_lowess:
        extra_handles.append(Line2D([0], [0], color="#111111", linewidth=2.4, label="LOWESS global"))
    extra_handles.extend(pipeline_lowess_handles)

    legend1 = ax_global.legend(
        handles=pipeline_handles + extra_handles,
        title="Pipeline",
        loc="upper left",
        bbox_to_anchor=(1.02, 1.00),
        borderaxespad=0.0,
    )
    ax_global.add_artist(legend1)
    ax_global.legend(
        handles=measure_handles,
        title="Measure",
        loc="upper left",
        bbox_to_anchor=(1.02, 0.42),
        borderaxespad=0.0,
    )

    if bottom_axes:
        bottom_axes[-1].legend(
            handles=measure_handles + [Line2D([0], [0], color="#111111", linewidth=2.2, label="LOWESS pipeline")],
            title="Measure",
            loc="upper left",
            bbox_to_anchor=(1.02, 1.00),
            borderaxespad=0.0,
        )

    plt.subplots_adjust(right=0.80)
    save_current_figure(output_path, use_tight_layout=False)
    return output_path


def make_boxplot_f1_by_pipeline(
    df: pd.DataFrame,
    output_path: Path,
    *,
    title: str,
) -> Optional[Path]:
    needed = ["pipeline", "f05_test_f1"]
    if df.empty or any(c not in df.columns for c in needed):
        return None

    sub = df[needed].copy()
    sub["f05_test_f1"] = pd.to_numeric(sub["f05_test_f1"], errors="coerce")
    sub = sub.dropna(subset=["pipeline", "f05_test_f1"])
    if sub.empty:
        return None

    pipeline_order = ["synchro_auto","synchro_all","synchro_none", "asynOW_none"]
    ordered = [p for p in pipeline_order if p in set(sub["pipeline"].astype(str))]
    ordered += [p for p in sorted(set(sub["pipeline"].astype(str))) if p not in ordered]
    groups = [sub.loc[sub["pipeline"].astype(str) == p, "f05_test_f1"].to_numpy(dtype=float) for p in ordered]
    groups = [g for g in groups if len(g) > 0]
    ordered = [p for p in ordered if len(sub.loc[sub["pipeline"].astype(str) == p, "f05_test_f1"]) > 0]
    if not groups:
        return None

    plt.figure(figsize=(9.5, 6.5))
    ax = plt.gca()
    bp = ax.boxplot(groups, patch_artist=True, showfliers=True)
    palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#9467bd", "#8c564b"]
    for patch, color in zip(bp["boxes"], palette * 3):
        patch.set_facecolor(color)
        patch.set_alpha(0.35)

    x = np.arange(1, len(ordered) + 1)
    means = [float(np.mean(g)) for g in groups]
    medians = [float(np.median(g)) for g in groups]
    ax.scatter(x, means, color="#111111", marker="D", s=48, zorder=3, label="Media")
    ax.scatter(x, medians, color="#b22222", marker="_", s=340, linewidths=2.2, zorder=3, label="Mediana")

    for xi, mean_val, median_val in zip(x, means, medians):
        ax.text(xi + 0.04, mean_val, f"mean={mean_val:.3f}", fontsize=8, va="bottom", color="#111111")
        ax.text(xi + 0.04, median_val, f"med={median_val:.3f}", fontsize=8, va="top", color="#b22222")

    ax.set_xticks(x)
    ax.set_xticklabels(ordered, rotation=15, ha="right")
    ax.set_ylabel("f05_test_f1")
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.22)
    ax.legend()
    save_current_figure(output_path)
    return output_path


def make_ow_pw_f1_heatmap_by_pipeline(
    df: pd.DataFrame,
    output_path: Path,
    *,
    title: str,
) -> Optional[Path]:
    needed = ["pipeline", "OW", "PW", "f05_test_f1"]
    if df.empty or any(c not in df.columns for c in needed):
        return None

    sub = df[needed].copy()
    for c in ["OW", "PW", "f05_test_f1"]:
        sub[c] = pd.to_numeric(sub[c], errors="coerce")
    sub = sub.dropna(subset=needed)
    if sub.empty:
        return None

    pipeline_order = ["synchro_auto", "synchro_all", "synchro_none", "asynOW_none"]
    pipelines = [p for p in pipeline_order if p in set(sub["pipeline"].astype(str))]
    pipelines += [p for p in sorted(set(sub["pipeline"].astype(str))) if p not in pipelines]
    if not pipelines:
        return None

    pivots: List[Tuple[str, pd.DataFrame]] = []
    global_min = np.inf
    global_max = -np.inf
    for pipeline_name in pipelines:
        cur = sub[sub["pipeline"].astype(str) == pipeline_name].copy()
        pivot = cur.pivot_table(index="OW", columns="PW", values="f05_test_f1", aggfunc="mean")
        if pivot.empty:
            continue
        pivot = pivot.reindex(
            index=sorted([x for x in pivot.index if not pd.isna(x)], reverse=True),
            columns=sorted([x for x in pivot.columns if not pd.isna(x)]),
        )
        vals = pivot.to_numpy(dtype=float)
        if np.isfinite(vals).any():
            global_min = min(global_min, np.nanmin(vals))
            global_max = max(global_max, np.nanmax(vals))
        pivots.append((pipeline_name, pivot))

    if not pivots:
        return None

    fig, axes = plt.subplots(1, len(pivots), figsize=(5.7 * len(pivots), 5.6), squeeze=False)
    fig.suptitle(title, y=1.02)
    last_im = None
    for ax, (pipeline_name, pivot) in zip(axes[0], pivots):
        arr = pivot.to_numpy(dtype=float)
        last_im = ax.imshow(arr, aspect="auto", vmin=global_min, vmax=global_max, cmap="viridis")
        ax.set_title(pipeline_name)
        ax.set_xticks(np.arange(len(pivot.columns)))
        ax.set_yticks(np.arange(len(pivot.index)))
        ax.set_xticklabels([human_time(c) for c in pivot.columns], rotation=25, ha="right")
        ax.set_yticklabels([human_time(i) for i in pivot.index])
        ax.set_xlabel("PW")
        ax.set_ylabel("OW")
        for i in range(arr.shape[0]):
            for j in range(arr.shape[1]):
                val = arr[i, j]
                if np.isnan(val):
                    continue
                ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=8, color="white")

    if last_im is not None:
        fig.colorbar(last_im, ax=axes.ravel().tolist(), fraction=0.022, pad=0.02)
    save_current_figure(output_path, use_tight_layout=False)
    return output_path


def make_ambiguity_by_pipeline_scatter(
    df: pd.DataFrame,
    output_path: Path,
    *,
    title: str,
) -> Optional[Path]:
    return make_colored_marker_scatter_with_lowess(
        df,
        x_col="f04_ambiguous_ratio",
        y_col="f05_test_f1",
        output_path=output_path,
        title=title,
        xlabel="f04_ambiguous_ratio",
        ylabel="f05_test_f1",
        add_global_lowess=True,
        add_pipeline_lowess=False,
    )


def make_measures_difficulty_barplot(
    df: pd.DataFrame,
    output_path: Path,
    *,
    title: str,
) -> Optional[Path]:
    needed = ["measure_name", "f05_test_f1"]
    if df.empty or any(c not in df.columns for c in needed):
        return None

    sub = df[needed].copy()
    sub["f05_test_f1"] = pd.to_numeric(sub["f05_test_f1"], errors="coerce")
    sub = sub.dropna(subset=needed)
    if sub.empty:
        return None

    agg = (
        sub.groupby("measure_name", dropna=False)["f05_test_f1"]
        .agg(mean_f1="mean", std_f1="std", min_f1="min")
        .reset_index()
    )
    agg["std_f1"] = agg["std_f1"].fillna(0.0)
    agg = agg.sort_values(["mean_f1", "min_f1"], ascending=[True, True]).reset_index(drop=True)
    if agg.empty:
        return None

    x = np.arange(len(agg))
    plt.figure(figsize=(max(9, len(agg) * 1.6), 6.2))
    ax = plt.gca()
    bars = ax.bar(x, agg["mean_f1"], color="#4c78a8", alpha=0.85, label="Mean F1")
    ax.errorbar(x, agg["mean_f1"], yerr=agg["std_f1"], fmt="none", ecolor="#333333", capsize=4, linewidth=1.2, label="Std F1")
    ax.scatter(x, agg["min_f1"], color="#d62728", marker="v", s=62, zorder=3, label="Min F1")
    ax.bar_label(bars, labels=[f"{v:.2f}" for v in agg["mean_f1"]], padding=3, fontsize=8)
    for xi, min_val in zip(x, agg["min_f1"]):
        ax.text(xi, min_val - 0.02, f"min={min_val:.2f}", ha="center", va="top", fontsize=8, color="#a61c1c")
    ax.set_xticks(x)
    ax.set_xticklabels(agg["measure_name"], rotation=20, ha="right")
    ax.set_ylabel("f05_test_f1")
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.2)
    ax.legend()
    save_current_figure(output_path)
    return output_path


def make_stability_mean_std_f1_plot(
    df: pd.DataFrame,
    output_path: Path,
    *,
    title: str,
) -> Optional[Path]:
    group_cols = [
        "measure_name",
        "pipeline",
        "window_strategy",
        "deduplication_mode_effective",
        "OW",
        "PW",
        "LT",
        "model_family",
    ]
    needed = group_cols + ["f05_test_f1"]
    if df.empty or any(c not in df.columns for c in needed):
        return None

    sub = df[needed].copy()
    sub["f05_test_f1"] = pd.to_numeric(sub["f05_test_f1"], errors="coerce")
    for c in ["OW", "PW", "LT"]:
        sub[c] = pd.to_numeric(sub[c], errors="coerce")
    sub = sub.dropna(subset=["measure_name", "pipeline", "window_strategy", "deduplication_mode_effective", "OW", "PW", "LT", "model_family", "f05_test_f1"])
    if sub.empty:
        return None

    agg = (
        sub.groupby(group_cols, dropna=False)["f05_test_f1"]
        .agg(mean_f1="mean", std_f1="std", n_runs="count")
        .reset_index()
    )
    agg["std_f1"] = agg["std_f1"].fillna(0.0)
    agg = agg.dropna(subset=["mean_f1", "std_f1"])
    if agg.empty:
        return None

    present_pipelines, pipeline_colors, present_measures, measure_markers = get_scatter_style_maps(agg)
    max_runs = max(float(agg["n_runs"].max()), 1.0)
    sizes = 60 + 180 * (agg["n_runs"].astype(float) / max_runs)

    plt.figure(figsize=(11, 7.4))
    ax = plt.gca()

    for measure_name in present_measures:
        cur = agg[agg["measure_name"].astype(str) == str(measure_name)].copy()
        if cur.empty:
            continue
        cur_sizes = 60 + 180 * (cur["n_runs"].astype(float) / max_runs)
        colors = cur["pipeline"].astype(str).map(pipeline_colors).fillna("#555555")
        ax.scatter(
            cur["mean_f1"],
            cur["std_f1"],
            c=colors,
            marker=measure_markers.get(measure_name, "o"),
            s=cur_sizes,
            alpha=0.82,
            edgecolors="white",
            linewidths=0.6,
        )

    mean_line = float(agg["mean_f1"].mean())
    std_line = float(agg["std_f1"].mean())
    ax.axvline(mean_line, color="#333333", linestyle="--", linewidth=1.4)
    ax.axhline(std_line, color="#333333", linestyle="--", linewidth=1.4)

    p25_std = float(agg["std_f1"].quantile(0.25))
    to_label = agg[(agg["mean_f1"] > 0.97) & (agg["std_f1"] < p25_std)].copy()
    for _, row in to_label.iterrows():
        label = (
            f"{row['measure_name']} | {row['pipeline']} | "
            f"OW={human_time(row['OW'])} PW={human_time(row['PW'])}"
        )
        ax.annotate(
            label,
            (row["mean_f1"], row["std_f1"]),
            xytext=(5, 5),
            textcoords="offset points",
            fontsize=8,
            alpha=0.9,
        )

    pipeline_handles = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor=pipeline_colors[p], markeredgecolor=pipeline_colors[p], markersize=8, label=p)
        for p in present_pipelines
    ]
    measure_handles = [
        Line2D([0], [0], marker=measure_markers[m], color="#444444", linestyle="None", markersize=8, label=m)
        for m in present_measures
    ]
    size_handles = []
    for n in sorted(set([1, int(np.ceil(max_runs / 2)), int(max_runs)])):
        s = 60 + 180 * (float(n) / max_runs)
        size_handles.append(Line2D([0], [0], marker="o", color="none", markerfacecolor="#888888", markeredgecolor="#888888", markersize=np.sqrt(s) / 1.8, label=f"n_runs={n}"))

    legend1 = ax.legend(
        handles=pipeline_handles,
        title="Pipeline",
        loc="upper left",
        bbox_to_anchor=(1.28, 1.00),
        borderaxespad=0.0,
    )
    ax.add_artist(legend1)
    legend2 = ax.legend(
        handles=measure_handles,
        title="Measure",
        loc="upper left",
        bbox_to_anchor=(1.28, 0.66),
        borderaxespad=0.0,
    )
    ax.add_artist(legend2)
    ax.legend(
        handles=size_handles,
        title="Seeds",
        loc="upper left",
        bbox_to_anchor=(1.28, 0.32),
        borderaxespad=0.0,
    )

    ax.set_xlabel("mean_f1")
    ax.set_ylabel("std_f1")
    ax.set_title(title)
    ax.grid(alpha=0.22)
    plt.subplots_adjust(right=0.74)
    save_current_figure(output_path)
    return output_path


def make_feature_importance_barplot(
    feature_importance_df: pd.DataFrame,
    output_path: Path,
    *,
    title: str,
) -> Optional[Path]:
    if feature_importance_df.empty:
        return None

    plot_df = feature_importance_df.sort_values("importance", ascending=True).reset_index(drop=True)
    plt.figure(figsize=(10.5, max(6, len(plot_df) * 0.35)))
    ax = plt.gca()
    bars = ax.barh(plot_df["feature"], plot_df["importance"], color="#4c78a8", alpha=0.9)
    ax.bar_label(bars, labels=[f"{v:.3f}" for v in plot_df["importance"]], padding=4, fontsize=8)
    ax.set_xlabel("Importance")
    ax.set_title(title)
    ax.grid(axis="x", alpha=0.2)
    save_current_figure(output_path)
    return output_path


def generate_modeling_analysis(
    project_root: Path,
    master_f045: pd.DataFrame,
) -> Tuple[str, Dict[str, Path]]:
    fig_root = figures_dir(project_root) / "f045" / "extra"
    fig_root.mkdir(parents=True, exist_ok=True)
    out_dir = outputs_dir(project_root)

    if master_f045.empty:
        return "<section class='panel'><p class='muted'>No hay datos para anÃƒÂ¡lisis de modelado.</p></section>", {}

    figure_paths: Dict[str, Path] = {}

    def select_first_named_columns(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
        selected = []
        for col in cols:
            matches = df.loc[:, df.columns == col]
            if matches.shape[1] == 0:
                raise KeyError(col)
            series = matches.iloc[:, 0].copy()
            series.name = col
            selected.append(series)
        return pd.concat(selected, axis=1)

    rf_features = [
        # diseÃƒÂ±o
        "pipeline",
        "measure_name",
        "direction",
        "OW",
        "PW",
        "LT",

        # dataset final
        "f04_positive_ratio",
        "f04_duplicate_ratio",
        "f04_ambiguous_ratio",
        "f04_avg_label_consistency_per_ow",
        "f04_n_windows_pos",

        # train real
        "f05_n_train",
        "f05_positive_ratio_train",
        "f05_removed_ratio_by_dedup",
    ]
    rf_target = "f05_test_f1"
    rf_html = "<p class='muted'>No se pudo entrenar el Random Forest.</p>"

    if all(c in master_f045.columns for c in rf_features + [rf_target]):
        rf_df = select_first_named_columns(master_f045, rf_features + [rf_target])
        rf_df[rf_target] = pd.to_numeric(rf_df[rf_target], errors="coerce")
        for c in [
            "OW",
            "PW",
            "LT",
            "f04_positive_ratio",
            "f04_duplicate_ratio",
            "f04_ambiguous_ratio",
            "f04_avg_label_consistency_per_ow",
            "f04_n_windows_pos",
            "f05_n_train",
            "f05_positive_ratio_train",
            "f05_removed_ratio_by_dedup",
        ]:
            rf_df[c] = pd.to_numeric(rf_df[c], errors="coerce")
        rf_df = rf_df.dropna(subset=[rf_target, "pipeline"])

        if len(rf_df) >= 10:
            X = pd.get_dummies(
                rf_df[rf_features],
                columns=["pipeline", "measure_name", "direction"],
                drop_first=False,
                dtype=float,
            )
            y = rf_df[rf_target].astype(float)
            imputer = SimpleImputer(strategy="median")
            X_imp = pd.DataFrame(imputer.fit_transform(X), columns=X.columns, index=X.index)
            X_train, X_test, y_train, y_test = train_test_split(X_imp, y, test_size=0.2, random_state=42)

            rf = RandomForestRegressor(n_estimators=500, random_state=42)
            rf.fit(X_train, y_train)
            y_pred = rf.predict(X_test)
            r2 = r2_score(y_test, y_pred)
            mae = mean_absolute_error(y_test, y_pred)

            importance_df = (
                pd.DataFrame({"feature": X_imp.columns, "importance": rf.feature_importances_})
                .sort_values("importance", ascending=False)
                .reset_index(drop=True)
            )
            importance_df.to_csv(out_dir / "feature_importance_f1.csv", index=False, encoding="utf-8")
            importance_path = make_feature_importance_barplot(
                importance_df.head(25),
                output_path=fig_root / "feature_importance_f1.png",
                title="Feature importance for f05_test_f1",
            )
            if importance_path is not None:
                figure_paths["feature_importance_f1"] = importance_path

            rf_summary_df = pd.DataFrame(
                {
                    "metric": ["R2 test", "MAE test", "n_train", "n_test"],
                    "value": [f"{r2:.4f}", f"{mae:.4f}", str(len(X_train)), str(len(X_test))],
                }
            )
            rf_html = table_html(rf_summary_df)

    ols_html = "<p class='muted'>No se pudo ajustar el modelo OLS.</p>"
    ols_formula = (
        "f05_test_f1 ~ "
        "C(pipeline) + C(measure_name) + C(direction) + C(OW) + C(PW) + C(LT) + "
        "f04_positive_ratio + f04_duplicate_ratio + f04_ambiguous_ratio + "
        "f04_avg_label_consistency_per_ow + f04_n_windows_pos + "
        "f05_n_train + f05_positive_ratio_train + f05_removed_ratio_by_dedup"
    )
    ols_cols = [
        "f05_test_f1",
        "pipeline",
        "measure_name",
        "direction",
        "OW",
        "PW",
        "LT",
        "f04_positive_ratio",
        "f04_duplicate_ratio",
        "f04_ambiguous_ratio",
        "f04_avg_label_consistency_per_ow",
        "f04_n_windows_pos",
        "f05_n_train",
        "f05_positive_ratio_train",
        "f05_removed_ratio_by_dedup",
    ]
    if all(c in master_f045.columns for c in ols_cols):
        ols_df = select_first_named_columns(master_f045, ols_cols)
        for c in [
            "f05_test_f1",
            "OW",
            "PW",
            "LT",
            "f04_positive_ratio",
            "f04_duplicate_ratio",
            "f04_ambiguous_ratio",
            "f04_avg_label_consistency_per_ow",
            "f04_n_windows_pos",
            "f05_n_train",
            "f05_positive_ratio_train",
            "f05_removed_ratio_by_dedup",
        ]:
            ols_df[c] = pd.to_numeric(ols_df[c], errors="coerce")
        ols_df = ols_df.dropna()
        if len(ols_df) >= 10:
            model = smf.ols(ols_formula, data=ols_df).fit()
            anova_note = "ANOVA Type II"
            try:
                anova_df = anova_lm(model, typ=2).reset_index().rename(columns={"index": "term"})
            except Exception:
                anova_df = anova_lm(model, typ=1).reset_index().rename(columns={"index": "term"})
                anova_note = "ANOVA Type I (fallback por singularidad / colinealidad en type II)"
            anova_df.to_csv(out_dir / "anova_f1.csv", index=False, encoding="utf-8")
            (out_dir / "ols_f1_summary.txt").write_text(model.summary().as_text(), encoding="utf-8")

            anova_fmt = anova_df.copy()
            for col in anova_fmt.columns:
                if col != "term":
                    anova_fmt[col] = anova_fmt[col].map(lambda x: "" if pd.isna(x) else f"{float(x):.6f}")

            ols_html = (
                "<section class='panel'>"
                "<h3>OLS Summary</h3>"
                "<p class='caption'>Modelo OLS alineado con el mismo bloque de variables usado en el Random Forest.</p>"
                f"<pre class='code-block'>{model.summary().as_text()}</pre>"
                "</section>"
                "<section class='panel'>"
                "<h3>ANOVA Type II</h3>"
                f"<p class='caption'>{anova_note}</p>"
                f"{table_html(anova_fmt)}"
                "</section>"
            )

    feature_img_html = (
        "<img class='plot plot-zoomable' src='../figures/f045/extra/feature_importance_f1.png' "
        "alt='Feature importance f1' data-fullsrc='../figures/f045/extra/feature_importance_f1.png' role='button' tabindex='0'>"
        if "feature_importance_f1" in figure_paths
        else "<p class='muted'>No se pudo generar la figura feature_importance_f1.png.</p>"
    )

    html = f"""
    <h2>Modelado F1</h2>
    <section class='panel'>
      <h3>Random Forest Regressor</h3>
      <p class='caption'>
        Modelo con <code>n_estimators=500</code> y <code>random_state=42</code> para predecir <code>f05_test_f1</code>
        usando <code>pipeline</code>, <code>measure_name</code>, <code>direction</code>, <code>OW</code>, <code>PW</code>, <code>LT</code>,
        <code>f04_positive_ratio</code>, <code>f04_duplicate_ratio</code>, <code>f04_ambiguous_ratio</code>,
        <code>f04_avg_label_consistency_per_ow</code>, <code>f04_n_windows_pos</code>,
        <code>f05_n_train</code>, <code>f05_positive_ratio_train</code> y <code>f05_removed_ratio_by_dedup</code>.
        Las categÃƒÂ³ricas se codifican con one-hot.
      </p>
      {rf_html}
      {feature_img_html}
    </section>
    {ols_html}
    """
    return html, figure_paths


def generate_extra_images_analysis(
    project_root: Path,
    master_f045: pd.DataFrame,
) -> Tuple[str, Dict[str, Path]]:
    fig_root = figures_dir(project_root) / "f045" / "extra"
    fig_root.mkdir(parents=True, exist_ok=True)

    if master_f045.empty:
        return "<section class='panel'><p class='muted'>No hay datos para imÃƒÂ¡genes extra.</p></section>", {}

    figure_paths: Dict[str, Path] = {}
    out_dir = outputs_dir(project_root)

    ambiguity_path = make_colored_marker_scatter_with_lowess(
        master_f045,
        x_col="f04_ambiguous_ratio",
        y_col="f05_test_f1",
        output_path=fig_root / "ambiguity_vs_f1.png",
        title="Ambiguous ratio vs F1 por pipeline y medida",
        xlabel="f04_ambiguous_ratio",
        ylabel="f05_test_f1",
        add_global_lowess=True,
        add_pipeline_lowess=False,
    )
    if ambiguity_path is not None:
        figure_paths["ambiguity_vs_f1"] = ambiguity_path

    consistency_path = make_colored_marker_scatter_with_lowess(
        master_f045,
        x_col="f04_avg_label_consistency_per_ow",
        y_col="f05_test_f1",
        output_path=fig_root / "consistency_vs_f1.png",
        title="Consistencia media vs F1 por pipeline y medida",
        xlabel="f04_avg_label_consistency_per_ow",
        ylabel="f05_test_f1",
        add_global_lowess=True,
        add_pipeline_lowess=True,
    )
    if consistency_path is not None:
        figure_paths["consistency_vs_f1"] = consistency_path

    dedup_path = make_colored_marker_scatter_with_lowess(
        master_f045,
        x_col="f05_removed_ratio_by_dedup",
        y_col="f05_test_f1",
        output_path=fig_root / "dedup_vs_f1.png",
        title="Removed ratio by dedup vs F1 por pipeline y medida",
        xlabel="f05_removed_ratio_by_dedup",
        ylabel="f05_test_f1",
        add_global_lowess=True,
        add_pipeline_lowess=False,
    )
    if dedup_path is not None:
        figure_paths["dedup_vs_f1"] = dedup_path

    class_balance_path = make_colored_marker_scatter_with_lowess(
        master_f045,
        x_col="f04_positive_ratio",
        y_col="f05_test_f1",
        output_path=fig_root / "class_balance_vs_f1.png",
        title="Positive ratio vs F1 por pipeline y medida",
        xlabel="f04_positive_ratio",
        ylabel="f05_test_f1",
        add_global_lowess=True,
        add_pipeline_lowess=False,
    )
    if class_balance_path is not None:
        figure_paths["class_balance_vs_f1"] = class_balance_path

    class_balance_train_path = make_colored_marker_scatter_with_lowess(
        master_f045,
        x_col="f05_positive_ratio_train",
        y_col="f05_test_f1",
        output_path=fig_root / "class_balance_train_vs_f1.png",
        title="Positive ratio train vs F1 por pipeline y medida",
        xlabel="f05_positive_ratio_train",
        ylabel="f05_test_f1",
        add_global_lowess=True,
        add_pipeline_lowess=False,
    )
    if class_balance_train_path is not None:
        figure_paths["class_balance_train_vs_f1"] = class_balance_train_path

    class_balance_train_recall_path = make_colored_marker_scatter_with_lowess(
        master_f045,
        x_col="f05_positive_ratio_train",
        y_col="f05_test_recall",
        output_path=fig_root / "class_balance_train_vs_recall.png",
        title="Positive ratio train vs recall por pipeline y medida",
        xlabel="f05_positive_ratio_train",
        ylabel="f05_test_recall",
        add_global_lowess=True,
        add_pipeline_lowess=True,
    )
    if class_balance_train_recall_path is not None:
        figure_paths["class_balance_train_vs_recall"] = class_balance_train_recall_path

    train_positive_precision_path = make_colored_marker_scatter_with_lowess(
        master_f045,
        x_col="f05_positive_ratio_train",
        y_col="f05_test_precision",
        output_path=fig_root / "train_positive_vs_precision.png",
        title="Positive ratio train vs precision por pipeline y medida",
        xlabel="f05_positive_ratio_train",
        ylabel="f05_test_precision",
        add_global_lowess=True,
        add_pipeline_lowess=True,
    )
    if train_positive_precision_path is not None:
        figure_paths["train_positive_vs_precision"] = train_positive_precision_path

    heatmap_ow_pw_path = make_ow_pw_f1_heatmap_by_pipeline(
        master_f045,
        output_path=fig_root / "heatmap_ow_pw_f1.png",
        title="F1 medio por OW/PW y pipeline",
    )
    if heatmap_ow_pw_path is not None:
        figure_paths["heatmap_ow_pw_f1"] = heatmap_ow_pw_path

    ambiguity_by_pipeline_path = None
    measures_difficulty_path = make_measures_difficulty_barplot(
        master_f045,
        output_path=fig_root / "measures_difficulty.png",
        title="Dificultad relativa por medida",
    )
    if measures_difficulty_path is not None:
        figure_paths["measures_difficulty"] = measures_difficulty_path

    stability_path = make_stability_mean_std_f1_plot(
        master_f045,
        output_path=fig_root / "stability_mean_std_f1.png",
        title="Stability plot: mean F1 vs variability across seeds",
    )
    if stability_path is not None:
        figure_paths["stability_mean_std_f1"] = stability_path

    boxplot_path = make_boxplot_f1_by_pipeline(
        master_f045,
        output_path=fig_root / "boxplot_f1_pipeline.png",
        title="DistribuciÃƒÂ³n de f05_test_f1 por pipeline",
    )
    if boxplot_path is not None:
        figure_paths["boxplot_f1_pipeline"] = boxplot_path

    ambiguity_corr_df = compute_xy_correlations(
        master_f045,
        x_col="f04_ambiguous_ratio",
        y_col="f05_test_f1",
        group_col="measure_name",
    )
    ambiguity_corr_df.to_csv(out_dir / "ambiguity_vs_f1_correlations.csv", index=False, encoding="utf-8")

    consistency_corr_df = compute_xy_correlations(
        master_f045,
        x_col="f04_avg_label_consistency_per_ow",
        y_col="f05_test_f1",
        group_col="pipeline",
    )
    consistency_corr_df.to_csv(out_dir / "consistency_vs_f1_correlations.csv", index=False, encoding="utf-8")

    def corr_table_html(corr_df: pd.DataFrame) -> str:
        if corr_df.empty:
            return "<p class='muted'>No se pudieron calcular correlaciones para esta figura.</p>"
        corr_fmt = corr_df.copy()
        corr_fmt["pearson"] = corr_fmt["pearson"].map(lambda x: "" if pd.isna(x) else f"{float(x):.3f}")
        corr_fmt["spearman"] = corr_fmt["spearman"].map(lambda x: "" if pd.isna(x) else f"{float(x):.3f}")
        return table_html(corr_fmt)

    ambiguity_corr_html = corr_table_html(ambiguity_corr_df)
    consistency_corr_html = corr_table_html(consistency_corr_df)

    def rel(path: Optional[Path]) -> Optional[str]:
        if path is None:
            return None
        return "../" + path.relative_to(analysis_root(project_root)).as_posix()

    section_html = f"""
    <h2>ImÃƒÂ¡genes extra</h2>
    <section class='panel'>
      <h3>AmbigÃƒÂ¼edad F04 vs F1 final</h3>
      <p class='caption'>
        Scatter global construido desde <code>master_f045</code> con <code>x = f04_ambiguous_ratio</code>,
        <code>y = f05_test_f1</code>, color por <code>pipeline</code> y marcador por <code>measure_name</code>.
        La lÃƒÂ­nea negra muestra una tendencia global LOWESS para resumir la relaciÃƒÂ³n no lineal entre ambigÃƒÂ¼edad y rendimiento.
      </p>
      {f"<img class='plot plot-zoomable' src='{rel(ambiguity_path)}' alt='Ambiguity vs F1' data-fullsrc='{rel(ambiguity_path)}' role='button' tabindex='0'>" if ambiguity_path else "<p class='muted'>No se pudo generar la figura ambiguity_vs_f1.png.</p>"}
    </section>
    <section class='panel'>
      <h3>Correlaciones Pearson y Spearman</h3>
      <p class='caption'>
        Se reporta la relaciÃƒÂ³n global y por <code>measure_name</code> entre <code>f04_ambiguous_ratio</code> y <code>f05_test_f1</code>.
        Pearson captura tendencia lineal y Spearman la relaciÃƒÂ³n monÃƒÂ³tona por rangos.
      </p>
      {ambiguity_corr_html}
    </section>
    <section class='panel'>
      <h3>Consistencia media vs F1</h3>
      <p class='caption'>
        Scatter con <code>x = f04_avg_label_consistency_per_ow</code> y <code>y = f05_test_f1</code>, color por
        <code>pipeline</code> y marcador por <code>measure_name</code>. Se aÃƒÂ±ade LOWESS global y una LOWESS por pipeline.
      </p>
      {f"<img class='plot plot-zoomable' src='{rel(consistency_path)}' alt='Consistency vs F1' data-fullsrc='{rel(consistency_path)}' role='button' tabindex='0'>" if consistency_path else "<p class='muted'>No se pudo generar la figura consistency_vs_f1.png.</p>"}
    </section>
    <section class='panel'>
      <h3>Correlaciones de consistencia</h3>
      <p class='caption'>
        Se reporta la relaciÃƒÂ³n global y por <code>pipeline</code> entre <code>f04_avg_label_consistency_per_ow</code> y <code>f05_test_f1</code>.
      </p>
      {consistency_corr_html}
    </section>
    <section class='panel'>
      <h3>DeduplicaciÃƒÂ³n vs F1</h3>
      <p class='caption'>
        Scatter con <code>x = f05_removed_ratio_by_dedup</code> y <code>y = f05_test_f1</code>, con color por pipeline y marcador por medida.
      </p>
      {f"<img class='plot plot-zoomable' src='{rel(dedup_path)}' alt='Dedup vs F1' data-fullsrc='{rel(dedup_path)}' role='button' tabindex='0'>" if dedup_path else "<p class='muted'>No se pudo generar la figura dedup_vs_f1.png.</p>"}
    </section>
    <section class='panel'>
      <h3>Balance de clases vs F1</h3>
      <p class='caption'>
        Scatter con <code>x = f04_positive_ratio</code> y <code>y = f05_test_f1</code>, con color por pipeline y marcador por medida.
      </p>
      {f"<img class='plot plot-zoomable' src='{rel(class_balance_path)}' alt='Class balance vs F1' data-fullsrc='{rel(class_balance_path)}' role='button' tabindex='0'>" if class_balance_path else "<p class='muted'>No se pudo generar la figura class_balance_vs_f1.png.</p>"}
    </section>
    <section class='panel'>
      <h3>Balance train vs F1</h3>
      <p class='caption'>
        Scatter con <code>x = f05_positive_ratio_train</code> y <code>y = f05_test_f1</code>, con color por pipeline,
        marcador por medida y LOWESS global.
      </p>
      {f"<img class='plot plot-zoomable' src='{rel(class_balance_train_path)}' alt='Class balance train vs F1' data-fullsrc='{rel(class_balance_train_path)}' role='button' tabindex='0'>" if class_balance_train_path else "<p class='muted'>No se pudo generar la figura class_balance_train_vs_f1.png.</p>"}
    </section>
    <section class='panel'>
      <h3>Balance train vs Recall</h3>
      <p class='caption'>
        Scatter con <code>x = f05_positive_ratio_train</code> y <code>y = f05_test_recall</code>, con color por pipeline,
        marcador por medida, LOWESS global y una LOWESS por pipeline.
      </p>
      {f"<img class='plot plot-zoomable' src='{rel(class_balance_train_recall_path)}' alt='Class balance train vs Recall' data-fullsrc='{rel(class_balance_train_recall_path)}' role='button' tabindex='0'>" if class_balance_train_recall_path else "<p class='muted'>No se pudo generar la figura class_balance_train_vs_recall.png.</p>"}
    </section>
    <section class='panel'>
      <h3>Train positive vs Precision</h3>
      <p class='caption'>
        Scatter con <code>x = f05_positive_ratio_train</code> y <code>y = f05_test_precision</code>, con color por pipeline,
        marcador por medida, LOWESS global y una LOWESS por pipeline.
      </p>
      {f"<img class='plot plot-zoomable' src='{rel(train_positive_precision_path)}' alt='Train positive vs Precision' data-fullsrc='{rel(train_positive_precision_path)}' role='button' tabindex='0'>" if train_positive_precision_path else "<p class='muted'>No se pudo generar la figura train_positive_vs_precision.png.</p>"}
    </section>
    <section class='panel'>
      <h3>Heatmap OW/PW vs F1</h3>
      <p class='caption'>
        AgrupaciÃƒÂ³n por <code>OW</code> y <code>PW</code> calculando la media de <code>f05_test_f1</code> y mostrÃƒÂ¡ndola en un heatmap por pipeline.
      </p>
      {f"<img class='plot plot-zoomable' src='{rel(heatmap_ow_pw_path)}' alt='Heatmap OW PW F1' data-fullsrc='{rel(heatmap_ow_pw_path)}' role='button' tabindex='0'>" if heatmap_ow_pw_path else "<p class='muted'>No se pudo generar la figura heatmap_ow_pw_f1.png.</p>"}
    </section>
    <section class='panel'>
      <h3>Dificultad por medida</h3>
      <p class='caption'>
        Barplot ordenado por <code>measure_name</code> mostrando <code>mean F1</code>, <code>std F1</code> y <code>min F1</code> para identificar quÃƒÂ© medidas parecen mÃƒÂ¡s difÃƒÂ­ciles.
      </p>
      {f"<img class='plot plot-zoomable' src='{rel(measures_difficulty_path)}' alt='Measures difficulty' data-fullsrc='{rel(measures_difficulty_path)}' role='button' tabindex='0'>" if measures_difficulty_path else "<p class='muted'>No se pudo generar la figura measures_difficulty.png.</p>"}
    </section>
    <section class='panel'>
      <h3>Stability Plot</h3>
      <p class='caption'>
        Agrupa ejecuciones repetidas ignorando <code>seed</code> por configuraciÃƒÂ³n
        (<code>measure_name</code>, <code>pipeline</code>, <code>window_strategy</code>,
        <code>deduplication_mode_effective</code>, <code>OW</code>, <code>PW</code>, <code>LT</code>, <code>model_family</code>)
        y representa <code>mean_f1</code> frente a <code>std_f1</code>. El tamaÃƒÂ±o indica <code>n_runs</code>;
        las lÃƒÂ­neas guÃƒÂ­a muestran la media global de ambos ejes.
      </p>
      {f"<img class='plot plot-zoomable' src='{rel(stability_path)}' alt='Stability mean std F1' data-fullsrc='{rel(stability_path)}' role='button' tabindex='0'>" if stability_path else "<p class='muted'>No se pudo generar la figura stability_mean_std_f1.png.</p>"}
    </section>
    <section class='panel'>
      <h3>Boxplot F1 por pipeline</h3>
      <p class='caption'>
        DistribuciÃƒÂ³n de <code>f05_test_f1</code> por <code>pipeline</code> mostrando tambiÃƒÂ©n la media y la mediana.
      </p>
      {f"<img class='plot plot-zoomable' src='{rel(boxplot_path)}' alt='Boxplot F1 pipeline' data-fullsrc='{rel(boxplot_path)}' role='button' tabindex='0'>" if boxplot_path else "<p class='muted'>No se pudo generar la figura boxplot_f1_pipeline.png.</p>"}
    </section>
    """
    return section_html, figure_paths


def make_feature_correlation_heatmap(
    corr_long: pd.DataFrame,
    output_path: Path,
    title: str,
) -> Optional[Path]:
    if corr_long.empty:
        return None

    pivot = corr_long.pivot_table(index="feature", columns="measure_name", values="correlation", aggfunc="mean")
    if pivot.empty:
        return None

    feature_order = pivot.abs().mean(axis=1).sort_values(ascending=False).index.tolist()
    measure_order = get_preferred_measure_order(corr_long.rename(columns={"measure_name": "measure_name"}))
    present_measures = [m for m in measure_order if m in pivot.columns] + [m for m in pivot.columns if m not in measure_order]
    pivot = pivot.reindex(index=feature_order, columns=present_measures)

    arr = pivot.to_numpy(dtype=float)
    plt.figure(figsize=(max(8, len(pivot.columns) * 1.6), max(6, len(pivot.index) * 0.55)))
    ax = plt.gca()
    im = ax.imshow(arr, vmin=-1.0, vmax=1.0, aspect="auto", cmap="coolwarm")
    ax.set_xticks(np.arange(len(pivot.columns)))
    ax.set_yticks(np.arange(len(pivot.index)))
    ax.set_xticklabels(pivot.columns, rotation=35, ha="right")
    ax.set_yticklabels(pivot.index)
    ax.set_title(title)
    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            val = arr[i, j]
            if np.isnan(val):
                continue
            ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=8, color="black")
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    save_current_figure(output_path)
    return output_path


def make_feature_mean_corr_barplot(
    summary_df: pd.DataFrame,
    output_path: Path,
    title: str,
) -> Optional[Path]:
    if summary_df.empty:
        return None

    plot_df = summary_df.copy()
    x = np.arange(len(plot_df))
    colors = ["#2ca02c" if v >= 0 else "#d62728" for v in plot_df["mean_corr"]]

    plt.figure(figsize=(max(10, len(plot_df) * 0.7), 6.2))
    ax = plt.gca()
    bars = ax.bar(x, plot_df["mean_corr"], color=colors, alpha=0.88)
    yerr = plot_df["std_corr"].to_numpy(dtype=float)
    ax.errorbar(x, plot_df["mean_corr"], yerr=yerr, fmt="none", ecolor="#333333", capsize=4, linewidth=1.2)
    ax.bar_label(
        bars,
        labels=[f"{v:.2f}" for v in plot_df["mean_corr"]],
        padding=3,
        fontsize=8,
    )
    ax.axhline(0.0, color="#666666", linewidth=1.0)
    ax.set_xticks(x)
    ax.set_xticklabels(plot_df["feature"], rotation=35, ha="right")
    ax.set_ylabel("mean_corr")
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.2)
    save_current_figure(output_path)
    return output_path

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




# ============================================================
# PLOTS Ã¢â‚¬â€ F04 + F05
# ============================================================




def generate_f045_figures(project_root: Path, f045_summary: pd.DataFrame) -> Dict[str, Path]:
    fig_root = figures_dir(project_root) / "f045"
    fig_root.mkdir(parents=True, exist_ok=True)

    figure_paths: Dict[str, Path] = {}

    if f045_summary.empty:
        return figure_paths

    unique_pairs = (
        f045_summary[["measure_name", "direction", "measure_direction"]]
        .drop_duplicates()
        .sort_values(["measure_name", "direction"])
        .to_dict("records")
    )

    # Heatmaps por measure + direction
    heatmap_metrics = [
        ("f05_test_f1_mean", "F1 medio"),
        ("f05_test_recall_mean", "Recall medio"),
        ("f05_test_precision_mean", "Precision media"),
        ("f04_positive_ratio_mean", "Positive ratio"),
        ("f04_duplicate_ratio_mean", "Duplicate ratio tras target"),
        ("f04_ambiguous_ratio_mean", "Ambiguous ratio"),
        ("f05_execution_time_mean", "Tiempo medio F05"),
    ]

    for item in unique_pairs:
        measure = item["measure_name"]
        direction = item["direction"]
        label = item["measure_direction"]
        sub = f045_summary[
            (f045_summary["measure_name"] == measure) &
            (f045_summary["direction"] == direction)
        ].copy()

        key_suffix = sanitize_filename(f"{measure}__{direction}")

        for metric_col, metric_title in heatmap_metrics:
            out = fig_root / f"heatmap_{metric_col}__{key_suffix}.png"
            p = make_heatmap_from_df(
                sub,
                index_col="OW",
                column_col="PW",
                value_col=metric_col,
                title=f"{label} Ã¢â‚¬â€ {metric_title}",
                xlabel="PW",
                ylabel="OW",
                output_path=out,
                time_axes=True,
            )
            if p:
                figure_paths[f"f045_heatmap_{metric_col}__{key_suffix}"] = p

    # Barras de pipelines globales
    for metric_col, title in [
        ("f05_test_f1_mean", "F1 medio por pipeline"),
        ("f05_test_recall_mean", "Recall medio por pipeline"),
        ("f05_test_precision_mean", "Precision media por pipeline"),
        ("f04_ambiguous_ratio_mean", "Ambiguous ratio medio por pipeline(ambiguous_ratio = ambiguous_samples / total_sequences)"),
        ("f05_removed_ratio_by_dedup_mean", "Removed ratio por dedup por pipeline"),
    ]:
        agg = (
            f045_summary.groupby("pipeline", dropna=False)[metric_col]
            .mean()
            .sort_values(ascending=False)
        )
        out = fig_root / f"bar_{metric_col}_by_pipeline.png"
        p = make_bar_from_series(
            agg,
            title=title,
            ylabel=metric_col,
            output_path=out,
        )
        if p:
            figure_paths[f"f045_bar_{metric_col}_by_pipeline"] = p

    # Barras por measure_direction y pipeline
    metrics_for_md = [
        ("f05_test_f1_mean", "F1 medio"),
        ("f05_test_recall_mean", "Recall medio"),
        ("f05_test_precision_mean", "Precision media"),
    ]

    for metric_col, metric_title in metrics_for_md:
        pivot = (
            f045_summary.pivot_table(
                index="measure_direction",
                columns="pipeline",
                values=metric_col,
                aggfunc="mean",
            )
            .sort_index()
        )

        if not pivot.empty:
            plt.figure(figsize=(12, 6))
            x = np.arange(len(pivot.index))
            ncols = len(pivot.columns)
            width = 0.8 / max(1, ncols)

            for i, col in enumerate(pivot.columns):
                plt.bar(
                    x + (i - (ncols - 1) / 2) * width,
                    pivot[col].values,
                    width=width,
                    label=str(col),
                )

            plt.xticks(x, pivot.index, rotation=20, ha="right")
            plt.ylabel(metric_col)
            plt.title(f"{metric_title} por measure+direction y pipeline")
            plt.legend()
            out = fig_root / f"grouped_{metric_col}_by_measure_direction_pipeline.png"
            save_current_figure(out)
            figure_paths[f"f045_grouped_{metric_col}_by_measure_direction_pipeline"] = out

    # Scatters
    scatter_specs = [
        (
            "f03_dup_ratio_ow_mean",
            "f05_test_f1_mean",
            "DuplicaciÃƒÂ³n OW vs F1",
            "Dup ratio OW",
            "F1 medio",
        ),
        (
            "f04_positive_ratio_mean",
            "f05_test_f1_mean",
            "Positive ratio vs F1",
            "Positive ratio",
            "F1 medio",
        ),
        (
            "f04_ambiguous_ratio_mean",
            "f05_test_f1_mean",
            "Ambiguous ratio vs F1",
            "Ambiguous ratio",
            "F1 medio",
        ),
        (
            "f05_removed_ratio_by_dedup_mean",
            "f05_test_f1_mean",
            "Removed ratio by dedup vs F1",
            "Removed ratio by dedup",
            "F1 medio",
        ),
        (
            "f05_execution_time_mean",
            "f05_test_f1_mean",
            "Tiempo F05 vs F1",
            "Tiempo medio F05",
            "F1 medio",
        ),
    ]

    for x_col, y_col, title, xlabel, ylabel in scatter_specs:
        out = fig_root / f"scatter_{x_col}__{y_col}.png"
        p = make_scatter(
            f045_summary,
            x_col=x_col,
            y_col=y_col,
            label_cols=["measure_direction", "pipeline"],
            title=title,
            xlabel=xlabel,
            ylabel=ylabel,
            output_path=out,
        )
        if p:
            figure_paths[f"f045_scatter_{x_col}__{y_col}"] = p

    return figure_paths


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


def make_grouped_pipeline_metric_plot(
    df: pd.DataFrame,
    metric_specs: List[Tuple[str, str]],
    title: str,
    output_path: Path,
) -> Optional[Path]:
    if df.empty or "pipeline" not in df.columns:
        return None

    valid_specs = [(col, label) for col, label in metric_specs if col in df.columns]
    if not valid_specs:
        return None

    agg = (
        df.groupby("pipeline", dropna=False)[[col for col, _ in valid_specs]]
        .mean()
        .reindex(["synchro_auto", "synchro_all", "synchro_none", "asynOW_none"])
        .dropna(how="all")
    )
    if agg.empty:
        return None

    x = np.arange(len(agg.index))
    width = 0.8 / max(1, len(valid_specs))

    plt.figure(figsize=(12, 5.5))
    ax = plt.gca()

    for i, (metric_col, metric_label) in enumerate(valid_specs):
        vals = agg[metric_col].to_numpy(dtype=float)
        bars = ax.bar(
            x + (i - (len(valid_specs) - 1) / 2.0) * width,
            vals,
            width=width,
            label=metric_label,
        )
        ax.bar_label(
            bars,
            labels=[("" if np.isnan(v) else f"{v:.3f}") for v in vals],
            padding=3,
            fontsize=8,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(agg.index)
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.2)
    ax.legend()
    save_current_figure(output_path)
    return output_path


def make_pipeline_scatter_plot(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    title: str,
    xlabel: str,
    ylabel: str,
    output_path: Path,
    *,
    facet_by_pipeline: bool = False,
) -> Optional[Path]:
    needed = [x_col, y_col, "pipeline"]
    if df.empty or not all(c in df.columns for c in needed):
        return None

    sub = df[needed + [c for c in ["OW", "PW", "variant_f04"] if c in df.columns]].dropna().copy()
    if sub.empty:
        return None

    pipeline_order = ["synchro_auto", "synchro_all", "synchro_none", "asynOW_none"]
    color_map = {
        "synchro_auto": "#1f77b4",
        "synchro_all": "#ff7f0e",
        "synchro_none": "#2ca02c",
        "asynOW_none": "#d62728",
    }

    if facet_by_pipeline:
        present = [p for p in pipeline_order if p in set(sub["pipeline"].astype(str))]
        if not present:
            return None

        fig, axes = plt.subplots(1, len(present), figsize=(5.2 * len(present), 5.2), sharey=True, squeeze=False)
        axes = axes[0]
        for ax, pipeline in zip(axes, present):
            cur = sub[sub["pipeline"].astype(str) == pipeline].copy()
            if cur.empty:
                continue
            ax.scatter(
                cur[x_col],
                cur[y_col],
                s=80,
                alpha=0.82,
                color=color_map.get(pipeline, "#444"),
                edgecolors="white",
                linewidths=0.7,
            )
            ax.set_title(pipeline)
            ax.set_xlabel(xlabel)
            ax.grid(alpha=0.22)
            for _, r in cur.iterrows():
                label_parts = []
                if "OW" in cur.columns and not pd.isna(r.get("OW")):
                    label_parts.append(f"OW={human_time(r['OW'])}")
                if "PW" in cur.columns and not pd.isna(r.get("PW")):
                    label_parts.append(f"PW={human_time(r['PW'])}")
                if label_parts:
                    ax.annotate(" | ".join(label_parts), (r[x_col], r[y_col]), fontsize=7, alpha=0.75)
        axes[0].set_ylabel(ylabel)
        fig.suptitle(title)
        save_current_figure(output_path)
        return output_path

    plt.figure(figsize=(7.2, 5.8))
    ax = plt.gca()
    for pipeline in pipeline_order:
        cur = sub[sub["pipeline"].astype(str) == pipeline].copy()
        if cur.empty:
            continue
        ax.scatter(
            cur[x_col],
            cur[y_col],
            s=84,
            alpha=0.82,
            color=color_map.get(pipeline, "#444"),
            edgecolors="white",
            linewidths=0.7,
            label=pipeline,
        )
        for _, r in cur.iterrows():
            label_parts = []
            if "OW" in cur.columns and not pd.isna(r.get("OW")):
                label_parts.append(f"OW={human_time(r['OW'])}")
            if "PW" in cur.columns and not pd.isna(r.get("PW")):
                label_parts.append(f"PW={human_time(r['PW'])}")
            if label_parts:
                ax.annotate(" | ".join(label_parts), (r[x_col], r[y_col]), fontsize=7, alpha=0.72)

    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(alpha=0.22)
    ax.legend(title="pipeline")
    save_current_figure(output_path)
    return output_path


def generate_analysis_by_pipeline(
    project_root: Path,
    master_f045: pd.DataFrame,
) -> Tuple[str, Dict[str, Path]]:
    fig_root = figures_dir(project_root) / "f045" / "analysis_by_pipeline"
    fig_root.mkdir(parents=True, exist_ok=True)

    if master_f045.empty:
        return "<section class='panel'><p class='muted'>No hay datos en master_f045 para anÃƒÂ¡lisis por pipeline.</p></section>", {}

    df = master_f045.copy()
    if "pipeline" not in df.columns:
        df["pipeline"] = df.apply(
            lambda r: pipeline_label(
                str(r.get("window_strategy", "")),
                str(r.get("deduplication_mode", "")),
            ),
            axis=1,
        )

    preferred_measure_order = [
        "Battery_Active_Power",
        "FC_Active_Power",
        "Outlet_Temperature",
        "PVPCS_Active_Power",
    ]
    measures_present = [m for m in preferred_measure_order if m in set(df["measure_name"].dropna().astype(str))]
    remaining_measures = [
        m for m in sorted(df["measure_name"].dropna().astype(str).unique().tolist())
        if m not in measures_present
    ]
    measure_order = measures_present + remaining_measures
    direction_order = ["high", "low"]
    pipeline_order = ["synchro_auto", "synchro_all", "synchro_none", "asynOW_none"]
    figure_paths: Dict[str, Path] = {}
    sections: List[str] = []

    def rel_to_analysis(path: Optional[Path]) -> Optional[str]:
        if path is None:
            return None
        return "../" + path.relative_to(analysis_root(project_root)).as_posix()

    def fmt_card_val(value: Any, kind: str = "float") -> str:
        if value is None or pd.isna(value):
            return "N/A"
        if kind == "int":
            return f"{int(float(value)):,}"
        if kind == "pct":
            return f"{100 * float(value):.2f}%"
        return f"{float(value):.4f}"

    def hash_image_for_row(row: pd.Series) -> Optional[Path]:
        variant_f04 = str(row.get("variant_f04", "")).strip()
        if not variant_f04:
            return None
        base = figures_dir(project_root) / "f04" / "hash_by_label"
        if str(row.get("pipeline", "")) == "synchro_auto":
            p = base / f"{variant_f04}__hash_by_label__dedup_auto.png"
            if p.exists():
                return p
        p = base / f"{variant_f04}__hash_by_label.png"
        return p if p.exists() else None

    def build_pipeline_card(row: pd.Series) -> str:
        img_path = hash_image_for_row(row)
        img_html = ""
        if img_path is not None:
            rel = rel_to_analysis(img_path)
            img_html = (
                f"<img class='plot plot-zoomable' src='{rel}' "
                f"alt='Hash by label {row.get('variant_f04', '')}' "
                f"data-fullsrc='{rel}' role='button' tabindex='0'>"
            )

        return f"""
        <section class="panel">
          <h4>{row.get('pipeline', '')}</h4>
          <p class="caption">
            Variante F04 seleccionada por mejor <code>f05_test_f1</code> medio dentro del pipeline.
            ConfiguraciÃƒÂ³n: OW={human_time(row.get('OW'))}, PW={human_time(row.get('PW'))}, LT={human_time(row.get('LT'))}.
          </p>
          <div class="hashmap-meta-grid">
            <div class="kv-item"><div class="kv-label">variant_f04</div><div class="kv-value">{row.get('variant_f04', '')}</div></div>
            <div class="kv-item"><div class="kv-label">window_strategy</div><div class="kv-value">{row.get('window_strategy', '')}</div></div>
            <div class="kv-item"><div class="kv-label">dedup_mode</div><div class="kv-value">{row.get('deduplication_mode', '')}</div></div>
            <div class="kv-item"><div class="kv-label">dedup_effective</div><div class="kv-value">{row.get('deduplication_mode_effective', '')}</div></div>
            <div class="kv-item"><div class="kv-label">f04_n_windows</div><div class="kv-value">{fmt_card_val(row.get('f04_n_windows'), 'int')}</div></div>
            <div class="kv-item"><div class="kv-label">f04_n_windows_pos</div><div class="kv-value">{fmt_card_val(row.get('f04_n_windows_pos'), 'int')}</div></div>
            <div class="kv-item"><div class="kv-label">f04_n_windows_neg</div><div class="kv-value">{fmt_card_val(row.get('f04_n_windows_neg'), 'int')}</div></div>
            <div class="kv-item"><div class="kv-label">f04_positive_ratio</div><div class="kv-value">{fmt_card_val(row.get('f04_positive_ratio'), 'pct')}</div></div>
            <div class="kv-item"><div class="kv-label">f04_duplicate_ratio</div><div class="kv-value">{fmt_card_val(row.get('f04_duplicate_ratio'), 'pct')}</div></div>
            <div class="kv-item"><div class="kv-label">f04_unique_ratio</div><div class="kv-value">{fmt_card_val(row.get('f04_unique_ratio'), 'pct')}</div></div>
            <div class="kv-item"><div class="kv-label">f05_test_f1_mean</div><div class="kv-value">{fmt_card_val(row.get('f05_test_f1_mean'))}</div></div>
          </div>
          <div class="hashmap-explanation">
            <h5 class="subpanel-title">AmbigÃƒÂ¼edad</h5>
            <div class="hashmap-meta-grid">
              <div class="kv-item"><div class="kv-label">ambiguous_sequences</div><div class="kv-value">{fmt_card_val(row.get('f04_ambiguous_sequences'), 'int')}</div></div>
              <div class="kv-item"><div class="kv-label">ambiguous_samples</div><div class="kv-value">{fmt_card_val(row.get('f04_ambiguous_samples'), 'int')}</div></div>
              <div class="kv-item"><div class="kv-label">ambiguous_ratio</div><div class="kv-value">{fmt_card_val(row.get('f04_ambiguous_ratio'), 'pct')}</div></div>
              <div class="kv-item"><div class="kv-label">avg_label_consistency_per_ow</div><div class="kv-value">{fmt_card_val(row.get('f04_avg_label_consistency_per_ow'))}</div></div>
            </div>
            <p>
              La consistencia media (<code>avg_label_consistency_per_ow</code>) mide hasta quÃƒÂ© punto una misma ventana OW produce siempre la misma etiqueta:
              valores cercanos a 1 indican que el problema es estable y aprendible.
            </p>
            <p>
              El <code>ambiguous_ratio</code> cuantifica la fracciÃƒÂ³n de muestras en las que esa coherencia se rompe,
              es decir, casos en los que una misma OW aparece asociada a etiquetas distintas.
            </p>
            <p>
              Ambas mÃƒÂ©tricas son complementarias: un dataset ideal presenta alta consistencia y bajo
              <code>ambiguous_ratio</code>, lo que implica baja ambigÃƒÂ¼edad y mayor capacidad de aprendizaje por parte del modelo.
            </p>
          </div>
          {img_html}
        </section>
        """

    for measure_name in measure_order:
        measure_df = df[df["measure_name"] == measure_name].copy()
        if measure_df.empty:
            continue

        direction_sections: List[str] = []
        for direction in direction_order:
            sub = measure_df[measure_df["direction"] == direction].copy()
            if sub.empty:
                continue

            representative = (
                sub.groupby(
                    [
                        "pipeline",
                        "variant_f04",
                        "window_strategy",
                        "deduplication_mode",
                        "deduplication_mode_effective",
                        "OW",
                        "PW",
                        "LT",
                    ],
                    dropna=False,
                )
                .agg(
                    f05_test_f1_mean=("f05_test_f1", "mean"),
                    f04_n_windows=("f04_n_windows", "mean"),
                    f04_n_windows_pos=("f04_n_windows_pos", "mean"),
                    f04_n_windows_neg=("f04_n_windows_neg", "mean"),
                    f04_positive_ratio=("f04_positive_ratio", "mean"),
                    f04_duplicate_ratio=("f04_duplicate_ratio", "mean"),
                    f04_ambiguous_sequences=("f04_ambiguous_sequences", "mean"),
                    f04_ambiguous_samples=("f04_ambiguous_samples", "mean"),
                    f04_ambiguous_ratio=("f04_ambiguous_ratio", "mean"),
                    f04_avg_label_consistency_per_ow=("f04_avg_label_consistency_per_ow", "mean"),
                    f04_unique_ratio=("f04_unique_ratio", "mean"),
                )
                .reset_index()
                .sort_values(["pipeline", "f05_test_f1_mean"], ascending=[True, False])
            )
            representative = representative.groupby("pipeline", as_index=False).head(1)
            present_categories = [p for p in pipeline_order if p in set(representative["pipeline"].astype(str))]
            extra_categories = [
                p for p in representative["pipeline"].dropna().astype(str).unique().tolist()
                if p not in present_categories
            ]
            representative["pipeline"] = pd.Categorical(
                representative["pipeline"],
                categories=present_categories + extra_categories,
                ordered=True,
            )
            representative = representative.sort_values("pipeline")

            perf_fig = make_grouped_pipeline_metric_plot(
                sub,
                metric_specs=[
                    ("f05_test_f1", "F1"),
                    ("f05_test_recall", "Recall"),
                    ("f05_test_precision", "Precision"),
                ],
                title=f"{measure_name} [{direction}] - desempeÃƒÂ±o F05 por pipeline",
                output_path=fig_root / f"{sanitize_filename(measure_name)}__{direction}__perf.png",
            )
            if perf_fig is not None:
                figure_paths[f"{measure_name}__{direction}__perf"] = perf_fig

            f04_fig = make_grouped_pipeline_metric_plot(
                sub,
                metric_specs=[
                    ("f04_positive_ratio", "Positive ratio"),
                    ("f04_duplicate_ratio", "Duplicate ratio"),
                    ("f04_ambiguous_ratio", "Ambiguous ratio"),
                    ("f05_removed_ratio_by_dedup", "Removed ratio dedup"),
                ],
                title=f"{measure_name} [{direction}] - estructura F04 por pipeline",
                output_path=fig_root / f"{sanitize_filename(measure_name)}__{direction}__f04.png",
            )
            if f04_fig is not None:
                figure_paths[f"{measure_name}__{direction}__f04"] = f04_fig

            cards_html = "\n".join(
                build_pipeline_card(row) for _, row in representative.iterrows()
            ) if not representative.empty else "<section class='panel'><p class='muted'>No hay pipelines disponibles.</p></section>"

            perf_html = ""
            if perf_fig is not None:
                perf_html += f"""
                <section class='panel'>
                  <h4>Comparativa F05</h4>
                  <img class='plot' src='{rel_to_analysis(perf_fig)}' alt='Comparativa F05 {measure_name} {direction}'>
                </section>
                """
            
            # Agregar informaciÃƒÂ³n sobre muestras F05 entrenamiento
            samples_fig = make_grouped_pipeline_metric_plot(
                sub,
                metric_specs=[
                    ("f05_n_train", "Muestras entrenamiento F05"),
                    ("f05_n_samples_after_dedup", "Ventanas disponibles tras dedup"),
                ],
                title=f"{measure_name} [{direction}] - muestras F05 entrenamiento por pipeline",
                output_path=fig_root / f"{sanitize_filename(measure_name)}__{direction}__samples.png",
            )
            if samples_fig is not None:
                perf_html += f"""
                <section class='panel'>
                  <h4>Muestras F05 Entrenamiento (pre rare_events)</h4>
                  <p class="caption">Se muestran dos referencias reales del pipeline:
                  el tamaÃƒÂ±o del split de entrenamiento en F05 (<code>f05_n_train</code>)
                  y el nÃƒÂºmero de ventanas disponibles tras deduplicaciÃƒÂ³n y antes de la fase de entrenamiento
                  (<code>f05_n_samples_after_dedup</code>).
                  Para <code>synchro_none</code>, <code>synchro_all</code> y <code>asynOW_none</code>, esta segunda cifra coincide con todas las muestras disponibles.
                  Para <code>synchro_auto</code>, refleja las ventanas que sobreviven a la deduplicaciÃƒÂ³n.</p>
                  <img class='plot' src='{rel_to_analysis(samples_fig)}' alt='Muestras F05 {measure_name} {direction}'>
                </section>
                """
            if f04_fig is not None:
                perf_html += f"""
                <section class='panel'>
                  <h4>Comparativa estructural F04</h4>
                  <img class='plot' src='{rel_to_analysis(f04_fig)}' alt='Comparativa F04 {measure_name} {direction}'>
                </section>
                """

            structural_analysis_html = ""
            ambiguity_fig = make_pipeline_scatter_plot(
                sub,
                x_col="f04_ambiguous_ratio",
                y_col="f05_test_f1",
                title=f"{measure_name} [{direction}] - ambigÃƒÂ¼edad vs F1",
                xlabel="f04_ambiguous_ratio",
                ylabel="f05_test_f1",
                output_path=fig_root / f"{sanitize_filename(measure_name)}__{direction}__ambiguous_vs_f1.png",
            )
            if ambiguity_fig is not None:
                figure_paths[f"{measure_name}__{direction}__ambiguous_vs_f1"] = ambiguity_fig

            dedup_fig = make_pipeline_scatter_plot(
                sub,
                x_col="f05_removed_ratio_by_dedup",
                y_col="f05_test_f1",
                title=f"{measure_name} [{direction}] - deduplicaciÃƒÂ³n vs F1",
                xlabel="f05_removed_ratio_by_dedup",
                ylabel="f05_test_f1",
                output_path=fig_root / f"{sanitize_filename(measure_name)}__{direction}__dedup_vs_f1.png",
            )
            if dedup_fig is not None:
                figure_paths[f"{measure_name}__{direction}__dedup_vs_f1"] = dedup_fig

            dup_fig = make_pipeline_scatter_plot(
                sub,
                x_col="f03_dup_ratio_ow",
                y_col="f05_test_f1",
                title=f"{measure_name} [{direction}] - duplicaciÃƒÂ³n OW vs F1 por pipeline",
                xlabel="f03_dup_ratio_ow",
                ylabel="f05_test_f1",
                output_path=fig_root / f"{sanitize_filename(measure_name)}__{direction}__dup_vs_f1.png",
                facet_by_pipeline=True,
            )
            if dup_fig is not None:
                figure_paths[f"{measure_name}__{direction}__dup_vs_f1"] = dup_fig

            consistency_fig = make_pipeline_scatter_plot(
                sub,
                x_col="f04_avg_label_consistency_per_ow",
                y_col="f05_test_f1",
                title=f"{measure_name} [{direction}] - consistencia vs F1",
                xlabel="f04_avg_label_consistency_per_ow",
                ylabel="f05_test_f1",
                output_path=fig_root / f"{sanitize_filename(measure_name)}__{direction}__consistency_vs_f1.png",
            )
            if consistency_fig is not None:
                figure_paths[f"{measure_name}__{direction}__consistency_vs_f1"] = consistency_fig

            structural_blocks = []
            if ambiguity_fig is not None:
                structural_blocks.append(
                    f"""
                    <section class='panel'>
                      <h4>Impacto estructural en F1</h4>
                      <p class="caption">RelaciÃƒÂ³n entre la ambigÃƒÂ¼edad del dataset F04 y el rendimiento final en F1. Es la vista clave para detectar conflicto estructural.</p>
                      <img class='plot' src='{rel_to_analysis(ambiguity_fig)}' alt='AmbigÃƒÂ¼edad vs F1 {measure_name} {direction}'>
                    </section>
                    """
                )
            if dedup_fig is not None:
                structural_blocks.append(
                    f"""
                    <section class='panel'>
                      <h4>DeduplicaciÃƒÂ³n vs rendimiento</h4>
                      <p class="caption">Permite ver si quitar muestras por deduplicaciÃƒÂ³n ayuda o perjudica al rendimiento final.</p>
                      <img class='plot' src='{rel_to_analysis(dedup_fig)}' alt='DeduplicaciÃƒÂ³n vs F1 {measure_name} {direction}'>
                    </section>
                    """
                )
            if dup_fig is not None:
                structural_blocks.append(
                    f"""
                    <section class='panel'>
                      <h4>DuplicaciÃƒÂ³n OW vs rendimiento</h4>
                      <p class="caption">Se muestra separada por pipeline para ver quÃƒÂ© familias soportan mejor la redundancia estructural heredada de F03.</p>
                      <img class='plot' src='{rel_to_analysis(dup_fig)}' alt='DuplicaciÃƒÂ³n OW vs F1 {measure_name} {direction}'>
                    </section>
                    """
                )
            if consistency_fig is not None:
                structural_blocks.append(
                    f"""
                    <section class='panel'>
                      <h4>Consistencia vs rendimiento</h4>
                      <p class="caption">Esta relaciÃƒÂ³n suele ser muy directa: cuanto mÃƒÂ¡s consistente es la asignaciÃƒÂ³n de etiquetas por OW, mÃƒÂ¡s aprendible tiende a ser el problema.</p>
                      <img class='plot' src='{rel_to_analysis(consistency_fig)}' alt='Consistencia vs F1 {measure_name} {direction}'>
                    </section>
                    """
                )

            if structural_blocks:
                structural_analysis_html = f"""
                <h4>Lectura estructural del rendimiento</h4>
                <p class="section-note">
                  Esta subsecciÃƒÂ³n estudia cÃƒÂ³mo se relaciona el comportamiento estructural del dataset con <code>f05_test_f1</code>:
                  ambigÃƒÂ¼edad, deduplicaciÃƒÂ³n efectiva, duplicaciÃƒÂ³n heredada de F03 y consistencia de etiquetas.
                </p>
                <div class="two-col">
                  {''.join(structural_blocks)}
                </div>
                """

            direction_sections.append(
                f"""
                <h3>{direction}</h3>
                <p class="section-note">
                  Se compara la representaciÃƒÂ³n F04 y el rendimiento F05 de los cuatro pipelines:
                  <code>synchro_auto</code>, <code>synchro_all</code>, <code>synchro_none</code> y <code>asynOW_none</code>.
                </p>
                <div class="three-col">
                  {cards_html}
                </div>
                <div class="two-col">
                  {perf_html}
                </div>
                {structural_analysis_html}
                """
            )

        if direction_sections:
            sections.append(
                f"""
                <h2>{measure_name}</h2>
                {''.join(direction_sections)}
                """
            )

    if not sections:
        return "<section class='panel'><p class='muted'>No se encontraron secciones vÃƒÂ¡lidas para anÃƒÂ¡lisis por pipeline.</p></section>", figure_paths

    intro = """
  <h3>AnÃƒÂ¡lisis por pipeline</h3>
  <p>
    Para cada medida se presentan dos escenarios, <code>high</code> y <code>low</code>, que permiten comparar comportamientos en condiciones distintas del dataset.
    En cada caso, se selecciona una variante F04 representativa por pipeline, eligiendo aquella que obtiene el mejor rendimiento medio en <code>f05_test_f1</code>.
  </p>
  <p>
    Para cada pipeline seleccionado se muestra su distribuciÃƒÂ³n de hashes por etiqueta, lo que permite visualizar la estructura del dataset subyacente.
    AdemÃƒÂ¡s, se incluyen comparativas agregadas entre los principales pipelines (<code>synchro_auto</code>, <code>synchro_all</code>, <code>synchro_none</code> y <code>asynOW_none</code>),
    facilitando el anÃƒÂ¡lisis de cÃƒÂ³mo afectan las distintas estrategias de windowing y deduplicaciÃƒÂ³n al rendimiento del modelo.
  </p>
</section>
    """
    return intro + "\n".join(sections), figure_paths


def generate_measure_correlation_analysis(
    project_root: Path,
    master_f045: pd.DataFrame,
) -> Tuple[str, Dict[str, Path]]:
    fig_root = figures_dir(project_root) / "f045" / "correlations_by_measure"
    fig_root.mkdir(parents=True, exist_ok=True)

    master_f045 = add_ow_pw_ratio_feature(master_f045)

    if master_f045.empty or "measure_name" not in master_f045.columns:
        return "<section class='panel'><p class='muted'>No hay datos para correlaciÃƒÂ³n por medida.</p></section>", {}

    feature_cols = [
        "OW",
        "OW/PW",
        "LT",
        "f03_dup_ratio_ow",
        "f04_positive_ratio",
        "f04_ambiguous_ratio",
        "f04_avg_label_consistency_per_ow",
        "f05_removed_ratio_by_dedup",
        "f05_test_precision",
        "f05_test_recall",
        "f05_test_f1",
        "f05_execution_time",
    ]
    heatmap_feature_cols = [c for c in feature_cols if c != "f05_test_f1"]

    figure_paths: Dict[str, Path] = {}
    sections: List[str] = []

    def rel_to_analysis(path: Optional[Path]) -> Optional[str]:
        if path is None:
            return None
        return "../" + path.relative_to(analysis_root(project_root)).as_posix()

    corr_long = compute_correlations_by_measure_feature(
        master_f045,
        target_col="f05_test_f1",
        feature_cols=feature_cols,
        method="spearman",
    )
    summary_df = summarize_feature_correlations(corr_long)

    heatmap_path = make_feature_correlation_heatmap(
        corr_long,
        output_path=fig_root / "feature_correlation_by_measure_heatmap.png",
        title="CorrelaciÃƒÂ³n Spearman feature vs f05_test_f1 por medida",
    )
    if heatmap_path is not None:
        figure_paths["feature_correlation_by_measure_heatmap"] = heatmap_path

    barplot_path = make_feature_mean_corr_barplot(
        summary_df,
        output_path=fig_root / "feature_mean_correlation_barplot.png",
        title="CorrelaciÃƒÂ³n media por feature con f05_test_f1",
    )
    if barplot_path is not None:
        figure_paths["feature_mean_correlation_barplot"] = barplot_path

    if not summary_df.empty:
        summary_fmt = summary_df.copy()
        for col in ["mean_corr", "std_corr", "min_corr", "max_corr"]:
            summary_fmt[col] = summary_fmt[col].map(lambda x: f"{float(x):.3f}")
        for col in ["same_sign", "strong_corr", "stable"]:
            summary_fmt[col] = summary_fmt[col].map(lambda x: "True" if bool(x) else "False")
        summary_html = table_html(summary_fmt)
    else:
        summary_html = "<p class='muted'>No se pudo resumir la correlaciÃƒÂ³n por feature.</p>"

    corr_long_html = "<p class='muted'>No hay correlaciones por medida disponibles.</p>"
    if not corr_long.empty:
        corr_long_fmt = corr_long.copy()
        corr_long_fmt["correlation"] = corr_long_fmt["correlation"].map(lambda x: f"{float(x):.3f}")
        corr_long_html = table_html(corr_long_fmt)

    measure_sections: List[str] = []
    measure_order = get_preferred_measure_order(master_f045)
    for measure_name in measure_order:
        sub = master_f045[master_f045["measure_name"].astype(str) == measure_name].copy()
        if sub.empty:
            continue

        out = fig_root / f"{sanitize_filename(measure_name)}__correlation_heatmap.png"
        p = make_correlation_heatmap(
            sub,
            columns=heatmap_feature_cols + ["f05_test_f1"],
            title=f"{measure_name} - correlation heatmap",
            output_path=out,
            method="spearman",
        )
        if p is None:
            continue

        figure_paths[f"{measure_name}__correlation_heatmap"] = p
        measure_sections.append(
            f"""
            <section class='panel'>
              <h4>{measure_name}</h4>
              <p class='caption'>
                CorrelaciÃƒÂ³n interna especÃƒÂ­fica de la medida. Esto permite ver relaciones estructurales propias
                de <code>{measure_name}</code> sin mezclarlas con otras variables objetivo, porque
                <code>FC_Active_Power</code> no tiene por quÃƒÂ© comportarse igual que <code>Battery_Active_Power</code>.
              </p>
              <img class='plot' src='{rel_to_analysis(p)}' alt='Correlation heatmap {measure_name}'>
            </section>
            """
        )

    if not measure_sections and heatmap_path is None and barplot_path is None:
        return "<section class='panel'><p class='muted'>No se pudieron generar heatmaps de correlaciÃƒÂ³n por medida.</p></section>", figure_paths

    overview_html = ""
    if heatmap_path is not None:
        overview_html += f"""
        <section class='panel'>
          <h4>Heatmap feature Ãƒâ€” measure</h4>
          <p class='caption'>
            CorrelaciÃƒÂ³n Spearman entre cada feature y <code>f05_test_f1</code> por medida.
            Esta vista deja claro que <code>FC_Active_Power</code> no tiene por quÃƒÂ© comportarse igual que <code>Battery_Active_Power</code>.
          </p>
          <img class='plot' src='{rel_to_analysis(heatmap_path)}' alt='Feature correlation by measure heatmap'>
        </section>
        """
    if barplot_path is not None:
        overview_html += f"""
        <section class='panel'>
          <h4>Importancia media por feature</h4>
          <p class='caption'>
            Barras ordenadas por <code>|mean_corr|</code>. Las barras de error representan la desviaciÃƒÂ³n entre medidas.
          </p>
          <img class='plot' src='{rel_to_analysis(barplot_path)}' alt='Mean feature correlation barplot'>
        </section>
        """

    intro = f"""
    <h2>CorrelaciÃƒÂ³n por medida</h2>
    <p class="section-note">
      AquÃƒÂ­ la correlaciÃƒÂ³n se calcula por separado para cada <code>measure_name</code> y luego se resume por feature.
      Se marca si una feature mantiene el mismo signo en todas las medidas (<code>same_sign</code>),
      si su efecto medio es fuerte (<code>strong_corr</code>) y si es estable entre medidas (<code>stable</code>).
    </p>
    <div class="two-col">
      {overview_html}
    </div>
    <section class='panel'>
      <h4>Resumen agregado por feature</h4>
      {summary_html}
    </section>
    <section class='panel'>
      <h4>CorrelaciÃƒÂ³n larga por medida y feature</h4>
      {corr_long_html}
    </section>
    """
    return intro + "\n".join(measure_sections), figure_paths


# ============================================================
# HTML
# ============================================================


def build_html(
    project_root: Path,
    master_f03: pd.DataFrame,
    master_f045: pd.DataFrame,
    f03_summary: pd.DataFrame,
    f045_summary: pd.DataFrame,
    fig_f045: Dict[str, Path],
    fig_global: Dict[str, Path],
    top_corr_f1: pd.DataFrame,
    top_corr_recall: pd.DataFrame

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
            # Fallback para rutas fuera del ÃƒÂ¡rbol de analysis.
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


    def fmt(x, pct=False, nd=3):
        if x is None or pd.isna(x):
            return "N/A"
        if pct:
            return f"{100*x:.1f}%"
        return f"{x:,.{nd}f}"


    pipeline_analysis_html, pipeline_analysis_figs = generate_analysis_by_pipeline(project_root, master_f045)
    fig_f045.update(pipeline_analysis_figs)
    measure_corr_html, measure_corr_figs = generate_measure_correlation_analysis(project_root, master_f045)
    fig_f045.update(measure_corr_figs)
    extra_images_html, extra_images_figs = generate_extra_images_analysis(project_root, master_f045)
    fig_f045.update(extra_images_figs)
    modeling_html, modeling_figs = generate_modeling_analysis(project_root, master_f045)
    fig_f045.update(modeling_figs)

    total_runs = len(master_f045)
    total_measures = master_f045["measure_name"].nunique() if not master_f045.empty and "measure_name" in master_f045.columns else 0
    total_pipelines = master_f045["pipeline"].nunique() if not master_f045.empty and "pipeline" in master_f045.columns else 0
    best_f1 = master_f045["f05_test_f1"].max() if not master_f045.empty and "f05_test_f1" in master_f045.columns else None
    best_recall = master_f045["f05_test_recall"].max() if not master_f045.empty and "f05_test_recall" in master_f045.columns else None

    html = f"""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>Informe de anÃƒÂ¡lisis F04-F05</title>
    <link rel="stylesheet" href="../report.css">
  <style>
    .plot-zoomable {{
      cursor: zoom-in;
    }}
    .lightbox {{
      position: fixed;
      inset: 0;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 24px;
      background: rgba(0, 0, 0, 0.86);
      z-index: 9999;
    }}
    .lightbox.is-open {{
      display: flex;
    }}
    .lightbox-image {{
      max-width: min(96vw, 1800px);
      max-height: 92vh;
      width: auto;
      height: auto;
      object-fit: contain;
      background: white;
      border-radius: 10px;
      box-shadow: 0 12px 36px rgba(0, 0, 0, 0.35);
    }}
    .lightbox-close {{
      position: absolute;
      top: 18px;
      right: 22px;
      border: 0;
      border-radius: 999px;
      width: 42px;
      height: 42px;
      font-size: 28px;
      line-height: 1;
      cursor: pointer;
      color: #111;
      background: rgba(255, 255, 255, 0.94);
    }}
  </style>
</head>
<body>

  <h1>AnÃƒÂ¡lisis F04-F05 Ã¢â‚¬â€ pipelines y modelado</h1>
  <p class="small">Generado el {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>

  <p class="lead">
    Informe comparativo a partir de <code>master_f045</code> para conectar la estructura del dataset etiquetado
    en F04 con el rendimiento final observado en F05.
  </p>

  <div class="kpi-grid">
    {metric_card("Runs F05", str(total_runs))}
    {metric_card("Measures", str(total_measures))}
    {metric_card("Pipelines", str(total_pipelines))}
    {metric_card("Best F1", fmt(best_f1))}
    {metric_card("Best Recall", fmt(best_recall))}
  </div>

  {pipeline_analysis_html}

  {measure_corr_html}

  {extra_images_html}

  {modeling_html}

  <div class="lightbox" id="lightbox" aria-hidden="true">
    <button class="lightbox-close" id="lightbox-close" type="button" aria-label="Cerrar imagen">Ãƒâ€”</button>
    <img class="lightbox-image" id="lightbox-image" alt="">
  </div>

  <script>
    (function () {{
      const lightbox = document.getElementById('lightbox');
      const lightboxImage = document.getElementById('lightbox-image');
      const lightboxClose = document.getElementById('lightbox-close');
      if (!lightbox || !lightboxImage || !lightboxClose) return;

      function openLightbox(src, alt) {{
        lightboxImage.src = src;
        lightboxImage.alt = alt || '';
        lightbox.classList.add('is-open');
        lightbox.setAttribute('aria-hidden', 'false');
      }}

      function closeLightbox() {{
        lightbox.classList.remove('is-open');
        lightbox.setAttribute('aria-hidden', 'true');
        lightboxImage.src = '';
      }}

      document.querySelectorAll('.plot-zoomable').forEach((img) => {{
        const handler = () => openLightbox(img.dataset.fullsrc || img.src, img.alt);
        img.addEventListener('click', handler);
        img.addEventListener('keydown', (event) => {{
          if (event.key === 'Enter' || event.key === ' ') {{
            event.preventDefault();
            handler();
          }}
        }});
      }});

      lightboxClose.addEventListener('click', closeLightbox);
      lightbox.addEventListener('click', (event) => {{
        if (event.target === lightbox) closeLightbox();
      }});
      document.addEventListener('keydown', (event) => {{
        if (event.key === 'Escape' && lightbox.classList.contains('is-open')) {{
          closeLightbox();
        }}
      }});
    }})();
  </script>

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
    master_f045_path = (
        args.master_f045.resolve()
        if args.master_f045
        else out_dir / "master_f045.csv"
    )

    if not master_f03_path.exists():
        raise FileNotFoundError(f"No existe master_f03.csv: {master_f03_path}")
    if not master_f045_path.exists():
        raise FileNotFoundError(f"No existe master_f045.csv: {master_f045_path}")

    master_f03 = pd.read_csv(master_f03_path)
    master_f045 = pd.read_csv(master_f045_path)
    master_f045 = add_ow_pw_ratio_feature(master_f045)

    f03_summary = build_f03_summary(master_f03)
    f045_summary = build_f045_summary(master_f045)

    f045_summary.to_csv(out_dir / "config_summary_f045.csv", index=False, encoding="utf-8")

    corr_feature_cols = [
        "OW",
        "OW/PW",
        "LT",
        "f03_dup_ratio_ow",
        "f03_dup_ratio_pw",
        "f04_positive_ratio",
        "f04_duplicate_ratio",
        "f04_ambiguous_ratio",
        "f04_avg_label_consistency_per_ow",
        "f05_removed_ratio_by_dedup",
        "f05_test_precision",
        "f05_test_recall",
        "f05_test_f1",
        "f05_execution_time",
    ]
    corr_long_df = compute_correlations_by_measure_feature(
        master_f045,
        target_col="f05_test_f1",
        feature_cols=corr_feature_cols,
        method="spearman",
    )
    corr_summary_df = summarize_feature_correlations(corr_long_df)
    corr_long_df.to_csv(out_dir / "correlations_by_measure_long.csv", index=False, encoding="utf-8")
    corr_summary_df.to_csv(out_dir / "correlations_by_feature_summary.csv", index=False, encoding="utf-8")

    fig_f045 = generate_f045_figures(project_root, f045_summary)

        
    fig_global = {}
    global_fig_root = figures_dir(project_root) / "global"
    global_fig_root.mkdir(parents=True, exist_ok=True)

    corr_cols = [
        "OW",
        "OW/PW",
        "LT",
        "f03_dup_ratio_ow",
        "f03_dup_ratio_pw",
        "f03_seq_len_mean_ow",
        "f03_seq_len_mean_pw",
        "f04_positive_ratio",
        "f04_ambiguous_ratio",
        "f05_removed_ratio_by_dedup",
        "f05_test_precision",
        "f05_test_recall",
        "f05_test_f1",
        "f05_best_val_recall",
        "f05_execution_time",
    ]

    p = make_correlation_heatmap(
        master_f045,
        columns=corr_cols,
        title="Global correlation heatmap (master_f045)",
        output_path=global_fig_root / "correlation_master_f045.png",
        method="spearman",
    )
    if p:
        fig_global["correlation_master_f045"] = p

    top_corr_f1 = get_top_correlations(
        master_f045,
        target_col="f05_test_f1",
        candidate_cols=[
            "OW",
            "OW/PW",
            "LT",
            "f03_dup_ratio_ow",
            "f03_dup_ratio_pw",
            "f03_seq_len_mean_ow",
            "f04_positive_ratio",
            "f04_ambiguous_ratio",
            "f05_removed_ratio_by_dedup",
            "f05_execution_time",
        ],
        method="spearman",
        top_k=8,
    )

    top_corr_recall = get_top_correlations(
        master_f045,
        target_col="f05_test_recall",
        candidate_cols=[
            "OW",
            "PW",
            "LT",
            "f03_dup_ratio_ow",
            "f03_dup_ratio_pw",
            "f03_seq_len_mean_ow",
            "f04_positive_ratio",
            "f04_ambiguous_ratio",
            "f05_removed_ratio_by_dedup",
            "f05_execution_time",
        ],
        method="spearman",
        top_k=8,
    )

    # html
    output_html = (
        args.output_html.resolve()
        if args.output_html
        else out_dir / "reportf045.html"
    )
    output_html.write_text(
        build_html(
            project_root=project_root,
            master_f03=master_f03,
            master_f045=master_f045,
            f03_summary=f03_summary,
            f045_summary=f045_summary,
            fig_f045=fig_f045,
            fig_global=fig_global,
            top_corr_f1=top_corr_f1,
            top_corr_recall=top_corr_recall,
        ),
        encoding="utf-8",
    )

    print(f"[OK] config_summary_f03.csv generado en: {out_dir / 'config_summary_f03.csv'}")
    print(f"[OK] config_summary_f045.csv generado en: {out_dir / 'config_summary_f045.csv'}")
    print(f"[OK] figuras F045 generadas en: {figures_dir(project_root) / 'f045'}")
    print(f"[OK] reportf045.html generado en: {output_html}")


if __name__ == "__main__":
    main()

# python test/experiments/aticus/analysis/build_reportf045.py
