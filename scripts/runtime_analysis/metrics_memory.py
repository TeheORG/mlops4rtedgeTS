# runtime_analysis/metrics_memory.py

# Valores de heap_free por debajo de este umbral se consideran lecturas corruptas del firmware.
# En ESP32, el sistema no puede operar con menos de 1 KB libre.
_HEAP_FREE_MIN_VALID = 1000


def compute_memory_summary(df):

    mem = df[df["event_name"].str.contains("MEM")]

    heap_total_ref = None
    if "event_name" in df.columns and "heap_total" in df.columns:
        ref_vals = df.loc[df["event_name"] == "INST_SYS_P0_MEM_TOTAL_REF", "heap_total"]
        ref_vals = ref_vals.dropna()
        if not ref_vals.empty:
            heap_total_ref = int(ref_vals.iloc[0])

    if mem.empty:
        return (
            dict(heap_total_ref=heap_total_ref)
            if heap_total_ref is not None
            else {}
        )

    # Filtrar lecturas claramente inválidas
    valid = mem[mem["heap_free"].notna() & (mem["heap_free"].astype(float) >= _HEAP_FREE_MIN_VALID)]
    if valid.empty:
        valid = mem

    heap_free_min = int(valid["heap_free"].min())
    heap_free_max = int(valid["heap_free"].max())
    heap_free_mean = float(valid["heap_free"].mean())
    heap_min_ever_vals = valid[valid["heap_min"].notna() & (valid["heap_min"].astype(float) >= 0)]
    heap_min_ever = int(heap_min_ever_vals["heap_min"].min()) if not heap_min_ever_vals.empty else None

    # Estadísticos por fase del ciclo de sistema
    phase_stats = {}
    for phase_tag, col_key in [
        ("before_read", "INST_SYS_P0_MEM_BEFORE_READ"),
        ("after_read",  "INST_SYS_P1_MEM_AFTER_READ"),
        ("before_inf",  "INST_P2_MEM_BEFORE_INF"),
    ]:
        phase_df = valid[valid["event_name"] == col_key]["heap_free"]
        if not phase_df.empty:
            phase_stats[f"heap_free_min_{phase_tag}_bytes"] = int(phase_df.min())
            phase_stats[f"heap_free_mean_{phase_tag}_bytes"] = round(float(phase_df.mean()), 1)

    return dict(
        # Referencia total del heap (solo cuando el firmware emite INST_SYS_P0_MEM_TOTAL_REF)
        heap_total_ref=heap_total_ref,
        # Mínimo de heap libre observado en todo el run (peor caso de dimensionamiento)
        heap_free_min_bytes=heap_free_min,
        # Watermark de mínimo histórico reportado por FreeRTOS (xPortGetMinimumEverFreeHeapSize)
        heap_min_ever_bytes=heap_min_ever,
        # Estadísticos globales
        heap_free_max_bytes=heap_free_max,
        heap_free_mean_bytes=round(heap_free_mean, 1),
        # Ocupación máxima absoluta (solo disponible con heap_total_ref)
        mem_used_max_bytes=(heap_total_ref - heap_free_min) if heap_total_ref is not None else None,
        mem_used_max_pct=(round((heap_total_ref - heap_free_min) / heap_total_ref * 100.0, 2)
                         if heap_total_ref not in (None, 0) else None),
        # Estadísticos por fase del ciclo de sistema
        **phase_stats,
    )