#include "models_mgr.h"
#include "models_data.h"  
#include "esp_system.h"
#include <inttypes.h>
#include <stdlib.h>
#include <string.h>

void models_mgr_init(void) {
    for (size_t i = 0; i < g_models_count; ++i) {
        printf("0,MODEL_MEM,%s,%zu,%" PRIu64 ",%f,%" PRIu64 ",%d,%p\n",
           g_models[i].name,
           g_models[i].size,
           g_models[i].exec_time,
           g_models[i].threshold,
           (uint64_t)g_models[i].trigger_count,
           g_models[i].trigger_all ? 1 : 0,
           (void *)g_models[i].triggers
    );
    }
}

size_t models_mgr_get_count(void) {
    return g_models_count;
}

const model_t *models_mgr_get_all(size_t *out_count) {
    if (out_count) {
        *out_count = g_models_count;
    }
    return g_models;
}

// all models activation
const model_t **models_mgr_get_models_for_events(event_t *events,
                                           size_t num_events,
                                           size_t *out_num) {
    static const model_t *activated[ MAX_MODELS ];  // ajusta MAX_MODELS si hace falta
    size_t cnt = 0;
    event_t first = 0;
    if (num_events > 0) {
        first = events[0];
    }
    for (size_t i = 0; i < g_models_count; ++i) {
        const model_t *m = &g_models[i];
        if (m->trigger_all) {
            activated[cnt++] = m;
            continue;
        }
        if (num_events == 0) {
            continue;
        }
        for (size_t j = 0; j < m->trigger_count; ++j) {
            if (first == m->triggers[j]) {
                activated[cnt++] = m;
                break;
            }
        }
    }
    *out_num = cnt;
    return activated;                                                
/*    size_t activated_count = g_models_count;
    if (out_num_models) {
        *out_num_models = activated_count;
    }
    const model_t **activated = malloc(sizeof(*activated) * activated_count);
    if (!activated) {
        if (out_num_models) *out_num_models = 0;
        return NULL;
    }
    for (size_t i = 0; i < activated_count; ++i) {
        activated[i] = &g_models[i];
    }
    return activated;
*/
}

int models_mgr_run_model(model_t *model,
                         const void *input,
                         void *output) {
    (void)model; (void)input; (void)output;
    return 0;
}

int models_mgr_index_of(const model_t *m) {
    for (size_t i = 0; i < g_models_count; ++i) {
        if (m == &g_models[i]) {
            return (int)i;
        }
    }
    return -1;
}
