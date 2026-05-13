# scripts/runtime_analysis/inference_reconstruction.py
# -*- coding: utf-8 -*-

"""
Inference reconstruction engine.

Builds one analytical record per (model_id, tu), representing the
runtime attempt of a model within a TU.

Provides:
    - reconstruct_inference_records()

Pure analytical module.
No CLI. No prints. No file writing.
"""

import pandas as pd


def _first_ts(g: pd.DataFrame, event_name: str):
    x = g.loc[g["event_name"] == event_name, "ts_us"]
    return int(x.iloc[0]) if not x.empty else None


def _first_value(g: pd.DataFrame, event_name: str, col: str):
    x = g.loc[g["event_name"] == event_name, col]
    x = x.dropna()
    return x.iloc[0] if not x.empty else None


def _first_row(g: pd.DataFrame, event_name: str):
    x = g.loc[g["event_name"] == event_name]
    return x.iloc[0] if not x.empty else None


def _safe_delta(start_ts, end_ts):
    if start_ts is None or end_ts is None:
        return None
    delta = int(end_ts) - int(start_ts)
    return delta if delta >= 0 else None


def reconstruct_inference_records(df: pd.DataFrame) -> pd.DataFrame:
    """
    Reconstruct one record per (model_id, tu).

    Output columns include:
        - outcome
        - infer_time_us
        - process_time_us
        - start/end timing errors
        - heap deltas
        - prediction payload
    """
    if df.empty:
        return pd.DataFrame()

    mod_df = df[df["domain"].isin(["MOD", "MEM", "FUNC"])].copy()
    if mod_df.empty:
        return pd.DataFrame()

    rows = []

    for (model_id, tu), g in mod_df.groupby(["model_id", "tu"], sort=True):
        if int(model_id) == -1:
            continue

        g = g.sort_values("ts_us")

        model_name = None
        if "model_name" in g.columns:
            mn = g["model_name"].dropna()
            model_name = str(mn.iloc[0]) if not mn.empty else f"model_{int(model_id)}"
        else:
            model_name = f"model_{int(model_id)}"

        model_begin_ts = _first_ts(g, "INST_MOD_P0_MODEL_BEGIN")
        timer_arm_row = _first_row(g, "INST_MOD_P1_TIMER_ARM_BEG")
        inf_start_ts = _first_ts(g, "INST_MOD_P2_INF_START")
        inf_end_ts = _first_ts(g, "INST_MOD_P2_INF_END")
        wdg_fire_ts = _first_ts(g, "INST_MOD_PX_WDG_FIRE")
        model_end_ts = _first_ts(g, "INST_MOD_P3_MODEL_END")

        pred_row = _first_row(g, "FUNC_PRED_RESULT")
        offload_row = _first_row(g, "FUNC_OFFLOAD_RESULT")
        urgent_row = _first_row(g, "FUNC_URGENT_RESULT")

        plan_start_us = None
        plan_deadline_us = None
        if timer_arm_row is not None:
            try:
                plan_start_us = int(timer_arm_row["plan_start_us"])
            except Exception:
                plan_start_us = int(timer_arm_row["a"])
            try:
                plan_deadline_us = int(timer_arm_row["plan_deadline_us"])
            except Exception:
                plan_deadline_us = int(timer_arm_row["b"])

        if inf_start_ts is not None and inf_end_ts is not None:
            outcome = "ok"
            infer_stop_ts = inf_end_ts
        elif wdg_fire_ts is not None and inf_start_ts is not None:
            outcome = "wd_late"
            infer_stop_ts = wdg_fire_ts
        elif wdg_fire_ts is not None and inf_start_ts is None:
            outcome = "wd_early"
            infer_stop_ts = None
        elif inf_start_ts is not None and inf_end_ts is None:
            outcome = "inference_incomplete"
            infer_stop_ts = None
        elif offload_row is not None:
            outcome = "offload"
            infer_stop_ts = None
        elif urgent_row is not None:
            outcome = "urgent"
            infer_stop_ts = None
        elif (
            model_begin_ts is not None
            or model_end_ts is not None
            or timer_arm_row is not None
        ):
            outcome = "no_inference"
            infer_stop_ts = None
        else:
            # Sin actividad model-level real en este (model_id, tu)
            continue

        infer_time_us = _safe_delta(inf_start_ts, infer_stop_ts)
        process_time_us = _safe_delta(model_begin_ts, model_end_ts)
        post_time_us = _safe_delta(inf_end_ts, model_end_ts) if inf_end_ts is not None else None

        start_error_us = _safe_delta(plan_start_us, inf_start_ts)
        end_error_us = _safe_delta(plan_deadline_us, infer_stop_ts) if infer_stop_ts is not None else None

        heap_before_inf = _first_value(g, "INST_P2_MEM_BEFORE_INF", "heap_free")
        heap_after_inf = _first_value(g, "INST_P2_MEM_AFTER_INF", "heap_free")
        heap_after_post = _first_value(g, "INST_P3_MEM_AFTER_POST", "heap_free")
        heap_after_wdg = _first_value(g, "INST_PX_MEM_AFTER_WDG", "heap_free")

        heap_min_before_inf = _first_value(g, "INST_P2_MEM_BEFORE_INF", "heap_min")
        heap_min_after_inf = _first_value(g, "INST_P2_MEM_AFTER_INF", "heap_min")
        heap_min_after_post = _first_value(g, "INST_P3_MEM_AFTER_POST", "heap_min")
        heap_min_after_wdg = _first_value(g, "INST_PX_MEM_AFTER_WDG", "heap_min")

        heap_delta_inf_free = (
            int(heap_after_inf) - int(heap_before_inf)
            if heap_before_inf is not None and heap_after_inf is not None
            else None
        )

        heap_delta_post_free = (
            int(heap_after_post) - int(heap_after_inf)
            if heap_after_inf is not None and heap_after_post is not None
            else None
        )

        fingerprint = None
        predicted = None
        pred_result_ts = None
        if pred_row is not None:
            try:
                fingerprint = int(pred_row["fingerprint"])
            except Exception:
                try:
                    fingerprint = int(pred_row["a"])
                except Exception:
                    fingerprint = None
            try:
                predicted = int(pred_row["predicted"])
            except Exception:
                try:
                    predicted = int(pred_row["b"])
                except Exception:
                    predicted = None
            pred_result_ts = int(pred_row["ts_us"])

        rows.append({
            "model_id": int(model_id),
            "model_name": model_name,
            "tu": int(tu),

            "model_begin_ts": model_begin_ts,
            "plan_start_us": plan_start_us,
            "plan_deadline_us": plan_deadline_us,
            "inf_start_ts": inf_start_ts,
            "inf_end_ts": inf_end_ts,
            "wdg_fire_ts": wdg_fire_ts,
            "model_end_ts": model_end_ts,
            "pred_result_ts": pred_result_ts,

            "outcome": outcome,
            "infer_time_us": infer_time_us,
            "process_time_us": process_time_us,
            "post_time_us": post_time_us,
            "start_error_us": start_error_us,
            "end_error_us": end_error_us,

            "heap_before_inf": int(heap_before_inf) if heap_before_inf is not None else None,
            "heap_after_inf": int(heap_after_inf) if heap_after_inf is not None else None,
            "heap_after_post": int(heap_after_post) if heap_after_post is not None else None,
            "heap_after_wdg": int(heap_after_wdg) if heap_after_wdg is not None else None,

            "heap_min_before_inf": int(heap_min_before_inf) if heap_min_before_inf is not None else None,
            "heap_min_after_inf": int(heap_min_after_inf) if heap_min_after_inf is not None else None,
            "heap_min_after_post": int(heap_min_after_post) if heap_min_after_post is not None else None,
            "heap_min_after_wdg": int(heap_min_after_wdg) if heap_min_after_wdg is not None else None,

            "heap_delta_inf_free": heap_delta_inf_free,
            "heap_delta_post_free": heap_delta_post_free,

            "fingerprint": fingerprint,
            "predicted": predicted,

            "has_prediction_result": pred_row is not None,
            "has_offload_result": offload_row is not None,
            "has_urgent_result": urgent_row is not None,
        })

    return pd.DataFrame(rows)