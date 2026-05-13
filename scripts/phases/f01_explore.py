#!/usr/bin/env python3

import argparse
import sys
import shutil
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import yaml
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import matplotlib.pyplot as plt

from scripts.core.artifacts import sha256_of_file, save_outputs_yaml, load_params, get_variant_dir
from scripts.core.traceability import validate_outputs

# ============================================================
# CONSTANTES
# ============================================================

PHASE = "f01_explore"
PROJECT_ROOT = REPO_ROOT
EXECUTIONS_DIR = PROJECT_ROOT / "executions" / PHASE




# ============================================================
# LÓGICA DE NEGOCIO
# ============================================================

def prepare_time_axis(df: pd.DataFrame):

    time_col = None

    if "Timestamp" in df.columns:
        time_col = "Timestamp"
    else:
        candidates = [
            c for c in df.columns
            if any(k in c.lower() for k in ["time", "timestamp", "fecha", "date"])
        ]
        if candidates:
            time_col = candidates[0]

    if time_col:
        ts = pd.to_datetime(df[time_col])
        df["segs"] = (ts - pd.Timestamp("1970-01-01")) // pd.Timedelta("1s")
        df = df.set_index("segs").sort_index()
    elif "segs" in df.columns:
        df = df.set_index("segs").sort_index()
    else:
        raise RuntimeError(
            "No existe columna temporal ('Timestamp' o 'segs')."
        )

    df["segs_diff"] = df.index.to_series().diff()
    Tu_value = int(df["segs_diff"].median())

    return df, Tu_value


def apply_cleaning(df: pd.DataFrame, params: dict):

    strategy = params.get("cleaning")
    nan_values = params.get("nan_values", [])
    error_values = params.get("error_values", {})

    df_clean = df.copy()

    # NaNs originales (antes de limpiar)
    n_nan_detected_before = int(df_clean.isna().sum().sum())
    n_nan_replaced = 0

    if strategy != "none":

        # ----------------------------
        # 1) Sentinelas "nan_values"
        # ----------------------------
        if nan_values:
            for sentinel in nan_values:
                # Si el sentinel es None y ya cuenta como NaN, no cambiará el conteo,
                # pero tampoco rompe nada.
                mask = df_clean.eq(sentinel)
                replaced_here = int(mask.sum().sum())
                if replaced_here > 0:
                    df_clean = df_clean.mask(mask, np.nan)
                    n_nan_replaced += replaced_here

        # ----------------------------
        # 2) Valores "error_values"
        # ----------------------------
        if strategy in ["basic", "strict"]:
            for col, vals in error_values.items():
                if col in df_clean.columns and vals:
                    # Para cada valor erróneo, contamos y reemplazamos
                    col_series = df_clean[col]
                    for v in vals:
                        mask = col_series.eq(v)
                        replaced_here = int(mask.sum())
                        if replaced_here > 0:
                            col_series = col_series.mask(mask, np.nan)
                            n_nan_replaced += replaced_here
                    df_clean[col] = col_series

        # ----------------------------
        # 3) Estrategia strict → drop rows con cualquier NaN
        # ----------------------------
        if strategy == "strict":
            df_clean.dropna(axis=0, how="any", inplace=True)

    # NaNs después de limpiar (antes de dropna ya se ha contado)
    n_nan_detected_after = int(df_clean.isna().sum().sum())
    n_rows = int(len(df_clean))
    n_cols = int(df_clean.shape[1])

    nan_ratio = float(n_nan_detected_after / (n_rows * n_cols)) if n_rows > 0 else 0.0

    return (
        df_clean,
        n_nan_detected_before,
        n_nan_replaced,
        n_nan_detected_after,
        nan_ratio,
    )


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

    print(f"\n===== INICIO {PHASE} / {variant} =====")

    start_time = time.perf_counter()

    raw_path = PROJECT_ROOT / params["raw_path"]

    if not raw_path.exists():
        raise RuntimeError(f"No existe dataset RAW: {raw_path}")

    # --------------------------------------------------------
    # Lectura dataset
    # --------------------------------------------------------

    if raw_path.suffix.lower() == ".csv":
        df = pd.read_csv(raw_path)
    else:
        df = pq.read_table(raw_path, memory_map=True).to_pandas()

    # Subsetting opcional
    first_line = params.get("first_line")
    max_lines = params.get("max_lines")

    if first_line is not None or max_lines is not None:
        start_idx = max(int(first_line or 0), 0)
        end_idx = start_idx + int(max_lines) if max_lines else None
        df = df.iloc[start_idx:end_idx].reset_index(drop=True)

    # --------------------------------------------------------
    # Preparar eje temporal
    # --------------------------------------------------------

    df, Tu_value = prepare_time_axis(df)

    (
        df_clean,
        n_nan_before,
        n_nan_replaced,
        n_nan_after,
        nan_ratio,
    ) = apply_cleaning(df, params)

    # --------------------------------------------------------
    # Eje temporal y columnas de medida
    # --------------------------------------------------------

    # Aseguramos que 'segs' exista como columna (no solo índice)
    if df_clean.index.name == "segs" and "segs" not in df_clean.columns:
        df_clean = df_clean.reset_index()

    # Columnas numéricas
    numeric_cols = df_clean.select_dtypes(include=[np.number]).columns.tolist()

    # Columnas de medida "físicas": excluimos segs y columnas auxiliares *_diff
    measure_cols = [
        c for c in numeric_cols
        if c != "segs" and not c.endswith("_diff")
    ]

    # --------------------------------------------------------
    # Guardar dataset limpio
    # --------------------------------------------------------

    dataset_path = variant_dir / "01_explore_dataset.parquet"
    df_clean.to_parquet(dataset_path)

    # --------------------------------------------------------
    # Generar report simple
    # --------------------------------------------------------

    report_path = variant_dir / "01_explore_report.html"

    # Usamos solo columnas de medida para el preview
    plot_cols = measure_cols[:5]

    if plot_cols:
        plt.figure(figsize=(10, 4))
        df_clean[plot_cols].plot()
        plt.tight_layout()
        fig_path = variant_dir / "preview.png"
        plt.savefig(fig_path)
        plt.close()
    else:
        fig_path = None  # por si quieres usarlo luego


    plt.tight_layout()
    fig_path = variant_dir / "preview.png"
    plt.savefig(fig_path)
    plt.close()

    report_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>F01 Explore Report — {variant}</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 40px;
            }}
            h1 {{ color: #333; }}
            table {{
                border-collapse: collapse;
                margin-top: 20px;
            }}
            th, td {{
                border: 1px solid #ccc;
                padding: 6px 10px;
                text-align: right;
            }}
            th {{
                background-color: #f0f0f0;
            }}
            .section {{
                margin-top: 30px;
            }}
        </style>
    </head>
    <body>

    <h1>F01 Explore Report — {variant}</h1>

    <div class="section">
    <h2>Dataset Summary</h2>
    <table>
    <tr><th>Rows</th><td>{len(df_clean)}</td></tr>
    <tr><th>Columns</th><td>{df_clean.shape[1]}</td></tr>
    <tr><th>Tu (seconds)</th><td>{Tu_value}</td></tr>
    </table>
    </div>

    <div class="section">
    <h2>NaN Analysis</h2>
    <table>
    <tr><th>NaN detected before cleaning</th><td>{n_nan_before}</td></tr>
    <tr><th>NaN replaced (sentinels)</th><td>{n_nan_replaced}</td></tr>
    <tr><th>NaN detected after cleaning</th><td>{n_nan_after}</td></tr>
    <tr><th>NaN ratio (after)</th><td>{nan_ratio:.6f}</td></tr>
    </table>
    </div>

    <div class="section">
    <h2>Cleaning Parameters</h2>
    <table>
    <tr><th>Strategy</th><td>{params.get("cleaning")}</td></tr>
    <tr><th>nan_values</th><td>{params.get("nan_values")}</td></tr>
    <tr><th>error_values</th><td>{params.get("error_values")}</td></tr>
    </table>
    </div>

    <div class="section">
    <h2>Preview</h2>
    <img src="preview.png" width="800"/>
    </div>

    </body>
    </html>
    """

    report_path.write_text(report_html)

    # --------------------------------------------------------
    # Construir outputs.yaml
    # --------------------------------------------------------

    execution_time = float(time.perf_counter() - start_time)

    outputs_content = {
        "phase": PHASE,
        "variant": variant,
        "artifacts": {
            "dataset": {
                "path": dataset_path.name,
                "sha256": sha256_of_file(dataset_path),
            },
            "report": {
                "path": report_path.name,
                "sha256": sha256_of_file(report_path),
            },
        },
        "exports": {
            "Tu": int(Tu_value),
            "n_rows": int(len(df_clean)),
            "n_columns": int(df_clean.shape[1]),
            "measure_cols": list(measure_cols),
        },
        "metrics": {
            "execution_time": execution_time,
            "n_nan_detected": int(n_nan_after),
            "n_nan_replaced": int(n_nan_replaced),
            "nan_ratio": float(nan_ratio),
        },
        "provenance": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    
    save_outputs_yaml(variant_dir, outputs_content)
    validate_outputs(PHASE, outputs_content)
    print(f"\n===== FASE {PHASE} COMPLETADA =====")


if __name__ == "__main__":
    main()