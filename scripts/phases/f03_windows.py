#!/usr/bin/env python3

import argparse
import time
from datetime import datetime, timezone
from pathlib import Path
from bisect import bisect_left

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import hashlib

from scripts.core.artifacts import (
    sha256_of_file,
    save_outputs_yaml,
    load_params,
    get_variant_dir,
)
from scripts.core.phase_io import load_phase_outputs, resolve_artifact_path
from scripts.core.traceability import validate_outputs


# ============================================================
PHASE = "f03_windows"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
# ============================================================


# ============================================================
# HELPERS
# ============================================================

def has_nan_in_range(nan_prefix, i0, i1):
    if i0 >= i1:
        return False
    return nan_prefix[i1 - 1] - (nan_prefix[i0 - 1] if i0 else 0) > 0


def flush_rows(writer, rows, schema):
    if rows:
        writer.write_table(pa.Table.from_pylist(rows, schema))
        rows.clear()


def stable_array_hash(arr):
    if len(arr) == 0:
        return "EMPTY"
    a = np.asarray(arr, dtype=np.float64)
    return hashlib.md5(a.tobytes()).hexdigest()


def register_window(rows, ow, pw, ow_lengths, pw_lengths, ow_hashes, pw_hashes):
    rows.append({"OW_values": ow, "PW_values": pw})
    ow_lengths.append(len(ow))
    pw_lengths.append(len(pw))
    ow_hashes.add(stable_array_hash(ow))
    pw_hashes.add(stable_array_hash(pw))

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
    # Resolver parent F02
    # --------------------------------------------------------

    parent_phase = "f02_events"

    parent_outputs, parent_dir = load_phase_outputs(
        PROJECT_ROOT,
        parent_phase,
        parent_variant,
        "F03",
    )
    parent_exports = parent_outputs.get("exports", {})

    if (
        parent_exports.get("measure_compatible") is False
        or parent_exports.get("compatible") is False
    ):
        reason = (
            parent_exports.get("incompatibility_reason")
            or "Parent F02 measure is incompatible"
        )
        Tu = params["Tu"]
        OW = params["OW"]
        LT = params["LT"]
        PW = params["PW"]
        window_strategy = params["window_strategy"]
        nan_mode = params["nan_mode"]
        elapsed = time.perf_counter() - start_time

        report_path = variant_dir / "03_windows_report.html"
        report_path.write_text(
            f"""
            <html>
            <body>
            <h1>F03 Windows — {variant}</h1>
            <p>Parent F02: {parent_variant}</p>
            <p>compatible = False</p>
            <p>reason = Parent F02 measure is incompatible: {reason}</p>
            <p>OW={OW}, LT={LT}, PW={PW}, Tu={Tu}</p>
            </body>
            </html>
            """,
            encoding="utf-8",
        )

        outputs_content = {
            "phase": PHASE,
            "variant": variant,
            "artifacts": {
                "report": {
                    "path": report_path.name,
                    "sha256": sha256_of_file(report_path),
                },
            },
            "exports": {
                "Tu": Tu,
                "OW": OW,
                "LT": LT,
                "PW": PW,
                "Ratio_PW_OW": PW / OW if OW > 0 else None,
                "window_strategy": window_strategy,
                "nan_mode": nan_mode,
                "parent_f02": parent_variant,
                "n_windows": 0,
                "compatible": False,
                "measure_compatible": False,
                "incompatibility_reason": (
                    f"Parent F02 measure is incompatible: {reason}"
                ),
            },
            "metrics": {
                "execution_time": float(elapsed),
                "n_rows_in": 0,
                "n_windows_out": 0,
                "compatible": False,
                "incompatibility_reason": (
                    f"Parent F02 measure is incompatible: {reason}"
                ),
            },
            "provenance": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        }

        save_outputs_yaml(variant_dir, outputs_content)
        validate_outputs(PHASE, outputs_content)
        print(f"[WARN] F03 no genera ventanas: {reason}")
        print(f"\n===== FASE {PHASE} COMPLETADA SIN DATASET =====")
        return

    parent_series_path = resolve_artifact_path(
        parent_dir,
        parent_outputs,
        ["series"],
        "F03",
    )


    df = pq.read_table(parent_series_path, memory_map=True).to_pandas()

    # --------------------------------------------------------
    # Parámetros
    # --------------------------------------------------------

    Tu = params["Tu"]
    OW = params["OW"]
    LT = params["LT"]
    PW = params["PW"]
    window_strategy = params["window_strategy"]
    nan_mode = params["nan_mode"]
    BATCH = 10_000

    # --------------------------------------------------------
    # Validaciones básicas
    # --------------------------------------------------------

    if "segs" not in df.columns:
        raise RuntimeError("El dataset padre no contiene columna 'segs'")

    if "value" not in df.columns:
        raise RuntimeError("El dataset padre no contiene columna 'value'")

    df = df.sort_values("segs", kind="mergesort").reset_index(drop=True)
    if df.empty:
        raise RuntimeError("El dataset padre de series está vacío")

    # --------------------------------------------------------
    # Preparar arrays
    # --------------------------------------------------------

    times = df["segs"].to_numpy(dtype=np.int64)
    values = df["value"].to_numpy(dtype=np.float64)
    has_nan = np.isnan(values)

    if nan_mode == "discard":
        nan_prefix = np.cumsum(has_nan, dtype=np.int64)
    else:
        nan_prefix = None

    # --------------------------------------------------------
    # Geometría temporal
    # --------------------------------------------------------

    OW_span = OW * Tu
    PW_start = (OW + LT) * Tu
    PW_span = PW * Tu
    total_span = PW_start + PW_span

    # --------------------------------------------------------
    # Output parquet
    # --------------------------------------------------------

    output_path = variant_dir / "03_windows.parquet"

    schema = pa.schema([
        ("OW_values", pa.list_(pa.float64())),
        ("PW_values", pa.list_(pa.float64())),
    ])

    writer = pq.ParquetWriter(output_path, schema, compression="snappy")

    rows = []
    windows_total = 0
    windows_written = 0


    ow_lengths = []
    pw_lengths = []

    ow_hashes = set()
    pw_hashes = set()

    # =================================================================
    # FAST PATH: SYNCHRO
    # =================================================================
    if window_strategy == "synchro":
        n = len(times)
        t0 = times[0]

        i_ow_0 = bisect_left(times, t0)
        i_ow_1 = bisect_left(times, t0 + OW_span)
        i_pw_0 = bisect_left(times, t0 + PW_start)
        i_pw_1 = bisect_left(times, t0 + PW_start + PW_span)

        while t0 + total_span <= times[-1]:
            windows_total += 1

            if i_ow_0 != i_ow_1 or i_pw_0 != i_pw_1:
                if nan_mode == "discard":
                    if (
                        has_nan_in_range(nan_prefix, i_ow_0, i_ow_1)
                        or has_nan_in_range(nan_prefix, i_pw_0, i_pw_1)
                    ):
                        pass
                    else:
                        ow = values[i_ow_0:i_ow_1]
                        pw = values[i_pw_0:i_pw_1]
                        if len(ow) or len(pw):
                            register_window(rows, ow, pw, ow_lengths, pw_lengths, ow_hashes, pw_hashes)
                            windows_written += 1
                else:
                    ow = values[i_ow_0:i_ow_1]
                    pw = values[i_pw_0:i_pw_1]
                    if len(ow) or len(pw):
                        register_window(rows, ow, pw, ow_lengths, pw_lengths, ow_hashes, pw_hashes)
                        windows_written += 1


            if len(rows) >= BATCH:
                flush_rows(writer, rows, schema)

            t0 += Tu
            ow_start = t0
            ow_end = t0 + OW_span
            pw_start = t0 + PW_start
            pw_end = pw_start + PW_span

            while i_ow_0 < n and times[i_ow_0] < ow_start:
                i_ow_0 += 1
            while i_ow_1 < n and times[i_ow_1] < ow_end:
                i_ow_1 += 1
            while i_pw_0 < n and times[i_pw_0] < pw_start:
                i_pw_0 += 1
            while i_pw_1 < n and times[i_pw_1] < pw_end:
                i_pw_1 += 1

    # =================================================================
    # ASYNOW
    # =================================================================
    elif window_strategy == "asynOW":
        active_mask = ~has_nan if nan_mode == "discard" else np.ones(len(times), dtype=bool)
        active_bins = np.unique(((times[active_mask] - times[0]) // Tu).astype(np.int64))

        for b in active_bins:
            t0 = times[0] + b * Tu
            if t0 + total_span > times[-1]:
                continue

            windows_total += 1

            i_ow_0 = bisect_left(times, t0)
            i_ow_1 = bisect_left(times, t0 + OW_span)
            if i_ow_0 == i_ow_1:
                continue

            i_pw_0 = bisect_left(times, t0 + PW_start)
            i_pw_1 = bisect_left(times, t0 + PW_start + PW_span)

            if nan_mode == "discard":
                if (
                    has_nan_in_range(nan_prefix, i_ow_0, i_ow_1)
                    or has_nan_in_range(nan_prefix, i_pw_0, i_pw_1)
                ):
                    continue

            ow = values[i_ow_0:i_ow_1]
            pw = values[i_pw_0:i_pw_1]
            if len(ow) or len(pw):
                register_window(rows, ow, pw, ow_lengths, pw_lengths, ow_hashes, pw_hashes)
                windows_written += 1

            if len(rows) >= BATCH:
                flush_rows(writer, rows, schema)

    else:
        raise ValueError(f"Estrategia desconocida: {window_strategy}")

    flush_rows(writer, rows, schema)
    writer.close()

    elapsed = time.perf_counter() - start_time

    # --------------------------------------------------------
    # Report
    # --------------------------------------------------------

    report_path = variant_dir / "03_windows_report.html"
    report_path.write_text(
        f"""
        <html>
        <body>
        <h1>F03 Windows — {variant}</h1>
        <p>Parent: {parent_variant}</p>
        <p>Strategy: {window_strategy}</p>
        <p>OW={OW}, LT={LT}, PW={PW}, Tu={Tu}</p>
        <p>Windows total: {windows_total}</p>
        <p>Windows written: {windows_written}</p>
        </body>
        </html>
        """
    )

    # --------------------------------------------------------
    # outputs.yaml
    # --------------------------------------------------------

    n_unique_ow_hash = len(ow_hashes)
    n_unique_pw_hash = len(pw_hashes)

    dup_ratio_ow = (
        1.0 - (n_unique_ow_hash / windows_written)
        if windows_written > 0 else 0.0
    )
    dup_ratio_pw = (
        1.0 - (n_unique_pw_hash / windows_written)
        if windows_written > 0 else 0.0
    )

    seq_len_mean_ow = float(np.mean(ow_lengths)) if ow_lengths else 0.0
    seq_len_mean_pw = float(np.mean(pw_lengths)) if pw_lengths else 0.0
    seq_len_std_ow = float(np.std(ow_lengths)) if ow_lengths else 0.0
    seq_len_std_pw = float(np.std(pw_lengths)) if pw_lengths else 0.0

    outputs_content = {
        "phase": PHASE,
        "variant": variant,
        "artifacts": {
            "dataset": {
                "path": output_path.name,
                "sha256": sha256_of_file(output_path),
            },
            "report": {
                "path": report_path.name,
                "sha256": sha256_of_file(report_path),
            },
        },
        "exports": {
            "Tu": Tu,
            "OW": OW,
            "LT": LT,
            "PW": PW,
            "Ratio_PW_OW": PW / OW if OW > 0 else None,
            "window_strategy": window_strategy,
            "nan_mode": nan_mode,
            "parent_f02": parent_variant,
            "n_windows": windows_written,
            "n_unique_ow_hash": n_unique_ow_hash,
            "n_unique_pw_hash": n_unique_pw_hash,
            "dup_ratio_ow": float(dup_ratio_ow),
            "dup_ratio_pw": float(dup_ratio_pw),
            "seq_len_mean_ow": seq_len_mean_ow,
            "seq_len_mean_pw": seq_len_mean_pw,
            "seq_len_std_ow": seq_len_std_ow,
            "seq_len_std_pw": seq_len_std_pw,
        },
        "metrics": {
            "execution_time": float(elapsed),
            "n_rows_in": int(len(df)),
            "n_windows_out": int(windows_written),
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
