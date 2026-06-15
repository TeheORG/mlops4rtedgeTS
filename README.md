# MLOps4RT-Edge

Pipeline reproducible por fases para entrenar y validar modelos de series temporales orientados a edge.

La forma normal de uso es siempre la misma:

```bash
make variantN ...
make scriptN VARIANT=vN_XXXX
make checkN VARIANT=vN_XXXX
make registerN VARIANT=vN_XXXX
```

Cada fase crea una variante en `executions/<fase>/<variant>/` con `params.yaml`, artefactos, reportes y `outputs.yaml`.

## Setup

Requisitos minimos:

- Python 3.11
- GNU Make
- Git

Configuracion local:

```bash
make setup SETUP_CFG=setup/local.yaml
make check-setup
```

Ayuda general:

```bash
make help
```

Limpiar entorno local generado:

```bash
make clean-setup
```

## Flujo Principal

El flujo actual F01-F04 trabaja con una serie temporal univariable:

1. F01 explora y limpia el dataset bruto.
2. F02 selecciona una medida y genera `02_series.parquet`.
3. F03 construye ventanas `OW_values` y `PW_values`.
4. F04 etiqueta cada ventana usando un umbral sobre los valores de prediccion o, si se trabaja con eventos binarios, una regla de transicion.

El umbral de F04 es un porcentaje entre el minimo y el maximo de la medida exportados por F02:

```text
threshold_value = min + (threshold / 100) * (max - min)
```

Con `DIRECTION=high`, la etiqueta es 1 si algun valor de `PW_values` supera el umbral.  
Con `DIRECTION=low`, la etiqueta es 1 si algun valor de `PW_values` queda por debajo del umbral.

Cuando `EVENT_STRATEGY=transitions`, F04 no recalcula umbrales sobre eventos ya binarios. La etiqueta vale 1 solo si el ultimo evento de la ventana de observacion es 0 y en la ventana de prediccion aparece al menos un 1:

```text
label = last(OW_events) == 0 AND any(PW_events == 1)
```

Las ventanas vacias se etiquetan como 0.

## Ejemplo F01-F04

### F01: explorar datos

```bash
make variant1 VARIANT=v1_0000 RAW=data/raw.csv CLEANING=basic NAN_VALUES='[-999999]'
make script1 VARIANT=v1_0000
make check1 VARIANT=v1_0000
make register1 VARIANT=v1_0000
```

Opcionales habituales: `ERROR_VALUES`, `FIRST_LINE`, `MAX_LINES`.

### F02: crear serie univariable

```bash
make variant2 VARIANT=v2_0000 PARENT=v1_0000 MEASURE=Battery_Active_Power
make script2 VARIANT=v2_0000
make check2 VARIANT=v2_0000
make register2 VARIANT=v2_0000
```

Salida principal:

- `02_series.parquet`
- `02_series_stats.json`
- `02_series_report.html`

### F03: crear ventanas

```bash
make variant3 VARIANT=v3_0000 PARENT=v2_0000 OW=600 LT=10 PW=10 STRATEGY=synchro NAN_MODE=discard
make script3 VARIANT=v3_0000
make check3 VARIANT=v3_0000
make register3 VARIANT=v3_0000
```

Parametros:

- `OW`: longitud de la ventana de observacion, en multiplos de `Tu`
- `LT`: lead time entre observacion y prediccion
- `PW`: longitud de la ventana de prediccion
- `STRATEGY`: `synchro` o `asynOW`
- `NAN_MODE`: `keep` o `discard`

Salida principal:

- `03_windows.parquet`, con `OW_values` y `PW_values`
- `03_windows_report.html`

### F04: crear etiquetas

```bash
make variant4 VARIANT=v4_0000 PARENT=v3_0000 THRESHOLD=80 DIRECTION=high NAME=battery_high_80
make script4 VARIANT=v4_0000
make check4 VARIANT=v4_0000
make register4 VARIANT=v4_0000
```

Para eventos binarios por transicion:

```bash
make variant4 VARIANT=v4_0000 PARENT=v3_0000 EVENT_STRATEGY=transitions NAME=event_transition_0_to_1
make script4 VARIANT=v4_0000
```

Parametros:

- `EVENT_STRATEGY`: `threshold` por defecto, o `transitions` para eventos binarios
- `THRESHOLD`: porcentaje entre 0 y 100 del rango min-max de F02
- `DIRECTION`: `high` o `low`
- `NAME`: nombre opcional del objetivo

Salida principal:

- `04_targets.parquet`, con `OW_values` y `label`
- `04_targets_report.html`

## Fases Posteriores

Las fases F05-F08 usan el dataset etiquetado de F04:

- F05 entrena modelos.
- F06 cuantiza y empaqueta modelos.
- F07 valida un modelo en hardware edge.
- F08 valida una configuracion multi-modelo.

### Ejemplo F06: cuantizar y empaquetar

F06 parte de una variante entrenada en F05 y genera el modelo preparado para edge, incluyendo el `.tflite`, el reporte de cuantizacion y los metadatos de despliegue.

```bash
make variant6 VARIANT=v6_0000 PARENT=v5_0000 DEPLOY_TARGET=esp32 REQUIRE_INT8=true
make script6 VARIANT=v6_0000
make check6 VARIANT=v6_0000
make register6 VARIANT=v6_0000
```

Opcionales habituales:

- `DEPLOY_TARGET`: plataforma objetivo, por ejemplo `esp32`.
- `DEPLOY_RUNTIME`: runtime de despliegue, por ejemplo `esp-tflite-micro`.
- `DEPLOY_VERSION`: version del runtime.
- `REQUIRE_INT8`: exige que el modelo final sea INT8.
- `MEMORY_LIMIT`: limite de memoria objetivo en bytes.
- `QUANTIZATION`: configuracion avanzada de cuantizacion.
- `THRESHOLDING`: configuracion avanzada para recalibrar el umbral.

Salida principal:

- `06_model_float.h5`
- `06_model_tflite.tflite`
- `06_calibration_dataset.parquet`
- `06_quant_report.html`
- `eedu/eedu_manifest.yaml`

Consulta la ayuda especifica cuando las uses:

```bash
make help5
make help6
make help7
make help8
```

## Comandos Utiles

Eliminar una variante, si no tiene hijas:

```bash
make remove4 VARIANT=v4_0000
```

Eliminar todas las variantes de una fase de forma segura:

```bash
make remove-phase-all PHASE=f04_targets VARIANTS_DIR=executions/f04_targets
```

Regenerar el panel de linaje:

```bash
make generate_lineage
```

## Donde se Guardan los Resultados

Los resultados se escriben en `executions/`. Este directorio contiene variantes, artefactos, reportes y metadatos generados por ejecucion.

Los artefactos grandes se registran mediante DVC cuando ejecutas `make registerN`. La configuracion de DVC, MLflow y Git se define durante `make setup`.

## Notas

- Usa variantes canonicas como `v1_0000`, `v2_0000`, etc.
- Las formas cortas como `VARIANT=0` tambien se normalizan segun la fase.
- F02 ya no genera catalogos de eventos.
- F04 conserva el etiquetado numerico por umbral y tambien soporta `OW_events`/`PW_events` binarios con regla de transicion 0->1. Ya no etiqueta positivo por la mera presencia de cualquier evento en `PW_events`.

## Cambios Realizados Desde el Inicio del Repositorio Git

Esta lista resume los cambios hechos respecto al commit inicial del repositorio. El cambio mas importante es que el flujo principal ha pasado de trabajar con eventos discretos a trabajar con una serie temporal numerica de una sola medida.

### F01: exploracion y limpieza

No se han hecho cambios directos en el script de F01.

F01 sigue siendo la fase que lee el dataset bruto, prepara el eje temporal, limpia valores invalidos y exporta las columnas de medida disponibles. Lo que si ha cambiado es que ahora F02 usa de forma mas directa la informacion que F01 exporta: la lista de medidas sirve para validar que la medida elegida en F02 existe realmente en el dataset limpio.

### F02: de dataset de eventos a serie temporal univariable

Este es uno de los cambios principales.

Antes F02 generaba un dataset de eventos. Para ello discretizaba varias medidas en bandas, creaba un catalogo de eventos y producia artefactos como `02_events.parquet` y `02_events_catalog.json`.

Ahora F02 selecciona una sola medida con el parametro `MEASURE` y genera una serie temporal numerica simple:

- `02_series.parquet`
- `02_series_stats.json`
- `02_series_report.html`

El dataset resultante contiene la columna temporal y una columna `value`. Esto simplifica mucho el flujo, porque las fases siguientes ya no dependen de codigos de eventos ni de catalogos. Tambien se calculan estadisticas utiles de la serie, como minimo, maximo, media, mediana, desviacion, proporcion de NaN y continuidad temporal.

Tambien se ha cambiado el `Makefile`: ahora `variant2` pide `MEASURE` en lugar de `STRATEGY`, `BANDS` y `NAN_MODE`. Ademas, se valida que la medida exista entre las columnas exportadas por F01.

### F03: ventanas sobre valores numericos

F03 se ha adaptado al nuevo formato de F02.

Antes construia ventanas con listas de eventos:

- `OW_events`
- `PW_events`

Ahora construye ventanas con valores numericos:

- `OW_values`
- `PW_values`

La logica de ventanas se mantiene en lo esencial: se siguen usando `OW`, `LT`, `PW`, `STRATEGY` y `NAN_MODE`. La diferencia es que las ventanas ya no contienen IDs de eventos, sino valores reales de la medida seleccionada en F02.

Tambien se ha eliminado la copia del catalogo de eventos en F03, porque ya no existe un catalogo. El chequeo de fase se ha actualizado para no exigir `03_events_catalog.json`.

### F04: etiquetas por umbral numerico

F04 tambien ha cambiado de forma importante.

Antes F04 etiquetaba una ventana buscando si en `PW_events` aparecia alguno de los eventos definidos en `target_event_types`, normalmente usando una regla OR.

Ahora F04 etiqueta cada ventana mirando los valores de `PW_values`. El usuario define:

- `THRESHOLD`: porcentaje entre 0 y 100.
- `DIRECTION`: `high` o `low`.
- `NAME`: nombre opcional del objetivo.

El porcentaje se convierte en un valor real usando el minimo y maximo calculados en F02:

```text
threshold_value = min + (threshold / 100) * (max - min)
```

Con `DIRECTION=high`, la etiqueta vale 1 si algun valor de la ventana de prediccion supera el umbral. Con `DIRECTION=low`, vale 1 si algun valor queda por debajo. En `EVENT_STRATEGY=transitions`, la etiqueta vale 1 solo cuando `last(OW_events) == 0` y `any(PW_events == 1)`; si `OW_events` o `PW_events` estan vacias, devuelve 0.

Tambien se ha hecho el etiquetado por lotes con PyArrow. Esto evita cargar todo el parquet completo en memoria cuando el dataset es grande. La salida principal sigue siendo `04_targets.parquet`; en modo numerico contiene `OW_values` y `label`, y en modo transiciones conserva `OW_events` y `label`.

### F05: entrenamiento con secuencias numericas

F05 se ha adaptado para entrenar modelos usando `OW_values`.

Antes el entrenamiento trabajaba con secuencias de eventos o bolsas de eventos. Eso necesitaba cosas como `event_type_count`, vocabularios de eventos y modelos pensados para IDs categoricos.

Ahora el entrenamiento trabaja con secuencias numericas continuas. Cada muestra que llega desde F04 tiene:

- `OW_values`: los valores reales de la ventana de observacion.
- `label`: la etiqueta calculada en F04.

Antes, para `cnn1d`, el flujo era este:

```text
OW_events -> IDs de eventos -> Embedding -> Conv1D -> salida
```

Es decir, la red no veia la senal original. Veia codigos enteros de eventos. Por eso necesitaba una capa `Embedding`, un vocabulario de eventos y `event_type_count`.

Ahora, para `cnn1d`, el flujo es este:

```text
OW_values -> secuencia numerica normalizada -> Conv1D -> salida
```

La red recibe directamente la forma de la serie temporal. Por ejemplo, si la medida elegida en F02 es `Battery_Active_Power`, la CNN trabaja con la evolucion numerica de esa potencia dentro de la ventana de observacion.

El preprocesado nuevo de F05 hace estos pasos:

1. Lee solo `OW_values` y `label` del parquet de F04.
2. Convierte cada `OW_values` en una secuencia de numeros `float32`.
3. Calcula una longitud comun `max_len` usando el percentil 95 de las longitudes.
4. Rellena con ceros o recorta las secuencias para que todas tengan esa longitud.
5. Normaliza los valores con media y desviacion tipica. (el modelo aprende mejor si la entrada tiene una escala estable y los valores que podemos tener son muy dispersos (-216.8, 0.4, 15.2, 119.9, ...) (valor_normalizado = (valor - media) / desviacion_tipica))
6. Si el modelo es `cnn1d`, convierte la entrada a forma `[muestras, max_len, 1]`.

Ese ultimo `1` significa que hay un solo canal de entrada, porque el flujo actual usa una serie univariable. Es el formato que espera una `Conv1D` para aprender patrones locales en una senal temporal.

El modelo `cnn1d` tambien se ha simplificado. Antes empezaba con una capa `Embedding`; ahora empieza directamente con una entrada numerica:

```text
Input(max_len, 1) -> Conv1D -> GlobalMaxPooling1D -> Dense -> Dense(1)
```

La salida final sigue siendo una probabilidad binaria, con activacion `sigmoid`, para predecir si la ventana pertenece o no al objetivo definido en F04.


Tambien se ha ajustado la carga del dataset para el caso de clases desbalanceadas. En la estrategia `rare_events`, F05 puede leer etiquetas, seleccionar positivos y una muestra limitada de negativos, y despues cargar solo esas filas. Esto reduce memoria y tiempo cuando hay muchos negativos.

### F06: cuantizacion y empaquetado desde entrada numerica

F06 se ha cambiado para calibrar y cuantizar modelos que reciben `OW_values`.

Antes la calibracion dependia de eventos y de `event_type_count`. Tambien habia comprobaciones sobre si el numero de tipos de evento cabia en ciertos rangos.

Ahora F06 reconstruye la entrada numerica esperada por el modelo, aplica padding o recorte, normaliza la secuencia y genera los datos de calibracion para TFLite. En los metadatos se guardan campos como:

- `input_sequence_column`
- `input_max_len`
- `normalization_mean`
- `normalization_std`

Esto hace que el empaquetado edge siga teniendo trazabilidad sobre como se preparo la entrada del modelo.


### Cambios transversales de soporte

Tambien se han actualizado piezas comunes para que el nuevo flujo sea coherente:

- `Makefile`: comandos de F02 y F04 cambiados para usar `MEASURE`, `THRESHOLD` y `DIRECTION`.
- `makefile_check_phases.yml`: los chequeos ahora esperan los nuevos artefactos de F02 y ya no exigen catalogos de eventos.
- `scripts/traceability_schema.yaml`: el esquema de trazabilidad se ha adaptado a `series`, `OW_values`, `PW_values`, umbrales numericos y modelos sin `event_type_count`.
- `scripts/core/params_manager.py`: se ha anadido validacion para evitar elegir una medida que no existe en el parent.
- `scripts/core/artifacts.py`: se ha anadido una comprobacion defensiva relacionada con medidas exportadas.

En resumen, el repositorio ahora tiene un flujo mas simple y directo para series temporales: F01 limpia, F02 elige una medida, F03 crea ventanas numericas, F04 etiqueta por umbral, F05 entrena, F06 cuantiza y F07-F08 validan en edge.
