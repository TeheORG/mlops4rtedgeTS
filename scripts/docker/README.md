# Reproducibilidad de `run-test.sh --to 6` con Docker

Objetivo: ejecutar exactamente el mismo entorno Linux en hosts macOS, Windows y Linux, guardar `executions` por host y comparar resultados.

## 1) Ejecutar en cada host

En cada máquina (macOS, Windows, Linux), desde la raíz del repo:

```bash
bash scripts/docker/run_to6_in_docker.sh <host_tag>
```

Ejemplos:

```bash
bash scripts/docker/run_to6_in_docker.sh macos
bash scripts/docker/run_to6_in_docker.sh windows
bash scripts/docker/run_to6_in_docker.sh linux
```

Salida por host:

- `scripts/docker-artifacts/executions-<host_tag>`
- `scripts/docker-artifacts/timing-<host_tag>`

## 2) Comparar resultados entre hosts

En una máquina que tenga las tres carpetas (copiadas si hace falta):

```bash
bash scripts/docker/compare_host_runs.sh macos linux
bash scripts/docker/compare_host_runs.sh windows linux
bash scripts/docker/compare_host_runs.sh macos windows
```

Genera:

- `scripts/docker-artifacts/compare-<left>-vs-<right>.csv`
- `scripts/docker-artifacts/compare-<left>-vs-<right>.md`

## Nota sobre `tf.config.experimental` y threading

En F05, la configuración de reproducibilidad ya captura excepciones y solo emite warning si una API no está disponible, no aborta la fase por ese motivo.

Al ejecutar en este contenedor Linux único, la disponibilidad de APIs de TensorFlow debería ser consistente entre hosts porque el runtime dentro del contenedor es el mismo.
