from __future__ import annotations

import argparse
import html
import math
import re
from itertools import combinations
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


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


def figures_dir(project_root: Path) -> Path:
    return outputs_dir(project_root) / "figures"


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def make_variant_order(values: list[Any]) -> list[str]:
    return [str(v) for v in sorted({str(v) for v in values}, key=natural_variant_key)]


def variant_numeric_id(value: Any) -> int | None:
    text = str(value or "")
    match = VARIANT_RE.match(text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def compact_band_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return "[" + text.replace("|", ", ") + "]"


def build_variant_axis_labels(measure_df: pd.DataFrame, variant_order: list[str]) -> list[str]:
    if measure_df.empty or "variant_f02" not in measure_df.columns or "band_labels_measure" not in measure_df.columns:
        return variant_order

    labels_by_variant: dict[str, str] = {}
    for variant in variant_order:
        series = (
            measure_df.loc[measure_df["variant_f02"].astype(str) == str(variant), "band_labels_measure"]
            .dropna()
            .astype(str)
        )
        band_text = ""
        if not series.empty:
            band_text = series.mode().iloc[0]
        compact = compact_band_label(band_text)
        labels_by_variant[str(variant)] = f"{variant}\n{compact}" if compact else str(variant)
    return [labels_by_variant.get(str(variant), str(variant)) for variant in variant_order]


def split_boundary_after_v220(variant_order: list[str]) -> int | None:
    for idx, variant in enumerate(variant_order):
        numeric_id = variant_numeric_id(variant)
        if numeric_id is not None and numeric_id >= 220:
            return idx
    return None


def safe_float(value: Any) -> float:
    try:
        if value is None or pd.isna(value):
            return float("nan")
        return float(value)
    except Exception:
        return float("nan")


def format_number(value: Any, nd: int = 3) -> str:
    try:
        if value is None or pd.isna(value):
            return "N/A"
        return f"{float(value):,.{nd}f}"
    except Exception:
        return "N/A"


def format_pct(value: Any, nd: int = 1) -> str:
    try:
        if value is None or pd.isna(value):
            return "N/A"
        return f"{100 * float(value):.{nd}f}%"
    except Exception:
        return "N/A"


def rel_to_outputs(path: Path) -> str:
    return path.relative_to(outputs_dir(discover_project_root())).as_posix()


def save_bar_plot(df: pd.DataFrame, x_col: str, y_col: str, title: str, ylabel: str, output_path: Path) -> Path | None:
    if df.empty or x_col not in df.columns or y_col not in df.columns:
        return None
    work = df[[x_col, y_col]].dropna()
    if work.empty:
        return None
    fig, ax = plt.subplots(figsize=(10, 4.8))
    x = np.arange(len(work))
    bars = ax.bar(x, work[y_col].astype(float).to_numpy(), color="#3a6ea5")
    ax.set_xticks(x)
    ax.set_xticklabels(work[x_col].astype(str), rotation=45, ha="right")
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", alpha=0.25)
    for rect, value in zip(bars, work[y_col].astype(float)):
        ax.text(rect.get_x() + rect.get_width() / 2, rect.get_height(), f"{value:.3g}", ha="center", va="bottom", fontsize=8)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return output_path


def save_heatmap(
    matrix_df: pd.DataFrame,
    title: str,
    output_path: Path,
    fmt: str = ".2f",
    cmap: str = "viridis",
    x_ticklabels: list[str] | None = None,
    x_axis_label: str | None = None,
    split_after_col: int | None = None,
) -> Path | None:
    if matrix_df.empty:
        return None
    data = matrix_df.to_numpy(dtype=float)
    fig_w = max(7.5, 1.1 * len(matrix_df.columns) + 2)
    fig_h = max(4.5, 0.45 * len(matrix_df.index) + 2)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    im = ax.imshow(data, aspect="auto", cmap=cmap)
    ax.set_title(title)
    ax.set_xticks(np.arange(len(matrix_df.columns)))
    ax.set_yticks(np.arange(len(matrix_df.index)))
    tick_labels = x_ticklabels if x_ticklabels is not None else list(matrix_df.columns)
    ax.set_xticklabels(tick_labels, rotation=45, ha="right")
    ax.set_yticklabels(matrix_df.index)
    if x_axis_label:
        ax.set_xlabel(x_axis_label)
    if split_after_col is not None and 0 < split_after_col < len(matrix_df.columns):
        ax.axvline(split_after_col - 0.5, color="#d62728", linewidth=3.0, alpha=0.95)
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            value = data[i, j]
            label = "" if np.isnan(value) else format(value, fmt)
            ax.text(j, i, label, ha="center", va="center", fontsize=8, color="white" if not np.isnan(value) and value > np.nanmean(data) else "black")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return output_path


def save_heatmap_grid(
    heatmaps: list[tuple[str, pd.DataFrame]],
    output_path: Path,
    fmt: str = ".2f",
    cmap: str = "YlGnBu",
    x_ticklabels: list[str] | None = None,
    x_axis_label: str | None = None,
    split_after_col: int | None = None,
) -> Path | None:
    available = [(title, matrix_df) for title, matrix_df in heatmaps if matrix_df is not None and not matrix_df.empty]
    if not available:
        return None

    ncols = 2
    nrows = int(math.ceil(len(available) / ncols))
    max_cols = max(len(matrix.columns) for _, matrix in available)
    max_rows = max(len(matrix.index) for _, matrix in available)
    fig_w = max(12, 1.1 * max_cols * ncols + 2)
    fig_h = max(8, 0.45 * max_rows * nrows + 2.5 * nrows)
    fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(fig_w, fig_h))
    axes = np.atleast_1d(axes).ravel()

    for ax, (title, matrix_df) in zip(axes, available):
        data = matrix_df.to_numpy(dtype=float)
        im = ax.imshow(data, aspect="auto", cmap=cmap)
        ax.set_title(title)
        ax.set_xticks(np.arange(len(matrix_df.columns)))
        ax.set_yticks(np.arange(len(matrix_df.index)))
        tick_labels = x_ticklabels if x_ticklabels is not None else list(matrix_df.columns)
        ax.set_xticklabels(tick_labels, rotation=45, ha="right")
        ax.set_yticklabels(matrix_df.index)
        if x_axis_label:
            ax.set_xlabel(x_axis_label)
        if split_after_col is not None and 0 < split_after_col < len(matrix_df.columns):
            ax.axvline(split_after_col - 0.5, color="#d62728", linewidth=3.0, alpha=0.95)
        mean_value = np.nanmean(data) if not np.isnan(data).all() else np.nan
        for i in range(data.shape[0]):
            for j in range(data.shape[1]):
                value = data[i, j]
                label = "" if np.isnan(value) else format(value, fmt)
                color = "white" if not np.isnan(mean_value) and not np.isnan(value) and value > mean_value else "black"
                ax.text(j, i, label, ha="center", va="center", fontsize=8, color=color)
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    for ax in axes[len(available):]:
        ax.axis("off")

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return output_path


def variant_color_map(variants: list[str]) -> dict[str, Any]:
    cmap = plt.get_cmap("tab10")
    return {variant: cmap(i % 10) for i, variant in enumerate(variants)}


def save_scatter_plot(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    title: str,
    output_path: Path,
    color_col: str = "variant_f02",
    annotate: bool = False,
) -> Path | None:
    needed = [x_col, y_col, color_col]
    if any(col not in df.columns for col in needed):
        return None
    work = df[needed].dropna()
    if work.empty:
        return None
    colors = variant_color_map(make_variant_order(work[color_col].tolist()))
    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    for variant, sub in work.groupby(color_col):
        ax.scatter(sub[x_col], sub[y_col], label=str(variant), color=colors.get(str(variant)), s=55, alpha=0.8, edgecolors="white", linewidths=0.4)
        if annotate:
            for _, row in sub.iterrows():
                ax.text(row[x_col], row[y_col], str(variant), fontsize=7, alpha=0.8)
    ax.set_xlabel(x_col)
    ax.set_ylabel(y_col)
    ax.set_title(title)
    ax.grid(alpha=0.25)
    handles, labels = ax.get_legend_handles_labels()
    if len(handles) <= 12:
        ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return output_path


def save_histogram(df: pd.DataFrame, column: str, title: str, output_path: Path, bins: int = 20) -> Path | None:
    if column not in df.columns:
        return None
    values = df[column].dropna().astype(float)
    if values.empty:
        return None
    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    ax.hist(values, bins=bins, color="#4f7cac", edgecolor="white")
    ax.set_title(title)
    ax.set_xlabel(column)
    ax.set_ylabel("Count")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return output_path


def compute_correlations(df: pd.DataFrame, variables: list[str], scope: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    available = [col for col in variables if col in df.columns]
    for x_col, y_col in combinations(available, 2):
        sub = df[[x_col, y_col]].dropna()
        if len(sub) < 3:
            pearson = np.nan
            spearman = np.nan
        else:
            pearson = sub[x_col].corr(sub[y_col], method="pearson")
            spearman = sub[x_col].corr(sub[y_col], method="spearman")
        rows.append(
            {
                "scope": scope,
                "variable_x": x_col,
                "variable_y": y_col,
                "pearson": pearson,
                "spearman": spearman,
                "abs_spearman": abs(spearman) if pd.notna(spearman) else np.nan,
            }
        )
    corr_df = pd.DataFrame(rows)
    if not corr_df.empty:
        corr_df = corr_df.sort_values(["scope", "abs_spearman"], ascending=[True, False]).reset_index(drop=True)
    return corr_df


def make_global_summary(global_df: pd.DataFrame) -> pd.DataFrame:
    if global_df.empty:
        return pd.DataFrame()
    cols = [
        "variant_f02",
        "n_bands",
        "total_events_generated",
        "n_event_types_observed",
        "rare_event_ratio",
        "empty_rows_ratio",
        "normalized_event_entropy",
        "jump_size_mean",
        "event_density_flag",
        "extreme_focus_flag",
        "variant_score",
    ]
    cols = [col for col in cols if col in global_df.columns]
    return global_df[cols].sort_values("variant_f02", key=lambda s: s.map(natural_variant_key)).reset_index(drop=True)


def make_measure_detail_table(measure_df: pd.DataFrame) -> pd.DataFrame:
    if measure_df.empty:
        return pd.DataFrame()
    cols = [
        "variant_f02",
        "measure_name",
        "n_events_generated",
        "n_active_bands",
        "max_band_ratio",
        "extreme_band_ratio",
        "occupancy_entropy",
        "band_degeneracy_flag",
        "extreme_occupancy_flag",
    ]
    cols = [col for col in cols if col in measure_df.columns]
    return measure_df[cols].sort_values(["measure_name", "variant_f02"], key=lambda s: s.map(natural_variant_key) if s.name == "variant_f02" else s).reset_index(drop=True)


def build_rankings(global_df: pd.DataFrame, measure_df: pd.DataFrame, out_dir: Path) -> dict[str, pd.DataFrame]:
    rankings: dict[str, pd.DataFrame] = {}
    if not global_df.empty:
        rankings["top_diversity"] = global_df.sort_values("normalized_event_entropy", ascending=False)[
            ["variant_f02", "normalized_event_entropy", "catalog_coverage_ratio", "variant_score"]
        ].reset_index(drop=True)
        rankings["top_extreme_sensitivity"] = global_df.sort_values("rare_event_ratio", ascending=False)[
            ["variant_f02", "rare_event_ratio", "normalized_event_entropy", "variant_score"]
        ].reset_index(drop=True)
        rankings["top_catalog_coverage"] = global_df.sort_values("catalog_coverage_ratio", ascending=False)[
            ["variant_f02", "catalog_coverage_ratio", "n_event_types_observed", "variant_score"]
        ].reset_index(drop=True)
        rankings["top_variant_score"] = global_df.sort_values("variant_score", ascending=False)[
            ["variant_f02", "variant_score", "normalized_event_entropy", "rare_event_ratio", "empty_rows_ratio"]
        ].reset_index(drop=True)

    if not measure_df.empty:
        rankings["most_degenerate_measures"] = measure_df.sort_values(
            ["max_band_ratio", "n_events_generated"], ascending=[False, False]
        )[
            ["variant_f02", "measure_name", "max_band_ratio", "extreme_band_ratio", "n_events_generated", "band_degeneracy_flag"]
        ].reset_index(drop=True)
        informative = measure_df.copy()
        informative["informativeness_score"] = informative["n_events_generated"].fillna(0) * informative["normalized_occupancy_entropy"].fillna(0)
        rankings["most_informative_measures"] = informative.sort_values(
            ["informativeness_score", "n_events_generated"], ascending=[False, False]
        )[
            ["variant_f02", "measure_name", "informativeness_score", "n_events_generated", "occupancy_entropy", "normalized_occupancy_entropy"]
        ].reset_index(drop=True)

    for name, df in rankings.items():
        df.to_csv(out_dir / f"{name}.csv", index=False, encoding="utf-8")
    return rankings


def strongest_pair(corr_df: pd.DataFrame, x_name: str, y_name: str, scope: str) -> float | None:
    if corr_df.empty:
        return None
    pair = corr_df[
        (corr_df["scope"] == scope)
        & (
            ((corr_df["variable_x"] == x_name) & (corr_df["variable_y"] == y_name))
            | ((corr_df["variable_x"] == y_name) & (corr_df["variable_y"] == x_name))
        )
    ]
    if pair.empty:
        return None
    return safe_float(pair.iloc[0]["spearman"])


def correlation_insights(corr_df: pd.DataFrame) -> list[str]:
    notes: list[str] = []
    rel = strongest_pair(corr_df, "rare_event_ratio", "normalized_event_entropy", "global")
    if rel is not None and not math.isnan(rel):
        direction = "higher" if rel > 0 else "lower"
        notes.append(f"Rare-event emphasis tends to coincide with {direction} entropy (Spearman {rel:.3f}).")
    rel = strongest_pair(corr_df, "n_bands", "total_events_generated", "global")
    if rel is not None and not math.isnan(rel):
        direction = "more" if rel > 0 else "fewer"
        notes.append(f"Adding bands tends to produce {direction} events overall (Spearman {rel:.3f}).")
    rel = strongest_pair(corr_df, "max_band_ratio", "n_events_generated", "measure")
    if rel is not None and not math.isnan(rel):
        direction = "lower" if rel < 0 else "higher"
        notes.append(f"More degenerate band occupancy is associated with {direction} measure activity (Spearman {rel:.3f}).")
    rel = strongest_pair(corr_df, "extreme_band_ratio", "n_events_generated", "measure")
    if rel is not None and not math.isnan(rel):
        direction = "higher" if rel > 0 else "lower"
        notes.append(f"Extreme-band occupancy tends to come with {direction} measure-level event counts (Spearman {rel:.3f}).")
    return notes


def metric_card(label: str, value: str) -> str:
    return f"<div class='metric-card'><div class='metric-label'>{html.escape(label)}</div><div class='metric-value'>{html.escape(value)}</div></div>"


def table_html(df: pd.DataFrame, max_rows: int | None = None) -> str:
    if df.empty:
        return "<p class='muted'>No data available.</p>"
    work = df.copy()
    if max_rows is not None:
        work = work.head(max_rows)
    return work.to_html(index=False, classes="data-table", border=0, justify="left")


def image_block(path: Path | None, title: str) -> str:
    if path is None or not path.exists():
        return f"<section class='panel'><h4>{html.escape(title)}</h4><p class='muted'>Figure not available.</p></section>"
    rel = path.relative_to(outputs_dir(discover_project_root())).as_posix()
    return f"<section class='panel'><h4>{html.escape(title)}</h4><img class='plot' src='{rel}' alt='{html.escape(title)}'></section>"


def build_html(
    project_root: Path,
    global_df: pd.DataFrame,
    measure_df: pd.DataFrame,
    variant_summary: pd.DataFrame,
    measure_summary: pd.DataFrame,
    corr_df: pd.DataFrame,
    figures: dict[str, Path | None],
    rankings: dict[str, pd.DataFrame],
) -> str:
    total_events = global_df["total_events_generated"].sum() if "total_events_generated" in global_df.columns and not global_df.empty else 0
    n_variants = global_df["variant_f02"].nunique() if "variant_f02" in global_df.columns and not global_df.empty else 0
    n_measures = measure_df["measure_name"].nunique() if "measure_name" in measure_df.columns and not measure_df.empty else 0

    best_diversity = global_df.sort_values("normalized_event_entropy", ascending=False).iloc[0]["variant_f02"] if not global_df.empty else "N/A"
    best_extreme = global_df.sort_values("rare_event_ratio", ascending=False).iloc[0]["variant_f02"] if not global_df.empty else "N/A"
    densest = global_df.sort_values("empty_rows_ratio", ascending=True).iloc[0]["variant_f02"] if not global_df.empty else "N/A"
    if not measure_df.empty:
        degenerate_by_variant = measure_df.groupby("variant_f02", dropna=False)["max_band_ratio"].mean().sort_values(ascending=False)
        most_degenerate_variant = degenerate_by_variant.index[0]
        most_degenerate_measure = measure_df.groupby("measure_name", dropna=False)["max_band_ratio"].mean().sort_values(ascending=False).index[0]
        most_informative_measure = (
            measure_df.assign(informativeness=lambda d: d["n_events_generated"].fillna(0) * d["normalized_occupancy_entropy"].fillna(0))
            .groupby("measure_name", dropna=False)["informativeness"]
            .mean()
            .sort_values(ascending=False)
            .index[0]
        )
    else:
        most_degenerate_variant = "N/A"
        most_degenerate_measure = "N/A"
        most_informative_measure = "N/A"

    top_corr = corr_df.head(12)[["scope", "variable_x", "variable_y", "pearson", "spearman"]] if not corr_df.empty else pd.DataFrame()
    conclusions = [
        f"Variant {best_diversity} shows the highest event diversity.",
        f"Variant {best_extreme} is the most extreme-focused under the rare-event definition.",
        f"Variant {densest} produces the densest temporal event representation.",
        f"Variant {most_degenerate_variant} concentrates occupancy most strongly into a few bands.",
        f"Measure {most_degenerate_measure} appears most structurally degenerate across variants.",
        f"Measure {most_informative_measure} appears most structurally informative across variants.",
    ]
    corr_notes = correlation_insights(corr_df)

    global_figure_keys = [
        "bar_total_events_generated",
        "bar_n_event_types_observed",
        "bar_rare_event_ratio",
        "bar_empty_rows_ratio",
        "bar_normalized_event_entropy",
        "bar_jump_size_mean",
        "scatter_rare_vs_entropy",
        "scatter_nbands_vs_total_events",
        "scatter_catalog_vs_total_events",
        "scatter_top1_vs_entropy",
        "scatter_jump_vs_pct2",
    ]
    measure_scatter_keys = [
        "scatter_extreme_vs_events",
        "scatter_max_vs_events",
        "scatter_active_bands_vs_events",
        "scatter_entropy_vs_events",
        "scatter_rare_vs_top1_measure",
    ]
    distribution_keys = [
        "hist_n_events_generated",
        "hist_max_band_ratio",
        "hist_extreme_band_ratio",
        "hist_occupancy_entropy",
    ]

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Jenofonte F02 Analysis</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #1f2933; background: #f7fafc; }}
    h1, h2, h3, h4 {{ color: #102a43; }}
    .lead {{ font-size: 1.05rem; max-width: 1000px; }}
    .metric-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 18px 0 24px; }}
    .metric-card {{ background: white; border-radius: 10px; padding: 14px; box-shadow: 0 1px 3px rgba(16,42,67,0.12); }}
    .metric-label {{ font-size: 0.85rem; color: #486581; }}
    .metric-value {{ font-size: 1.35rem; font-weight: 700; margin-top: 6px; }}
    .panel {{ background: white; border-radius: 12px; padding: 18px; margin: 18px 0; box-shadow: 0 1px 3px rgba(16,42,67,0.12); }}
    .two-col {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }}
    .three-col {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }}
    .plot {{ width: 100%; height: auto; border-radius: 8px; border: 1px solid #d9e2ec; }}
    .data-table {{ width: 100%; border-collapse: collapse; font-size: 0.92rem; }}
    .data-table th, .data-table td {{ border-bottom: 1px solid #d9e2ec; padding: 8px 10px; text-align: left; }}
    .data-table th {{ background: #f0f4f8; }}
    .muted {{ color: #7b8794; }}
    ul.flat li {{ margin: 6px 0; }}
  </style>
</head>
<body>
  <h1>Jenofonte F02 Event Analysis</h1>
  <p class="lead">
    Comparative analysis of F02 discretization variants focused on extreme-state event generation. This report consolidates
    global event quality, per-measure occupancy structure, pairwise correlations and heuristic rankings to decide which variants
    are strongest candidates for downstream F03-F05 analysis.
  </p>

  <section class="panel">
    <h2>1. Executive Summary</h2>
    <div class="metric-grid">
      {metric_card("F02 variants", str(n_variants))}
      {metric_card("Measures", str(n_measures))}
      {metric_card("Total events", format_number(total_events, 0))}
      {metric_card("Best diversity", str(best_diversity))}
      {metric_card("Best extreme focus", str(best_extreme))}
      {metric_card("Most degenerate variant", str(most_degenerate_variant))}
      {metric_card("Densest variant", str(densest))}
      {metric_card("Top measure", str(most_informative_measure))}
    </div>
    <ul class="flat">
      {''.join(f"<li>{html.escape(item)}</li>" for item in conclusions)}
    </ul>
  </section>

  <section class="panel">
    <h2>2. Variant Summary Table</h2>
    {table_html(variant_summary)}
  </section>

  <h2>3. Global Figures</h2>
  <div class="two-col">
    {''.join(image_block(figures.get(key), key.replace('_', ' ').title()) for key in global_figure_keys)}
  </div>

  <h2>4. Heatmaps By Measure</h2>
  <div class="two-col">
    {image_block(figures.get("heatmap_measure_bundle"), "Measure Heatmaps Bundle")}
  </div>
  <p class="muted">
    Higher occupancy entropy means the dataset is more evenly distributed across bands, which usually indicates a better balanced use of the discretization space.
  </p>

  <h2>5. Measure-Level Analysis</h2>
  <section class="panel">
    <h3>Measure Summary</h3>
    {table_html(measure_summary)}
  </section>
  <section class="panel">
    <h3>Measure Detail</h3>
    {table_html(make_measure_detail_table(measure_df), max_rows=200)}
  </section>
  <div class="two-col">
    {''.join(image_block(figures.get(key), key.replace('_', ' ').title()) for key in measure_scatter_keys)}
  </div>

  <h2>6. Correlations</h2>
  <section class="panel">
    <h3>Relevant Correlation Pairs</h3>
    {table_html(top_corr)}
    <ul class="flat">
      {''.join(f"<li>{html.escape(item)}</li>" for item in corr_notes)}
    </ul>
  </section>

  <h2>7. Distributions</h2>
  <div class="two-col">
    {''.join(image_block(figures.get(key), key.replace('_', ' ').title()) for key in distribution_keys)}
  </div>

  <h2>8. Rankings</h2>
  <div class="two-col">
    <section class="panel">
      <h3>Top Diversity</h3>
      {table_html(rankings.get("top_diversity", pd.DataFrame()), max_rows=10)}
    </section>
    <section class="panel">
      <h3>Top Extreme Sensitivity</h3>
      {table_html(rankings.get("top_extreme_sensitivity", pd.DataFrame()), max_rows=10)}
    </section>
    <section class="panel">
      <h3>Top Catalog Coverage</h3>
      {table_html(rankings.get("top_catalog_coverage", pd.DataFrame()), max_rows=10)}
    </section>
    <section class="panel">
      <h3>Top Variant Score</h3>
      {table_html(rankings.get("top_variant_score", pd.DataFrame()), max_rows=10)}
    </section>
    <section class="panel">
      <h3>Most Degenerate Measures</h3>
      {table_html(rankings.get("most_degenerate_measures", pd.DataFrame()), max_rows=10)}
    </section>
    <section class="panel">
      <h3>Most Informative Measures</h3>
      {table_html(rankings.get("most_informative_measures", pd.DataFrame()), max_rows=10)}
    </section>
  </div>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build F02 report for Jenofonte")
    parser.add_argument("--project-root", default=None, help="Project root path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = discover_project_root(args.project_root)
    out_dir = outputs_dir(project_root)
    fig_dir = figures_dir(project_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    global_df = load_csv(out_dir / "f02_master_global.csv")
    measure_df = load_csv(out_dir / "f02_master_measure.csv")
    variant_summary = load_csv(out_dir / "f02_variant_summary.csv")
    measure_summary = load_csv(out_dir / "f02_measure_summary.csv")

    if not global_df.empty:
        global_df = global_df.sort_values("variant_f02", key=lambda s: s.map(natural_variant_key)).reset_index(drop=True)
    if not measure_df.empty:
        measure_df = measure_df.sort_values(["measure_name", "variant_f02"], key=lambda s: s.map(natural_variant_key) if s.name == "variant_f02" else s).reset_index(drop=True)

    global_corr_vars = [
        "n_bands",
        "total_events_generated",
        "mean_events_per_row",
        "empty_rows_ratio",
        "n_event_types_observed",
        "catalog_coverage_ratio",
        "rare_event_ratio",
        "top1_event_ratio",
        "normalized_event_entropy",
        "jump_size_mean",
        "pct_jump_eq_1",
        "pct_jump_ge_2",
    ]
    measure_corr_vars = [
        "n_events_generated",
        "n_unique_event_types_observed",
        "top1_ratio",
        "rare_event_ratio",
        "jump_size_mean",
        "n_active_bands",
        "max_band_ratio",
        "extreme_band_ratio",
        "occupancy_entropy",
        "normalized_occupancy_entropy",
    ]
    corr_df = pd.concat(
        [
            compute_correlations(global_df, global_corr_vars, "global"),
            compute_correlations(measure_df, measure_corr_vars, "measure"),
        ],
        ignore_index=True,
    )
    corr_df.to_csv(out_dir / "f02_correlations.csv", index=False, encoding="utf-8")

    figures: dict[str, Path | None] = {}
    bar_specs = [
        ("total_events_generated", "Total events generated by variant", "Events", "bar_total_events_generated.png"),
        ("n_event_types_observed", "Observed event types by variant", "Observed event types", "bar_n_event_types_observed.png"),
        ("rare_event_ratio", "Rare event ratio by variant", "Rare event ratio", "bar_rare_event_ratio.png"),
        ("empty_rows_ratio", "Empty rows ratio by variant", "Empty rows ratio", "bar_empty_rows_ratio.png"),
        ("normalized_event_entropy", "Normalized event entropy by variant", "Normalized entropy", "bar_normalized_event_entropy.png"),
        ("jump_size_mean", "Jump size mean by variant", "Jump size mean", "bar_jump_size_mean.png"),
    ]
    for metric, title, ylabel, filename in bar_specs:
        figures[f"bar_{metric}"] = save_bar_plot(global_df, "variant_f02", metric, title, ylabel, fig_dir / filename)

    heatmap_metrics = [
        "n_events_generated",
        "n_unique_event_types_observed",
        "rare_event_ratio",
        "max_band_ratio",
        "extreme_band_ratio",
        "occupancy_entropy",
    ]
    if not measure_df.empty:
        variant_order = make_variant_order(measure_df["variant_f02"].tolist())
        variant_ticklabels = build_variant_axis_labels(measure_df, variant_order)
        split_after_col = split_boundary_after_v220(variant_order)
        measure_order = sorted(measure_df["measure_name"].astype(str).unique().tolist())
        heatmap_matrices: list[tuple[str, pd.DataFrame]] = []
        for metric in heatmap_metrics:
            matrix = (
                measure_df.pivot_table(index="measure_name", columns="variant_f02", values=metric, aggfunc="mean")
                .reindex(index=measure_order, columns=variant_order)
            )
            if metric in {
                "n_events_generated",
                "n_unique_event_types_observed",
                "rare_event_ratio",
                "occupancy_entropy",
            }:
                heatmap_matrices.append((metric.replace("_", " ").title(), matrix))
            figures[f"heatmap_{metric}"] = save_heatmap(
                matrix,
                title=f"{metric} by measure and variant",
                output_path=fig_dir / f"heatmap_{metric}.png",
                fmt=".2f",
                cmap="YlGnBu",
                x_ticklabels=variant_ticklabels,
                x_axis_label="Variant ID + bands",
                split_after_col=split_after_col,
            )
        figures["heatmap_measure_bundle"] = save_heatmap_grid(
            heatmap_matrices,
            output_path=fig_dir / "heatmap_measure_bundle.png",
            fmt=".2f",
            cmap="YlGnBu",
            x_ticklabels=variant_ticklabels,
            x_axis_label="Variant ID + bands",
            split_after_col=split_after_col,
        )

    global_scatter_specs = [
        ("rare_event_ratio", "normalized_event_entropy", "Rare event ratio vs normalized entropy", "scatter_rare_vs_entropy.png", "scatter_rare_vs_entropy"),
        ("n_bands", "total_events_generated", "Number of bands vs total events", "scatter_nbands_vs_total_events.png", "scatter_nbands_vs_total_events"),
        ("catalog_coverage_ratio", "total_events_generated", "Catalog coverage vs total events", "scatter_catalog_vs_total_events.png", "scatter_catalog_vs_total_events"),
        ("top1_event_ratio", "normalized_event_entropy", "Top1 event ratio vs normalized entropy", "scatter_top1_vs_entropy.png", "scatter_top1_vs_entropy"),
        ("jump_size_mean", "pct_jump_ge_2", "Jump size mean vs pct_jump_ge_2", "scatter_jump_vs_pct2.png", "scatter_jump_vs_pct2"),
    ]
    for x_col, y_col, title, filename, key in global_scatter_specs:
        figures[key] = save_scatter_plot(global_df, x_col, y_col, title, fig_dir / filename, annotate=True)

    measure_scatter_specs = [
        ("extreme_band_ratio", "n_events_generated", "Extreme band ratio vs measure events", "scatter_extreme_vs_events.png", "scatter_extreme_vs_events"),
        ("max_band_ratio", "n_events_generated", "Max band ratio vs measure events", "scatter_max_vs_events.png", "scatter_max_vs_events"),
        ("n_active_bands", "n_events_generated", "Active bands vs measure events", "scatter_active_bands_vs_events.png", "scatter_active_bands_vs_events"),
        ("occupancy_entropy", "n_events_generated", "Occupancy entropy vs measure events", "scatter_entropy_vs_events.png", "scatter_entropy_vs_events"),
        ("rare_event_ratio", "top1_ratio", "Rare event ratio vs top1 ratio", "scatter_rare_vs_top1_measure.png", "scatter_rare_vs_top1_measure"),
    ]
    for x_col, y_col, title, filename, key in measure_scatter_specs:
        figures[key] = save_scatter_plot(measure_df, x_col, y_col, title, fig_dir / filename, annotate=False)

    hist_specs = [
        ("n_events_generated", "Distribution of events generated per measure row", "hist_n_events_generated.png", "hist_n_events_generated"),
        ("max_band_ratio", "Distribution of max band ratio", "hist_max_band_ratio.png", "hist_max_band_ratio"),
        ("extreme_band_ratio", "Distribution of extreme band ratio", "hist_extreme_band_ratio.png", "hist_extreme_band_ratio"),
        ("occupancy_entropy", "Distribution of occupancy entropy", "hist_occupancy_entropy.png", "hist_occupancy_entropy"),
    ]
    for column, title, filename, key in hist_specs:
        figures[key] = save_histogram(measure_df, column, title, fig_dir / filename)

    rankings = build_rankings(global_df, measure_df, out_dir)
    html_report = build_html(project_root, global_df, measure_df, variant_summary, measure_summary, corr_df, figures, rankings)
    report_path = out_dir / "report_f02.html"
    report_path.write_text(html_report, encoding="utf-8")

    print(f"f02_correlations.csv -> {out_dir / 'f02_correlations.csv'}")
    print(f"report_f02.html -> {report_path}")


if __name__ == "__main__":
    main()
