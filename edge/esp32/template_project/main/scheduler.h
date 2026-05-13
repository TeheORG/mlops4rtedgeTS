#ifndef SCHEDULER_H
#define SCHEDULER_H

#include <stddef.h>
#include <stdint.h>
#include "models_mgr.h"

typedef struct {
    const model_t *model;
    uint64_t event_time;
    uint64_t start_time;
    uint64_t deadline;
} schedule_entry_t;

typedef struct {
    schedule_entry_t *accepted;
    size_t accepted_count;
    const model_t **rejected;
    size_t rejected_count;
} schedule_result_t;

int scheduler_schedule(const model_t **models,
                       size_t num_models,
                       uint64_t event_time,
                       schedule_result_t *out);

void scheduler_free_result(schedule_result_t *out);

#endif // SCHEDULER_H