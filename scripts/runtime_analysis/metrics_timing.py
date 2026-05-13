import pandas as pd


def _summary_from_cycles_ms(cycles_ms: pd.Series):
    if cycles_ms is None:
        return {}

    cycles_ms = cycles_ms.dropna()
    if cycles_ms.empty:
        return {}

    return dict(
        n_tu=len(cycles_ms),
        sys_cycle_worst_ms=float(cycles_ms.max()),
        sys_cycle_process_max_ms=float(cycles_ms.max()),
        sys_cycle_mean_ms=float(cycles_ms.mean()),
        sys_cycle_median_ms=float(cycles_ms.median()),
        sys_cycle_max_ms=float(cycles_ms.max()),
        sys_cycle_std_ms=float(cycles_ms.std(ddof=0)),
    )


def compute_system_summary(df):

    if "event_name" not in df.columns:
        return {}

    # Formato actual (parser enriquecido): reconstruir por TU usando timestamps.
    if {"ts_us", "tu"}.issubset(df.columns):
        wake = (
            df[df["event_name"] == "INST_SYS_P0_TU_WAKE"]
            .groupby("tu")["ts_us"]
            .min()
        )
        end = (
            df[df["event_name"] == "INST_SYS_P3_TU_END"]
            .groupby("tu")["ts_us"]
            .max()
        )
        if not wake.empty and not end.empty:
            cycles_us = (end - wake).dropna()
            # Mantener solo duraciones positivas para evitar pares corruptos.
            cycles_us = cycles_us[cycles_us > 0]
            if not cycles_us.empty:
                return _summary_from_cycles_ms(cycles_us / 1000.0)

    # Formato legacy: evento con duración ya codificada en value (ms).
    if "value" in df.columns:
        sys_cycles = df[df["event_name"] == "INST_SYS_P3_CYCLE_END"]
        if not sys_cycles.empty:
            return _summary_from_cycles_ms(sys_cycles["value"])

    return {}