# Trazabilidad de parámetros por linaje

Cada fila representa un parámetro observado en el linaje de una variante hoja v70?.
Se indica dónde aparece por primera vez, su valor original, su valor en la hoja si sigue presente y la traza fase a fase.

Filas generadas: 502

| variante hoja | parámetro | fase origen | variante origen | valor origen | valor en hoja | herencia | f01 | f02 | f03 | f04 | f05 | f06 | f07 | historial |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v700 | LT | f03_windows | v300 | 1 | 1 | heredado_sin_cambios; cambios_en=- | - | - | v300=1 | v400=1 | v500=1 | v600=1 | v700=1 | f03_windows:v300=1 -> f04_targets:v400=1 -> f05_modeling:v500=1 -> f06_quant:v600=1 -> f07_modval:v700=1 |
| v700 | MTI_MS | f07_modval | v700 | 100 | 100 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v700=100 | f07_modval:v700=100 |
| v700 | OW | f03_windows | v300 | 6 | 6 | heredado_sin_cambios; cambios_en=- | - | - | v300=6 | v400=6 | v500=6 | v600=6 | v700=6 | f03_windows:v300=6 -> f04_targets:v400=6 -> f05_modeling:v500=6 -> f06_quant:v600=6 -> f07_modval:v700=6 |
| v700 | PW | f03_windows | v300 | 1 | 1 | heredado_sin_cambios; cambios_en=- | - | - | v300=1 | v400=1 | v500=1 | v600=1 | v700=1 | f03_windows:v300=1 -> f04_targets:v400=1 -> f05_modeling:v500=1 -> f06_quant:v600=1 -> f07_modval:v700=1 |
| v700 | Tu | f02_events | v200 | 10 | 10 | heredado_sin_cambios; cambios_en=- | - | v200=10 | v300=10 | v400=10 | v500=10 | v600=10 | v700=10 | f02_events:v200=10 -> f03_windows:v300=10 -> f04_targets:v400=10 -> f05_modeling:v500=10 -> f06_quant:v600=10 -> f07_modval:v700=10 |
| v700 | automl.enabled | f05_modeling | v500 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | v500=true | - | - | f05_modeling:v500=true |
| v700 | automl.max_trials | f05_modeling | v500 | 5 | - | solo_ancestro; cambios_en=- | - | - | - | - | v500=5 | - | - | f05_modeling:v500=5 |
| v700 | automl.seed | f05_modeling | v500 | 42 | - | solo_ancestro; cambios_en=- | - | - | - | - | v500=42 | - | - | f05_modeling:v500=42 |
| v700 | bands | f02_events | v200 | [40, 60, 80] | - | solo_ancestro; cambios_en=- | - | v200=[40, 60, 80] | - | - | - | - | - | f02_events:v200=[40, 60, 80] |
| v700 | cleaning | f01_explore | v100 | basic | - | solo_ancestro; cambios_en=- | v100=basic | - | - | - | - | - | - | f01_explore:v100=basic |
| v700 | decision_threshold | f07_modval | v700 | 0.26571032404899597 | 0.26571032404899597 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v700=0.26571032404899597 | f07_modval:v700=0.26571032404899597 |
| v700 | deployment.memory_limit_bytes | f06_quant | v600 | 327680 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v600=327680 | - | f06_quant:v600=327680 |
| v700 | deployment.require_int8 | f06_quant | v600 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v600=true | - | f06_quant:v600=true |
| v700 | deployment.runtime | f06_quant | v600 | esp-tflite-micro | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v600=esp-tflite-micro | - | f06_quant:v600=esp-tflite-micro |
| v700 | deployment.runtime_version | f06_quant | v600 | 1.3.3 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v600=1.3.3 | - | f06_quant:v600=1.3.3 |
| v700 | deployment.target | f06_quant | v600 | esp32 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v600=esp32 | - | f06_quant:v600=esp32 |
| v700 | eedu.layout | f06_quant | v600 | default | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v600=default | - | f06_quant:v600=default |
| v700 | eedu.version | f06_quant | v600 | 1.0 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v600=1.0 | - | f06_quant:v600=1.0 |
| v700 | evaluation.split.test | f05_modeling | v500 | 0.15 | - | solo_ancestro; cambios_en=- | - | - | - | - | v500=0.15 | - | - | f05_modeling:v500=0.15 |
| v700 | evaluation.split.train | f05_modeling | v500 | 0.7 | - | solo_ancestro; cambios_en=- | - | - | - | - | v500=0.7 | - | - | f05_modeling:v500=0.7 |
| v700 | evaluation.split.val | f05_modeling | v500 | 0.15 | - | solo_ancestro; cambios_en=- | - | - | - | - | v500=0.15 | - | - | f05_modeling:v500=0.15 |
| v700 | event_type_count | f04_targets | v400 | 221 | 221 | heredado_sin_cambios; cambios_en=- | - | - | - | v400=221 | v500=221 | v600=221 | v700=221 | f04_targets:v400=221 -> f05_modeling:v500=221 -> f06_quant:v600=221 -> f07_modval:v700=221 |
| v700 | imbalance_max_majority_samples | f05_modeling | v500 | 20000 | - | solo_ancestro; cambios_en=- | - | - | - | - | v500=20000 | - | - | f05_modeling:v500=20000 |
| v700 | imbalance_strategy | f05_modeling | v500 | rare_events | - | solo_ancestro; cambios_en=- | - | - | - | - | v500=rare_events | - | - | f05_modeling:v500=rare_events |
| v700 | model_family | f05_modeling | v500 | cnn1d | - | solo_ancestro; cambios_en=- | - | - | - | - | v500=cnn1d | - | - | f05_modeling:v500=cnn1d |
| v700 | nan_mode | f02_events | v200 | keep | - | solo_ancestro; cambios_en=f03_windows:v300 | - | v200=keep | v300=discard | - | - | - | - | f02_events:v200=keep -> f03_windows:v300=discard |
| v700 | nan_values | f01_explore | v100 | [-999999] | - | solo_ancestro; cambios_en=- | v100=[-999999] | - | - | - | - | - | - | f01_explore:v100=[-999999] |
| v700 | parent_variant | f03_windows | v300 | v200 | v600 | redefinido_en_linaje; cambios_en=f04_targets:v400, f05_modeling:v500, f06_quant:v600, f07_modval:v700 | - | - | v300=v200 | v400=v300 | v500=v400 | v600=v500 | v700=v600 | f03_windows:v300=v200 -> f04_targets:v400=v300 -> f05_modeling:v500=v400 -> f06_quant:v600=v500 -> f07_modval:v700=v600 |
| v700 | platform | f07_modval | v700 | esp32 | esp32 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v700=esp32 | f07_modval:v700=esp32 |
| v700 | prediction_name | f04_targets | v400 | Battery_Active_Power_any-to-80_100 | Battery_Active_Power_any-to-80_100 | heredado_sin_cambios; cambios_en=- | - | - | - | v400=Battery_Active_Power_any-to-80_100 | v500=Battery_Active_Power_any-to-80_100 | v600=Battery_Active_Power_any-to-80_100 | v700=Battery_Active_Power_any-to-80_100 | f04_targets:v400=Battery_Active_Power_any-to-80_100 -> f05_modeling:v500=Battery_Active_Power_any-to-80_100 -> f06_quant:v600=Battery_Active_Power_any-to-80_100 -> f07_modval:v700=Battery_Active_Power_any-to-80_100 |
| v700 | quantization.calibration_samples | f06_quant | v600 | 512 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v600=512 | - | f06_quant:v600=512 |
| v700 | quantization.keep_float_fallback | f06_quant | v600 | false | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v600=false | - | f06_quant:v600=false |
| v700 | quantization.per_channel | f06_quant | v600 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v600=true | - | f06_quant:v600=true |
| v700 | quantization.representative_dataset | f06_quant | v600 | val | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v600=val | - | f06_quant:v600=val |
| v700 | quantization.symmetric_int8 | f06_quant | v600 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v600=true | - | f06_quant:v600=true |
| v700 | quantization.tflite_optimization | f06_quant | v600 | DEFAULT | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v600=DEFAULT | - | f06_quant:v600=DEFAULT |
| v700 | raw_path | f01_explore | v100 | data/raw.csv | - | solo_ancestro; cambios_en=- | v100=data/raw.csv | - | - | - | - | - | - | f01_explore:v100=data/raw.csv |
| v700 | search_space.cnn1d.embed_dim | f05_modeling | v500 | [64] | - | solo_ancestro; cambios_en=- | - | - | - | - | v500=[64] | - | - | f05_modeling:v500=[64] |
| v700 | search_space.cnn1d.filters | f05_modeling | v500 | [64, 128] | - | solo_ancestro; cambios_en=- | - | - | - | - | v500=[64, 128] | - | - | f05_modeling:v500=[64, 128] |
| v700 | search_space.cnn1d.kernel_size | f05_modeling | v500 | [3, 5] | - | solo_ancestro; cambios_en=- | - | - | - | - | v500=[3, 5] | - | - | f05_modeling:v500=[3, 5] |
| v700 | search_space.common.batch_size | f05_modeling | v500 | [128, 256] | - | solo_ancestro; cambios_en=- | - | - | - | - | v500=[128, 256] | - | - | f05_modeling:v500=[128, 256] |
| v700 | search_space.common.dropout | f05_modeling | v500 | [0.0, 0.2] | - | solo_ancestro; cambios_en=- | - | - | - | - | v500=[0.0, 0.2] | - | - | f05_modeling:v500=[0.0, 0.2] |
| v700 | search_space.common.learning_rate | f05_modeling | v500 | [0.001, 0.0005] | - | solo_ancestro; cambios_en=- | - | - | - | - | v500=[0.001, 0.0005] | - | - | f05_modeling:v500=[0.001, 0.0005] |
| v700 | search_space.common.n_layers | f05_modeling | v500 | [1, 2] | - | solo_ancestro; cambios_en=- | - | - | - | - | v500=[1, 2] | - | - | f05_modeling:v500=[1, 2] |
| v700 | search_space.common.units | f05_modeling | v500 | [64, 128] | - | solo_ancestro; cambios_en=- | - | - | - | - | v500=[64, 128] | - | - | f05_modeling:v500=[64, 128] |
| v700 | search_space.sequence_embedding.embed_dim | f05_modeling | v500 | [64, 128] | - | solo_ancestro; cambios_en=- | - | - | - | - | v500=[64, 128] | - | - | f05_modeling:v500=[64, 128] |
| v700 | strategy | f02_events | v200 | transitions | - | solo_ancestro; cambios_en=- | - | v200=transitions | - | - | - | - | - | f02_events:v200=transitions |
| v700 | target_event_types | f04_targets | v400 | ["Battery_Active_Power_0_40-to-80_100", "Battery_Active_Power_40_60-to-80_100", "Battery_Active_Power_60_80-to-80_100"] | - | solo_ancestro; cambios_en=- | - | - | - | v400=["Battery_Active_Power_0_40-to-80_100", "Battery_Active_Power_40_60-to-80_100", "Battery_Active_Power_60_80-to-80_100"] | - | - | - | f04_targets:v400=["Battery_Active_Power_0_40-to-80_100", "Battery_Active_Power_40_60-to-80_100", "Battery_Active_Power_60_80-to-80_100"] |
| v700 | target_operator | f04_targets | v400 | OR | - | solo_ancestro; cambios_en=- | - | - | - | v400=OR | - | - | - | f04_targets:v400=OR |
| v700 | thresholding.grid_points | f06_quant | v600 | 101 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v600=101 | - | f06_quant:v600=101 |
| v700 | thresholding.maximize_metric | f06_quant | v600 | recall | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v600=recall | - | f06_quant:v600=recall |
| v700 | thresholding.strategy | f06_quant | v600 | recalibrate_on_quantized | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v600=recalibrate_on_quantized | - | f06_quant:v600=recalibrate_on_quantized |
| v700 | time_scale_factor | f07_modval | v700 | 0.01 | 0.01 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v700=0.01 | f07_modval:v700=0.01 |
| v700 | training.epochs | f05_modeling | v500 | 20 | - | solo_ancestro; cambios_en=- | - | - | - | - | v500=20 | - | - | f05_modeling:v500=20 |
| v700 | training.max_samples | f05_modeling | v500 | - | - | solo_ancestro; cambios_en=- | - | - | - | - | v500=- | - | - | f05_modeling:v500=- |
| v700 | window_strategy | f03_windows | v300 | synchro | - | solo_ancestro; cambios_en=- | - | - | v300=synchro | - | - | - | - | f03_windows:v300=synchro |
| v701 | LT | f03_windows | v300 | 1 | 1 | heredado_sin_cambios; cambios_en=- | - | - | v300=1 | v401=1 | v501=1 | v601=1 | v701=1 | f03_windows:v300=1 -> f04_targets:v401=1 -> f05_modeling:v501=1 -> f06_quant:v601=1 -> f07_modval:v701=1 |
| v701 | MTI_MS | f07_modval | v701 | 100 | 100 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v701=100 | f07_modval:v701=100 |
| v701 | OW | f03_windows | v300 | 6 | 6 | heredado_sin_cambios; cambios_en=- | - | - | v300=6 | v401=6 | v501=6 | v601=6 | v701=6 | f03_windows:v300=6 -> f04_targets:v401=6 -> f05_modeling:v501=6 -> f06_quant:v601=6 -> f07_modval:v701=6 |
| v701 | PW | f03_windows | v300 | 1 | 1 | heredado_sin_cambios; cambios_en=- | - | - | v300=1 | v401=1 | v501=1 | v601=1 | v701=1 | f03_windows:v300=1 -> f04_targets:v401=1 -> f05_modeling:v501=1 -> f06_quant:v601=1 -> f07_modval:v701=1 |
| v701 | Tu | f02_events | v200 | 10 | 10 | heredado_sin_cambios; cambios_en=- | - | v200=10 | v300=10 | v401=10 | v501=10 | v601=10 | v701=10 | f02_events:v200=10 -> f03_windows:v300=10 -> f04_targets:v401=10 -> f05_modeling:v501=10 -> f06_quant:v601=10 -> f07_modval:v701=10 |
| v701 | automl.enabled | f05_modeling | v501 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | v501=true | - | - | f05_modeling:v501=true |
| v701 | automl.max_trials | f05_modeling | v501 | 5 | - | solo_ancestro; cambios_en=- | - | - | - | - | v501=5 | - | - | f05_modeling:v501=5 |
| v701 | automl.seed | f05_modeling | v501 | 42 | - | solo_ancestro; cambios_en=- | - | - | - | - | v501=42 | - | - | f05_modeling:v501=42 |
| v701 | bands | f02_events | v200 | [40, 60, 80] | - | solo_ancestro; cambios_en=- | - | v200=[40, 60, 80] | - | - | - | - | - | f02_events:v200=[40, 60, 80] |
| v701 | cleaning | f01_explore | v100 | basic | - | solo_ancestro; cambios_en=- | v100=basic | - | - | - | - | - | - | f01_explore:v100=basic |
| v701 | decision_threshold | f07_modval | v701 | 0.5296909213066101 | 0.5296909213066101 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v701=0.5296909213066101 | f07_modval:v701=0.5296909213066101 |
| v701 | deployment.memory_limit_bytes | f06_quant | v601 | 327680 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v601=327680 | - | f06_quant:v601=327680 |
| v701 | deployment.require_int8 | f06_quant | v601 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v601=true | - | f06_quant:v601=true |
| v701 | deployment.runtime | f06_quant | v601 | esp-tflite-micro | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v601=esp-tflite-micro | - | f06_quant:v601=esp-tflite-micro |
| v701 | deployment.runtime_version | f06_quant | v601 | 1.3.3 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v601=1.3.3 | - | f06_quant:v601=1.3.3 |
| v701 | deployment.target | f06_quant | v601 | esp32 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v601=esp32 | - | f06_quant:v601=esp32 |
| v701 | eedu.layout | f06_quant | v601 | default | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v601=default | - | f06_quant:v601=default |
| v701 | eedu.version | f06_quant | v601 | 1.0 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v601=1.0 | - | f06_quant:v601=1.0 |
| v701 | evaluation.split.test | f05_modeling | v501 | 0.15 | - | solo_ancestro; cambios_en=- | - | - | - | - | v501=0.15 | - | - | f05_modeling:v501=0.15 |
| v701 | evaluation.split.train | f05_modeling | v501 | 0.7 | - | solo_ancestro; cambios_en=- | - | - | - | - | v501=0.7 | - | - | f05_modeling:v501=0.7 |
| v701 | evaluation.split.val | f05_modeling | v501 | 0.15 | - | solo_ancestro; cambios_en=- | - | - | - | - | v501=0.15 | - | - | f05_modeling:v501=0.15 |
| v701 | event_type_count | f04_targets | v401 | 221 | 221 | heredado_sin_cambios; cambios_en=- | - | - | - | v401=221 | v501=221 | v601=221 | v701=221 | f04_targets:v401=221 -> f05_modeling:v501=221 -> f06_quant:v601=221 -> f07_modval:v701=221 |
| v701 | imbalance_max_majority_samples | f05_modeling | v501 | 20000 | - | solo_ancestro; cambios_en=- | - | - | - | - | v501=20000 | - | - | f05_modeling:v501=20000 |
| v701 | imbalance_strategy | f05_modeling | v501 | rare_events | - | solo_ancestro; cambios_en=- | - | - | - | - | v501=rare_events | - | - | f05_modeling:v501=rare_events |
| v701 | model_family | f05_modeling | v501 | cnn1d | - | solo_ancestro; cambios_en=- | - | - | - | - | v501=cnn1d | - | - | f05_modeling:v501=cnn1d |
| v701 | nan_mode | f02_events | v200 | keep | - | solo_ancestro; cambios_en=f03_windows:v300 | - | v200=keep | v300=discard | - | - | - | - | f02_events:v200=keep -> f03_windows:v300=discard |
| v701 | nan_values | f01_explore | v100 | [-999999] | - | solo_ancestro; cambios_en=- | v100=[-999999] | - | - | - | - | - | - | f01_explore:v100=[-999999] |
| v701 | parent_variant | f03_windows | v300 | v200 | v601 | redefinido_en_linaje; cambios_en=f04_targets:v401, f05_modeling:v501, f06_quant:v601, f07_modval:v701 | - | - | v300=v200 | v401=v300 | v501=v401 | v601=v501 | v701=v601 | f03_windows:v300=v200 -> f04_targets:v401=v300 -> f05_modeling:v501=v401 -> f06_quant:v601=v501 -> f07_modval:v701=v601 |
| v701 | platform | f07_modval | v701 | esp32 | esp32 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v701=esp32 | f07_modval:v701=esp32 |
| v701 | prediction_name | f04_targets | v401 | Battery_Active_Power_Set_Response_any-to-80_100 | Battery_Active_Power_Set_Response_any-to-80_100 | heredado_sin_cambios; cambios_en=- | - | - | - | v401=Battery_Active_Power_Set_Response_any-to-80_100 | v501=Battery_Active_Power_Set_Response_any-to-80_100 | v601=Battery_Active_Power_Set_Response_any-to-80_100 | v701=Battery_Active_Power_Set_Response_any-to-80_100 | f04_targets:v401=Battery_Active_Power_Set_Response_any-to-80_100 -> f05_modeling:v501=Battery_Active_Power_Set_Response_any-to-80_100 -> f06_quant:v601=Battery_Active_Power_Set_Response_any-to-80_100 -> f07_modval:v701=Battery_Active_Power_Set_Response_any-to-80_100 |
| v701 | quantization.calibration_samples | f06_quant | v601 | 512 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v601=512 | - | f06_quant:v601=512 |
| v701 | quantization.keep_float_fallback | f06_quant | v601 | false | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v601=false | - | f06_quant:v601=false |
| v701 | quantization.per_channel | f06_quant | v601 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v601=true | - | f06_quant:v601=true |
| v701 | quantization.representative_dataset | f06_quant | v601 | val | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v601=val | - | f06_quant:v601=val |
| v701 | quantization.symmetric_int8 | f06_quant | v601 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v601=true | - | f06_quant:v601=true |
| v701 | quantization.tflite_optimization | f06_quant | v601 | DEFAULT | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v601=DEFAULT | - | f06_quant:v601=DEFAULT |
| v701 | raw_path | f01_explore | v100 | data/raw.csv | - | solo_ancestro; cambios_en=- | v100=data/raw.csv | - | - | - | - | - | - | f01_explore:v100=data/raw.csv |
| v701 | search_space.cnn1d.embed_dim | f05_modeling | v501 | [64] | - | solo_ancestro; cambios_en=- | - | - | - | - | v501=[64] | - | - | f05_modeling:v501=[64] |
| v701 | search_space.cnn1d.filters | f05_modeling | v501 | [64, 128] | - | solo_ancestro; cambios_en=- | - | - | - | - | v501=[64, 128] | - | - | f05_modeling:v501=[64, 128] |
| v701 | search_space.cnn1d.kernel_size | f05_modeling | v501 | [3, 5] | - | solo_ancestro; cambios_en=- | - | - | - | - | v501=[3, 5] | - | - | f05_modeling:v501=[3, 5] |
| v701 | search_space.common.batch_size | f05_modeling | v501 | [128, 256] | - | solo_ancestro; cambios_en=- | - | - | - | - | v501=[128, 256] | - | - | f05_modeling:v501=[128, 256] |
| v701 | search_space.common.dropout | f05_modeling | v501 | [0.0, 0.2] | - | solo_ancestro; cambios_en=- | - | - | - | - | v501=[0.0, 0.2] | - | - | f05_modeling:v501=[0.0, 0.2] |
| v701 | search_space.common.learning_rate | f05_modeling | v501 | [0.001, 0.0005] | - | solo_ancestro; cambios_en=- | - | - | - | - | v501=[0.001, 0.0005] | - | - | f05_modeling:v501=[0.001, 0.0005] |
| v701 | search_space.common.n_layers | f05_modeling | v501 | [1, 2] | - | solo_ancestro; cambios_en=- | - | - | - | - | v501=[1, 2] | - | - | f05_modeling:v501=[1, 2] |
| v701 | search_space.common.units | f05_modeling | v501 | [64, 128] | - | solo_ancestro; cambios_en=- | - | - | - | - | v501=[64, 128] | - | - | f05_modeling:v501=[64, 128] |
| v701 | search_space.sequence_embedding.embed_dim | f05_modeling | v501 | [64, 128] | - | solo_ancestro; cambios_en=- | - | - | - | - | v501=[64, 128] | - | - | f05_modeling:v501=[64, 128] |
| v701 | strategy | f02_events | v200 | transitions | - | solo_ancestro; cambios_en=- | - | v200=transitions | - | - | - | - | - | f02_events:v200=transitions |
| v701 | target_event_types | f04_targets | v401 | ["Battery_Active_Power_Set_Response_0_40-to-80_100", "Battery_Active_Power_Set_Response_40_60-to-80_100", "Battery_Active_Power_Set_Response_60_80-to-80_100"] | - | solo_ancestro; cambios_en=- | - | - | - | v401=["Battery_Active_Power_Set_Response_0_40-to-80_100", "Battery_Active_Power_Set_Response_40_60-to-80_100", "Battery_Active_Power_Set_Response_60_80-to-80_100"] | - | - | - | f04_targets:v401=["Battery_Active_Power_Set_Response_0_40-to-80_100", "Battery_Active_Power_Set_Response_40_60-to-80_100", "Battery_Active_Power_Set_Response_60_80-to-80_100"] |
| v701 | target_operator | f04_targets | v401 | OR | - | solo_ancestro; cambios_en=- | - | - | - | v401=OR | - | - | - | f04_targets:v401=OR |
| v701 | thresholding.grid_points | f06_quant | v601 | 101 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v601=101 | - | f06_quant:v601=101 |
| v701 | thresholding.maximize_metric | f06_quant | v601 | recall | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v601=recall | - | f06_quant:v601=recall |
| v701 | thresholding.strategy | f06_quant | v601 | recalibrate_on_quantized | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v601=recalibrate_on_quantized | - | f06_quant:v601=recalibrate_on_quantized |
| v701 | time_scale_factor | f07_modval | v701 | 0.01 | 0.01 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v701=0.01 | f07_modval:v701=0.01 |
| v701 | training.epochs | f05_modeling | v501 | 20 | - | solo_ancestro; cambios_en=- | - | - | - | - | v501=20 | - | - | f05_modeling:v501=20 |
| v701 | training.max_samples | f05_modeling | v501 | - | - | solo_ancestro; cambios_en=- | - | - | - | - | v501=- | - | - | f05_modeling:v501=- |
| v701 | window_strategy | f03_windows | v300 | synchro | - | solo_ancestro; cambios_en=- | - | - | v300=synchro | - | - | - | - | f03_windows:v300=synchro |
| v702 | LT | f03_windows | v300 | 1 | 1 | heredado_sin_cambios; cambios_en=- | - | - | v300=1 | v402=1 | v502=1 | v602=1 | v702=1 | f03_windows:v300=1 -> f04_targets:v402=1 -> f05_modeling:v502=1 -> f06_quant:v602=1 -> f07_modval:v702=1 |
| v702 | MTI_MS | f07_modval | v702 | 100 | 100 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v702=100 | f07_modval:v702=100 |
| v702 | OW | f03_windows | v300 | 6 | 6 | heredado_sin_cambios; cambios_en=- | - | - | v300=6 | v402=6 | v502=6 | v602=6 | v702=6 | f03_windows:v300=6 -> f04_targets:v402=6 -> f05_modeling:v502=6 -> f06_quant:v602=6 -> f07_modval:v702=6 |
| v702 | PW | f03_windows | v300 | 1 | 1 | heredado_sin_cambios; cambios_en=- | - | - | v300=1 | v402=1 | v502=1 | v602=1 | v702=1 | f03_windows:v300=1 -> f04_targets:v402=1 -> f05_modeling:v502=1 -> f06_quant:v602=1 -> f07_modval:v702=1 |
| v702 | Tu | f02_events | v200 | 10 | 10 | heredado_sin_cambios; cambios_en=- | - | v200=10 | v300=10 | v402=10 | v502=10 | v602=10 | v702=10 | f02_events:v200=10 -> f03_windows:v300=10 -> f04_targets:v402=10 -> f05_modeling:v502=10 -> f06_quant:v602=10 -> f07_modval:v702=10 |
| v702 | automl.enabled | f05_modeling | v502 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | v502=true | - | - | f05_modeling:v502=true |
| v702 | automl.max_trials | f05_modeling | v502 | 5 | - | solo_ancestro; cambios_en=- | - | - | - | - | v502=5 | - | - | f05_modeling:v502=5 |
| v702 | automl.seed | f05_modeling | v502 | 42 | - | solo_ancestro; cambios_en=- | - | - | - | - | v502=42 | - | - | f05_modeling:v502=42 |
| v702 | bands | f02_events | v200 | [40, 60, 80] | - | solo_ancestro; cambios_en=- | - | v200=[40, 60, 80] | - | - | - | - | - | f02_events:v200=[40, 60, 80] |
| v702 | cleaning | f01_explore | v100 | basic | - | solo_ancestro; cambios_en=- | v100=basic | - | - | - | - | - | - | f01_explore:v100=basic |
| v702 | decision_threshold | f07_modval | v702 | 0.36092594265937805 | 0.36092594265937805 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v702=0.36092594265937805 | f07_modval:v702=0.36092594265937805 |
| v702 | deployment.memory_limit_bytes | f06_quant | v602 | 327680 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v602=327680 | - | f06_quant:v602=327680 |
| v702 | deployment.require_int8 | f06_quant | v602 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v602=true | - | f06_quant:v602=true |
| v702 | deployment.runtime | f06_quant | v602 | esp-tflite-micro | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v602=esp-tflite-micro | - | f06_quant:v602=esp-tflite-micro |
| v702 | deployment.runtime_version | f06_quant | v602 | 1.3.3 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v602=1.3.3 | - | f06_quant:v602=1.3.3 |
| v702 | deployment.target | f06_quant | v602 | esp32 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v602=esp32 | - | f06_quant:v602=esp32 |
| v702 | eedu.layout | f06_quant | v602 | default | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v602=default | - | f06_quant:v602=default |
| v702 | eedu.version | f06_quant | v602 | 1.0 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v602=1.0 | - | f06_quant:v602=1.0 |
| v702 | evaluation.split.test | f05_modeling | v502 | 0.15 | - | solo_ancestro; cambios_en=- | - | - | - | - | v502=0.15 | - | - | f05_modeling:v502=0.15 |
| v702 | evaluation.split.train | f05_modeling | v502 | 0.7 | - | solo_ancestro; cambios_en=- | - | - | - | - | v502=0.7 | - | - | f05_modeling:v502=0.7 |
| v702 | evaluation.split.val | f05_modeling | v502 | 0.15 | - | solo_ancestro; cambios_en=- | - | - | - | - | v502=0.15 | - | - | f05_modeling:v502=0.15 |
| v702 | event_type_count | f04_targets | v402 | 221 | 221 | heredado_sin_cambios; cambios_en=- | - | - | - | v402=221 | v502=221 | v602=221 | v702=221 | f04_targets:v402=221 -> f05_modeling:v502=221 -> f06_quant:v602=221 -> f07_modval:v702=221 |
| v702 | imbalance_max_majority_samples | f05_modeling | v502 | 20000 | - | solo_ancestro; cambios_en=- | - | - | - | - | v502=20000 | - | - | f05_modeling:v502=20000 |
| v702 | imbalance_strategy | f05_modeling | v502 | rare_events | - | solo_ancestro; cambios_en=- | - | - | - | - | v502=rare_events | - | - | f05_modeling:v502=rare_events |
| v702 | model_family | f05_modeling | v502 | cnn1d | - | solo_ancestro; cambios_en=- | - | - | - | - | v502=cnn1d | - | - | f05_modeling:v502=cnn1d |
| v702 | nan_mode | f02_events | v200 | keep | - | solo_ancestro; cambios_en=f03_windows:v300 | - | v200=keep | v300=discard | - | - | - | - | f02_events:v200=keep -> f03_windows:v300=discard |
| v702 | nan_values | f01_explore | v100 | [-999999] | - | solo_ancestro; cambios_en=- | v100=[-999999] | - | - | - | - | - | - | f01_explore:v100=[-999999] |
| v702 | parent_variant | f03_windows | v300 | v200 | v602 | redefinido_en_linaje; cambios_en=f04_targets:v402, f05_modeling:v502, f06_quant:v602, f07_modval:v702 | - | - | v300=v200 | v402=v300 | v502=v402 | v602=v502 | v702=v602 | f03_windows:v300=v200 -> f04_targets:v402=v300 -> f05_modeling:v502=v402 -> f06_quant:v602=v502 -> f07_modval:v702=v602 |
| v702 | platform | f07_modval | v702 | esp32 | esp32 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v702=esp32 | f07_modval:v702=esp32 |
| v702 | prediction_name | f04_targets | v402 | PVPCS_Active_Power_any-to-80_100 | PVPCS_Active_Power_any-to-80_100 | heredado_sin_cambios; cambios_en=- | - | - | - | v402=PVPCS_Active_Power_any-to-80_100 | v502=PVPCS_Active_Power_any-to-80_100 | v602=PVPCS_Active_Power_any-to-80_100 | v702=PVPCS_Active_Power_any-to-80_100 | f04_targets:v402=PVPCS_Active_Power_any-to-80_100 -> f05_modeling:v502=PVPCS_Active_Power_any-to-80_100 -> f06_quant:v602=PVPCS_Active_Power_any-to-80_100 -> f07_modval:v702=PVPCS_Active_Power_any-to-80_100 |
| v702 | quantization.calibration_samples | f06_quant | v602 | 512 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v602=512 | - | f06_quant:v602=512 |
| v702 | quantization.keep_float_fallback | f06_quant | v602 | false | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v602=false | - | f06_quant:v602=false |
| v702 | quantization.per_channel | f06_quant | v602 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v602=true | - | f06_quant:v602=true |
| v702 | quantization.representative_dataset | f06_quant | v602 | val | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v602=val | - | f06_quant:v602=val |
| v702 | quantization.symmetric_int8 | f06_quant | v602 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v602=true | - | f06_quant:v602=true |
| v702 | quantization.tflite_optimization | f06_quant | v602 | DEFAULT | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v602=DEFAULT | - | f06_quant:v602=DEFAULT |
| v702 | raw_path | f01_explore | v100 | data/raw.csv | - | solo_ancestro; cambios_en=- | v100=data/raw.csv | - | - | - | - | - | - | f01_explore:v100=data/raw.csv |
| v702 | search_space.cnn1d.embed_dim | f05_modeling | v502 | [64] | - | solo_ancestro; cambios_en=- | - | - | - | - | v502=[64] | - | - | f05_modeling:v502=[64] |
| v702 | search_space.cnn1d.filters | f05_modeling | v502 | [64, 128] | - | solo_ancestro; cambios_en=- | - | - | - | - | v502=[64, 128] | - | - | f05_modeling:v502=[64, 128] |
| v702 | search_space.cnn1d.kernel_size | f05_modeling | v502 | [3, 5] | - | solo_ancestro; cambios_en=- | - | - | - | - | v502=[3, 5] | - | - | f05_modeling:v502=[3, 5] |
| v702 | search_space.common.batch_size | f05_modeling | v502 | [128, 256] | - | solo_ancestro; cambios_en=- | - | - | - | - | v502=[128, 256] | - | - | f05_modeling:v502=[128, 256] |
| v702 | search_space.common.dropout | f05_modeling | v502 | [0.0, 0.2] | - | solo_ancestro; cambios_en=- | - | - | - | - | v502=[0.0, 0.2] | - | - | f05_modeling:v502=[0.0, 0.2] |
| v702 | search_space.common.learning_rate | f05_modeling | v502 | [0.001, 0.0005] | - | solo_ancestro; cambios_en=- | - | - | - | - | v502=[0.001, 0.0005] | - | - | f05_modeling:v502=[0.001, 0.0005] |
| v702 | search_space.common.n_layers | f05_modeling | v502 | [1, 2] | - | solo_ancestro; cambios_en=- | - | - | - | - | v502=[1, 2] | - | - | f05_modeling:v502=[1, 2] |
| v702 | search_space.common.units | f05_modeling | v502 | [64, 128] | - | solo_ancestro; cambios_en=- | - | - | - | - | v502=[64, 128] | - | - | f05_modeling:v502=[64, 128] |
| v702 | search_space.sequence_embedding.embed_dim | f05_modeling | v502 | [64, 128] | - | solo_ancestro; cambios_en=- | - | - | - | - | v502=[64, 128] | - | - | f05_modeling:v502=[64, 128] |
| v702 | strategy | f02_events | v200 | transitions | - | solo_ancestro; cambios_en=- | - | v200=transitions | - | - | - | - | - | f02_events:v200=transitions |
| v702 | target_event_types | f04_targets | v402 | ["PVPCS_Active_Power_0_40-to-80_100", "PVPCS_Active_Power_40_60-to-80_100", "PVPCS_Active_Power_60_80-to-80_100"] | - | solo_ancestro; cambios_en=- | - | - | - | v402=["PVPCS_Active_Power_0_40-to-80_100", "PVPCS_Active_Power_40_60-to-80_100", "PVPCS_Active_Power_60_80-to-80_100"] | - | - | - | f04_targets:v402=["PVPCS_Active_Power_0_40-to-80_100", "PVPCS_Active_Power_40_60-to-80_100", "PVPCS_Active_Power_60_80-to-80_100"] |
| v702 | target_operator | f04_targets | v402 | OR | - | solo_ancestro; cambios_en=- | - | - | - | v402=OR | - | - | - | f04_targets:v402=OR |
| v702 | thresholding.grid_points | f06_quant | v602 | 101 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v602=101 | - | f06_quant:v602=101 |
| v702 | thresholding.maximize_metric | f06_quant | v602 | recall | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v602=recall | - | f06_quant:v602=recall |
| v702 | thresholding.strategy | f06_quant | v602 | recalibrate_on_quantized | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v602=recalibrate_on_quantized | - | f06_quant:v602=recalibrate_on_quantized |
| v702 | time_scale_factor | f07_modval | v702 | 0.01 | 0.01 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v702=0.01 | f07_modval:v702=0.01 |
| v702 | training.epochs | f05_modeling | v502 | 20 | - | solo_ancestro; cambios_en=- | - | - | - | - | v502=20 | - | - | f05_modeling:v502=20 |
| v702 | training.max_samples | f05_modeling | v502 | - | - | solo_ancestro; cambios_en=- | - | - | - | - | v502=- | - | - | f05_modeling:v502=- |
| v702 | window_strategy | f03_windows | v300 | synchro | - | solo_ancestro; cambios_en=- | - | - | v300=synchro | - | - | - | - | f03_windows:v300=synchro |
| v703 | LT | f03_windows | v300 | 1 | 1 | heredado_sin_cambios; cambios_en=- | - | - | v300=1 | v403=1 | v503=1 | v603=1 | v703=1 | f03_windows:v300=1 -> f04_targets:v403=1 -> f05_modeling:v503=1 -> f06_quant:v603=1 -> f07_modval:v703=1 |
| v703 | MTI_MS | f07_modval | v703 | 100 | 100 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v703=100 | f07_modval:v703=100 |
| v703 | OW | f03_windows | v300 | 6 | 6 | heredado_sin_cambios; cambios_en=- | - | - | v300=6 | v403=6 | v503=6 | v603=6 | v703=6 | f03_windows:v300=6 -> f04_targets:v403=6 -> f05_modeling:v503=6 -> f06_quant:v603=6 -> f07_modval:v703=6 |
| v703 | PW | f03_windows | v300 | 1 | 1 | heredado_sin_cambios; cambios_en=- | - | - | v300=1 | v403=1 | v503=1 | v603=1 | v703=1 | f03_windows:v300=1 -> f04_targets:v403=1 -> f05_modeling:v503=1 -> f06_quant:v603=1 -> f07_modval:v703=1 |
| v703 | Tu | f02_events | v200 | 10 | 10 | heredado_sin_cambios; cambios_en=- | - | v200=10 | v300=10 | v403=10 | v503=10 | v603=10 | v703=10 | f02_events:v200=10 -> f03_windows:v300=10 -> f04_targets:v403=10 -> f05_modeling:v503=10 -> f06_quant:v603=10 -> f07_modval:v703=10 |
| v703 | automl.enabled | f05_modeling | v503 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | v503=true | - | - | f05_modeling:v503=true |
| v703 | automl.max_trials | f05_modeling | v503 | 5 | - | solo_ancestro; cambios_en=- | - | - | - | - | v503=5 | - | - | f05_modeling:v503=5 |
| v703 | automl.seed | f05_modeling | v503 | 42 | - | solo_ancestro; cambios_en=- | - | - | - | - | v503=42 | - | - | f05_modeling:v503=42 |
| v703 | bands | f02_events | v200 | [40, 60, 80] | - | solo_ancestro; cambios_en=- | - | v200=[40, 60, 80] | - | - | - | - | - | f02_events:v200=[40, 60, 80] |
| v703 | cleaning | f01_explore | v100 | basic | - | solo_ancestro; cambios_en=- | v100=basic | - | - | - | - | - | - | f01_explore:v100=basic |
| v703 | decision_threshold | f07_modval | v703 | 0.46126407384872437 | 0.46126407384872437 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v703=0.46126407384872437 | f07_modval:v703=0.46126407384872437 |
| v703 | deployment.memory_limit_bytes | f06_quant | v603 | 327680 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v603=327680 | - | f06_quant:v603=327680 |
| v703 | deployment.require_int8 | f06_quant | v603 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v603=true | - | f06_quant:v603=true |
| v703 | deployment.runtime | f06_quant | v603 | esp-tflite-micro | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v603=esp-tflite-micro | - | f06_quant:v603=esp-tflite-micro |
| v703 | deployment.runtime_version | f06_quant | v603 | 1.3.3 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v603=1.3.3 | - | f06_quant:v603=1.3.3 |
| v703 | deployment.target | f06_quant | v603 | esp32 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v603=esp32 | - | f06_quant:v603=esp32 |
| v703 | eedu.layout | f06_quant | v603 | default | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v603=default | - | f06_quant:v603=default |
| v703 | eedu.version | f06_quant | v603 | 1.0 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v603=1.0 | - | f06_quant:v603=1.0 |
| v703 | evaluation.split.test | f05_modeling | v503 | 0.15 | - | solo_ancestro; cambios_en=- | - | - | - | - | v503=0.15 | - | - | f05_modeling:v503=0.15 |
| v703 | evaluation.split.train | f05_modeling | v503 | 0.7 | - | solo_ancestro; cambios_en=- | - | - | - | - | v503=0.7 | - | - | f05_modeling:v503=0.7 |
| v703 | evaluation.split.val | f05_modeling | v503 | 0.15 | - | solo_ancestro; cambios_en=- | - | - | - | - | v503=0.15 | - | - | f05_modeling:v503=0.15 |
| v703 | event_type_count | f04_targets | v403 | 221 | 221 | heredado_sin_cambios; cambios_en=- | - | - | - | v403=221 | v503=221 | v603=221 | v703=221 | f04_targets:v403=221 -> f05_modeling:v503=221 -> f06_quant:v603=221 -> f07_modval:v703=221 |
| v703 | imbalance_max_majority_samples | f05_modeling | v503 | 20000 | - | solo_ancestro; cambios_en=- | - | - | - | - | v503=20000 | - | - | f05_modeling:v503=20000 |
| v703 | imbalance_strategy | f05_modeling | v503 | rare_events | - | solo_ancestro; cambios_en=- | - | - | - | - | v503=rare_events | - | - | f05_modeling:v503=rare_events |
| v703 | model_family | f05_modeling | v503 | cnn1d | - | solo_ancestro; cambios_en=- | - | - | - | - | v503=cnn1d | - | - | f05_modeling:v503=cnn1d |
| v703 | nan_mode | f02_events | v200 | keep | - | solo_ancestro; cambios_en=f03_windows:v300 | - | v200=keep | v300=discard | - | - | - | - | f02_events:v200=keep -> f03_windows:v300=discard |
| v703 | nan_values | f01_explore | v100 | [-999999] | - | solo_ancestro; cambios_en=- | v100=[-999999] | - | - | - | - | - | - | f01_explore:v100=[-999999] |
| v703 | parent_variant | f03_windows | v300 | v200 | v603 | redefinido_en_linaje; cambios_en=f04_targets:v403, f05_modeling:v503, f06_quant:v603, f07_modval:v703 | - | - | v300=v200 | v403=v300 | v503=v403 | v603=v503 | v703=v603 | f03_windows:v300=v200 -> f04_targets:v403=v300 -> f05_modeling:v503=v403 -> f06_quant:v603=v503 -> f07_modval:v703=v603 |
| v703 | platform | f07_modval | v703 | esp32 | esp32 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v703=esp32 | f07_modval:v703=esp32 |
| v703 | prediction_name | f04_targets | v403 | GE_Active_Power_any-to-80_100 | GE_Active_Power_any-to-80_100 | heredado_sin_cambios; cambios_en=- | - | - | - | v403=GE_Active_Power_any-to-80_100 | v503=GE_Active_Power_any-to-80_100 | v603=GE_Active_Power_any-to-80_100 | v703=GE_Active_Power_any-to-80_100 | f04_targets:v403=GE_Active_Power_any-to-80_100 -> f05_modeling:v503=GE_Active_Power_any-to-80_100 -> f06_quant:v603=GE_Active_Power_any-to-80_100 -> f07_modval:v703=GE_Active_Power_any-to-80_100 |
| v703 | quantization.calibration_samples | f06_quant | v603 | 512 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v603=512 | - | f06_quant:v603=512 |
| v703 | quantization.keep_float_fallback | f06_quant | v603 | false | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v603=false | - | f06_quant:v603=false |
| v703 | quantization.per_channel | f06_quant | v603 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v603=true | - | f06_quant:v603=true |
| v703 | quantization.representative_dataset | f06_quant | v603 | val | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v603=val | - | f06_quant:v603=val |
| v703 | quantization.symmetric_int8 | f06_quant | v603 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v603=true | - | f06_quant:v603=true |
| v703 | quantization.tflite_optimization | f06_quant | v603 | DEFAULT | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v603=DEFAULT | - | f06_quant:v603=DEFAULT |
| v703 | raw_path | f01_explore | v100 | data/raw.csv | - | solo_ancestro; cambios_en=- | v100=data/raw.csv | - | - | - | - | - | - | f01_explore:v100=data/raw.csv |
| v703 | search_space.cnn1d.embed_dim | f05_modeling | v503 | [64] | - | solo_ancestro; cambios_en=- | - | - | - | - | v503=[64] | - | - | f05_modeling:v503=[64] |
| v703 | search_space.cnn1d.filters | f05_modeling | v503 | [64, 128] | - | solo_ancestro; cambios_en=- | - | - | - | - | v503=[64, 128] | - | - | f05_modeling:v503=[64, 128] |
| v703 | search_space.cnn1d.kernel_size | f05_modeling | v503 | [3, 5] | - | solo_ancestro; cambios_en=- | - | - | - | - | v503=[3, 5] | - | - | f05_modeling:v503=[3, 5] |
| v703 | search_space.common.batch_size | f05_modeling | v503 | [128, 256] | - | solo_ancestro; cambios_en=- | - | - | - | - | v503=[128, 256] | - | - | f05_modeling:v503=[128, 256] |
| v703 | search_space.common.dropout | f05_modeling | v503 | [0.0, 0.2] | - | solo_ancestro; cambios_en=- | - | - | - | - | v503=[0.0, 0.2] | - | - | f05_modeling:v503=[0.0, 0.2] |
| v703 | search_space.common.learning_rate | f05_modeling | v503 | [0.001, 0.0005] | - | solo_ancestro; cambios_en=- | - | - | - | - | v503=[0.001, 0.0005] | - | - | f05_modeling:v503=[0.001, 0.0005] |
| v703 | search_space.common.n_layers | f05_modeling | v503 | [1, 2] | - | solo_ancestro; cambios_en=- | - | - | - | - | v503=[1, 2] | - | - | f05_modeling:v503=[1, 2] |
| v703 | search_space.common.units | f05_modeling | v503 | [64, 128] | - | solo_ancestro; cambios_en=- | - | - | - | - | v503=[64, 128] | - | - | f05_modeling:v503=[64, 128] |
| v703 | search_space.sequence_embedding.embed_dim | f05_modeling | v503 | [64, 128] | - | solo_ancestro; cambios_en=- | - | - | - | - | v503=[64, 128] | - | - | f05_modeling:v503=[64, 128] |
| v703 | strategy | f02_events | v200 | transitions | - | solo_ancestro; cambios_en=- | - | v200=transitions | - | - | - | - | - | f02_events:v200=transitions |
| v703 | target_event_types | f04_targets | v403 | ["GE_Active_Power_0_40-to-80_100", "GE_Active_Power_40_60-to-80_100", "GE_Active_Power_60_80-to-80_100"] | - | solo_ancestro; cambios_en=- | - | - | - | v403=["GE_Active_Power_0_40-to-80_100", "GE_Active_Power_40_60-to-80_100", "GE_Active_Power_60_80-to-80_100"] | - | - | - | f04_targets:v403=["GE_Active_Power_0_40-to-80_100", "GE_Active_Power_40_60-to-80_100", "GE_Active_Power_60_80-to-80_100"] |
| v703 | target_operator | f04_targets | v403 | OR | - | solo_ancestro; cambios_en=- | - | - | - | v403=OR | - | - | - | f04_targets:v403=OR |
| v703 | thresholding.grid_points | f06_quant | v603 | 101 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v603=101 | - | f06_quant:v603=101 |
| v703 | thresholding.maximize_metric | f06_quant | v603 | recall | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v603=recall | - | f06_quant:v603=recall |
| v703 | thresholding.strategy | f06_quant | v603 | recalibrate_on_quantized | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v603=recalibrate_on_quantized | - | f06_quant:v603=recalibrate_on_quantized |
| v703 | time_scale_factor | f07_modval | v703 | 0.01 | 0.01 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v703=0.01 | f07_modval:v703=0.01 |
| v703 | training.epochs | f05_modeling | v503 | 20 | - | solo_ancestro; cambios_en=- | - | - | - | - | v503=20 | - | - | f05_modeling:v503=20 |
| v703 | training.max_samples | f05_modeling | v503 | - | - | solo_ancestro; cambios_en=- | - | - | - | - | v503=- | - | - | f05_modeling:v503=- |
| v703 | window_strategy | f03_windows | v300 | synchro | - | solo_ancestro; cambios_en=- | - | - | v300=synchro | - | - | - | - | f03_windows:v300=synchro |
| v704 | LT | f03_windows | v300 | 1 | 1 | heredado_sin_cambios; cambios_en=- | - | - | v300=1 | v404=1 | v504=1 | v604=1 | v704=1 | f03_windows:v300=1 -> f04_targets:v404=1 -> f05_modeling:v504=1 -> f06_quant:v604=1 -> f07_modval:v704=1 |
| v704 | MTI_MS | f07_modval | v704 | 100 | 100 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v704=100 | f07_modval:v704=100 |
| v704 | OW | f03_windows | v300 | 6 | 6 | heredado_sin_cambios; cambios_en=- | - | - | v300=6 | v404=6 | v504=6 | v604=6 | v704=6 | f03_windows:v300=6 -> f04_targets:v404=6 -> f05_modeling:v504=6 -> f06_quant:v604=6 -> f07_modval:v704=6 |
| v704 | PW | f03_windows | v300 | 1 | 1 | heredado_sin_cambios; cambios_en=- | - | - | v300=1 | v404=1 | v504=1 | v604=1 | v704=1 | f03_windows:v300=1 -> f04_targets:v404=1 -> f05_modeling:v504=1 -> f06_quant:v604=1 -> f07_modval:v704=1 |
| v704 | Tu | f02_events | v200 | 10 | 10 | heredado_sin_cambios; cambios_en=- | - | v200=10 | v300=10 | v404=10 | v504=10 | v604=10 | v704=10 | f02_events:v200=10 -> f03_windows:v300=10 -> f04_targets:v404=10 -> f05_modeling:v504=10 -> f06_quant:v604=10 -> f07_modval:v704=10 |
| v704 | automl.enabled | f05_modeling | v504 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | v504=true | - | - | f05_modeling:v504=true |
| v704 | automl.max_trials | f05_modeling | v504 | 5 | - | solo_ancestro; cambios_en=- | - | - | - | - | v504=5 | - | - | f05_modeling:v504=5 |
| v704 | automl.seed | f05_modeling | v504 | 42 | - | solo_ancestro; cambios_en=- | - | - | - | - | v504=42 | - | - | f05_modeling:v504=42 |
| v704 | bands | f02_events | v200 | [40, 60, 80] | - | solo_ancestro; cambios_en=- | - | v200=[40, 60, 80] | - | - | - | - | - | f02_events:v200=[40, 60, 80] |
| v704 | cleaning | f01_explore | v100 | basic | - | solo_ancestro; cambios_en=- | v100=basic | - | - | - | - | - | - | f01_explore:v100=basic |
| v704 | decision_threshold | f07_modval | v704 | 0.4130264222621918 | 0.4130264222621918 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v704=0.4130264222621918 | f07_modval:v704=0.4130264222621918 |
| v704 | deployment.memory_limit_bytes | f06_quant | v604 | 327680 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v604=327680 | - | f06_quant:v604=327680 |
| v704 | deployment.require_int8 | f06_quant | v604 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v604=true | - | f06_quant:v604=true |
| v704 | deployment.runtime | f06_quant | v604 | esp-tflite-micro | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v604=esp-tflite-micro | - | f06_quant:v604=esp-tflite-micro |
| v704 | deployment.runtime_version | f06_quant | v604 | 1.3.3 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v604=1.3.3 | - | f06_quant:v604=1.3.3 |
| v704 | deployment.target | f06_quant | v604 | esp32 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v604=esp32 | - | f06_quant:v604=esp32 |
| v704 | eedu.layout | f06_quant | v604 | default | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v604=default | - | f06_quant:v604=default |
| v704 | eedu.version | f06_quant | v604 | 1.0 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v604=1.0 | - | f06_quant:v604=1.0 |
| v704 | evaluation.split.test | f05_modeling | v504 | 0.15 | - | solo_ancestro; cambios_en=- | - | - | - | - | v504=0.15 | - | - | f05_modeling:v504=0.15 |
| v704 | evaluation.split.train | f05_modeling | v504 | 0.7 | - | solo_ancestro; cambios_en=- | - | - | - | - | v504=0.7 | - | - | f05_modeling:v504=0.7 |
| v704 | evaluation.split.val | f05_modeling | v504 | 0.15 | - | solo_ancestro; cambios_en=- | - | - | - | - | v504=0.15 | - | - | f05_modeling:v504=0.15 |
| v704 | event_type_count | f04_targets | v404 | 221 | 221 | heredado_sin_cambios; cambios_en=- | - | - | - | v404=221 | v504=221 | v604=221 | v704=221 | f04_targets:v404=221 -> f05_modeling:v504=221 -> f06_quant:v604=221 -> f07_modval:v704=221 |
| v704 | imbalance_max_majority_samples | f05_modeling | v504 | 20000 | - | solo_ancestro; cambios_en=- | - | - | - | - | v504=20000 | - | - | f05_modeling:v504=20000 |
| v704 | imbalance_strategy | f05_modeling | v504 | rare_events | - | solo_ancestro; cambios_en=- | - | - | - | - | v504=rare_events | - | - | f05_modeling:v504=rare_events |
| v704 | model_family | f05_modeling | v504 | cnn1d | - | solo_ancestro; cambios_en=- | - | - | - | - | v504=cnn1d | - | - | f05_modeling:v504=cnn1d |
| v704 | nan_mode | f02_events | v200 | keep | - | solo_ancestro; cambios_en=f03_windows:v300 | - | v200=keep | v300=discard | - | - | - | - | f02_events:v200=keep -> f03_windows:v300=discard |
| v704 | nan_values | f01_explore | v100 | [-999999] | - | solo_ancestro; cambios_en=- | v100=[-999999] | - | - | - | - | - | - | f01_explore:v100=[-999999] |
| v704 | parent_variant | f03_windows | v300 | v200 | v604 | redefinido_en_linaje; cambios_en=f04_targets:v404, f05_modeling:v504, f06_quant:v604, f07_modval:v704 | - | - | v300=v200 | v404=v300 | v504=v404 | v604=v504 | v704=v604 | f03_windows:v300=v200 -> f04_targets:v404=v300 -> f05_modeling:v504=v404 -> f06_quant:v604=v504 -> f07_modval:v704=v604 |
| v704 | platform | f07_modval | v704 | esp32 | esp32 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v704=esp32 | f07_modval:v704=esp32 |
| v704 | prediction_name | f04_targets | v404 | GE_Body_Active_Power_any-to-80_100 | GE_Body_Active_Power_any-to-80_100 | heredado_sin_cambios; cambios_en=- | - | - | - | v404=GE_Body_Active_Power_any-to-80_100 | v504=GE_Body_Active_Power_any-to-80_100 | v604=GE_Body_Active_Power_any-to-80_100 | v704=GE_Body_Active_Power_any-to-80_100 | f04_targets:v404=GE_Body_Active_Power_any-to-80_100 -> f05_modeling:v504=GE_Body_Active_Power_any-to-80_100 -> f06_quant:v604=GE_Body_Active_Power_any-to-80_100 -> f07_modval:v704=GE_Body_Active_Power_any-to-80_100 |
| v704 | quantization.calibration_samples | f06_quant | v604 | 512 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v604=512 | - | f06_quant:v604=512 |
| v704 | quantization.keep_float_fallback | f06_quant | v604 | false | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v604=false | - | f06_quant:v604=false |
| v704 | quantization.per_channel | f06_quant | v604 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v604=true | - | f06_quant:v604=true |
| v704 | quantization.representative_dataset | f06_quant | v604 | val | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v604=val | - | f06_quant:v604=val |
| v704 | quantization.symmetric_int8 | f06_quant | v604 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v604=true | - | f06_quant:v604=true |
| v704 | quantization.tflite_optimization | f06_quant | v604 | DEFAULT | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v604=DEFAULT | - | f06_quant:v604=DEFAULT |
| v704 | raw_path | f01_explore | v100 | data/raw.csv | - | solo_ancestro; cambios_en=- | v100=data/raw.csv | - | - | - | - | - | - | f01_explore:v100=data/raw.csv |
| v704 | search_space.cnn1d.embed_dim | f05_modeling | v504 | [64] | - | solo_ancestro; cambios_en=- | - | - | - | - | v504=[64] | - | - | f05_modeling:v504=[64] |
| v704 | search_space.cnn1d.filters | f05_modeling | v504 | [64, 128] | - | solo_ancestro; cambios_en=- | - | - | - | - | v504=[64, 128] | - | - | f05_modeling:v504=[64, 128] |
| v704 | search_space.cnn1d.kernel_size | f05_modeling | v504 | [3, 5] | - | solo_ancestro; cambios_en=- | - | - | - | - | v504=[3, 5] | - | - | f05_modeling:v504=[3, 5] |
| v704 | search_space.common.batch_size | f05_modeling | v504 | [128, 256] | - | solo_ancestro; cambios_en=- | - | - | - | - | v504=[128, 256] | - | - | f05_modeling:v504=[128, 256] |
| v704 | search_space.common.dropout | f05_modeling | v504 | [0.0, 0.2] | - | solo_ancestro; cambios_en=- | - | - | - | - | v504=[0.0, 0.2] | - | - | f05_modeling:v504=[0.0, 0.2] |
| v704 | search_space.common.learning_rate | f05_modeling | v504 | [0.001, 0.0005] | - | solo_ancestro; cambios_en=- | - | - | - | - | v504=[0.001, 0.0005] | - | - | f05_modeling:v504=[0.001, 0.0005] |
| v704 | search_space.common.n_layers | f05_modeling | v504 | [1, 2] | - | solo_ancestro; cambios_en=- | - | - | - | - | v504=[1, 2] | - | - | f05_modeling:v504=[1, 2] |
| v704 | search_space.common.units | f05_modeling | v504 | [64, 128] | - | solo_ancestro; cambios_en=- | - | - | - | - | v504=[64, 128] | - | - | f05_modeling:v504=[64, 128] |
| v704 | search_space.sequence_embedding.embed_dim | f05_modeling | v504 | [64, 128] | - | solo_ancestro; cambios_en=- | - | - | - | - | v504=[64, 128] | - | - | f05_modeling:v504=[64, 128] |
| v704 | strategy | f02_events | v200 | transitions | - | solo_ancestro; cambios_en=- | - | v200=transitions | - | - | - | - | - | f02_events:v200=transitions |
| v704 | target_event_types | f04_targets | v404 | ["GE_Body_Active_Power_0_40-to-80_100", "GE_Body_Active_Power_40_60-to-80_100", "GE_Body_Active_Power_60_80-to-80_100"] | - | solo_ancestro; cambios_en=- | - | - | - | v404=["GE_Body_Active_Power_0_40-to-80_100", "GE_Body_Active_Power_40_60-to-80_100", "GE_Body_Active_Power_60_80-to-80_100"] | - | - | - | f04_targets:v404=["GE_Body_Active_Power_0_40-to-80_100", "GE_Body_Active_Power_40_60-to-80_100", "GE_Body_Active_Power_60_80-to-80_100"] |
| v704 | target_operator | f04_targets | v404 | OR | - | solo_ancestro; cambios_en=- | - | - | - | v404=OR | - | - | - | f04_targets:v404=OR |
| v704 | thresholding.grid_points | f06_quant | v604 | 101 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v604=101 | - | f06_quant:v604=101 |
| v704 | thresholding.maximize_metric | f06_quant | v604 | recall | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v604=recall | - | f06_quant:v604=recall |
| v704 | thresholding.strategy | f06_quant | v604 | recalibrate_on_quantized | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v604=recalibrate_on_quantized | - | f06_quant:v604=recalibrate_on_quantized |
| v704 | time_scale_factor | f07_modval | v704 | 0.01 | 0.01 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v704=0.01 | f07_modval:v704=0.01 |
| v704 | training.epochs | f05_modeling | v504 | 20 | - | solo_ancestro; cambios_en=- | - | - | - | - | v504=20 | - | - | f05_modeling:v504=20 |
| v704 | training.max_samples | f05_modeling | v504 | - | - | solo_ancestro; cambios_en=- | - | - | - | - | v504=- | - | - | f05_modeling:v504=- |
| v704 | window_strategy | f03_windows | v300 | synchro | - | solo_ancestro; cambios_en=- | - | - | v300=synchro | - | - | - | - | f03_windows:v300=synchro |
| v705 | LT | f03_windows | v300 | 1 | 1 | heredado_sin_cambios; cambios_en=- | - | - | v300=1 | v405=1 | v505=1 | v605=1 | v705=1 | f03_windows:v300=1 -> f04_targets:v405=1 -> f05_modeling:v505=1 -> f06_quant:v605=1 -> f07_modval:v705=1 |
| v705 | MTI_MS | f07_modval | v705 | 100 | 100 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v705=100 | f07_modval:v705=100 |
| v705 | OW | f03_windows | v300 | 6 | 6 | heredado_sin_cambios; cambios_en=- | - | - | v300=6 | v405=6 | v505=6 | v605=6 | v705=6 | f03_windows:v300=6 -> f04_targets:v405=6 -> f05_modeling:v505=6 -> f06_quant:v605=6 -> f07_modval:v705=6 |
| v705 | PW | f03_windows | v300 | 1 | 1 | heredado_sin_cambios; cambios_en=- | - | - | v300=1 | v405=1 | v505=1 | v605=1 | v705=1 | f03_windows:v300=1 -> f04_targets:v405=1 -> f05_modeling:v505=1 -> f06_quant:v605=1 -> f07_modval:v705=1 |
| v705 | Tu | f02_events | v200 | 10 | 10 | heredado_sin_cambios; cambios_en=- | - | v200=10 | v300=10 | v405=10 | v505=10 | v605=10 | v705=10 | f02_events:v200=10 -> f03_windows:v300=10 -> f04_targets:v405=10 -> f05_modeling:v505=10 -> f06_quant:v605=10 -> f07_modval:v705=10 |
| v705 | automl.enabled | f05_modeling | v505 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | v505=true | - | - | f05_modeling:v505=true |
| v705 | automl.max_trials | f05_modeling | v505 | 5 | - | solo_ancestro; cambios_en=- | - | - | - | - | v505=5 | - | - | f05_modeling:v505=5 |
| v705 | automl.seed | f05_modeling | v505 | 42 | - | solo_ancestro; cambios_en=- | - | - | - | - | v505=42 | - | - | f05_modeling:v505=42 |
| v705 | bands | f02_events | v200 | [40, 60, 80] | - | solo_ancestro; cambios_en=- | - | v200=[40, 60, 80] | - | - | - | - | - | f02_events:v200=[40, 60, 80] |
| v705 | cleaning | f01_explore | v100 | basic | - | solo_ancestro; cambios_en=- | v100=basic | - | - | - | - | - | - | f01_explore:v100=basic |
| v705 | deployment.memory_limit_bytes | f06_quant | v605 | 327680 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v605=327680 | - | f06_quant:v605=327680 |
| v705 | deployment.require_int8 | f06_quant | v605 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v605=true | - | f06_quant:v605=true |
| v705 | deployment.runtime | f06_quant | v605 | esp-tflite-micro | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v605=esp-tflite-micro | - | f06_quant:v605=esp-tflite-micro |
| v705 | deployment.runtime_version | f06_quant | v605 | 1.3.3 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v605=1.3.3 | - | f06_quant:v605=1.3.3 |
| v705 | deployment.target | f06_quant | v605 | esp32 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v605=esp32 | - | f06_quant:v605=esp32 |
| v705 | eedu.layout | f06_quant | v605 | default | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v605=default | - | f06_quant:v605=default |
| v705 | eedu.version | f06_quant | v605 | 1.0 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v605=1.0 | - | f06_quant:v605=1.0 |
| v705 | evaluation.split.test | f05_modeling | v505 | 0.15 | - | solo_ancestro; cambios_en=- | - | - | - | - | v505=0.15 | - | - | f05_modeling:v505=0.15 |
| v705 | evaluation.split.train | f05_modeling | v505 | 0.7 | - | solo_ancestro; cambios_en=- | - | - | - | - | v505=0.7 | - | - | f05_modeling:v505=0.7 |
| v705 | evaluation.split.val | f05_modeling | v505 | 0.15 | - | solo_ancestro; cambios_en=- | - | - | - | - | v505=0.15 | - | - | f05_modeling:v505=0.15 |
| v705 | event_type_count | f04_targets | v405 | 221 | 221 | heredado_sin_cambios; cambios_en=- | - | - | - | v405=221 | v505=221 | v605=221 | v705=221 | f04_targets:v405=221 -> f05_modeling:v505=221 -> f06_quant:v605=221 -> f07_modval:v705=221 |
| v705 | imbalance_max_majority_samples | f05_modeling | v505 | 20000 | - | solo_ancestro; cambios_en=- | - | - | - | - | v505=20000 | - | - | f05_modeling:v505=20000 |
| v705 | imbalance_strategy | f05_modeling | v505 | rare_events | - | solo_ancestro; cambios_en=- | - | - | - | - | v505=rare_events | - | - | f05_modeling:v505=rare_events |
| v705 | model_family | f05_modeling | v505 | cnn1d | - | solo_ancestro; cambios_en=- | - | - | - | - | v505=cnn1d | - | - | f05_modeling:v505=cnn1d |
| v705 | nan_mode | f02_events | v200 | keep | - | solo_ancestro; cambios_en=f03_windows:v300 | - | v200=keep | v300=discard | - | - | - | - | f02_events:v200=keep -> f03_windows:v300=discard |
| v705 | nan_values | f01_explore | v100 | [-999999] | - | solo_ancestro; cambios_en=- | v100=[-999999] | - | - | - | - | - | - | f01_explore:v100=[-999999] |
| v705 | parent_variant | f03_windows | v300 | v200 | v605 | redefinido_en_linaje; cambios_en=f04_targets:v405, f05_modeling:v505, f06_quant:v605, f07_modval:v705 | - | - | v300=v200 | v405=v300 | v505=v405 | v605=v505 | v705=v605 | f03_windows:v300=v200 -> f04_targets:v405=v300 -> f05_modeling:v505=v405 -> f06_quant:v605=v505 -> f07_modval:v705=v605 |
| v705 | platform | f07_modval | v705 | esp32 | esp32 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v705=esp32 | f07_modval:v705=esp32 |
| v705 | prediction_name | f04_targets | v405 | GE_Body_Active_Power_Set_Response_any-to-80_100 | GE_Body_Active_Power_Set_Response_any-to-80_100 | heredado_sin_cambios; cambios_en=- | - | - | - | v405=GE_Body_Active_Power_Set_Response_any-to-80_100 | v505=GE_Body_Active_Power_Set_Response_any-to-80_100 | v605=GE_Body_Active_Power_Set_Response_any-to-80_100 | v705=GE_Body_Active_Power_Set_Response_any-to-80_100 | f04_targets:v405=GE_Body_Active_Power_Set_Response_any-to-80_100 -> f05_modeling:v505=GE_Body_Active_Power_Set_Response_any-to-80_100 -> f06_quant:v605=GE_Body_Active_Power_Set_Response_any-to-80_100 -> f07_modval:v705=GE_Body_Active_Power_Set_Response_any-to-80_100 |
| v705 | quantization.calibration_samples | f06_quant | v605 | 512 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v605=512 | - | f06_quant:v605=512 |
| v705 | quantization.keep_float_fallback | f06_quant | v605 | false | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v605=false | - | f06_quant:v605=false |
| v705 | quantization.per_channel | f06_quant | v605 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v605=true | - | f06_quant:v605=true |
| v705 | quantization.representative_dataset | f06_quant | v605 | val | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v605=val | - | f06_quant:v605=val |
| v705 | quantization.symmetric_int8 | f06_quant | v605 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v605=true | - | f06_quant:v605=true |
| v705 | quantization.tflite_optimization | f06_quant | v605 | DEFAULT | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v605=DEFAULT | - | f06_quant:v605=DEFAULT |
| v705 | raw_path | f01_explore | v100 | data/raw.csv | - | solo_ancestro; cambios_en=- | v100=data/raw.csv | - | - | - | - | - | - | f01_explore:v100=data/raw.csv |
| v705 | search_space.cnn1d.embed_dim | f05_modeling | v505 | [64] | - | solo_ancestro; cambios_en=- | - | - | - | - | v505=[64] | - | - | f05_modeling:v505=[64] |
| v705 | search_space.cnn1d.filters | f05_modeling | v505 | [64, 128] | - | solo_ancestro; cambios_en=- | - | - | - | - | v505=[64, 128] | - | - | f05_modeling:v505=[64, 128] |
| v705 | search_space.cnn1d.kernel_size | f05_modeling | v505 | [3, 5] | - | solo_ancestro; cambios_en=- | - | - | - | - | v505=[3, 5] | - | - | f05_modeling:v505=[3, 5] |
| v705 | search_space.common.batch_size | f05_modeling | v505 | [128, 256] | - | solo_ancestro; cambios_en=- | - | - | - | - | v505=[128, 256] | - | - | f05_modeling:v505=[128, 256] |
| v705 | search_space.common.dropout | f05_modeling | v505 | [0.0, 0.2] | - | solo_ancestro; cambios_en=- | - | - | - | - | v505=[0.0, 0.2] | - | - | f05_modeling:v505=[0.0, 0.2] |
| v705 | search_space.common.learning_rate | f05_modeling | v505 | [0.001, 0.0005] | - | solo_ancestro; cambios_en=- | - | - | - | - | v505=[0.001, 0.0005] | - | - | f05_modeling:v505=[0.001, 0.0005] |
| v705 | search_space.common.n_layers | f05_modeling | v505 | [1, 2] | - | solo_ancestro; cambios_en=- | - | - | - | - | v505=[1, 2] | - | - | f05_modeling:v505=[1, 2] |
| v705 | search_space.common.units | f05_modeling | v505 | [64, 128] | - | solo_ancestro; cambios_en=- | - | - | - | - | v505=[64, 128] | - | - | f05_modeling:v505=[64, 128] |
| v705 | search_space.sequence_embedding.embed_dim | f05_modeling | v505 | [64, 128] | - | solo_ancestro; cambios_en=- | - | - | - | - | v505=[64, 128] | - | - | f05_modeling:v505=[64, 128] |
| v705 | strategy | f02_events | v200 | transitions | - | solo_ancestro; cambios_en=- | - | v200=transitions | - | - | - | - | - | f02_events:v200=transitions |
| v705 | target_event_types | f04_targets | v405 | ["GE_Body_Active_Power_Set_Response_0_40-to-80_100", "GE_Body_Active_Power_Set_Response_40_60-to-80_100", "GE_Body_Active_Power_Set_Response_60_80-to-80_100"] | - | solo_ancestro; cambios_en=- | - | - | - | v405=["GE_Body_Active_Power_Set_Response_0_40-to-80_100", "GE_Body_Active_Power_Set_Response_40_60-to-80_100", "GE_Body_Active_Power_Set_Response_60_80-to-80_100"] | - | - | - | f04_targets:v405=["GE_Body_Active_Power_Set_Response_0_40-to-80_100", "GE_Body_Active_Power_Set_Response_40_60-to-80_100", "GE_Body_Active_Power_Set_Response_60_80-to-80_100"] |
| v705 | target_operator | f04_targets | v405 | OR | - | solo_ancestro; cambios_en=- | - | - | - | v405=OR | - | - | - | f04_targets:v405=OR |
| v705 | thresholding.grid_points | f06_quant | v605 | 101 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v605=101 | - | f06_quant:v605=101 |
| v705 | thresholding.maximize_metric | f06_quant | v605 | recall | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v605=recall | - | f06_quant:v605=recall |
| v705 | thresholding.strategy | f06_quant | v605 | recalibrate_on_quantized | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v605=recalibrate_on_quantized | - | f06_quant:v605=recalibrate_on_quantized |
| v705 | time_scale_factor | f07_modval | v705 | 0.01 | 0.01 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v705=0.01 | f07_modval:v705=0.01 |
| v705 | training.epochs | f05_modeling | v505 | 20 | - | solo_ancestro; cambios_en=- | - | - | - | - | v505=20 | - | - | f05_modeling:v505=20 |
| v705 | training.max_samples | f05_modeling | v505 | - | - | solo_ancestro; cambios_en=- | - | - | - | - | v505=- | - | - | f05_modeling:v505=- |
| v705 | window_strategy | f03_windows | v300 | synchro | - | solo_ancestro; cambios_en=- | - | - | v300=synchro | - | - | - | - | f03_windows:v300=synchro |
| v706 | LT | f03_windows | v300 | 1 | 1 | heredado_sin_cambios; cambios_en=- | - | - | v300=1 | v406=1 | v506=1 | v606=1 | v706=1 | f03_windows:v300=1 -> f04_targets:v406=1 -> f05_modeling:v506=1 -> f06_quant:v606=1 -> f07_modval:v706=1 |
| v706 | MTI_MS | f07_modval | v706 | 100 | 100 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v706=100 | f07_modval:v706=100 |
| v706 | OW | f03_windows | v300 | 6 | 6 | heredado_sin_cambios; cambios_en=- | - | - | v300=6 | v406=6 | v506=6 | v606=6 | v706=6 | f03_windows:v300=6 -> f04_targets:v406=6 -> f05_modeling:v506=6 -> f06_quant:v606=6 -> f07_modval:v706=6 |
| v706 | PW | f03_windows | v300 | 1 | 1 | heredado_sin_cambios; cambios_en=- | - | - | v300=1 | v406=1 | v506=1 | v606=1 | v706=1 | f03_windows:v300=1 -> f04_targets:v406=1 -> f05_modeling:v506=1 -> f06_quant:v606=1 -> f07_modval:v706=1 |
| v706 | Tu | f02_events | v200 | 10 | 10 | heredado_sin_cambios; cambios_en=- | - | v200=10 | v300=10 | v406=10 | v506=10 | v606=10 | v706=10 | f02_events:v200=10 -> f03_windows:v300=10 -> f04_targets:v406=10 -> f05_modeling:v506=10 -> f06_quant:v606=10 -> f07_modval:v706=10 |
| v706 | automl.enabled | f05_modeling | v506 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | v506=true | - | - | f05_modeling:v506=true |
| v706 | automl.max_trials | f05_modeling | v506 | 5 | - | solo_ancestro; cambios_en=- | - | - | - | - | v506=5 | - | - | f05_modeling:v506=5 |
| v706 | automl.seed | f05_modeling | v506 | 42 | - | solo_ancestro; cambios_en=- | - | - | - | - | v506=42 | - | - | f05_modeling:v506=42 |
| v706 | bands | f02_events | v200 | [40, 60, 80] | - | solo_ancestro; cambios_en=- | - | v200=[40, 60, 80] | - | - | - | - | - | f02_events:v200=[40, 60, 80] |
| v706 | cleaning | f01_explore | v100 | basic | - | solo_ancestro; cambios_en=- | v100=basic | - | - | - | - | - | - | f01_explore:v100=basic |
| v706 | decision_threshold | f07_modval | v706 | 0.6166953444480896 | 0.6166953444480896 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v706=0.6166953444480896 | f07_modval:v706=0.6166953444480896 |
| v706 | deployment.memory_limit_bytes | f06_quant | v606 | 327680 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v606=327680 | - | f06_quant:v606=327680 |
| v706 | deployment.require_int8 | f06_quant | v606 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v606=true | - | f06_quant:v606=true |
| v706 | deployment.runtime | f06_quant | v606 | esp-tflite-micro | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v606=esp-tflite-micro | - | f06_quant:v606=esp-tflite-micro |
| v706 | deployment.runtime_version | f06_quant | v606 | 1.3.3 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v606=1.3.3 | - | f06_quant:v606=1.3.3 |
| v706 | deployment.target | f06_quant | v606 | esp32 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v606=esp32 | - | f06_quant:v606=esp32 |
| v706 | eedu.layout | f06_quant | v606 | default | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v606=default | - | f06_quant:v606=default |
| v706 | eedu.version | f06_quant | v606 | 1.0 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v606=1.0 | - | f06_quant:v606=1.0 |
| v706 | evaluation.split.test | f05_modeling | v506 | 0.15 | - | solo_ancestro; cambios_en=- | - | - | - | - | v506=0.15 | - | - | f05_modeling:v506=0.15 |
| v706 | evaluation.split.train | f05_modeling | v506 | 0.7 | - | solo_ancestro; cambios_en=- | - | - | - | - | v506=0.7 | - | - | f05_modeling:v506=0.7 |
| v706 | evaluation.split.val | f05_modeling | v506 | 0.15 | - | solo_ancestro; cambios_en=- | - | - | - | - | v506=0.15 | - | - | f05_modeling:v506=0.15 |
| v706 | event_type_count | f04_targets | v406 | 221 | 221 | heredado_sin_cambios; cambios_en=- | - | - | - | v406=221 | v506=221 | v606=221 | v706=221 | f04_targets:v406=221 -> f05_modeling:v506=221 -> f06_quant:v606=221 -> f07_modval:v706=221 |
| v706 | imbalance_max_majority_samples | f05_modeling | v506 | 20000 | - | solo_ancestro; cambios_en=- | - | - | - | - | v506=20000 | - | - | f05_modeling:v506=20000 |
| v706 | imbalance_strategy | f05_modeling | v506 | rare_events | - | solo_ancestro; cambios_en=- | - | - | - | - | v506=rare_events | - | - | f05_modeling:v506=rare_events |
| v706 | model_family | f05_modeling | v506 | cnn1d | - | solo_ancestro; cambios_en=- | - | - | - | - | v506=cnn1d | - | - | f05_modeling:v506=cnn1d |
| v706 | nan_mode | f02_events | v200 | keep | - | solo_ancestro; cambios_en=f03_windows:v300 | - | v200=keep | v300=discard | - | - | - | - | f02_events:v200=keep -> f03_windows:v300=discard |
| v706 | nan_values | f01_explore | v100 | [-999999] | - | solo_ancestro; cambios_en=- | v100=[-999999] | - | - | - | - | - | - | f01_explore:v100=[-999999] |
| v706 | parent_variant | f03_windows | v300 | v200 | v606 | redefinido_en_linaje; cambios_en=f04_targets:v406, f05_modeling:v506, f06_quant:v606, f07_modval:v706 | - | - | v300=v200 | v406=v300 | v506=v406 | v606=v506 | v706=v606 | f03_windows:v300=v200 -> f04_targets:v406=v300 -> f05_modeling:v506=v406 -> f06_quant:v606=v506 -> f07_modval:v706=v606 |
| v706 | platform | f07_modval | v706 | esp32 | esp32 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v706=esp32 | f07_modval:v706=esp32 |
| v706 | prediction_name | f04_targets | v406 | FC_Active_Power_FC_END_Set_any-to-80_100 | FC_Active_Power_FC_END_Set_any-to-80_100 | heredado_sin_cambios; cambios_en=- | - | - | - | v406=FC_Active_Power_FC_END_Set_any-to-80_100 | v506=FC_Active_Power_FC_END_Set_any-to-80_100 | v606=FC_Active_Power_FC_END_Set_any-to-80_100 | v706=FC_Active_Power_FC_END_Set_any-to-80_100 | f04_targets:v406=FC_Active_Power_FC_END_Set_any-to-80_100 -> f05_modeling:v506=FC_Active_Power_FC_END_Set_any-to-80_100 -> f06_quant:v606=FC_Active_Power_FC_END_Set_any-to-80_100 -> f07_modval:v706=FC_Active_Power_FC_END_Set_any-to-80_100 |
| v706 | quantization.calibration_samples | f06_quant | v606 | 512 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v606=512 | - | f06_quant:v606=512 |
| v706 | quantization.keep_float_fallback | f06_quant | v606 | false | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v606=false | - | f06_quant:v606=false |
| v706 | quantization.per_channel | f06_quant | v606 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v606=true | - | f06_quant:v606=true |
| v706 | quantization.representative_dataset | f06_quant | v606 | val | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v606=val | - | f06_quant:v606=val |
| v706 | quantization.symmetric_int8 | f06_quant | v606 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v606=true | - | f06_quant:v606=true |
| v706 | quantization.tflite_optimization | f06_quant | v606 | DEFAULT | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v606=DEFAULT | - | f06_quant:v606=DEFAULT |
| v706 | raw_path | f01_explore | v100 | data/raw.csv | - | solo_ancestro; cambios_en=- | v100=data/raw.csv | - | - | - | - | - | - | f01_explore:v100=data/raw.csv |
| v706 | search_space.cnn1d.embed_dim | f05_modeling | v506 | [64] | - | solo_ancestro; cambios_en=- | - | - | - | - | v506=[64] | - | - | f05_modeling:v506=[64] |
| v706 | search_space.cnn1d.filters | f05_modeling | v506 | [64, 128] | - | solo_ancestro; cambios_en=- | - | - | - | - | v506=[64, 128] | - | - | f05_modeling:v506=[64, 128] |
| v706 | search_space.cnn1d.kernel_size | f05_modeling | v506 | [3, 5] | - | solo_ancestro; cambios_en=- | - | - | - | - | v506=[3, 5] | - | - | f05_modeling:v506=[3, 5] |
| v706 | search_space.common.batch_size | f05_modeling | v506 | [128, 256] | - | solo_ancestro; cambios_en=- | - | - | - | - | v506=[128, 256] | - | - | f05_modeling:v506=[128, 256] |
| v706 | search_space.common.dropout | f05_modeling | v506 | [0.0, 0.2] | - | solo_ancestro; cambios_en=- | - | - | - | - | v506=[0.0, 0.2] | - | - | f05_modeling:v506=[0.0, 0.2] |
| v706 | search_space.common.learning_rate | f05_modeling | v506 | [0.001, 0.0005] | - | solo_ancestro; cambios_en=- | - | - | - | - | v506=[0.001, 0.0005] | - | - | f05_modeling:v506=[0.001, 0.0005] |
| v706 | search_space.common.n_layers | f05_modeling | v506 | [1, 2] | - | solo_ancestro; cambios_en=- | - | - | - | - | v506=[1, 2] | - | - | f05_modeling:v506=[1, 2] |
| v706 | search_space.common.units | f05_modeling | v506 | [64, 128] | - | solo_ancestro; cambios_en=- | - | - | - | - | v506=[64, 128] | - | - | f05_modeling:v506=[64, 128] |
| v706 | search_space.sequence_embedding.embed_dim | f05_modeling | v506 | [64, 128] | - | solo_ancestro; cambios_en=- | - | - | - | - | v506=[64, 128] | - | - | f05_modeling:v506=[64, 128] |
| v706 | strategy | f02_events | v200 | transitions | - | solo_ancestro; cambios_en=- | - | v200=transitions | - | - | - | - | - | f02_events:v200=transitions |
| v706 | target_event_types | f04_targets | v406 | ["FC_Active_Power_FC_END_Set_0_40-to-80_100", "FC_Active_Power_FC_END_Set_40_60-to-80_100", "FC_Active_Power_FC_END_Set_60_80-to-80_100"] | - | solo_ancestro; cambios_en=- | - | - | - | v406=["FC_Active_Power_FC_END_Set_0_40-to-80_100", "FC_Active_Power_FC_END_Set_40_60-to-80_100", "FC_Active_Power_FC_END_Set_60_80-to-80_100"] | - | - | - | f04_targets:v406=["FC_Active_Power_FC_END_Set_0_40-to-80_100", "FC_Active_Power_FC_END_Set_40_60-to-80_100", "FC_Active_Power_FC_END_Set_60_80-to-80_100"] |
| v706 | target_operator | f04_targets | v406 | OR | - | solo_ancestro; cambios_en=- | - | - | - | v406=OR | - | - | - | f04_targets:v406=OR |
| v706 | thresholding.grid_points | f06_quant | v606 | 101 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v606=101 | - | f06_quant:v606=101 |
| v706 | thresholding.maximize_metric | f06_quant | v606 | recall | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v606=recall | - | f06_quant:v606=recall |
| v706 | thresholding.strategy | f06_quant | v606 | recalibrate_on_quantized | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v606=recalibrate_on_quantized | - | f06_quant:v606=recalibrate_on_quantized |
| v706 | time_scale_factor | f07_modval | v706 | 0.01 | 0.01 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v706=0.01 | f07_modval:v706=0.01 |
| v706 | training.epochs | f05_modeling | v506 | 20 | - | solo_ancestro; cambios_en=- | - | - | - | - | v506=20 | - | - | f05_modeling:v506=20 |
| v706 | training.max_samples | f05_modeling | v506 | - | - | solo_ancestro; cambios_en=- | - | - | - | - | v506=- | - | - | f05_modeling:v506=- |
| v706 | window_strategy | f03_windows | v300 | synchro | - | solo_ancestro; cambios_en=- | - | - | v300=synchro | - | - | - | - | f03_windows:v300=synchro |
| v707 | LT | f03_windows | v300 | 1 | 1 | heredado_sin_cambios; cambios_en=- | - | - | v300=1 | v407=1 | v507=1 | v607=1 | v707=1 | f03_windows:v300=1 -> f04_targets:v407=1 -> f05_modeling:v507=1 -> f06_quant:v607=1 -> f07_modval:v707=1 |
| v707 | MTI_MS | f07_modval | v707 | 100 | 100 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v707=100 | f07_modval:v707=100 |
| v707 | OW | f03_windows | v300 | 6 | 6 | heredado_sin_cambios; cambios_en=- | - | - | v300=6 | v407=6 | v507=6 | v607=6 | v707=6 | f03_windows:v300=6 -> f04_targets:v407=6 -> f05_modeling:v507=6 -> f06_quant:v607=6 -> f07_modval:v707=6 |
| v707 | PW | f03_windows | v300 | 1 | 1 | heredado_sin_cambios; cambios_en=- | - | - | v300=1 | v407=1 | v507=1 | v607=1 | v707=1 | f03_windows:v300=1 -> f04_targets:v407=1 -> f05_modeling:v507=1 -> f06_quant:v607=1 -> f07_modval:v707=1 |
| v707 | Tu | f02_events | v200 | 10 | 10 | heredado_sin_cambios; cambios_en=- | - | v200=10 | v300=10 | v407=10 | v507=10 | v607=10 | v707=10 | f02_events:v200=10 -> f03_windows:v300=10 -> f04_targets:v407=10 -> f05_modeling:v507=10 -> f06_quant:v607=10 -> f07_modval:v707=10 |
| v707 | automl.enabled | f05_modeling | v507 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | v507=true | - | - | f05_modeling:v507=true |
| v707 | automl.max_trials | f05_modeling | v507 | 5 | - | solo_ancestro; cambios_en=- | - | - | - | - | v507=5 | - | - | f05_modeling:v507=5 |
| v707 | automl.seed | f05_modeling | v507 | 42 | - | solo_ancestro; cambios_en=- | - | - | - | - | v507=42 | - | - | f05_modeling:v507=42 |
| v707 | bands | f02_events | v200 | [40, 60, 80] | - | solo_ancestro; cambios_en=- | - | v200=[40, 60, 80] | - | - | - | - | - | f02_events:v200=[40, 60, 80] |
| v707 | cleaning | f01_explore | v100 | basic | - | solo_ancestro; cambios_en=- | v100=basic | - | - | - | - | - | - | f01_explore:v100=basic |
| v707 | decision_threshold | f07_modval | v707 | 0.3615439832210541 | 0.3615439832210541 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v707=0.3615439832210541 | f07_modval:v707=0.3615439832210541 |
| v707 | deployment.memory_limit_bytes | f06_quant | v607 | 327680 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v607=327680 | - | f06_quant:v607=327680 |
| v707 | deployment.require_int8 | f06_quant | v607 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v607=true | - | f06_quant:v607=true |
| v707 | deployment.runtime | f06_quant | v607 | esp-tflite-micro | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v607=esp-tflite-micro | - | f06_quant:v607=esp-tflite-micro |
| v707 | deployment.runtime_version | f06_quant | v607 | 1.3.3 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v607=1.3.3 | - | f06_quant:v607=1.3.3 |
| v707 | deployment.target | f06_quant | v607 | esp32 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v607=esp32 | - | f06_quant:v607=esp32 |
| v707 | eedu.layout | f06_quant | v607 | default | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v607=default | - | f06_quant:v607=default |
| v707 | eedu.version | f06_quant | v607 | 1.0 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v607=1.0 | - | f06_quant:v607=1.0 |
| v707 | evaluation.split.test | f05_modeling | v507 | 0.15 | - | solo_ancestro; cambios_en=- | - | - | - | - | v507=0.15 | - | - | f05_modeling:v507=0.15 |
| v707 | evaluation.split.train | f05_modeling | v507 | 0.7 | - | solo_ancestro; cambios_en=- | - | - | - | - | v507=0.7 | - | - | f05_modeling:v507=0.7 |
| v707 | evaluation.split.val | f05_modeling | v507 | 0.15 | - | solo_ancestro; cambios_en=- | - | - | - | - | v507=0.15 | - | - | f05_modeling:v507=0.15 |
| v707 | event_type_count | f04_targets | v407 | 221 | 221 | heredado_sin_cambios; cambios_en=- | - | - | - | v407=221 | v507=221 | v607=221 | v707=221 | f04_targets:v407=221 -> f05_modeling:v507=221 -> f06_quant:v607=221 -> f07_modval:v707=221 |
| v707 | imbalance_max_majority_samples | f05_modeling | v507 | 20000 | - | solo_ancestro; cambios_en=- | - | - | - | - | v507=20000 | - | - | f05_modeling:v507=20000 |
| v707 | imbalance_strategy | f05_modeling | v507 | rare_events | - | solo_ancestro; cambios_en=- | - | - | - | - | v507=rare_events | - | - | f05_modeling:v507=rare_events |
| v707 | model_family | f05_modeling | v507 | cnn1d | - | solo_ancestro; cambios_en=- | - | - | - | - | v507=cnn1d | - | - | f05_modeling:v507=cnn1d |
| v707 | nan_mode | f02_events | v200 | keep | - | solo_ancestro; cambios_en=f03_windows:v300 | - | v200=keep | v300=discard | - | - | - | - | f02_events:v200=keep -> f03_windows:v300=discard |
| v707 | nan_values | f01_explore | v100 | [-999999] | - | solo_ancestro; cambios_en=- | v100=[-999999] | - | - | - | - | - | - | f01_explore:v100=[-999999] |
| v707 | parent_variant | f03_windows | v300 | v200 | v607 | redefinido_en_linaje; cambios_en=f04_targets:v407, f05_modeling:v507, f06_quant:v607, f07_modval:v707 | - | - | v300=v200 | v407=v300 | v507=v407 | v607=v507 | v707=v607 | f03_windows:v300=v200 -> f04_targets:v407=v300 -> f05_modeling:v507=v407 -> f06_quant:v607=v507 -> f07_modval:v707=v607 |
| v707 | platform | f07_modval | v707 | esp32 | esp32 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v707=esp32 | f07_modval:v707=esp32 |
| v707 | prediction_name | f04_targets | v407 | FC_Active_Power_any-to-80_100 | FC_Active_Power_any-to-80_100 | heredado_sin_cambios; cambios_en=- | - | - | - | v407=FC_Active_Power_any-to-80_100 | v507=FC_Active_Power_any-to-80_100 | v607=FC_Active_Power_any-to-80_100 | v707=FC_Active_Power_any-to-80_100 | f04_targets:v407=FC_Active_Power_any-to-80_100 -> f05_modeling:v507=FC_Active_Power_any-to-80_100 -> f06_quant:v607=FC_Active_Power_any-to-80_100 -> f07_modval:v707=FC_Active_Power_any-to-80_100 |
| v707 | quantization.calibration_samples | f06_quant | v607 | 512 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v607=512 | - | f06_quant:v607=512 |
| v707 | quantization.keep_float_fallback | f06_quant | v607 | false | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v607=false | - | f06_quant:v607=false |
| v707 | quantization.per_channel | f06_quant | v607 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v607=true | - | f06_quant:v607=true |
| v707 | quantization.representative_dataset | f06_quant | v607 | val | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v607=val | - | f06_quant:v607=val |
| v707 | quantization.symmetric_int8 | f06_quant | v607 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v607=true | - | f06_quant:v607=true |
| v707 | quantization.tflite_optimization | f06_quant | v607 | DEFAULT | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v607=DEFAULT | - | f06_quant:v607=DEFAULT |
| v707 | raw_path | f01_explore | v100 | data/raw.csv | - | solo_ancestro; cambios_en=- | v100=data/raw.csv | - | - | - | - | - | - | f01_explore:v100=data/raw.csv |
| v707 | search_space.cnn1d.embed_dim | f05_modeling | v507 | [64] | - | solo_ancestro; cambios_en=- | - | - | - | - | v507=[64] | - | - | f05_modeling:v507=[64] |
| v707 | search_space.cnn1d.filters | f05_modeling | v507 | [64, 128] | - | solo_ancestro; cambios_en=- | - | - | - | - | v507=[64, 128] | - | - | f05_modeling:v507=[64, 128] |
| v707 | search_space.cnn1d.kernel_size | f05_modeling | v507 | [3, 5] | - | solo_ancestro; cambios_en=- | - | - | - | - | v507=[3, 5] | - | - | f05_modeling:v507=[3, 5] |
| v707 | search_space.common.batch_size | f05_modeling | v507 | [128, 256] | - | solo_ancestro; cambios_en=- | - | - | - | - | v507=[128, 256] | - | - | f05_modeling:v507=[128, 256] |
| v707 | search_space.common.dropout | f05_modeling | v507 | [0.0, 0.2] | - | solo_ancestro; cambios_en=- | - | - | - | - | v507=[0.0, 0.2] | - | - | f05_modeling:v507=[0.0, 0.2] |
| v707 | search_space.common.learning_rate | f05_modeling | v507 | [0.001, 0.0005] | - | solo_ancestro; cambios_en=- | - | - | - | - | v507=[0.001, 0.0005] | - | - | f05_modeling:v507=[0.001, 0.0005] |
| v707 | search_space.common.n_layers | f05_modeling | v507 | [1, 2] | - | solo_ancestro; cambios_en=- | - | - | - | - | v507=[1, 2] | - | - | f05_modeling:v507=[1, 2] |
| v707 | search_space.common.units | f05_modeling | v507 | [64, 128] | - | solo_ancestro; cambios_en=- | - | - | - | - | v507=[64, 128] | - | - | f05_modeling:v507=[64, 128] |
| v707 | search_space.sequence_embedding.embed_dim | f05_modeling | v507 | [64, 128] | - | solo_ancestro; cambios_en=- | - | - | - | - | v507=[64, 128] | - | - | f05_modeling:v507=[64, 128] |
| v707 | strategy | f02_events | v200 | transitions | - | solo_ancestro; cambios_en=- | - | v200=transitions | - | - | - | - | - | f02_events:v200=transitions |
| v707 | target_event_types | f04_targets | v407 | ["FC_Active_Power_0_40-to-80_100", "FC_Active_Power_40_60-to-80_100", "FC_Active_Power_60_80-to-80_100"] | - | solo_ancestro; cambios_en=- | - | - | - | v407=["FC_Active_Power_0_40-to-80_100", "FC_Active_Power_40_60-to-80_100", "FC_Active_Power_60_80-to-80_100"] | - | - | - | f04_targets:v407=["FC_Active_Power_0_40-to-80_100", "FC_Active_Power_40_60-to-80_100", "FC_Active_Power_60_80-to-80_100"] |
| v707 | target_operator | f04_targets | v407 | OR | - | solo_ancestro; cambios_en=- | - | - | - | v407=OR | - | - | - | f04_targets:v407=OR |
| v707 | thresholding.grid_points | f06_quant | v607 | 101 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v607=101 | - | f06_quant:v607=101 |
| v707 | thresholding.maximize_metric | f06_quant | v607 | recall | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v607=recall | - | f06_quant:v607=recall |
| v707 | thresholding.strategy | f06_quant | v607 | recalibrate_on_quantized | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v607=recalibrate_on_quantized | - | f06_quant:v607=recalibrate_on_quantized |
| v707 | time_scale_factor | f07_modval | v707 | 0.01 | 0.01 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v707=0.01 | f07_modval:v707=0.01 |
| v707 | training.epochs | f05_modeling | v507 | 20 | - | solo_ancestro; cambios_en=- | - | - | - | - | v507=20 | - | - | f05_modeling:v507=20 |
| v707 | training.max_samples | f05_modeling | v507 | - | - | solo_ancestro; cambios_en=- | - | - | - | - | v507=- | - | - | f05_modeling:v507=- |
| v707 | window_strategy | f03_windows | v300 | synchro | - | solo_ancestro; cambios_en=- | - | - | v300=synchro | - | - | - | - | f03_windows:v300=synchro |
| v708 | LT | f03_windows | v300 | 1 | 1 | heredado_sin_cambios; cambios_en=- | - | - | v300=1 | v408=1 | v508=1 | v608=1 | v708=1 | f03_windows:v300=1 -> f04_targets:v408=1 -> f05_modeling:v508=1 -> f06_quant:v608=1 -> f07_modval:v708=1 |
| v708 | MTI_MS | f07_modval | v708 | 100 | 100 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v708=100 | f07_modval:v708=100 |
| v708 | OW | f03_windows | v300 | 6 | 6 | heredado_sin_cambios; cambios_en=- | - | - | v300=6 | v408=6 | v508=6 | v608=6 | v708=6 | f03_windows:v300=6 -> f04_targets:v408=6 -> f05_modeling:v508=6 -> f06_quant:v608=6 -> f07_modval:v708=6 |
| v708 | PW | f03_windows | v300 | 1 | 1 | heredado_sin_cambios; cambios_en=- | - | - | v300=1 | v408=1 | v508=1 | v608=1 | v708=1 | f03_windows:v300=1 -> f04_targets:v408=1 -> f05_modeling:v508=1 -> f06_quant:v608=1 -> f07_modval:v708=1 |
| v708 | Tu | f02_events | v200 | 10 | 10 | heredado_sin_cambios; cambios_en=- | - | v200=10 | v300=10 | v408=10 | v508=10 | v608=10 | v708=10 | f02_events:v200=10 -> f03_windows:v300=10 -> f04_targets:v408=10 -> f05_modeling:v508=10 -> f06_quant:v608=10 -> f07_modval:v708=10 |
| v708 | automl.enabled | f05_modeling | v508 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | v508=true | - | - | f05_modeling:v508=true |
| v708 | automl.max_trials | f05_modeling | v508 | 5 | - | solo_ancestro; cambios_en=- | - | - | - | - | v508=5 | - | - | f05_modeling:v508=5 |
| v708 | automl.seed | f05_modeling | v508 | 42 | - | solo_ancestro; cambios_en=- | - | - | - | - | v508=42 | - | - | f05_modeling:v508=42 |
| v708 | bands | f02_events | v200 | [40, 60, 80] | - | solo_ancestro; cambios_en=- | - | v200=[40, 60, 80] | - | - | - | - | - | f02_events:v200=[40, 60, 80] |
| v708 | cleaning | f01_explore | v100 | basic | - | solo_ancestro; cambios_en=- | v100=basic | - | - | - | - | - | - | f01_explore:v100=basic |
| v708 | deployment.memory_limit_bytes | f06_quant | v608 | 327680 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v608=327680 | - | f06_quant:v608=327680 |
| v708 | deployment.require_int8 | f06_quant | v608 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v608=true | - | f06_quant:v608=true |
| v708 | deployment.runtime | f06_quant | v608 | esp-tflite-micro | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v608=esp-tflite-micro | - | f06_quant:v608=esp-tflite-micro |
| v708 | deployment.runtime_version | f06_quant | v608 | 1.3.3 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v608=1.3.3 | - | f06_quant:v608=1.3.3 |
| v708 | deployment.target | f06_quant | v608 | esp32 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v608=esp32 | - | f06_quant:v608=esp32 |
| v708 | eedu.layout | f06_quant | v608 | default | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v608=default | - | f06_quant:v608=default |
| v708 | eedu.version | f06_quant | v608 | 1.0 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v608=1.0 | - | f06_quant:v608=1.0 |
| v708 | evaluation.split.test | f05_modeling | v508 | 0.15 | - | solo_ancestro; cambios_en=- | - | - | - | - | v508=0.15 | - | - | f05_modeling:v508=0.15 |
| v708 | evaluation.split.train | f05_modeling | v508 | 0.7 | - | solo_ancestro; cambios_en=- | - | - | - | - | v508=0.7 | - | - | f05_modeling:v508=0.7 |
| v708 | evaluation.split.val | f05_modeling | v508 | 0.15 | - | solo_ancestro; cambios_en=- | - | - | - | - | v508=0.15 | - | - | f05_modeling:v508=0.15 |
| v708 | event_type_count | f04_targets | v408 | 221 | 221 | heredado_sin_cambios; cambios_en=- | - | - | - | v408=221 | v508=221 | v608=221 | v708=221 | f04_targets:v408=221 -> f05_modeling:v508=221 -> f06_quant:v608=221 -> f07_modval:v708=221 |
| v708 | imbalance_max_majority_samples | f05_modeling | v508 | 20000 | - | solo_ancestro; cambios_en=- | - | - | - | - | v508=20000 | - | - | f05_modeling:v508=20000 |
| v708 | imbalance_strategy | f05_modeling | v508 | rare_events | - | solo_ancestro; cambios_en=- | - | - | - | - | v508=rare_events | - | - | f05_modeling:v508=rare_events |
| v708 | model_family | f05_modeling | v508 | cnn1d | - | solo_ancestro; cambios_en=- | - | - | - | - | v508=cnn1d | - | - | f05_modeling:v508=cnn1d |
| v708 | nan_mode | f02_events | v200 | keep | - | solo_ancestro; cambios_en=f03_windows:v300 | - | v200=keep | v300=discard | - | - | - | - | f02_events:v200=keep -> f03_windows:v300=discard |
| v708 | nan_values | f01_explore | v100 | [-999999] | - | solo_ancestro; cambios_en=- | v100=[-999999] | - | - | - | - | - | - | f01_explore:v100=[-999999] |
| v708 | parent_variant | f03_windows | v300 | v200 | v608 | redefinido_en_linaje; cambios_en=f04_targets:v408, f05_modeling:v508, f06_quant:v608, f07_modval:v708 | - | - | v300=v200 | v408=v300 | v508=v408 | v608=v508 | v708=v608 | f03_windows:v300=v200 -> f04_targets:v408=v300 -> f05_modeling:v508=v408 -> f06_quant:v608=v508 -> f07_modval:v708=v608 |
| v708 | platform | f07_modval | v708 | esp32 | esp32 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v708=esp32 | f07_modval:v708=esp32 |
| v708 | prediction_name | f04_targets | v408 | MG-LV-MSB_AC_Voltage_any-to-80_100 | MG-LV-MSB_AC_Voltage_any-to-80_100 | heredado_sin_cambios; cambios_en=- | - | - | - | v408=MG-LV-MSB_AC_Voltage_any-to-80_100 | v508=MG-LV-MSB_AC_Voltage_any-to-80_100 | v608=MG-LV-MSB_AC_Voltage_any-to-80_100 | v708=MG-LV-MSB_AC_Voltage_any-to-80_100 | f04_targets:v408=MG-LV-MSB_AC_Voltage_any-to-80_100 -> f05_modeling:v508=MG-LV-MSB_AC_Voltage_any-to-80_100 -> f06_quant:v608=MG-LV-MSB_AC_Voltage_any-to-80_100 -> f07_modval:v708=MG-LV-MSB_AC_Voltage_any-to-80_100 |
| v708 | quantization.calibration_samples | f06_quant | v608 | 512 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v608=512 | - | f06_quant:v608=512 |
| v708 | quantization.keep_float_fallback | f06_quant | v608 | false | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v608=false | - | f06_quant:v608=false |
| v708 | quantization.per_channel | f06_quant | v608 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v608=true | - | f06_quant:v608=true |
| v708 | quantization.representative_dataset | f06_quant | v608 | val | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v608=val | - | f06_quant:v608=val |
| v708 | quantization.symmetric_int8 | f06_quant | v608 | true | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v608=true | - | f06_quant:v608=true |
| v708 | quantization.tflite_optimization | f06_quant | v608 | DEFAULT | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v608=DEFAULT | - | f06_quant:v608=DEFAULT |
| v708 | raw_path | f01_explore | v100 | data/raw.csv | - | solo_ancestro; cambios_en=- | v100=data/raw.csv | - | - | - | - | - | - | f01_explore:v100=data/raw.csv |
| v708 | search_space.cnn1d.embed_dim | f05_modeling | v508 | [64] | - | solo_ancestro; cambios_en=- | - | - | - | - | v508=[64] | - | - | f05_modeling:v508=[64] |
| v708 | search_space.cnn1d.filters | f05_modeling | v508 | [64, 128] | - | solo_ancestro; cambios_en=- | - | - | - | - | v508=[64, 128] | - | - | f05_modeling:v508=[64, 128] |
| v708 | search_space.cnn1d.kernel_size | f05_modeling | v508 | [3, 5] | - | solo_ancestro; cambios_en=- | - | - | - | - | v508=[3, 5] | - | - | f05_modeling:v508=[3, 5] |
| v708 | search_space.common.batch_size | f05_modeling | v508 | [128, 256] | - | solo_ancestro; cambios_en=- | - | - | - | - | v508=[128, 256] | - | - | f05_modeling:v508=[128, 256] |
| v708 | search_space.common.dropout | f05_modeling | v508 | [0.0, 0.2] | - | solo_ancestro; cambios_en=- | - | - | - | - | v508=[0.0, 0.2] | - | - | f05_modeling:v508=[0.0, 0.2] |
| v708 | search_space.common.learning_rate | f05_modeling | v508 | [0.001, 0.0005] | - | solo_ancestro; cambios_en=- | - | - | - | - | v508=[0.001, 0.0005] | - | - | f05_modeling:v508=[0.001, 0.0005] |
| v708 | search_space.common.n_layers | f05_modeling | v508 | [1, 2] | - | solo_ancestro; cambios_en=- | - | - | - | - | v508=[1, 2] | - | - | f05_modeling:v508=[1, 2] |
| v708 | search_space.common.units | f05_modeling | v508 | [64, 128] | - | solo_ancestro; cambios_en=- | - | - | - | - | v508=[64, 128] | - | - | f05_modeling:v508=[64, 128] |
| v708 | search_space.sequence_embedding.embed_dim | f05_modeling | v508 | [64, 128] | - | solo_ancestro; cambios_en=- | - | - | - | - | v508=[64, 128] | - | - | f05_modeling:v508=[64, 128] |
| v708 | strategy | f02_events | v200 | transitions | - | solo_ancestro; cambios_en=- | - | v200=transitions | - | - | - | - | - | f02_events:v200=transitions |
| v708 | target_event_types | f04_targets | v408 | ["MG-LV-MSB_AC_Voltage_0_40-to-80_100", "MG-LV-MSB_AC_Voltage_40_60-to-80_100", "MG-LV-MSB_AC_Voltage_60_80-to-80_100"] | - | solo_ancestro; cambios_en=- | - | - | - | v408=["MG-LV-MSB_AC_Voltage_0_40-to-80_100", "MG-LV-MSB_AC_Voltage_40_60-to-80_100", "MG-LV-MSB_AC_Voltage_60_80-to-80_100"] | - | - | - | f04_targets:v408=["MG-LV-MSB_AC_Voltage_0_40-to-80_100", "MG-LV-MSB_AC_Voltage_40_60-to-80_100", "MG-LV-MSB_AC_Voltage_60_80-to-80_100"] |
| v708 | target_operator | f04_targets | v408 | OR | - | solo_ancestro; cambios_en=- | - | - | - | v408=OR | - | - | - | f04_targets:v408=OR |
| v708 | thresholding.grid_points | f06_quant | v608 | 101 | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v608=101 | - | f06_quant:v608=101 |
| v708 | thresholding.maximize_metric | f06_quant | v608 | recall | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v608=recall | - | f06_quant:v608=recall |
| v708 | thresholding.strategy | f06_quant | v608 | recalibrate_on_quantized | - | solo_ancestro; cambios_en=- | - | - | - | - | - | v608=recalibrate_on_quantized | - | f06_quant:v608=recalibrate_on_quantized |
| v708 | time_scale_factor | f07_modval | v708 | 0.01 | 0.01 | generado_en_hoja; cambios_en=- | - | - | - | - | - | - | v708=0.01 | f07_modval:v708=0.01 |
| v708 | training.epochs | f05_modeling | v508 | 20 | - | solo_ancestro; cambios_en=- | - | - | - | - | v508=20 | - | - | f05_modeling:v508=20 |
| v708 | training.max_samples | f05_modeling | v508 | - | - | solo_ancestro; cambios_en=- | - | - | - | - | v508=- | - | - | f05_modeling:v508=- |
| v708 | window_strategy | f03_windows | v300 | synchro | - | solo_ancestro; cambios_en=- | - | - | v300=synchro | - | - | - | - | f03_windows:v300=synchro |
