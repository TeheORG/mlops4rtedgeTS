#include "scheduler.h"
#include "config.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

#define SCALE_US(x) ((x) * 1000ULL)

static uint64_t last_used_time = 0;

int scheduler_schedule(const model_t **models,
                       size_t num_models,
                       uint64_t event_time,
                       schedule_result_t *out) {
    if (!models || !out) return -1;
    static schedule_entry_t  acc_buf[MAX_MODELS];
    static const model_t    *rej_buf[MAX_MODELS];

    size_t a_cnt = 0;
    size_t r_cnt = 0;
    uint64_t slot_start = (event_time + SCALE_US(OW_MS) < last_used_time)
                        ? (last_used_time)
                        : (event_time + SCALE_US(OW_MS));
    uint64_t window_end = event_time + SCALE_US(OW_MS) + SCALE_US(MIT_MS);
    uint64_t current_time = slot_start; 
    for (size_t i = 0; i < num_models; ++i) {
        uint64_t deadline = current_time + SCALE_US(models[i]->exec_time);
        if ((event_time + SCALE_US(TUNIT_MS) + SCALE_US(OW_MS)) >= current_time &&
                (event_time + SCALE_US(TUNIT_MS) + SCALE_US(OW_MS)) < deadline) {
            deadline += 0; // IMPORTANT: No system task interference for now
            //printf("\nInterference: time (%llu), current_time(%llu) deadline(%llu)\n", (event_time + TUNIT_MS + OW_MS), current_time, deadline);
        }
        // ELIMINA CONTROL DE ADMISIÓN
        // window_end = deadline +1;
        if (deadline <= window_end) {
            acc_buf[a_cnt++] = (schedule_entry_t) {
                .model = (model_t *)models[i],
                .event_time = event_time,
                .start_time = current_time,
                .deadline = deadline
            };
            current_time = deadline;
        } else {
            rej_buf[r_cnt++] = (model_t *)models[i];
        }
    }
    if (a_cnt > 0) 
        last_used_time = current_time;
    out->accepted_count = a_cnt;
    out->rejected_count = r_cnt;
    out->accepted = acc_buf;
    out->rejected = rej_buf;
    return 0;
}

void scheduler_free_result(schedule_result_t *out) {
    if (!out) return;
    out->accepted = NULL;
    out->rejected = NULL;
    out->accepted_count = 0;
    out->rejected_count = 0;
}