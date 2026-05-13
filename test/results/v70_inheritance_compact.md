# Vista Compacta del Efecto de la Herencia

Filas base analizadas: 502

## Efecto por Fase de Origen

| fase_origen | total_filas | heredado_sin_cambios | redefinido_en_linaje | generado_en_hoja | solo_ancestro |
| --- | --- | --- | --- | --- | --- |
| f01_explore | 27 | 0 | 0 | 0 | 27 |
| f02_events | 36 | 9 | 0 | 0 | 27 |
| f03_windows | 45 | 27 | 9 | 0 | 9 |
| f04_targets | 36 | 18 | 0 | 0 | 18 |
| f05_modeling | 180 | 0 | 0 | 0 | 180 |
| f06_quant | 144 | 0 | 0 | 0 | 144 |
| f07_modval | 34 | 0 | 0 | 34 | 0 |

## Efecto por Parametro

| parameter | fase_origen_dominante | presente_en_variantes | presente_en_hoja | heredado_sin_cambios | redefinido_en_linaje | generado_en_hoja | solo_ancestro |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LT | f03_windows | 9/9 | 9 | 9 | 0 | 0 | 0 |
| MTI_MS | f07_modval | 9/9 | 9 | 0 | 0 | 9 | 0 |
| OW | f03_windows | 9/9 | 9 | 9 | 0 | 0 | 0 |
| PW | f03_windows | 9/9 | 9 | 9 | 0 | 0 | 0 |
| Tu | f02_events | 9/9 | 9 | 9 | 0 | 0 | 0 |
| automl.enabled | f05_modeling | 9/9 | 0 | 0 | 0 | 0 | 9 |
| automl.max_trials | f05_modeling | 9/9 | 0 | 0 | 0 | 0 | 9 |
| automl.seed | f05_modeling | 9/9 | 0 | 0 | 0 | 0 | 9 |
| bands | f02_events | 9/9 | 0 | 0 | 0 | 0 | 9 |
| cleaning | f01_explore | 9/9 | 0 | 0 | 0 | 0 | 9 |
| decision_threshold | f07_modval | 7/9 | 7 | 0 | 0 | 7 | 0 |
| deployment.memory_limit_bytes | f06_quant | 9/9 | 0 | 0 | 0 | 0 | 9 |
| deployment.require_int8 | f06_quant | 9/9 | 0 | 0 | 0 | 0 | 9 |
| deployment.runtime | f06_quant | 9/9 | 0 | 0 | 0 | 0 | 9 |
| deployment.runtime_version | f06_quant | 9/9 | 0 | 0 | 0 | 0 | 9 |
| deployment.target | f06_quant | 9/9 | 0 | 0 | 0 | 0 | 9 |
| eedu.layout | f06_quant | 9/9 | 0 | 0 | 0 | 0 | 9 |
| eedu.version | f06_quant | 9/9 | 0 | 0 | 0 | 0 | 9 |
| evaluation.split.test | f05_modeling | 9/9 | 0 | 0 | 0 | 0 | 9 |
| evaluation.split.train | f05_modeling | 9/9 | 0 | 0 | 0 | 0 | 9 |
| evaluation.split.val | f05_modeling | 9/9 | 0 | 0 | 0 | 0 | 9 |
| event_type_count | f04_targets | 9/9 | 9 | 9 | 0 | 0 | 0 |
| imbalance_max_majority_samples | f05_modeling | 9/9 | 0 | 0 | 0 | 0 | 9 |
| imbalance_strategy | f05_modeling | 9/9 | 0 | 0 | 0 | 0 | 9 |
| model_family | f05_modeling | 9/9 | 0 | 0 | 0 | 0 | 9 |
| nan_mode | f02_events | 9/9 | 0 | 0 | 0 | 0 | 9 |
| nan_values | f01_explore | 9/9 | 0 | 0 | 0 | 0 | 9 |
| parent_variant | f03_windows | 9/9 | 9 | 0 | 9 | 0 | 0 |
| platform | f07_modval | 9/9 | 9 | 0 | 0 | 9 | 0 |
| prediction_name | f04_targets | 9/9 | 9 | 9 | 0 | 0 | 0 |
| quantization.calibration_samples | f06_quant | 9/9 | 0 | 0 | 0 | 0 | 9 |
| quantization.keep_float_fallback | f06_quant | 9/9 | 0 | 0 | 0 | 0 | 9 |
| quantization.per_channel | f06_quant | 9/9 | 0 | 0 | 0 | 0 | 9 |
| quantization.representative_dataset | f06_quant | 9/9 | 0 | 0 | 0 | 0 | 9 |
| quantization.symmetric_int8 | f06_quant | 9/9 | 0 | 0 | 0 | 0 | 9 |
| quantization.tflite_optimization | f06_quant | 9/9 | 0 | 0 | 0 | 0 | 9 |
| raw_path | f01_explore | 9/9 | 0 | 0 | 0 | 0 | 9 |
| search_space.cnn1d.embed_dim | f05_modeling | 9/9 | 0 | 0 | 0 | 0 | 9 |
| search_space.cnn1d.filters | f05_modeling | 9/9 | 0 | 0 | 0 | 0 | 9 |
| search_space.cnn1d.kernel_size | f05_modeling | 9/9 | 0 | 0 | 0 | 0 | 9 |
| search_space.common.batch_size | f05_modeling | 9/9 | 0 | 0 | 0 | 0 | 9 |
| search_space.common.dropout | f05_modeling | 9/9 | 0 | 0 | 0 | 0 | 9 |
| search_space.common.learning_rate | f05_modeling | 9/9 | 0 | 0 | 0 | 0 | 9 |
| search_space.common.n_layers | f05_modeling | 9/9 | 0 | 0 | 0 | 0 | 9 |
| search_space.common.units | f05_modeling | 9/9 | 0 | 0 | 0 | 0 | 9 |
| search_space.sequence_embedding.embed_dim | f05_modeling | 9/9 | 0 | 0 | 0 | 0 | 9 |
| strategy | f02_events | 9/9 | 0 | 0 | 0 | 0 | 9 |
| target_event_types | f04_targets | 9/9 | 0 | 0 | 0 | 0 | 9 |
| target_operator | f04_targets | 9/9 | 0 | 0 | 0 | 0 | 9 |
| thresholding.grid_points | f06_quant | 9/9 | 0 | 0 | 0 | 0 | 9 |
| thresholding.maximize_metric | f06_quant | 9/9 | 0 | 0 | 0 | 0 | 9 |
| thresholding.strategy | f06_quant | 9/9 | 0 | 0 | 0 | 0 | 9 |
| time_scale_factor | f07_modval | 9/9 | 9 | 0 | 0 | 9 | 0 |
| training.epochs | f05_modeling | 9/9 | 0 | 0 | 0 | 0 | 9 |
| training.max_samples | f05_modeling | 9/9 | 0 | 0 | 0 | 0 | 9 |
| window_strategy | f03_windows | 9/9 | 0 | 0 | 0 | 0 | 9 |

## Figura Compacta

```mermaid
pie title Distribucion global del estado de herencia
    "heredado_sin_cambios" : 54
    "generado_en_hoja" : 34
    "solo_ancestro" : 405
    "redefinido_en_linaje" : 9
```
