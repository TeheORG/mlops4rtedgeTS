import pandas as pd


def _stats(series):

    if series is None or len(series) == 0:
        return dict(
            n=0,
            mean_us=None,
            median_us=None,
            max_us=None,
            std_us=None,
        )

    return dict(
        n=len(series),
        mean_us=float(series.mean()),
        median_us=float(series.median()),
        max_us=float(series.max()),
        std_us=float(series.std(ddof=0)),
    )


def _us_to_ms(v):
    return None if v is None else v / 1000.0


def _safe_column(df, col):
    if col in df.columns:
        return df[col]
    return None


def compute_model_metrics(df):

    rows = []

    if "model_id" not in df.columns:
        raise RuntimeError("Parser did not produce model_id column")

    for model_id, g in df.groupby("model_id"):

        model_name = (
            g["model_name"].iloc[0]
            if "model_name" in g.columns
            else f"model_{model_id}"
        )

        # ---------------------------------------------------
        # counters (alineados con eventos reales del firmware)
        # ---------------------------------------------------

        n_attempts = 0
        n_ok = 0
        n_wd_late = 0
        n_wd_early = 0
        n_inference_incomplete = 0
        n_offload = 0
        n_urgent = 0
        n_no_inference = 0

        attempt_tus = []
        if "tu" in g.columns:
            attempts = g[g["event_name"] == "INST_MOD_P0_MODEL_BEGIN"]
            attempt_tus = sorted(set(attempts["tu"].tolist()))
            n_attempts = len(attempt_tus)

            for tu in attempt_tus:
                gt = g[g["tu"] == tu]
                names = set(gt["event_name"].tolist())

                has_inf_start = "INST_MOD_P2_INF_START" in names
                has_inf_end = "INST_MOD_P2_INF_END" in names
                has_wdg = "INST_MOD_PX_WDG_FIRE" in names

                ts_inf_start = (
                    gt.loc[gt["event_name"] == "INST_MOD_P2_INF_START", "ts_us"].min()
                    if has_inf_start
                    else None
                )
                ts_inf_end = (
                    gt.loc[gt["event_name"] == "INST_MOD_P2_INF_END", "ts_us"].max()
                    if has_inf_end
                    else None
                )
                ts_wdg = (
                    gt.loc[gt["event_name"] == "INST_MOD_PX_WDG_FIRE", "ts_us"].min()
                    if has_wdg
                    else None
                )

                if "FUNC_OFFLOAD_RESULT" in names:
                    n_offload += 1
                elif "FUNC_URGENT_RESULT" in names:
                    n_urgent += 1
                elif "FUNC_PRED_RESULT" in names:
                    n_ok += 1
                elif has_wdg and not has_inf_start:
                    n_wd_early += 1
                elif has_wdg and has_inf_start and (not has_inf_end):
                    if ts_wdg is not None and ts_inf_start is not None and ts_wdg < ts_inf_start:
                        n_wd_early += 1
                    else:
                        n_wd_late += 1
                elif has_wdg and has_inf_start and has_inf_end:
                    # Clasificación temporal estricta cuando la inferencia completa existe.
                    if (
                        ts_wdg is not None
                        and ts_inf_start is not None
                        and ts_wdg < ts_inf_start
                    ):
                        n_wd_early += 1
                    elif (
                        ts_wdg is not None
                        and ts_inf_start is not None
                        and ts_inf_end is not None
                        and ts_inf_start <= ts_wdg <= ts_inf_end
                    ):
                        n_wd_late += 1
                    else:
                        n_no_inference += 1
                elif has_inf_start and not has_inf_end:
                    n_inference_incomplete += 1
                else:
                    n_no_inference += 1

        # ---------------------------------------------------
        # inference timing
        # ---------------------------------------------------

        starts = g[g["event_name"] == "INST_MOD_P2_INF_START"]["ts_us"].values
        ends = g[g["event_name"] == "INST_MOD_P2_INF_END"]["ts_us"].values

        n_inf = min(len(starts), len(ends))

        if n_inf > 0:
            infer_durations = pd.Series(ends[:n_inf] - starts[:n_inf])
        else:
            infer_durations = None

        infer_stats = _stats(infer_durations)

        # ---------------------------------------------------
        # process timing
        # ---------------------------------------------------

        proc_start = g[g["event_name"] == "INST_MOD_P1_PROCESS_START"]["ts_us"].values
        proc_end = g[g["event_name"] == "INST_MOD_P3_PROCESS_END"]["ts_us"].values

        n_proc = min(len(proc_start), len(proc_end))

        if n_proc > 0:
            process_durations = pd.Series(proc_end[:n_proc] - proc_start[:n_proc])
        else:
            # Fallback a evento begin/end de modelo, más estable con el firmware actual.
            mb = g[g["event_name"] == "INST_MOD_P0_MODEL_BEGIN"]["ts_us"].values
            me = g[g["event_name"] == "INST_MOD_P3_MODEL_END"]["ts_us"].values
            n_fallback = min(len(mb), len(me))
            if n_fallback > 0:
                process_durations = pd.Series(me[:n_fallback] - mb[:n_fallback])
                process_durations = process_durations[process_durations >= 0]
            else:
                process_durations = None

        process_stats = _stats(process_durations)

        # ---------------------------------------------------
        # inference overhead (process - inference) worst-case
        # ---------------------------------------------------

        overhead_durations_us = []
        if attempt_tus:
            for tu in attempt_tus:
                gt = g[g["tu"] == tu]

                mb = gt.loc[gt["event_name"] == "INST_MOD_P0_MODEL_BEGIN", "ts_us"]
                me = gt.loc[gt["event_name"] == "INST_MOD_P3_MODEL_END", "ts_us"]
                is_ = gt.loc[gt["event_name"] == "INST_MOD_P2_INF_START", "ts_us"]
                ie = gt.loc[gt["event_name"] == "INST_MOD_P2_INF_END", "ts_us"]

                if mb.empty or me.empty or is_.empty or ie.empty:
                    continue

                proc_us = int(me.max()) - int(mb.min())
                inf_us = int(ie.max()) - int(is_.min())
                overhead_us = proc_us - inf_us

                if proc_us >= 0 and inf_us >= 0 and overhead_us >= 0:
                    overhead_durations_us.append(overhead_us)

        overhead_max_us = max(overhead_durations_us) if overhead_durations_us else None
        overhead_max_ms = _us_to_ms(overhead_max_us)

        # ---------------------------------------------------
        # start error
        # ---------------------------------------------------

        start_err = None
        if "value" in g.columns:
            start_err = g[g["event_name"] == "INST_MOD_P1_START_ERROR"]["value"]

        start_err_stats = _stats(start_err)

        # ---------------------------------------------------
        # end error
        # ---------------------------------------------------

        end_err = None
        if "value" in g.columns:
            end_err = g[g["event_name"] == "INST_MOD_P3_END_ERROR"]["value"]

        end_err_stats = _stats(end_err)

        # ---------------------------------------------------
        # jitter
        # ---------------------------------------------------

        jitter = None
        if infer_stats["std_us"] is not None:
            jitter = infer_stats["std_us"] / 1000.0

        row = dict(
            model_id=model_id,
            model_name=model_name,
            n_attempts=int(n_attempts),
            n_ok=int(n_ok),
            n_wd_late=int(n_wd_late),
            n_wd_early=int(n_wd_early),
            n_inference_incomplete=int(n_inference_incomplete),
            n_offload=int(n_offload),
            n_urgent=int(n_urgent),
            n_no_inference=int(n_no_inference),
        )

        # infer
        for k, v in infer_stats.items():
            row[f"infer_{k}"] = v
            if k.endswith("_us"):
                row[f"infer_{k.replace('_us','_ms')}"] = _us_to_ms(v)

        # process
        for k, v in process_stats.items():
            row[f"process_{k}"] = v
            if k.endswith("_us"):
                row[f"process_{k.replace('_us','_ms')}"] = _us_to_ms(v)

        # start error
        for k, v in start_err_stats.items():
            row[f"start_error_{k}"] = v
            if k.endswith("_us"):
                row[f"start_error_{k.replace('_us','_ms')}"] = _us_to_ms(v)

        # end error
        for k, v in end_err_stats.items():
            row[f"end_error_{k}"] = v
            if k.endswith("_us"):
                row[f"end_error_{k.replace('_us','_ms')}"] = _us_to_ms(v)

        row["infer_jitter_ms"] = jitter
        row["infer_overhead_max_us"] = overhead_max_us
        row["infer_overhead_max_ms"] = overhead_max_ms

        rows.append(row)

    return pd.DataFrame(rows)