#include "predictions_mgr.h"
#include "tflite_runner.h"
#include "esp_timer.h"
#include "trace.h"
#include "models_mgr.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <freertos/queue.h>
#include "esp_heap_caps.h"


#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <stdbool.h>
#include <stdint.h>

#define BIT_START     (1 << 0)
#define BIT_DEADLINE  (1 << 1)
#define BIT_DONE      (1 << 2)   

typedef struct {
    schedule_entry_t *entries;
    size_t            count;
} pred_batch_t;

#define SCALE_US(x) ((x) * 1000ULL)

static events_mgr_t*    s_evt_mgr;
static QueueHandle_t    s_batch_queue;
static TaskHandle_t     s_mgr_handle;
static TaskHandle_t     s_worker_handle;
static esp_timer_handle_t s_start_timer;
static esp_timer_handle_t s_deadline_timer;
static schedule_entry_t s_slot;    

static event_t*         s_events;
static size_t           ev_count;

static int pred_result = 0;

static void IRAM_ATTR start_timer_cb(void *arg) {
    uint64_t ts_fire = esp_timer_get_time();
    BaseType_t woke = pdFALSE;
    xTaskNotifyFromISR(s_mgr_handle, BIT_START, eSetBits, &woke);
    portYIELD_FROM_ISR(woke);
}

static void IRAM_ATTR deadline_timer_cb(void *arg) {
    BaseType_t woke = pdFALSE;
    xTaskNotifyFromISR(s_mgr_handle, BIT_DEADLINE, eSetBits, &woke);
    portYIELD_FROM_ISR(woke);
}

static void worker_task(void *arg) {
    (void)arg;
    for (;;) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        schedule_entry_t slot = s_slot;
        //size_t ev_count;
        //const event_t *events = events_mgr_get_at(
        //    s_evt_mgr, slot.event_time, &ev_count);
        int model_id = models_mgr_index_of(slot.model);
        TRACE_INST(INST_MOD_P2_INF_START, model_id,
                slot.event_time, 0, 0, 0); 
        tflite_runner_run(slot.model, s_events, ev_count,
            &pred_result, sizeof(pred_result)
        );
        TRACE_INST(INST_MOD_P2_INF_END, model_id,
                slot.event_time, 0, 0, 0); 
        //free((void*)events);
        xTaskNotify(s_mgr_handle, BIT_DONE, eSetBits);
    }
}

static void manager_task(void *arg) {
    (void)arg;
    pred_batch_t batch;
    uint32_t bits;
    while (1) {
        if (xQueueReceive(s_batch_queue, &batch, portMAX_DELAY) != pdTRUE) {
            continue;
        }
        TRACE_INST(INST_MOD_P0_CPM_BEGIN, MODEL_SYS, batch.entries[0].event_time, batch.count, 0, 0);
        //size_t ev_count;
        //const event_t *
        s_events = events_mgr_get_at(s_evt_mgr, s_slot.event_time, &ev_count );
        uint32_t fp = events_mgr_fingerprint(s_events, ev_count);

        for (size_t i = 0; i < batch.count; ++i) {
            s_slot = batch.entries[i];
            int model_id = models_mgr_index_of(s_slot.model);

            uint64_t now_us    = esp_timer_get_time();
            int64_t  delay_us  = (int64_t) s_slot.start_time - (int64_t) now_us;
            delay_us = (delay_us < 0) ? 0 : delay_us;
            int64_t  dead_us   = (int64_t) s_slot.deadline - (int64_t) now_us;
            if (dead_us <= 0) {             
                TRACE_INST(INST_MOD_PX_WDG_FIRE, model_id, s_slot.event_time, 0, 0, 0);
                TRACE_FUNC_URGENT(model_id, s_slot.event_time, 0);
                size_t heap_free = xPortGetFreeHeapSize();
                size_t heap_min  = xPortGetMinimumEverFreeHeapSize();
                TRACE_INST(INST_PX_MEM_AFTER_WDG, model_id, s_slot.event_time, heap_free, heap_min, 0);
                continue;
            }

            TRACE_INST(INST_MOD_P1_TIMER_ARM_BEG, model_id, s_slot.event_time, s_slot.start_time, s_slot.deadline, dead_us);
            esp_timer_start_once(s_start_timer, delay_us);
            esp_timer_start_once(s_deadline_timer, dead_us);
            TRACE_INST(INST_MOD_P1_TIMER_ARM_END, model_id, s_slot.event_time, 0, 0, 0);
            size_t heap_free = xPortGetFreeHeapSize();
            size_t heap_min  = xPortGetMinimumEverFreeHeapSize();
            TRACE_INST(INST_P2_MEM_BEFORE_INF, model_id, s_slot.event_time, heap_free, heap_min, 0);

            bits = 0;
            xTaskNotifyWait(0, BIT_START | BIT_DEADLINE, &bits, portMAX_DELAY);
            TRACE_INST(INST_MOD_P0_MODEL_BEGIN, model_id, s_slot.event_time, 0, 0, 0);
            if (bits & BIT_DEADLINE) {
                esp_timer_stop(s_start_timer);
                TRACE_INST(INST_MOD_PX_WDG_FIRE, model_id, s_slot.event_time, 0, 0, 0);
                TRACE_FUNC_URGENT(model_id, s_slot.event_time, 0);
                size_t heap_free = xPortGetFreeHeapSize();
                size_t heap_min  = xPortGetMinimumEverFreeHeapSize();
                TRACE_INST(INST_PX_MEM_AFTER_WDG, model_id, s_slot.event_time, heap_free, heap_min, 0);
                continue;
            }

            xTaskNotifyGive(s_worker_handle);
            bits = 0;
            xTaskNotifyWait(0, BIT_DONE | BIT_DEADLINE, &bits, portMAX_DELAY);

            if (bits & BIT_DEADLINE) {
                vTaskDelete(s_worker_handle);
                int model_id = models_mgr_index_of(s_slot.model);
                TRACE_INST(INST_MOD_PX_WDG_FIRE, model_id, s_slot.event_time, 0, 0, 0);
                TRACE_FUNC_URGENT(model_id, s_slot.event_time, 0);
                size_t heap_free = xPortGetFreeHeapSize();
                size_t heap_min  = xPortGetMinimumEverFreeHeapSize();
                TRACE_INST(INST_PX_MEM_AFTER_WDG, model_id, s_slot.event_time, heap_free, heap_min, 0);
                xTaskCreatePinnedToCore(worker_task, "pred_worker", 8*1024, NULL,
                    configMAX_PRIORITIES-2, &s_worker_handle,1);
            } else {
                esp_timer_stop(s_deadline_timer);
                uint64_t end_us = esp_timer_get_time();
                char resbuf[16];
                snprintf(resbuf, sizeof(resbuf), "%d", pred_result );
                TRACE_INST(INST_MOD_P3_MODEL_END, model_id, s_slot.event_time, 0, 0, 0);
                TRACE_FUNC_PRED(model_id, s_slot.event_time, fp, pred_result);
                size_t heap_free = xPortGetFreeHeapSize();
                size_t heap_min  = xPortGetMinimumEverFreeHeapSize();
                TRACE_INST(INST_P2_MEM_AFTER_INF, model_id, s_slot.event_time, heap_free, heap_min, 0);                
            }
            //free((void*)s_events);
            heap_free = xPortGetFreeHeapSize();
            heap_min  = xPortGetMinimumEverFreeHeapSize();
            TRACE_INST(INST_P3_MEM_AFTER_POST, model_id, s_slot.event_time, heap_free, heap_min, 0);
        }
        TRACE_INST(INST_MOD_P3_CPM_END, MODEL_SYS, batch.entries[0].event_time, 0, 0, 0);
        free(batch.entries);
        free((void*)s_events);
        s_events = NULL;
        ev_count = 0;
    }
}

void prediction_mgr_init(events_mgr_t *evt_mgr) {
    s_evt_mgr     = evt_mgr;
    s_batch_queue = xQueueCreate(1024 //128
        , sizeof(pred_batch_t));
    configASSERT(s_batch_queue);
    {
        const esp_timer_create_args_t a1 = {
            .callback        = start_timer_cb,
            .arg             = NULL,
#if defined(ESP_TIMER_ISR)
    .dispatch_method = ESP_TIMER_ISR,
#endif
            .name            = "start_t"
        };
        ESP_ERROR_CHECK(esp_timer_create(&a1, &s_start_timer));
        const esp_timer_create_args_t a2 = {
            .callback        = deadline_timer_cb,
            .arg             = NULL,
#if defined(ESP_TIMER_ISR)
    .dispatch_method = ESP_TIMER_ISR,
#endif
            .name            = "dead_t"
        };
        ESP_ERROR_CHECK(esp_timer_create(&a2, &s_deadline_timer));
    }
    xTaskCreatePinnedToCore(
        worker_task, "pred_worker", 8*1024, NULL,
        configMAX_PRIORITIES-2, &s_worker_handle, 1
    );
    xTaskCreatePinnedToCore(
        manager_task, "pred_mgr", 8*1024, NULL,
        configMAX_PRIORITIES-1, &s_mgr_handle, 0
    );
}

void prediction_mgr_start(const schedule_entry_t *entries, size_t count) {
    schedule_entry_t *dup = malloc(sizeof(*dup)*count);
    if (!dup) return;
    memcpy(dup, entries, sizeof(*dup)*count);
    pred_batch_t b = { .entries = dup, .count = count };
    if (xQueueSend(s_batch_queue, &b, 0) != pdTRUE) {
        free(dup);
        return;
    }
    UBaseType_t queue_depth = uxQueueMessagesWaiting(s_batch_queue);
    TRACE_INST(INST_SYS_P1_QUEUE_SEND,
               MODEL_SYS,
               entries[0].event_time,        // el Tu del ciclo SYS
               count,             // a = nº modelos enviados
               queue_depth,       // b = profundidad cola tras enviar
               0);
}