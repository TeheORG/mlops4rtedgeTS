# MLOps4RT-Edge

Pipeline MLOps por fases para llevar una serie temporal numerica hasta modelos cuantizados y validacion en plataforma edge.

Este repositorio contiene codigo, automatizacion, schemas y templates. Los datasets, modelos, logs, builds ESP-IDF, caches DVC y estado de ejecuciones son artefactos locales y viven bajo `executions/`.

## Que Hace

El flujo completo tiene ocho fases:

| Fase | Nombre | Objetivo | Entrada principal | Salida principal |
| --- | --- | --- | --- | --- |
| F01 | `f01_explore` | Explorar y limpiar el dataset bruto | CSV/raw | dataset limpio parquet |
| F02 | `f02_events` | Seleccionar una medida y construir serie univariable | F01 | `02_series.parquet` |
| F03 | `f03_windows` | Crear ventanas temporales numericas | F02 | `03_windows.parquet` con `OW_values`/`PW_values` |
| F04 | `f04_targets` | Etiquetar ventanas por umbral o transicion | F03 | `04_targets.parquet` con `OW_values`/`label` |
| F05 | `f05_modeling` | Entrenar modelos sobre secuencias numericas | F04 | modelo Keras y metricas |
| F06 | `f06_quant` | Cuantizar y empaquetar para edge | F05 | `.tflite`, manifest y reporte |
| F07 | `f07_modval` | Validar un modelo en edge | F06 | runtime metrics y perfil del modelo |
| F08 | `f08_sysval` | Validar una configuracion multi-modelo | F07 | seleccion, firmware y metricas de sistema |

Cada fase trabaja con variantes. Una variante se guarda en:

```text
executions/<fase>/<variante>/
```

Cada variante contiene como minimo:

- `params.yaml`: parametros efectivos de la variante.
- `metadata.yaml`: estado de ciclo de vida.
- `outputs.yaml`: artefactos, exports y metricas de la fase.

El contrato de parametros, artefactos, exports y metricas esta declarado en `scripts/traceability_schema.yaml`.

## Idea Principal Del Repositorio

El flujo principal ya no usa catalogos ni IDs de eventos. Trabaja con una sola medida numerica:

```text
F02: value
F03: OW_values, PW_values
F04: OW_values, label
F05: secuencia numerica normalizada
F06: modelo TFLite INT8
F07/F08: entrada int8 cuantizada en edge
```

La entrada real del modelo cuantizado en edge es `int8`. Para reproducirla, F07 y F08 aplican la misma receta guardada por F06:

```text
OW_values raw
-> padding/truncado a input_max_len
-> normalizacion: (x - normalization_mean) / normalization_std
-> cuantizacion TFLite: round(normalized / input_quant_scale + input_quant_zero_point)
-> int8
-> tensor del modelo
```

Todavia hay nombres legacy en el firmware ESP32 como `event_t`, `memory_events.h` o `events_mgr`, pero en este repositorio ya no representan eventos de dominio. Son buffers de entrada temporal reutilizados por la plantilla edge.

## Requisitos

Minimos:

- Python 3.11
- GNU Make
- Git

Recomendados:

- Docker, necesario para F05/F06 y para el runner ESP32 virtual reproducible.
- DVC, si se registran o descargan artefactos pesados.
- MLflow, si se quiere tracking de entrenamientos.
- ESP-IDF/placa ESP32 solo si se ejecuta fuera del runner Docker.

En Windows se recomienda ejecutar `make` desde Git Bash o desde el entorno que ya use el proyecto.

## Setup

```bash
make setup SETUP_CFG=setup/local.yaml
make check-setup
```

Ayuda general:

```bash
make help
```

Ayuda por fase:

```bash
make help1
make help2
make help3
make help4
make help5
make help6
make help7
make help8
```

Limpiar setup local:

```bash
make clean-setup
```

## Patron De Uso

Para cada fase:

```bash
make variantN ...
make scriptN VARIANT=vN_XXXX
make checkN VARIANT=vN_XXXX
make registerN VARIANT=vN_XXXX
```

Los IDs cortos tambien se aceptan y se normalizan por fase. Por ejemplo, `VARIANT=0` puede convertirse en `v7_0000` cuando se usa con F07.

## Ejecucion Completa Por Fases

### F01: explorar y limpiar datos

```bash
make variant1 VARIANT=v1_0000 RAW=data/raw.csv CLEANING=basic NAN_VALUES='[-999999]'
make script1 VARIANT=v1_0000
make check1 VARIANT=v1_0000
make register1 VARIANT=v1_0000
```

Parametros principales:

- `RAW`: ruta al dataset bruto.
- `CLEANING`: `none`, `basic` o `strict`.
- `NAN_VALUES`: lista opcional de valores tratados como NaN.
- `ERROR_VALUES`: diccionario opcional por columna.
- `FIRST_LINE`, `MAX_LINES`: recorte opcional de lectura.

Salidas principales: dataset limpio parquet, reporte HTML y exports `Tu`, `n_rows`, `n_columns`, `measure_cols`.

### F02: construir serie temporal univariable

```bash
make variant2 VARIANT=v2_0000 PARENT=v1_0000 MEASURE=Battery_Active_Power
make script2 VARIANT=v2_0000
make check2 VARIANT=v2_0000
make register2 VARIANT=v2_0000
```

F02 valida que `MEASURE` exista entre las `measure_cols` exportadas por F01.

Parametros principales:

- `PARENT`: variante F01.
- `MEASURE`: columna numerica elegida.
- `TU`: opcional; si no se redefine, se hereda.
- `min_std_for_measure_compatibility`: umbral interno opcional para declarar incompatible una medida casi constante.

Salidas principales:

- `02_series.parquet`
- `02_series_stats.json`
- `02_series_report.html`

Si la medida no es compatible, F02 conserva `outputs.yaml` y el reporte, pero no publica la serie como artefacto util.

### F03: crear ventanas numericas

```bash
make variant3 VARIANT=v3_0000 PARENT=v2_0000 OW=90 LT=10 PW=10 STRATEGY=synchro NAN_MODE=discard
make script3 VARIANT=v3_0000
make check3 VARIANT=v3_0000
make register3 VARIANT=v3_0000
```

Parametros:

- `OW`: longitud de la ventana de observacion, en multiplos de `Tu`.
- `LT`: lead time entre observacion y prediccion.
- `PW`: longitud de la ventana de prediccion.
- `STRATEGY`: `synchro` o `asynOW`.
- `NAN_MODE`: `keep` o `discard`.

Salida principal:

- `03_windows.parquet`, con `OW_values` y `PW_values`.
- `03_windows_report.html`.

### F04: crear etiquetas

F04 etiqueta ventanas numericas por umbral:

```bash
make variant4 VARIANT=v4_0000 PARENT=v3_0000 THRESHOLD=80 DIRECTION=high NAME=battery_high_80
make script4 VARIANT=v4_0000
make check4 VARIANT=v4_0000
make register4 VARIANT=v4_0000
```

El umbral se interpreta como porcentaje entre el minimo y maximo de la medida exportados por F02:

```text
threshold_value = min + (threshold / 100) * (max - min)
```

Con `DIRECTION=high`, la etiqueta vale 1 si algun valor de `PW_values` supera el umbral. Con `DIRECTION=low`, vale 1 si algun valor de `PW_values` cae por debajo.

F04 tambien conserva modo de transicion para entradas binarias:

```bash
make variant4 VARIANT=v4_0001 PARENT=v3_0000 EVENT_STRATEGY=transitions NAME=event_transition_0_to_1
make script4 VARIANT=v4_0001
```

En modo `transitions`:

```text
label = last(OW_events) == 0 AND any(PW_events == 1)
```

Parametros:

- `EVENT_STRATEGY`: `threshold` por defecto, o `transitions`.
- `THRESHOLD`: porcentaje de rango, requerido en modo `threshold`.
- `DIRECTION`: `high` o `low`.
- `NAME`: nombre del objetivo, guardado como `prediction_name`.
- `min_positive_ratio_for_target_compatibility`: minimo opcional de positivos.

Salida principal:

- `04_targets.parquet`, con `OW_values` y `label` en el flujo numerico.
- `04_targets_report.html`.

### F05: entrenar modelos

```bash
make variant5 VARIANT=v5_0000 PARENT=v4_0000 MODEL_FAMILY=cnn1d IMBALANCE_STRATEGY=rare_events IMBALANCE_MAX_MAJ=20000
make script5 VARIANT=v5_0000
make check5 VARIANT=v5_0000
make register5 VARIANT=v5_0000
```

Modelos soportados:

- `cnn1d`
- `dense_bow`

F05 lee `OW_values` y `label`, calcula `input_max_len`, normaliza la serie con media/desviacion de train y entrena el modelo. Para `cnn1d`, la entrada tiene forma:

```text
[muestras, input_max_len, 1]
```

Parametros importantes:

- `MODEL_FAMILY`: familia de modelo.
- `AUTOML`: configuracion opcional de busqueda.
- `TRAINING`: configuracion opcional de entrenamiento.
- `DEDUPLICATION_MODE`: `none`, `auto`, `neg_only` o `all`.
- `SEED`: semilla opcional.
- `IMBALANCE_STRATEGY`: `none`, `rare_events` o `auto`.
- `IMBALANCE_MAX_MAJ`: maximo opcional de negativos/majority.

F05 corre en Docker. Para GPU:

```bash
make script5 VARIANT=v5_0000 F56_GPU=true
```

Salidas principales: modelo `.h5`, dataset etiquetado autocontenido, reporte HTML, historial y exports de calidad (`decision_threshold`, `test_precision`, `test_recall`, `test_f1`, `best_val_recall`).

### F06: cuantizar y empaquetar

```bash
make variant6 VARIANT=v6_0000 PARENT=v5_0000 DEPLOY_TARGET=esp32 REQUIRE_INT8=true
make script6 VARIANT=v6_0000
make check6 VARIANT=v6_0000
make register6 VARIANT=v6_0000
```

Parametros principales:

- `DEPLOY_TARGET`: plataforma objetivo, normalmente `esp32`.
- `DEPLOY_RUNTIME`: runtime, normalmente `esp-tflite-micro`.
- `DEPLOY_VERSION`: version del runtime.
- `REQUIRE_INT8`: exige contrato INT8.
- `MEMORY_LIMIT`: limite de memoria objetivo.
- `QUANTIZATION`: configuracion avanzada.
- `THRESHOLDING`: recalibracion opcional del umbral.

F06 reconstruye la entrada numerica esperada por el modelo, genera dataset representativo, convierte a TFLite INT8 e inspecciona operadores y firma.

Salidas principales:

- `06_model_float.h5`
- `06_model_tflite.tflite`
- `06_calibration_dataset.parquet`
- `06_test_dataset.parquet`
- `06_quant_report.html`
- `eedu/eedu_manifest.yaml`

Exports importantes para edge:

- `input_dtype: int8`
- `output_dtype: int8`
- `input_shape`, `output_shape`
- `input_bytes`, `output_bytes`
- `input_max_len`
- `normalization_mean`
- `normalization_std`
- `input_quant_scale`
- `input_quant_zero_point`
- `operators`
- `arena_estimated_bytes`
- `model_size_bytes`

Para GPU:

```bash
make script6 VARIANT=v6_0000 F56_GPU=true
```

### F07: validar un modelo en edge

ESP32 virtual:

```bash
make variant7 VARIANT=v7_0000 PARENT=v6_0000 PLATFORM=esp32 MTI_MS=100 TIME_SCALE=0.01 VIRTUAL=true MAX_ROWS=1000 ESP_FLASH_MB=4
make script7 VARIANT=v7_0000
make check7 VARIANT=v7_0000
make register7 VARIANT=v7_0000
```

Placa fisica:

```bash
make variant7 VARIANT=v7_0001 PARENT=v6_0000 PLATFORM=esp32 MTI_MS=100 TIME_SCALE=0.01 VIRTUAL=false MAX_ROWS=1000 ESP_FLASH_MB=4
make script7 VARIANT=v7_0001 PORT=/dev/ttyUSB0 BAUD=115200
make check7 VARIANT=v7_0001
make register7 VARIANT=v7_0001
```

Ejecucion por pasos:

```bash
make script7-prepare-build VARIANT=v7_0000
make script7-build-only VARIANT=v7_0000
make script7-flash-run VARIANT=v7_0000
make script7-post VARIANT=v7_0000
```

Parametros principales:

- `PARENT`: variante F06.
- `PLATFORM`: carpeta bajo `edge/`, por ejemplo `esp32`.
- `MTI_MS`: presupuesto temporal de inferencia en milisegundos.
- `ITMAX`: opcional; por defecto `MTI_MS`.
- `TIME_SCALE`: escala temporal para replay en edge. Por defecto `0.01`.
- `MAX_ROWS`: limita filas incluidas en el dataset generado y en el firmware.
- `MAX_LINES`: limita lineas enviadas por serial sin recortar el CSV generado.
- `VIRTUAL`: `true` para usar Docker/QEMU/socat.
- `ESP_FLASH_MB`: flash ESP32 declarada, por ejemplo `4`, `8`, `16`.

En F07, `memory_events.h` contiene entradas int8 ya cuantizadas. No contiene IDs de eventos. Si `MAX_ROWS=10000` y `OW=90`, se embeben aproximadamente 900 KB solo de dataset, asi que puede ser necesario usar `ESP_FLASH_MB=4` o bajar `MAX_ROWS`.

Artefactos principales:

- `07_edge_run_config.yaml`
- `07_model_profile.yaml`
- `07_input_dataset.csv`
- `07_evaluation_dataset.csv`
- `07_esp_build_log.txt`
- `07_esp_flash_log.txt`
- `07_esp_monitor_log.txt`
- `metrics_models.csv`
- `metrics_memory.csv`
- `metrics_system_timing.csv`
- `07_report.html`

### F08: validar una configuracion multi-modelo

Manual:

```bash
make variant8 VARIANT=v8_0000 PARENTS=v7_0000,v7_0001 PLATFORM=esp32 MTI_MS=100 SELECTION_MODE=manual VIRTUAL=true MAX_ROWS=1000
make script8 VARIANT=v8_0000
make check8 VARIANT=v8_0000
make register8 VARIANT=v8_0000
```

Seleccion automatica por ILP:

```bash
make variant8 VARIANT=v8_0001 PARENTS=v7_0000,v7_0001,v7_0002 PLATFORM=esp32 MTI_MS=100 SELECTION_MODE=auto_ilp OBJECTIVE=max_tp MIN_PRECISION=0.01 MAX_MODELS=2 VIRTUAL=true MAX_ROWS=1000
make script8 VARIANT=v8_0001
```

Parametros principales:

- `PARENTS`: lista de variantes F07.
- `SELECTION_MODE`: `manual` o `auto_ilp`.
- `OBJECTIVE`: `max_global_recall`, `global_recall`, `recall_global` o `max_tp`.
- `SOLVER_TIME_LIMIT_SEC`: limite para ILP.
- `MTI_MS`: presupuesto global.
- `MAX_ROWS`: filas usadas para dataset unico de ventanas.
- `MEMORY_BUDGET_BYTES`: presupuesto de memoria.
- `MAX_MODELS`: maximo de modelos seleccionados.
- `MIN_QUALITY_SCORE`, `MIN_PRECISION`, `MIN_RECALL`: filtros de seleccion.
- `VIRTUAL`: ejecucion en ESP32 virtual si aplica.

F08 valida que los modelos seleccionados compartan una firma de entrada compatible: geometria (`Tu`, `OW`, `LT`, `PW`), dtype INT8, shape, bytes, normalizacion y cuantizacion. Esto es importante porque todos los modelos usan el mismo replay de ventanas.

Artefactos principales:

- `08_selected_configuration.yaml`
- `08_selection_report.yaml`
- `08_candidate_summary.csv`
- `08_unique_windows.csv`
- `08_model_execution_plan.yaml`
- `08_system_profile.yaml`
- `08_edge_run_config.yaml`
- `metrics_models.csv`
- `metrics_memory.csv`
- `metrics_system_timing.csv`
- `metrics_outcomes.csv`
- `metrics_system_summary.yaml`
- `08_report.html`

## ESP32 Virtual

Si una variante F07/F08 tiene `VIRTUAL=true`, `make script7` o `make script8` usa el entorno virtual ESP32 basado en Docker, QEMU y `socat`.

Comandos utiles:

```bash
make esp32-virt-docker-build
make esp32-virt-verify
make script7-virtualESP32 VARIANT=v7_0000
make script8-virtualESP32 VARIANT=v8_0000
make esp32-virt-stop
```

El host solo necesita Docker. ESP-IDF, QEMU, `socat` y dependencias Python viven dentro del contenedor.

## ESP32 Fisica

Para placa real:

1. Crear la variante con `VIRTUAL=false`.
2. Conectar la placa.
3. Ejecutar con `PORT` y `BAUD` si hace falta.
4. Revisar logs y metricas de la variante.

Ejemplo:

```bash
make script7 VARIANT=v7_0001 PORT=/dev/ttyUSB0 BAUD=115200
```

En Windows el puerto puede ser `COM3`, `COM4`, etc., segun el entorno de shell.

## Registro, DVC Y MLflow

Responsabilidades:

- Git: codigo, documentacion, schemas y templates.
- DVC: artefactos pesados.
- MLflow: tracking de entrenamiento si esta habilitado.
- `executions/`: estado local de variantes.

Registrar una fase:

```bash
make register5 VARIANT=v5_0000
```

Traer artefactos registrados:

```bash
make dvc-pull VARIANT=v5_0000
```

Traer varios:

```bash
make dvc-pull VARIANT=v5_0000,v6_0000,v7_0000
```

Limpiar artefactos descargados:

```bash
make dvc-clean VARIANT=v5_0000
```

## Limpieza

Eliminar una variante si no tiene hijas:

```bash
make remove5 VARIANT=v5_0000
```

Eliminar todas las variantes de una fase:

```bash
make remove-phase-all PHASE=f05_modeling VARIANTS_DIR=executions/f05_modeling
```

Regenerar el panel de linaje:

```bash
make generate_lineage
```

## Troubleshooting

### Una fase no encuentra el parent

Comprueba que el parent existe y pertenece a la fase esperada:

```text
F03 -> parent F02
F04 -> parent F03
F05 -> parent F04
F06 -> parent F05
F07 -> parent F06
F08 -> parents F07
```

### F02 dice que `MEASURE` no es valido

F02 valida contra `measure_cols` de F01. Revisa:

```text
executions/f01_explore/<variant>/outputs.yaml
```

### F04 produce target incompatible

Revisa `positive_ratio` y `min_positive_ratio_for_target_compatibility` en `outputs.yaml`. Puede que el umbral sea demasiado extremo o que la medida no tenga suficientes casos positivos.

### F05/F06 falla en Docker

Comprueba:

- Docker arrancado.
- espacio en disco.
- imagen `mlops-f56-gpu` o imagen CPU disponible.
- `F56_GPU=true` solo si tienes runtime NVIDIA configurado.

### F07 falla con `firmware_too_large_for_partition`

La imagen no cabe en la particion de app. Suele pasar si `MAX_ROWS` es alto, porque el dataset se embebe en el firmware.

Opciones:

```bash
make variant7 VARIANT=v7_0000 PARENT=v6_0000 PLATFORM=esp32 MTI_MS=100 TIME_SCALE=0.01 VIRTUAL=true MAX_ROWS=1000
make variant7 VARIANT=v7_0000 PARENT=v6_0000 PLATFORM=esp32 MTI_MS=100 TIME_SCALE=0.01 VIRTUAL=true MAX_ROWS=10000 ESP_FLASH_MB=4
```

Mira:

- `07_build_status.yaml`
- `07_esp_build_log.txt`
- `07_model_profile.yaml`

### F07/F08 no genera monitor log

Si la build o el flash fallan antes de arrancar, no hay monitor log. F073/F084 exportan outputs parciales para que la causa quede trazada.

Revisa:

- `07_esp_build_log.txt` o `08_esp_build_log.txt`
- `07_esp_flash_log.txt` o `08_esp_flash_log.txt`
- `phase_status_reason` en `outputs.yaml`

### Inferencias edge fallan o no cumplen tiempo

Mira:

- `metrics_models.csv`
- `metrics_outcomes.csv`, si existe.
- `metrics_system_timing.csv`
- `07_esp_monitor_log.txt` o `08_esp_monitor_log.txt`

Indicadores comunes:

- `watchdog_rate` alto: inferencias que no terminaron a tiempo.
- `offload_rate` alto: fallback/offload.
- `edge_run_completed=false`: ejecucion incompleta.
- `phase_status_reason`: razon canonica de estado.

## Estructura Del Repositorio

```text
scripts/core/              logica comun
scripts/phases/            fases F01-F08
scripts/runtime_analysis/  parser y metricas runtime
scripts/esp32_virtual/     runner Docker/QEMU para ESP32 virtual
edge/                      templates y runtime edge
setup/                     configuracion local/remota
test/                      auditorias y experimentos
executions/                salidas locales generadas
```

## Para Desarrolladores

Lee tambien:

```text
DEVELOPERS.md
scripts/traceability_schema.yaml
```

Antes de publicar cambios:

- no subir `.env`;
- no subir caches DVC/MLflow;
- no subir builds pesados;
- revisar que `executions/` no contiene artefactos que no deban versionarse;
- actualizar este README si cambian parametros, comandos o contratos de fase.
