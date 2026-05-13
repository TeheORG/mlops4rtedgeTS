#ifndef TFLITE_RUNNER_H
#define TFLITE_RUNNER_H

#include <stddef.h>
#include <stdint.h>
#include "models_mgr.h"

#ifdef __cplusplus
extern "C" {
#endif

int tflite_runner_run(const model_t *model,
                      const event_t *input_data,
                      size_t input_len,
                      int *output_data,
                      size_t output_len);

void tflite_runner_init(const model_t *models, size_t model_count);

size_t count_models_that_fit();

#ifdef __cplusplus
}
#endif

#endif // TFLITE_RUNNER_H