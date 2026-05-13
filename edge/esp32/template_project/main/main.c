#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "data_reader.h"
#include "config.h"
#include "events_mgr.h"
#include "models_mgr.h"
#include "scheduler.h"
#include "predictions_mgr.h"
#include "tflite_runner.h"
#include "esp_timer.h"
#include "esp_heap_caps.h"
#include "trace.h"



#define PRIORITY_MAIN      (tskIDLE_PRIORITY + 24)

#if USE_SERIAL_READER
  #include "driver/uart.h"

  //////////////////////////////////////////////////////////////////////////////
  /// @brief Initialize UART0 for CSV‐over‐serial input, if serial mode is enabled
  static void init_serial_reader(void) {
      const uart_config_t uart_cfg = {
          .baud_rate = 115200,
          .data_bits = UART_DATA_8_BITS,
          .parity    = UART_PARITY_DISABLE,
          .stop_bits = UART_STOP_BITS_1,
          .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
      };
      // configure UART0 parameters
      uart_param_config(UART_NUM_0, &uart_cfg);
      // use default USB‐bridge TX/RX pins
      uart_set_pin(UART_NUM_0,
                   UART_PIN_NO_CHANGE,
                   UART_PIN_NO_CHANGE,
                   UART_PIN_NO_CHANGE,
                   UART_PIN_NO_CHANGE);
      // install driver, give it a 2 KB RX buffer
      uart_driver_install(UART_NUM_0, 2048, 0, 0, NULL, 0);
  }


#endif

#define MAX_EVENTS 1024

static event_t events[MAX_EVENTS];

void app_main(void) {
#if USE_SERIAL_READER
    // init_serial_reader();
#endif
    printf("TICK_MS = %u ms (configTICK_RATE_HZ = %u)\n",
       (unsigned)portTICK_PERIOD_MS,
       (unsigned)configTICK_RATE_HZ);

    trace_init(115200);

    models_mgr_init();
    size_t fit = count_models_that_fit();
    printf("\nAccepted models: %u\n", fit);
    tflite_runner_init(g_models, g_models_count);
    events_mgr_t *mgr = events_mgr_create();
    if (!mgr) {
        printf("Error: cannot create events manager\n");
        vTaskDelete(NULL);
    }
    vTaskPrioritySet(NULL, PRIORITY_MAIN);
    prediction_mgr_init(mgr);

    // Emitir referencia de heap antes del primer TU para no contaminar el ciclo medido.
    // El monitor serie tarda ~300 ms en engancharse tras el flash; esperamos 500 ms antes
    // de emitir para garantizar que las tramas sean capturadas.
    vTaskDelay(pdMS_TO_TICKS(500));
    for (int i = 0; i < 3; ++i) {
        uint64_t ts_ref = esp_timer_get_time();
        size_t heap_total_ref = heap_caps_get_total_size(MALLOC_CAP_8BIT);
        size_t heap_free_ref = xPortGetFreeHeapSize();
        size_t heap_min_ref = xPortGetMinimumEverFreeHeapSize();
        TRACE_INST(INST_SYS_P0_MEM_TOTAL_REF, MODEL_SYS, ts_ref, heap_total_ref, heap_free_ref, heap_min_ref);
        vTaskDelay(pdMS_TO_TICKS(50));
    }

    TickType_t last_wake = xTaskGetTickCount();
    while (1) {
        // (3) AJUSTAR ESTO SI HACE FALTA
        vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(TUNIT_MS));

        uint64_t ts_tu = esp_timer_get_time();
        uint64_t now = ts_tu / 1000; 
        TRACE_INST(INST_SYS_P0_TU_WAKE, MODEL_SYS, ts_tu, 0,0,0);

        size_t heap_free = xPortGetFreeHeapSize();
        size_t heap_min  = xPortGetMinimumEverFreeHeapSize();
        TRACE_INST(INST_SYS_P0_MEM_BEFORE_READ, MODEL_SYS,ts_tu,
            heap_free, heap_min, 0);

        size_t cnt = read_events(events, MAX_EVENTS);
        TRACE_INST(INST_SYS_P1_READ_EVENTS, MODEL_SYS, ts_tu,
            cnt, 0, 0);
        if (cnt == 0) 
            continue;
        // !!!!!!!!!!!!!!! (1)
        //if (events_mgr_add(mgr, now, events, cnt) != 0) 
        if (events_mgr_add(mgr, ts_tu, events, cnt) != 0) 
            continue;
        heap_free = xPortGetFreeHeapSize();
        heap_min  = xPortGetMinimumEverFreeHeapSize();
        TRACE_INST(INST_SYS_P1_MEM_AFTER_READ, MODEL_SYS,ts_tu,
            heap_free, heap_min, 0);
        size_t stored_len;
        event_t* stored = events_mgr_get_at(mgr, ts_tu, &stored_len);
        size_t num_models;
        const model_t **activated = models_mgr_get_models_for_events(
            stored,
            stored_len,
            &num_models
        );
        free(stored);
        if (!activated) continue;
        schedule_result_t result = { .accepted = NULL, .rejected = NULL,
                             .accepted_count = 0, .rejected_count = 0 };
        TRACE_INST(INST_SYS_P1_SCHED_START,MODEL_SYS,ts_tu,
           0, 0, 0);
        // !!!!!!!!!!!!!!!! (2)
        scheduler_schedule(activated, num_models, 
            ts_tu, &result);
            //now, &result); 
        for (size_t i = 0; i < result.rejected_count; ++i) {
            const model_t *m = result.rejected[i];           
            int model_id = models_mgr_index_of(m);
            TRACE_FUNC_OFFLOAD(model_id, now); //ts_tu) (3)
        }
        TRACE_INST(INST_SYS_P1_SCHED_DECISION,MODEL_SYS,ts_tu,
           result.accepted_count,
           result.rejected_count,
           0);
        prediction_mgr_start(result.accepted, result.accepted_count);
        //free(activated);
        scheduler_free_result(&result);
        TRACE_INST(INST_SYS_P3_TU_END,MODEL_SYS,ts_tu,
           0, 0, 0);    
    }
    events_mgr_destroy(mgr);
    vTaskDelete(NULL);
}
