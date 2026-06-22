#!/usr/bin/env python3

import argparse
import html
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.core.artifacts import (
    sha256_of_file,
    save_outputs_yaml,
    load_params,
    get_variant_dir,
    save_json,
)
from scripts.core.phase_io import load_phase_outputs, resolve_artifact_path
from scripts.core.traceability import validate_outputs


# ============================================================
# CONSTANTES
# ============================================================

PHASE = "f02_events"  # Mantener el nombre para no romper Makefile/rutas existentes.
PROJECT_ROOT = REPO_ROOT


# ============================================================
# HELPERS
# ============================================================

def html_escape(value):
    return html.escape("" if value is None else str(value))


def safe_float(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def get_epoch_col(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """
    F01 puede dejar 'segs' como columna o como índice.
    Esta función garantiza que F02 siempre trabaja con columna 'segs'.
    """
    if "segs" in df.columns:
        return df, "segs"

    if df.index.name == "segs":
        return df.reset_index(), "segs"

    raise RuntimeError(
        "No se encontró 'segs' ni como columna ni como índice en el dataset padre."
    )


def get_measure_name(params: dict) -> str:
    """
    Permite varios nombres por comodidad, pero lo recomendado es usar measure_name.
    """
    for key in ("measure_name", "measure_col", "signal_col"):
        value = params.get(key)
        if value:
            return str(value)

    raise RuntimeError(
        "No se encontró la medida en params. Usa, por ejemplo: parameters.measure_name: Battery_Active_Power"
    )


def compute_series_stats(df_series: pd.DataFrame, epoch_col: str, value_col: str, Tu: int | None):
    values = df_series[value_col]
    non_nan = values.dropna()

    n_rows = int(len(df_series))
    n_nan = int(values.isna().sum())
    n_non_nan = int(values.notna().sum())

    if n_non_nan > 0:
        desc = {
            "min": safe_float(non_nan.min()),
            "max": safe_float(non_nan.max()),
            "mean": safe_float(non_nan.mean()),
            "median": safe_float(non_nan.median()),
            "std": safe_float(non_nan.std(ddof=0)),
            "var": safe_float(non_nan.var(ddof=0)),
            "q01": safe_float(non_nan.quantile(0.01)),
            "q05": safe_float(non_nan.quantile(0.05)),
            "q10": safe_float(non_nan.quantile(0.10)),
            "q25": safe_float(non_nan.quantile(0.25)),
            "q75": safe_float(non_nan.quantile(0.75)),
            "q90": safe_float(non_nan.quantile(0.90)),
            "q95": safe_float(non_nan.quantile(0.95)),
            "q99": safe_float(non_nan.quantile(0.99)),
            "n_unique_values": safe_int(non_nan.nunique()),
            "zero_ratio": safe_float((non_nan == 0).mean()),
        }
    else:
        desc = {
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "std": None,
            "var": None,
            "q01": None,
            "q05": None,
            "q10": None,
            "q25": None,
            "q75": None,
            "q90": None,
            "q95": None,
            "q99": None,
            "n_unique_values": 0,
            "zero_ratio": None,
            "positive_ratio": None,
            "negative_ratio": None,
        }

    epochs = df_series[epoch_col].to_numpy(dtype=np.int64)

    if len(epochs) > 1:
        diffs = np.diff(epochs)
        n_steps = int(len(diffs))
        if Tu is not None:
            n_consecutive_steps = int((diffs == Tu).sum())
        else:
            n_consecutive_steps = 0

        time_start = safe_int(epochs[0])
        time_end = safe_int(epochs[-1])
        time_span = safe_int(epochs[-1] - epochs[0])
        consecutive_ratio = float(n_consecutive_steps / n_steps) if n_steps > 0 else 0.0
        broken_steps = int(n_steps - n_consecutive_steps)
        broken_ratio = float(broken_steps / n_steps) if n_steps > 0 else 0.0
    else:
        n_steps = 0
        n_consecutive_steps = 0
        broken_steps = 0
        consecutive_ratio = 0.0
        broken_ratio = 0.0
        time_start = safe_int(epochs[0]) if len(epochs) == 1 else None
        time_end = safe_int(epochs[0]) if len(epochs) == 1 else None
        time_span = 0 if len(epochs) == 1 else None

    stats = {
        "n_rows": n_rows,
        "n_non_nan": n_non_nan,
        "n_nan": n_nan,
        "nan_ratio": float(n_nan / n_rows) if n_rows > 0 else 0.0,
        "non_nan_ratio": float(n_non_nan / n_rows) if n_rows > 0 else 0.0,
        "time_start": time_start,
        "time_end": time_end,
        "time_span": time_span,
        "n_steps": n_steps,
        "Tu": safe_int(Tu),
        "n_consecutive_steps": n_consecutive_steps,
        "n_broken_steps": broken_steps,
        "consecutive_ratio": consecutive_ratio,
        "broken_ratio": broken_ratio,
        **desc,
    }

    return stats


def build_report_html(
    variant: str,
    parent_variant: str,
    measure_name: str,
    epoch_col: str,
    value_col: str,
    stats: dict,
):
    rows = []
    for key, value in stats.items():
        rows.append(
            "<tr>"
            f"<td><code>{html_escape(key)}</code></td>"
            f"<td>{html_escape(value)}</td>"
            "</tr>"
        )

    metrics_table = (
        '<table class="tbl">'
        "<thead><tr><th>Métrica</th><th>Valor</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )

    return f"""
    <!doctype html>
    <html lang="es">
    <head>
      <meta charset="utf-8">
      <title>F02 Series - {html_escape(variant)}</title>
      <style>
        body {{
          margin: 0;
          background: #f6f8fb;
          color: #172033;
          font-family: Arial, sans-serif;
          line-height: 1.45;
        }}
        main {{
          max-width: 1100px;
          margin: 0 auto;
          padding: 28px;
        }}
        .hero {{
          background: #ffffff;
          border: 1px solid #d9e0ea;
          border-radius: 10px;
          padding: 22px;
          box-shadow: 0 10px 24px rgba(23, 32, 51, 0.06);
        }}
        h1 {{
          margin: 0 0 10px;
          font-size: 28px;
        }}
        .meta {{
          color: #667085;
          font-size: 14px;
        }}
        code {{
          background: #eef3f8;
          padding: 2px 5px;
          border-radius: 4px;
        }}
        .kpi-grid {{
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: 12px;
          margin-top: 18px;
        }}
        .card {{
          border: 1px solid #d9e0ea;
          border-radius: 8px;
          padding: 14px;
          background: #ffffff;
        }}
        .card .k {{
          color: #667085;
          font-size: 12px;
          text-transform: uppercase;
          font-weight: 700;
        }}
        .card .v {{
          margin-top: 8px;
          font-size: 22px;
          font-weight: 800;
        }}
        .panel {{
          margin-top: 22px;
          background: #ffffff;
          border: 1px solid #d9e0ea;
          border-radius: 10px;
          padding: 18px;
        }}
        .tbl {{
          border-collapse: collapse;
          width: 100%;
          font-size: 13px;
        }}
        .tbl th, .tbl td {{
          border: 1px solid #d9e0ea;
          padding: 8px 10px;
          text-align: left;
        }}
        .tbl th {{
          background: #eef3f8;
        }}
      </style>
    </head>
    <body>
      <main>
        <section class="hero">
          <h1>F02 Series - {html_escape(variant)}</h1>
          <p class="meta">
            Parent: <code>{html_escape(parent_variant)}</code> |
            Measure: <code>{html_escape(measure_name)}</code> |
            Epoch column: <code>{html_escape(epoch_col)}</code> |
            Value column: <code>{html_escape(value_col)}</code>
          </p>

          <div class="kpi-grid">
            <div class="card"><div class="k">Rows</div><div class="v">{html_escape(stats.get("n_rows"))}</div></div>
            <div class="card"><div class="k">NaN ratio</div><div class="v">{100 * float(stats.get("nan_ratio", 0.0)):.2f}%</div></div>
            <div class="card"><div class="k">Min</div><div class="v">{html_escape(stats.get("min"))}</div></div>
            <div class="card"><div class="k">Max</div><div class="v">{html_escape(stats.get("max"))}</div></div>
            <div class="card"><div class="k">Mean</div><div class="v">{html_escape(stats.get("mean"))}</div></div>
            <div class="card"><div class="k">Median</div><div class="v">{html_escape(stats.get("median"))}</div></div>
          </div>
        </section>

        <section class="panel">
          <h2>Métricas completas</h2>
          {metrics_table}
        </section>
      </main>
    </body>
    </html>
    """


def build_outputs_metrics(stats: dict, execution_time: float):
    return {
        "execution_time": float(execution_time),
        "n_rows": int(stats["n_rows"]),
        "n_non_nan": int(stats["n_non_nan"]),
        "n_nan": int(stats["n_nan"]),
        "nan_ratio": float(stats["nan_ratio"]),
        "non_nan_ratio": float(stats["non_nan_ratio"]),
        "min": stats["min"],
        "max": stats["max"],
        "mean": stats["mean"],
        "median": stats["median"],
        "std": stats["std"],
        "q05": stats["q05"],
        "q95": stats["q95"],
        "positive_ratio": stats["positive_ratio"],
        "negative_ratio": stats["negative_ratio"],
        "zero_ratio": stats["zero_ratio"],
        "consecutive_ratio": float(stats["consecutive_ratio"]),
        "broken_ratio": float(stats["broken_ratio"]),
    }


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

    Tu = params.get("Tu")
    measure_name = get_measure_name(params)

    # --------------------------------------------------------
    # Resolver columna temporal
    # --------------------------------------------------------

    df, epoch_col = get_epoch_col(df)

    # --------------------------------------------------------
    # Validar medida
    # --------------------------------------------------------

    if measure_name not in df.columns:
        available_cols = list(df.columns)
        raise RuntimeError(
            f"La medida '{measure_name}' no existe en el dataset padre. "
            f"Columnas disponibles: {available_cols}"
        )

    # --------------------------------------------------------
    # Construir dataset univariable
    # --------------------------------------------------------

    value_col = "value"

    df_series = df[[epoch_col, measure_name]].copy()
    df_series = df_series.rename(columns={measure_name: value_col})

    # Orden defensivo por tiempo
    df_series = df_series.sort_values(epoch_col).reset_index(drop=True)

    # --------------------------------------------------------
    # Métricas
    # --------------------------------------------------------

    stats = compute_series_stats(
        df_series=df_series,
        epoch_col=epoch_col,
        value_col=value_col,
        Tu=Tu,
    )

    stats["measure_name"] = measure_name
    stats["epoch_col"] = epoch_col
    stats["value_col"] = value_col
    stats["parent_variant"] = parent_variant

    # --------------------------------------------------------
    # Guardar artefactos
    # --------------------------------------------------------

    series_path = variant_dir / "02_series.parquet"
    stats_path = variant_dir / "02_series_stats.json"
    report_path = variant_dir / "02_series_report.html"

    df_series.to_parquet(series_path, index=False)
    save_json(stats_path, stats)

    report_html = build_report_html(
        variant=variant,
        parent_variant=parent_variant,
        measure_name=measure_name,
        epoch_col=epoch_col,
        value_col=value_col,
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
            "series": {
                "path": series_path.name,
                "sha256": sha256_of_file(series_path),
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
            "Tu": int(Tu) if Tu is not None else None,
            "measure_name": measure_name,
            "epoch_col": epoch_col,
            "value_col": value_col,
            "n_rows": int(stats["n_rows"]),
            "n_non_nan": int(stats["n_non_nan"]),
            "nan_ratio": float(stats["nan_ratio"]),
        },
        "metrics": build_outputs_metrics(
            stats=stats,
            execution_time=execution_time,
        ),
        "provenance": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }

    save_outputs_yaml(variant_dir, outputs_content)

    validate_outputs(PHASE, outputs_content)

    print(f"\n===== FASE {PHASE} COMPLETADA =====")
    print(f"Medida seleccionada: {measure_name}")
    print(f"Dataset univariable: {series_path}")


if __name__ == "__main__":
    main()
