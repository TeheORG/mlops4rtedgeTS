#!/usr/bin/env bash
set -euo pipefail

# Configuración manual por defecto
sources_default=(
	"executions"
	"test"	
)
destino_default="pruebas-linux.tar.gz"
dry_run_default=false

# Archivos a excluir por patrón
exclude_files=(
	"*.parquet"
	"*.h5"
	"*.png"
	"run-test.sh"
	"*.bin"
)

# Directorios a excluir por nombre
exclude_dirs=(
	"esp32_project"
	"platform_build_bundle"
)

# Uso:
#   ./create_executions_export.sh [--dry-run] [carpeta1] [carpeta2] ... [archivo_salida]
#
# Ejemplos:
#   ./create_executions_export.sh
#   ./create_executions_export.sh --dry-run
#   ./create_executions_export.sh --dry-run executions test
#   ./create_executions_export.sh executions test data
#   ./create_executions_export.sh executions test data export_custom.tar.gz
#
# Si el último argumento termina en .tar.gz, se usa como archivo_salida.
# El resto se trata como carpetas a incluir.

print_usage() {
	echo "Uso: ./create_executions_export.sh [--dry-run] [carpeta1] [carpeta2] ... [archivo_salida]"
}

print_tree_from_relative_paths() {
	awk -F'/' '
	function indent(level,   i, out) {
		out = ""
		for (i = 1; i < level; i++) {
			out = out "    "
		}
		return out "└── "
	}
	{
		n = split($0, curr, "/")
		common = 0
		for (i = 1; i <= n && i <= prev_n; i++) {
			if (curr[i] == prev[i]) {
				common++
			} else {
				break
			}
		}
		for (i = common + 1; i <= n; i++) {
			print indent(i) curr[i]
		}
		for (i = 1; i <= n; i++) {
			prev[i] = curr[i]
		}
		prev_n = n
	}
	'
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

dry_run="$dry_run_default"
sources=()
destino=""

# Parsear argumentos
for arg in "$@"; do
	case "$arg" in
		--dry-run|-n)
			dry_run=true
			;;
		--help|-h)
			print_usage
			exit 0
			;;
		*)
			# Si termina en .tar.gz, es el destino
			if [[ "$arg" == *.tar.gz ]]; then
				destino="$arg"
			else
				sources+=("$arg")
			fi
			;;
	esac
done

# Usar valores por defecto si no se especificaron
if (( ${#sources[@]} == 0 )); then
	sources=("${sources_default[@]}")
fi

if [[ -z "$destino" ]]; then
	destino="$destino_default"
fi

# Validar que todas las carpetas de origen existan
for source in "${sources[@]}"; do
	if [[ ! -d "$source" ]]; then
		echo "[ERROR] No existe el directorio: $source"
		exit 1
	fi
done

echo "[INFO] Orígenes: ${sources[*]}"
echo "[INFO] Salida: $destino"
echo "[INFO] Excluyendo archivos: ${exclude_files[*]:-(ninguno)}"
echo "[INFO] Excluyendo directorios: ${exclude_dirs[*]:-(ninguno)}"

# Nombre del contenedor: usar el nombre del archivo destino sin la extensión .tar.gz
CONTAINER_NAME="${destino%.tar.gz}"

# Crear carpeta temporal contenedora (padre)
TEMP_PARENT=$(mktemp -d)
trap "rm -rf '$TEMP_PARENT'" EXIT

# Crear carpeta con nombre de contenedor dentro de TEMP_PARENT
TEMP_CONTAINER="$TEMP_PARENT/$CONTAINER_NAME"
mkdir -p "$TEMP_CONTAINER"

echo "[INFO] Contenedor: $CONTAINER_NAME"

# Función para procesar una carpeta y obtener sus archivos/directorios
# respetando las exclusiones
get_preview() {
	local source_dir="$1"
	local source_name=$(basename "$source_dir")
	
	find_cmd=(find "$source_dir")

	if (( ${#exclude_dirs[@]} > 0 )); then
		find_cmd+=("(" -type d "(")
		for i in "${!exclude_dirs[@]}"; do
			if (( i > 0 )); then
				find_cmd+=(-o)
			fi
			find_cmd+=(-name "${exclude_dirs[$i]}")
		done
		find_cmd+=(")" -prune ")" -o)
	fi

	find_cmd+=("(" -type d -print0 ")" -o "(" -type f)
	for pattern in "${exclude_files[@]}"; do
		find_cmd+=(! -name "$pattern")
	done
	find_cmd+=(-print0 ")")

	"${find_cmd[@]}"
}

if [[ "$dry_run" == "true" ]]; then
	echo "[DRY-RUN] No se genera tar. Vista previa de contenido:"
	echo "$CONTAINER_NAME/"
	
	for source in "${sources[@]}"; do
		echo "├── $(basename "$source")/"
		preview_entries=()
		
		while IFS= read -r -d '' path; do
			path="${path#./}"
			if [[ "$path" == "$source" ]]; then
				continue
			fi
			rel_path="${path#"$source"/}"
			if [[ "$rel_path" == "$path" || -z "$rel_path" ]]; then
				continue
			fi
			preview_entries+=("$rel_path")
		done < <(get_preview "$source")

		if (( ${#preview_entries[@]} > 0 )); then
			printf '%s\n' "${preview_entries[@]}" | sort -u | sed 's/^/│   /' | print_tree_from_relative_paths
		else
			echo "│   (sin contenido)"
		fi
	done

	exit 0
fi

# Empaquetar: crear tar.gz directamente sin copia intermedia
# Esto es mucho más rápido que cp -r + tar
tar_cmd=(tar -czf "$destino")

# Agregar exclusiones de archivos por patrón
for file_pattern in "${exclude_files[@]}"; do
	tar_cmd+=(--exclude="$file_pattern")
done

# Agregar exclusiones de directorios
for dir_name in "${exclude_dirs[@]}"; do
	tar_cmd+=(--exclude="$dir_name")
done

# Agregar cada fuente con su nombre dentro del contenedor
for source in "${sources[@]}"; do
	echo "[INFO] Empaquetando: $source"
	tar_cmd+=(--transform "s,^${source}/,${CONTAINER_NAME}/$(basename ${source})/," --transform "s,^${source}$,${CONTAINER_NAME}/$(basename ${source})/," -C "." "$source")
done

# Ejecutar tar
"${tar_cmd[@]}"

echo "[OK] Tar generado: $destino"
