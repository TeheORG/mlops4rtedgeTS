#!/usr/bin/env python3
"""
Genera una tabla CSV de variantes de una fase, extrayendo parámetros, artefactos, exports y métricas según traceability_schema.yaml.
Uso: python generate_table.py <root_dir> <phase>
"""
import sys
import os
import yaml
import json
import csv
from pathlib import Path

def load_schema(schema_path, phase):
    with open(schema_path, 'r') as f:
        schema = yaml.safe_load(f)
    phase_def = schema['phases'][phase]
    params = list(phase_def.get('parameters', {}).keys())
    artifacts = list(phase_def.get('outputs', {}).get('artifacts', {}).keys())
    exports = list(phase_def.get('outputs', {}).get('exports', {}).keys())
    metrics = list(phase_def.get('outputs', {}).get('metrics', {}).keys())
    return params, artifacts, exports, metrics

def find_variant_dirs(root, phase):
    phase_dir = Path(root) / phase
    if not phase_dir.exists():
        return []
    return [d for d in phase_dir.iterdir() if d.is_dir() and d.name.startswith('v')]

def load_json_or_yaml(path):
    if not path.exists():
        return {}
    if path.suffix in ['.yaml', '.yml']:
        with open(path, 'r') as f:
            return yaml.safe_load(f) or {}
    if path.suffix == '.json':
        with open(path, 'r') as f:
            return json.load(f)
    return {}

def format_value(val):
    if isinstance(val, float):
        return f"{val:.6f}"
    if isinstance(val, (list, tuple)):
        return ','.join(format_value(v) for v in val)
    if isinstance(val, dict):
        return ','.join(f"{k}={format_value(v)}" for k,v in val.items())
    return str(val)

def main():
    print("Entrando en main()")
    import argparse
    parser = argparse.ArgumentParser(description="Generate phase variant table as CSV.")
    parser.add_argument("root_dir", help="Root executions directory")
    parser.add_argument("phase", help="Phase name (e.g. f05_modeling)")
    parser.add_argument("--output", "-o", help="Output CSV file name", default=None)
    args = parser.parse_args()
    root, phase = args.root_dir, args.phase
    # Calcular la ruta absoluta al schema en scripts/ (siempre desde la raíz del repo)
    repo_root = Path(__file__).resolve().parent.parent
    schema_path = repo_root / 'scripts' / 'traceability_schema.yaml'
    if not schema_path.exists():
        # Intentar buscar la ruta absoluta desde el cwd, por si el script se mueve
        alt_schema_path = Path.cwd() / 'scripts' / 'traceability_schema.yaml'
        if alt_schema_path.exists():
            schema_path = alt_schema_path
    print(f"[DEBUG] Usando schema_path: {schema_path}")
    params, artifacts, exports, metrics = load_schema(str(schema_path), phase)
    # Extrae solo el número de fase (ej: f05_modeling -> 5)
    import re
    m = re.match(r"f0?([1-9])", phase)
    phase_num = m.group(1) if m else phase
    header = ['variant id', 'parameters', 'outputs-artifacts', 'outputs-exports', 'outputs-metrics']
    rows = []
    output_file = args.output if args.output else f"table_{phase_num}.csv"
    for vdir in find_variant_dirs(root, phase):
        vid = vdir.name  # Solo el nombre de la variante
        params_path = vdir / 'params.yaml'
        exports_path = vdir / 'exports.yaml'
        outputs_path = vdir / 'outputs.yaml'
        metrics_path = vdir / 'metrics.json'
        params_data = load_json_or_yaml(params_path)
        # Si no existe exports.yaml, intenta outputs.yaml y extrae las claves 'exports', 'artifacts', 'metrics' si existen
        if exports_path.exists():
            exports_data = load_json_or_yaml(exports_path)
            outputs_data = None
        elif outputs_path.exists():
            outputs_data = load_json_or_yaml(outputs_path)
            exports_data = outputs_data.get('exports', {}) if isinstance(outputs_data, dict) else {}
        else:
            exports_data = {}
            outputs_data = None
        # Artefactos: busca archivos existentes o extrae de outputs.yaml si están anidados
        found_artifacts = []
        if outputs_data and isinstance(outputs_data, dict) and 'artifacts' in outputs_data:
            arts_val = outputs_data['artifacts']
            if isinstance(arts_val, dict):
                for art in artifacts:
                    val = arts_val.get(art)
                    if val is not None:
                        found_artifacts.append(f"{art}={format_value(val)}")
            elif isinstance(arts_val, list):
                for item in arts_val:
                    found_artifacts.append(str(item))
        else:
            for art in artifacts:
                for f in vdir.glob(f"{art}.*"):
                    found_artifacts.append(f"{art}={f.name}")
        # Métricas: si no existe metrics.json, intenta outputs.yaml['metrics']
        if metrics_path.exists():
            metrics_data = load_json_or_yaml(metrics_path)
        elif outputs_data and isinstance(outputs_data, dict) and 'metrics' in outputs_data:
            metrics_data = outputs_data['metrics']
        else:
            metrics_data = {}
        # Params: solo los definidos en el schema
        param_vals = []
        for p in params:
            val = params_data.get('parameters', {}).get(p) if 'parameters' in params_data else params_data.get(p)
            if val is not None:
                param_vals.append(f"{p}={format_value(val)}")
        # Exports: solo los definidos en el schema
        export_vals = []
        for e in exports:
            val = exports_data.get(e)
            if val is not None:
                export_vals.append(f"{e}={format_value(val)}")
        # Metrics: solo los definidos en el schema
        metric_vals = []
        for m in metrics:
            val = metrics_data.get(m)
            if val is not None:
                metric_vals.append(f"{m}={format_value(val)}")
        row = [vid, ','.join(param_vals), ','.join(found_artifacts), ','.join(export_vals), ','.join(metric_vals)]
        rows.append(row)
        for p in params:
            v = params_data.get(p)
            if v is not None:
                param_vals.append(f"{p}={format_value(v)}")
        # Exports
        export_vals = []
        for e in exports:
            v = exports_data.get(e)
            if v is not None:
                export_vals.append(f"{e}={format_value(v)}")
        # ...existing code...
                params_path = vdir / 'params.yaml'
                exports_path = vdir / 'exports.yaml'
                metrics_path = vdir / 'metrics.json'
                params_data = load_json_or_yaml(params_path)
                exports_data = load_json_or_yaml(exports_path)
                metrics_data = load_json_or_yaml(metrics_path)
                # Artefactos: busca archivos existentes
                found_artifacts = []
                for art in artifacts:
                    for f in vdir.glob(f"{art}.*"):
                        found_artifacts.append(f"{art}={f.name}")
                # Params
                param_vals = []
                for p in params:
                    v = params_data.get(p)
                    if v is not None:
                        param_vals.append(f"{p}={format_value(v)}")
                # Exports
                export_vals = []
                for e in exports:
                    v = exports_data.get(e)
                    if v is not None:
                        export_vals.append(f"{e}={format_value(v)}")
                # Metrics
                metric_vals = []
                for m in metrics:
                    v = metrics_data.get(m)
                    if v is not None:
                        metric_vals.append(f"{m}={format_value(v)}")
                rows.append([
                    phase_num,
                    vid,
                    ','.join(param_vals),
                    ','.join(found_artifacts),
                    ','.join(export_vals),
                    ','.join(metric_vals)
                ])
            # Escribe CSV con ;
            output_file = args.output if args.output else f"table_{phase_num}.csv"
            print(f"Escribiendo archivo en: {output_file}")
            with open(output_file, 'w', newline='') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(header)
                writer.writerows(rows)
            print(f"{output_file} generated.")

# Ejecutar main si es el script principal
if __name__ == "__main__":
    main()