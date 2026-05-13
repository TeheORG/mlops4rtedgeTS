#ifndef MODELS_MGR_H
#define MODELS_MGR_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

#include "config.h"

typedef struct {
    const char *name;            
    const unsigned char *data;   
    size_t size;                 
    uint64_t exec_time;          
    float threshold;
    size_t arena_required;
    const event_t *triggers;
    size_t trigger_count;
    bool trigger_all;
} model_t;

extern const model_t  g_models[];
extern const size_t   g_models_count;

// required to init scheduler static memory
#define MAX_MODELS 30

void models_mgr_init(void);

size_t models_mgr_get_count(void);

const model_t *models_mgr_get_all(size_t *out_count);

const model_t **models_mgr_get_models_for_events(event_t *events,
                                           size_t num_events,
                                           size_t *out_num_models);

int models_mgr_run_model(model_t *model,
                         const void *input,
                         void *output);

int models_mgr_index_of(const model_t *m);

#endif // MODELS_MGR_H