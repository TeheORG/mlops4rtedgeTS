# scripts/runtime_analysis/parse.py
# -*- coding: utf-8 -*-

"""
Runtime trace parsing and enrichment engine.

Provides:
    - parse_raw_log()
    - enrich()
    - reconstruct_sys()
    - reconstruct_models()
    - reconstruct_memory()
    - summarize_by_tu()
    - parse_and_reconstruct()
    - parse_log_enriched()

Pure analytical module for F07 and F08.
No CLI. No prints. No file writing.
"""

from pathlib import Path
import pandas as pd


# ============================================================
# EVENT ENUMERATION
# ============================================================

EV_NAMES = {
    1:  "FUNC_PRED_RESULT",
    2:  "FUNC_OFFLOAD_RESULT",
    3:  "FUNC_URGENT_RESULT",

    4:  "INST_SYS_P0_TU_WAKE",
    5:  "INST_SYS_P0_MEM_BEFORE_READ",
    6:  "INST_SYS_P1_READ_EVENTS",
    7:  "INST_SYS_P1_MEM_AFTER_READ",
    8:  "INST_SYS_P1_SCHED_START",
    9:  "INST_SYS_P1_SCHED_DECISION",
    10: "INST_SYS_P1_SCHED_END",
    11: "INST_SYS_P1_QUEUE_SEND",
    12: "INST_SYS_P3_TU_END",

    13: "INST_MOD_P0_CPM_BEGIN",
    14: "INST_MOD_P3_CPM_END",

    15: "INST_MOD_P0_MODEL_BEGIN",
    16: "INST_MOD_P1_TIMER_ARM_BEG",
    17: "INST_MOD_P1_TIMER_ARM_END",
    18: "INST_MOD_P2_INF_START",
    19: "INST_MOD_P2_INF_END",
    20: "INST_P2_MEM_BEFORE_INF",
    21: "INST_P2_MEM_AFTER_INF",
    22: "INST_MOD_PX_WDG_FIRE",
    23: "INST_PX_MEM_AFTER_WDG",
    24: "INST_MOD_P3_MODEL_END",
    25: "INST_P3_MEM_AFTER_POST",

    26: "INST_P0_MEM_HEARTBEAT",
    27: "INST_SYS_P0_MEM_TOTAL_REF",
}

BASE_COLS = ["ts_us", "ev", "model_id", "tu", "a", "b", "c"]

MEM_EVENTS_SYSTEM = {
    "INST_SYS_P0_MEM_BEFORE_READ",
    "INST_SYS_P1_MEM_AFTER_READ",
    "INST_P0_MEM_HEARTBEAT",
}

MEM_EVENTS_MODEL = {
    "INST_P2_MEM_BEFORE_INF",
    "INST_P2_MEM_AFTER_INF",
    "INST_P3_MEM_AFTER_POST",
    "INST_PX_MEM_AFTER_WDG",
}

MEM_EVENTS_ALL = MEM_EVENTS_SYSTEM | MEM_EVENTS_MODEL


# ============================================================
# RAW PARSE
# ============================================================

def _is_valid_trace_line(line: str) -> bool:
    parts = line.strip().split(",")
    if len(parts) < 7:
        return False
    try:
        int(parts[0])
        ev = int(parts[1])
        int(parts[2])
        int(parts[3])
        int(parts[4])
        int(parts[5])
        int(parts[6])
    except ValueError:
        return False
    return ev in EV_NAMES


def parse_raw_log(log_path: Path) -> pd.DataFrame:
    rows = []
    with log_path.open("r", errors="ignore") as f:
        for line in f:
            if not _is_valid_trace_line(line):
                continue
            p = line.strip().split(",")
            rows.append({
                "ts_us": int(p[0]),
                "ev": int(p[1]),
                "model_id": int(p[2]),
                "tu": int(p[3]),
                "a": int(p[4]),
                "b": int(p[5]),
                "c": int(p[6]),
            })
    return pd.DataFrame(rows, columns=BASE_COLS)


# ============================================================
# ENRICHMENT
# ============================================================

def _classify_event(ev_name: str) -> str:
    if ev_name.startswith("FUNC_"):
        return "FUNC"
    if ev_name.startswith("INST_SYS_"):
        return "SYS"
    if ev_name.startswith("INST_MOD_"):
        return "MOD"
    if ev_name.startswith("INST_P"):
        return "MEM"
    return "OTHER"


def _decode_runtime_fields(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["heap_free"] = pd.NA
    df["heap_min"] = pd.NA
    df["heap_total"] = pd.NA
    df["fingerprint"] = pd.NA
    df["predicted"] = pd.NA
    df["plan_start_us"] = pd.NA
    df["plan_deadline_us"] = pd.NA

    mem_mask = df["event_name"].isin(MEM_EVENTS_ALL)
    df.loc[mem_mask, "heap_free"] = df.loc[mem_mask, "a"]
    df.loc[mem_mask, "heap_min"] = df.loc[mem_mask, "b"]

    # Referencia de heap total al arranque (no es MEM operacional, pero útil para ocupación absoluta).
    heap_ref_mask = df["event_name"] == "INST_SYS_P0_MEM_TOTAL_REF"
    df.loc[heap_ref_mask, "heap_total"] = df.loc[heap_ref_mask, "a"]
    df.loc[heap_ref_mask, "heap_free"] = df.loc[heap_ref_mask, "b"]
    df.loc[heap_ref_mask, "heap_min"] = df.loc[heap_ref_mask, "c"]

    pred_mask = df["event_name"] == "FUNC_PRED_RESULT"
    df.loc[pred_mask, "fingerprint"] = df.loc[pred_mask, "a"]
    df.loc[pred_mask, "predicted"] = df.loc[pred_mask, "b"]

    timer_mask = df["event_name"] == "INST_MOD_P1_TIMER_ARM_BEG"
    df.loc[timer_mask, "plan_start_us"] = df.loc[timer_mask, "a"]
    df.loc[timer_mask, "plan_deadline_us"] = df.loc[timer_mask, "b"]

    return df


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if df.empty:
        return df

    df["event_name"] = df["ev"].map(EV_NAMES)
    df["domain"] = df["event_name"].apply(_classify_event)

    df["model_name"] = pd.NA

    df.loc[df["model_id"] == -1, "model_name"] = "__SYSTEM__"
    fallback_mask = df["model_name"].isna() & (df["model_id"] != -1)
    df.loc[fallback_mask, "model_name"] = df.loc[fallback_mask, "model_id"].apply(
        lambda mid: f"model_{int(mid)}"
    )
    df["model_name"] = df["model_name"].fillna("__SYSTEM__")

    df = _decode_runtime_fields(df)
    return df


# ============================================================
# SYS RECONSTRUCTION
# ============================================================

def reconstruct_sys(df: pd.DataFrame) -> pd.DataFrame:
    sys_df = df[df["domain"] == "SYS"]
    rows = []

    for tu, g in sys_df.groupby("tu", sort=True):
        g = g.sort_values("ts_us")

        def ts(ev: str):
            x = g[g["event_name"] == ev]["ts_us"]
            return int(x.iloc[0]) if len(x) else None

        tu_wake = ts("INST_SYS_P0_TU_WAKE")
        tu_end = ts("INST_SYS_P3_TU_END")

        rows.append({
            "tu": tu,
            "tu_wake_ts": tu_wake,
            "tu_end_ts": tu_end,
            "sys_cycle_us": (tu_end - tu_wake) if (tu_wake is not None and tu_end is not None) else None,
        })

    return pd.DataFrame(rows)


# ============================================================
# MODEL RECONSTRUCTION
# ============================================================

def reconstruct_models(df: pd.DataFrame) -> pd.DataFrame:
    mod_df = df[df["domain"].isin(["MOD", "MEM", "FUNC"])]
    rows = []

    for (model_id, tu), g in mod_df.groupby(["model_id", "tu"], sort=True):
        if int(model_id) == -1:
            continue

        g = g.sort_values("ts_us")

        def ts(ev: str):
            x = g[g["event_name"] == ev]["ts_us"]
            return int(x.iloc[0]) if len(x) else None

        inf_start = ts("INST_MOD_P2_INF_START")
        inf_end = ts("INST_MOD_P2_INF_END")
        wdg_fire = ts("INST_MOD_PX_WDG_FIRE")
        model_begin = ts("INST_MOD_P0_MODEL_BEGIN")
        model_end = ts("INST_MOD_P3_MODEL_END")

        if wdg_fire is not None and inf_start is None:
            outcome = "wd_early"
        elif wdg_fire is not None and inf_start is not None and inf_end is None:
            outcome = "wd_late"
        elif inf_start is not None and inf_end is not None:
            outcome = "ok"
        elif inf_start is not None and inf_end is None:
            outcome = "inference_incomplete"
        elif model_begin is not None or model_end is not None:
            outcome = "no_inference"
        else:
            outcome = "no_activity"

        rows.append({
            "model_id": int(model_id),
            "model_name": g["model_name"].iloc[0],
            "tu": int(tu),
            "model_begin_ts": model_begin,
            "inf_start_ts": inf_start,
            "inf_end_ts": inf_end,
            "wdg_fire_ts": wdg_fire,
            "model_end_ts": model_end,
            "outcome": outcome,
        })

    return pd.DataFrame(rows)


# ============================================================
# MEMORY RECONSTRUCTION
# ============================================================

def reconstruct_memory(df: pd.DataFrame) -> pd.DataFrame:
    mem_df = df[df["domain"] == "MEM"]
    rows = []

    for (model_id, tu), g in mem_df.groupby(["model_id", "tu"], sort=True):
        if int(model_id) == -1:
            continue

        g = g.sort_values("ts_us")

        before = g[g["event_name"] == "INST_P2_MEM_BEFORE_INF"]["heap_free"]
        after = g[g["event_name"] == "INST_P2_MEM_AFTER_INF"]["heap_free"]

        rows.append({
            "model_id": int(model_id),
            "tu": int(tu),
            "heap_delta_inf": (
                int(after.iloc[0]) - int(before.iloc[0])
                if not before.empty and not after.empty
                else None
            ),
        })

    return pd.DataFrame(rows)


# ============================================================
# TU SUMMARY
# ============================================================

def summarize_by_tu(sys_tbl: pd.DataFrame, mod_tbl: pd.DataFrame) -> pd.DataFrame:
    if mod_tbl.empty:
        return sys_tbl.copy()

    counts = (
        mod_tbl.groupby(["tu", "outcome"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )
    return sys_tbl.merge(counts, on="tu", how="left")


# ============================================================
# HIGH-LEVEL ENTRYPOINT
# ============================================================

def parse_and_reconstruct(log_path: Path):
    raw = parse_raw_log(log_path)
    enriched = enrich(raw)

    sys_tbl = reconstruct_sys(enriched)
    mod_tbl = reconstruct_models(enriched)
    mem_tbl = reconstruct_memory(enriched)
    tu_summary = summarize_by_tu(sys_tbl, mod_tbl)

    return enriched, sys_tbl, mod_tbl, mem_tbl, tu_summary


def parse_log_enriched(log_path: Path) -> pd.DataFrame:
    raw = parse_raw_log(log_path)
    if raw.empty:
        return raw

    return enrich(raw)