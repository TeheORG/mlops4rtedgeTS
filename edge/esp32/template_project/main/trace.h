#ifndef TRACE_H
#define TRACE_H

#include <stdint.h>

// =========================
// Event enum (cerrado)
// =========================
typedef enum {
    /* =====================================================
     * Funcionales FINAL
     * (exactamente uno por (model_id, tu))
     * ===================================================== */
    FUNC_PRED_RESULT = 1,
    FUNC_OFFLOAD_RESULT,
    FUNC_URGENT_RESULT,

    /* =====================================================
     * Instrumentación – Ciclo de sistema (SYS)
     * ===================================================== */
    /* P0: inicio de Tu */
    INST_SYS_P0_TU_WAKE,
    INST_SYS_P0_MEM_BEFORE_READ,
    /* P1: lectura y planificación */
    INST_SYS_P1_READ_EVENTS,
    INST_SYS_P1_MEM_AFTER_READ,
    INST_SYS_P1_SCHED_START,
    INST_SYS_P1_SCHED_DECISION,
    INST_SYS_P1_SCHED_END,
    INST_SYS_P1_QUEUE_SEND,
    /* P3: fin de Tu */
    INST_SYS_P3_TU_END,

    /* =====================================================
     * Instrumentación – Ciclo planificado de modelos (MOD–CPM)
     * ===================================================== */
    INST_MOD_P0_CPM_BEGIN,
    INST_MOD_P3_CPM_END,
    /* =====================================================
     * Instrumentación – Ciclo de modelo (micro-ciclo)
     * ===================================================== */
    /* P0: inicio modelo */
    INST_MOD_P0_MODEL_BEGIN,
    /* P1: timers */
    INST_MOD_P1_TIMER_ARM_BEG,
    INST_MOD_P1_TIMER_ARM_END,
    /* P2: inferencia */
    INST_MOD_P2_INF_START,
    INST_MOD_P2_INF_END,
    INST_P2_MEM_BEFORE_INF,
    INST_P2_MEM_AFTER_INF,
    /* PX: excepción */
    INST_MOD_PX_WDG_FIRE,
    INST_PX_MEM_AFTER_WDG,
    /* P3: cierre modelo */
    INST_MOD_P3_MODEL_END,
    INST_P3_MEM_AFTER_POST,

    /* =====================================================
     * Instrumentación – Memoria transversal
     * ===================================================== */
    /* P0: latido periódico */
    INST_P0_MEM_HEARTBEAT,
    /* Referencia estática de heap al arranque: a=heap_total, b=heap_free0, c=heap_min0 */
    INST_SYS_P0_MEM_TOTAL_REF
} trace_event_t;
  #define TRACE_EVENT_COUNT INST_SYS_P0_MEM_TOTAL_REF


#define MODEL_SYS (-1)


// Inicialización del sistema de trazas
void trace_init(int baud_rate);

// Emisión base (canal 64-bit, sin truncado)
void trace_emit(uint32_t ev,
                int32_t  model,
                uint64_t tu,
                uint64_t a,
                uint64_t b,
                uint64_t c);

// =========================
// Funcionales: SIEMPRE activas
// =========================

#define TRACE_FUNC_PRED(model, tu, fingerprint, value) \
    trace_emit(FUNC_PRED_RESULT, \
               (int32_t)(model), \
               (uint64_t)(tu), \
               (uint64_t)(fingerprint), \
               (uint64_t)(value), \
               0)

#define TRACE_FUNC_OFFLOAD(model, tu) \
    trace_emit(FUNC_OFFLOAD_RESULT, \
               (int32_t)(model), \
               (uint64_t)(tu), \
               0, 0, 0)

#define TRACE_FUNC_URGENT(model, tu, fingerprint) \
    trace_emit(FUNC_URGENT_RESULT, \
               (int32_t)(model), \
               (uint64_t)(tu), \
               (uint64_t)(fingerprint), \
               0, 0)


// Instrumentación: conmutables
#ifdef ENABLE_TRACES
  #define TRACE_INST(ev,m,tu,a,b,c) \
      trace_emit((ev), (m), (uint64_t)(tu), (uint64_t)(a), (uint64_t)(b), (uint64_t)(c))
#else
  #define TRACE_INST(ev,m,tu,a,b,c) do{}while(0)
#endif

#endif // TRACE_H