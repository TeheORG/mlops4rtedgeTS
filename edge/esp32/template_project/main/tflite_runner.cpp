#include "tflite_runner.h"
#include "model_resolver.h"
#include "models_mgr.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <new>

#include <tensorflow/lite/micro/micro_mutable_op_resolver.h>
#include <tensorflow/lite/micro/micro_interpreter.h>
#include <tensorflow/lite/schema/schema_generated.h>
#include "esp_timer.h"


// ============================================================
// ESTADO GLOBAL
// ============================================================

static uint8_t *s_arena = nullptr;
static size_t s_arena_size = 0;

static tflite::MicroMutableOpResolver<MODEL_OPERATOR_COUNT> *s_resolver = nullptr;

// Un único interpreter activo, reconstruido sobre almacenamiento estático.
// Evita new/delete sobre heap en cada inferencia.
alignas(tflite::MicroInterpreter)
static unsigned char s_interpreter_storage[sizeof(tflite::MicroInterpreter)];
static tflite::MicroInterpreter *s_interpreter = nullptr;


// ============================================================
// UTILIDADES INTERNAS
// ============================================================

static void destroy_interpreter() {
  if (s_interpreter) {
    s_interpreter->~MicroInterpreter();
    s_interpreter = nullptr;
  }
}

static bool is_supported_input_type(TfLiteType type) {
  return type == kTfLiteInt8 || type == kTfLiteUInt8;
}

static int clear_and_copy_input_tensor(TfLiteTensor *in,
                                       const event_t *input_data,
                                       size_t input_len) {
  if (!in || !input_data) return -1;
  if (input_len > (size_t)in->bytes) return -2;

  if (in->type == kTfLiteInt8) {
    memset(in->data.int8, 0, in->bytes);
    // Copia byte a byte para preservar el valor uint8 original de event_t.
    memcpy(in->data.int8, input_data, input_len * sizeof(event_t));
    return 0;
  }

  if (in->type == kTfLiteUInt8) {
    memset(in->data.uint8, 0, in->bytes);
    memcpy(in->data.uint8, input_data, input_len * sizeof(event_t));
    return 0;
  }

  return -3;
}

static size_t compute_max_arena_required(const model_t *models, size_t model_count) {
  size_t max_arena = 0;

  for (size_t i = 0; i < model_count; ++i) {
    if (models[i].arena_required > max_arena) {
      max_arena = models[i].arena_required;
    }
  }

  return max_arena;
}

static int validate_model_once(const model_t *model) {
  if (!model) return -1;
  if (!model->data) return -2;
  if (model->arena_required == 0) return -3;
  if (!s_arena || !s_resolver || s_arena_size == 0) return -4;

  const tflite::Model *flat = tflite::GetModel(model->data);
  if (!flat) return -5;

  if (flat->version() != TFLITE_SCHEMA_VERSION) return -6;

  memset(s_arena, 0, s_arena_size);

  tflite::MicroInterpreter *tmp =
      new (s_interpreter_storage) tflite::MicroInterpreter(
          flat,
          *s_resolver,
          s_arena,
          s_arena_size,
          nullptr);

  if (tmp->AllocateTensors() != kTfLiteOk) {
    tmp->~MicroInterpreter();
    return -7;
  }

  TfLiteTensor *in = tmp->input(0);
  if (!in) {
    tmp->~MicroInterpreter();
    return -8;
  }

  if (!is_supported_input_type(in->type)) {
    tmp->~MicroInterpreter();
    return -9;
  }

  if (in->bytes < 1) {
    tmp->~MicroInterpreter();
    return -10;
  }

  TfLiteTensor *out = tmp->output(0);
  if (!out) {
    tmp->~MicroInterpreter();
    return -11;
  }

  if (out->type != kTfLiteInt8) {
    tmp->~MicroInterpreter();
    return -12;
  }

  if (out->bytes < 1) {
    tmp->~MicroInterpreter();
    return -13;
  }

  tmp->~MicroInterpreter();
  return 0;
}


// ============================================================
// API AUXILIAR
// ============================================================

size_t count_models_that_fit() {
  if (g_models_count == 0) return 0;

  size_t max_arena = compute_max_arena_required(g_models, g_models_count);
  if (max_arena == 0) return 0;

  uint8_t *arena = (uint8_t *)malloc(max_arena);
  if (!arena) return 0;

  tflite::MicroMutableOpResolver<MODEL_OPERATOR_COUNT> resolver;
  SetupModelResolver(resolver);

  size_t fit = 0;

  for (size_t i = 0; i < g_models_count; ++i) {
    const model_t *model = &g_models[i];

    const tflite::Model *flat = tflite::GetModel(model->data);
    if (!flat) break;
    if (flat->version() != TFLITE_SCHEMA_VERSION) break;

    memset(arena, 0, max_arena);

    tflite::MicroInterpreter test_interp(
        flat,
        resolver,
        arena,
        max_arena,
        nullptr);

    if (test_interp.AllocateTensors() != kTfLiteOk) {
      break;
    }

    TfLiteTensor *in = test_interp.input(0);
    TfLiteTensor *out = test_interp.output(0);

    if (!in || !out) break;
    if (!is_supported_input_type(in->type)) break;
    if (out->type != kTfLiteInt8) break;
    if (in->bytes < 1 || out->bytes < 1) break;

    ++fit;
  }

  free(arena);
  return fit;
}


// ============================================================
// INIT
// ============================================================

void tflite_runner_init(const model_t *models, size_t model_count) {
  if (s_arena) return;

  if (!models || model_count == 0) {
    printf("[TFLM] ERROR: no models provided\n");
    abort();
  }

  s_arena_size = compute_max_arena_required(models, model_count);
  if (s_arena_size == 0) {
    printf("[TFLM] ERROR: max arena size is 0\n");
    abort();
  }

  s_arena = (uint8_t *)malloc(s_arena_size);
  if (!s_arena) {
    printf("[TFLM] ERROR: cannot allocate shared arena of %zu bytes\n", s_arena_size);
    abort();
  }

  s_resolver = new tflite::MicroMutableOpResolver<MODEL_OPERATOR_COUNT>();
  SetupModelResolver(*s_resolver);

  // Validación única al arrancar.
  // Si algo falla aquí, el modelo no era realmente ejecutable en edge.
  for (size_t i = 0; i < model_count; ++i) {
    int rc = validate_model_once(&models[i]);
    if (rc != 0) {
      printf("[TFLM] ERROR: model '%s' failed preflight validation (%d)\n",
             models[i].name ? models[i].name : "<unnamed>",
             rc);
      abort();
    }
  }

  memset(s_arena, 0, s_arena_size);
}


// ============================================================
// RUN
// ============================================================

int tflite_runner_run(const model_t *model,
                      const event_t *input_data,
                      size_t input_len,
                      int *result,
                      size_t output_len) {
  (void)output_len;

  if (!model) return -1;
  if (!input_data) return -2;
  if (!result) return -3;
  if (!s_arena || !s_resolver) return -4;
  if (s_arena_size == 0) return -5;

  destroy_interpreter();

  const tflite::Model *flat = tflite::GetModel(model->data);
  if (!flat) return -6;

  if (flat->version() != TFLITE_SCHEMA_VERSION) return -7;

  // Arena compartida reutilizada entre modelos.
  // Se limpia antes de cada reconstrucción del interpreter para evitar residuos.
  memset(s_arena, 0, s_arena_size);

  s_interpreter = new (s_interpreter_storage) tflite::MicroInterpreter(
      flat,
      *s_resolver,
      s_arena,
      s_arena_size,
      nullptr);

  if (s_interpreter->AllocateTensors() != kTfLiteOk) {
    destroy_interpreter();
    return -8;
  }

  TfLiteTensor *in = s_interpreter->input(0);
  if (!in) {
    destroy_interpreter();
    return -9;
  }

  if (!is_supported_input_type(in->type)) {
    destroy_interpreter();
    return -10;
  }

  if (in->bytes < 1) {
    destroy_interpreter();
    return -11;
  }

  // El input del scheduler debe encajar exactamente en el tensor.
  // Si no encaja, el error debe haberse detectado antes en el pipeline.
  if (input_len > (size_t)in->bytes) {
    destroy_interpreter();
    return -12;
  }

  int copy_rc = clear_and_copy_input_tensor(in, input_data, input_len);
  if (copy_rc != 0) {
    destroy_interpreter();
    return -17;
  }

  if (s_interpreter->Invoke() != kTfLiteOk) {
    destroy_interpreter();
    return -13;
  }

  TfLiteTensor *out = s_interpreter->output(0);
  if (!out) {
    destroy_interpreter();
    return -14;
  }

  if (out->type != kTfLiteInt8) {
    destroy_interpreter();
    return -15;
  }

  if (out->bytes < 1) {
    destroy_interpreter();
    return -16;
  }

  const int8_t quantized_value = out->data.int8[0];
  const float scale = out->params.scale;
  const int zero_point = out->params.zero_point;

  const float prob = (quantized_value - zero_point) * scale;
  *result = (prob > model->threshold) ? 1 : 0;

  return 0;
}