#!/usr/bin/env python3
"""Genera diagramas de trazabilidad entre variantes por fase.

Uso:
  python test/generate_variants_diagram.py --executions-root executions

Salida por defecto:
  - <executions-root>/variants_lineage.mmd
  - <executions-root>/variants_lineage.md
	- <executions-root>/variants_lineage.drawio
"""

from __future__ import annotations

import argparse
import html
import math
import re
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


PHASE_RE = re.compile(r"^f(?P<num>\d{2})_.+$")
VARIANT_RE = re.compile(r"^v(?P<num>\d)_(?P<seq>\d{4})$")
EXCLUDED_PARAM_KEYS = {"variant", "parent", "parents", "parent_variant"}


def parse_iso_datetime(value: Any) -> datetime | None:
	if not isinstance(value, str) or not value.strip():
		return None
	text = value.strip()
	if text.endswith("Z"):
		text = text[:-1] + "+00:00"
	try:
		return datetime.fromisoformat(text)
	except ValueError:
		return None


def normalize_datetime_pair(a: datetime, b: datetime) -> tuple[datetime, datetime]:
	# Si una fecha trae tzinfo y la otra no, tratamos ambas como naive para evitar TypeError.
	if (a.tzinfo is None) != (b.tzinfo is None):
		return a.replace(tzinfo=None), b.replace(tzinfo=None)
	return a, b


def compact_value(value: Any, max_len: int = 80) -> str:
	if isinstance(value, (str, int, float, bool)) or value is None:
		text = str(value)
	elif isinstance(value, list):
		rendered = [compact_value(v, max_len=min(20, max_len)) for v in value[:8]]
		if len(value) > 8:
			rendered.append("...")
		text = "[" + ", ".join(rendered) + "]"
	elif isinstance(value, dict):
		# Los dicts largos degradan mucho la legibilidad del diagrama.
		return "{...}"
	else:
		text = str(value)

	if len(text) > max_len:
		return text[: max_len - 3] + "..."
	return text


def extract_display_params(
	params: dict[str, Any],
	max_value_len: int,
) -> list[tuple[str, str]]:
	parameters = params.get("parameters")
	if not isinstance(parameters, dict):
		return []

	out: list[tuple[str, str]] = []
	for k, v in parameters.items():
		if not isinstance(k, str):
			continue
		if k.strip().lower() in EXCLUDED_PARAM_KEYS:
			continue
		# Conservamos parámetros típicos de make variant y omitimos estructuras profundas.
		if isinstance(v, dict):
			continue
		out.append((k, compact_value(v, max_len=max_value_len)))
	return out


def compute_duration_seconds(
	created_at: Any,
	outputs: dict[str, Any],
) -> float | None:
	metrics = outputs.get("metrics")
	if isinstance(metrics, dict):
		exec_time = metrics.get("execution_time")
		if isinstance(exec_time, (int, float)) and math.isfinite(float(exec_time)):
			if float(exec_time) >= 0:
				return float(exec_time)

	end_candidates: list[Any] = [outputs.get("generated_at")]
	provenance = outputs.get("provenance")
	if isinstance(provenance, dict):
		end_candidates.append(provenance.get("generated_at"))

	start_dt = parse_iso_datetime(created_at)
	if start_dt is None:
		return None

	for end_raw in end_candidates:
		end_dt = parse_iso_datetime(end_raw)
		if end_dt is None:
			continue
		norm_end_dt, norm_start_dt = normalize_datetime_pair(end_dt, start_dt)
		delta = (norm_end_dt - norm_start_dt).total_seconds()
		if delta >= 0:
			return delta

	return None


def load_yaml(path: Path) -> dict[str, Any]:
	if not path.exists():
		return {}
	with path.open("r", encoding="utf-8") as f:
		data = yaml.safe_load(f)
	return data or {}


def phase_dirs(executions_root: Path) -> list[Path]:
	phases: list[tuple[int, Path]] = []
	for child in executions_root.iterdir():
		if not child.is_dir():
			continue
		m = PHASE_RE.match(child.name)
		if not m:
			continue
		phases.append((int(m.group("num")), child))
	phases.sort(key=lambda x: x[0])
	return [p for _, p in phases]


def phase_sort_key(phase_name: str) -> tuple[int, str]:
	m = PHASE_RE.match(phase_name)
	if not m:
		return (999, phase_name)
	return (int(m.group("num")), phase_name)


def list_phase_variants(phase_dir: Path) -> list[Path]:
	phase_match = PHASE_RE.match(phase_dir.name)
	if not phase_match:
		return []

	phase_num = phase_match.group("num")
	phase_num = str(int(phase_num))
	variants: list[Path] = []
	for child in phase_dir.iterdir():
		if not child.is_dir():
			continue
		m = VARIANT_RE.fullmatch(child.name)
		if not m:
			continue
		if m.group("num") != phase_num:
			continue
		variants.append(child)
	variants.sort(key=lambda p: variant_sort_key(p.name))
	return variants


def variant_sort_key(variant_name: str) -> tuple[int, str]:
	m = re.search(r"(\d+)$", variant_name)
	if not m:
		return (999999, variant_name)
	return (int(m.group(1)), variant_name)


def extract_parents(params: dict[str, Any]) -> list[str]:
	parents: list[str] = []

	top_parent = params.get("parent")
	if isinstance(top_parent, str) and top_parent.strip():
		parents.append(top_parent.strip())

	parameters = params.get("parameters")
	if isinstance(parameters, dict):
		raw_parents = parameters.get("parents")
		if isinstance(raw_parents, list):
			for p in raw_parents:
				if isinstance(p, str) and p.strip():
					parents.append(p.strip())

		parent_variant = parameters.get("parent_variant")
		if isinstance(parent_variant, str) and parent_variant.strip():
			parents.append(parent_variant.strip())

	# Mantener orden de aparición, evitando duplicados.
	seen: set[str] = set()
	result: list[str] = []
	for p in parents:
		if p not in seen:
			seen.add(p)
			result.append(p)
	return result


def build_graph(
	executions_root: Path,
	max_value_len: int,
	lineage_source: str,
) -> tuple[dict[str, list[str]], list[tuple[str, str]], set[str], dict[str, dict[str, Any]]]:
	if lineage_source == "tree":
		return build_graph_from_tree(executions_root, max_value_len=max_value_len)
	return build_graph_from_index(executions_root, max_value_len=max_value_len)


def build_graph_from_index(
	executions_root: Path,
	max_value_len: int,
) -> tuple[dict[str, list[str]], list[tuple[str, str]], set[str], dict[str, dict[str, Any]]]:
	phase_to_variants: dict[str, list[str]] = {}
	edges: list[tuple[str, str]] = []
	known_variants: set[str] = set()
	variant_info: dict[str, dict[str, Any]] = {}

	for phase_dir in phase_dirs(executions_root):
		phase_name = phase_dir.name
		variant_dirs = list_phase_variants(phase_dir)
		if not variant_dirs:
			continue

		phase_to_variants[phase_name] = []

		for variant_dir in variant_dirs:
			variant_name = variant_dir.name
			meta = load_yaml(variant_dir / "metadata.yaml")

			phase_to_variants[phase_name].append(variant_name)
			known_variants.add(variant_name)

			params_path: Path | None = None
			if isinstance(meta, dict):
				rel_path = meta.get("params_path")
				if isinstance(rel_path, str) and rel_path.strip():
					params_path = executions_root.parent / rel_path

			if params_path is None:
				params_path = variant_dir / "params.yaml"

			params = load_yaml(params_path)
			parents = extract_parents(params)
			for parent in parents:
				edges.append((parent, variant_name))

			outputs_path = variant_dir / "outputs.yaml"
			outputs = load_yaml(outputs_path)
			created_at = meta.get("created_at") if isinstance(meta, dict) else None

			variant_info[variant_name] = {
				"phase": phase_name,
				"params": extract_display_params(params, max_value_len=max_value_len),
				"duration_s": compute_duration_seconds(created_at, outputs),
			}

	return phase_to_variants, edges, known_variants, variant_info


def build_graph_from_tree(
	executions_root: Path,
	max_value_len: int,
) -> tuple[dict[str, list[str]], list[tuple[str, str]], set[str], dict[str, dict[str, Any]]]:
	phase_to_variants: dict[str, list[str]] = {}
	edges: list[tuple[str, str]] = []
	known_variants: set[str] = set()
	variant_info: dict[str, dict[str, Any]] = {}

	params_files = sorted(executions_root.rglob("params.yaml"))

	for params_path in params_files:
		try:
			rel = params_path.relative_to(executions_root)
		except ValueError:
			continue

		phase_name: str | None = None
		for part in rel.parts:
			if PHASE_RE.match(part):
				phase_name = part
				break
		if phase_name is None:
			continue

		params = load_yaml(params_path)

		variant_name = params.get("variant") if isinstance(params.get("variant"), str) else None
		if not variant_name:
			variant_name = params_path.parent.name

		if variant_name not in known_variants:
			known_variants.add(variant_name)
			phase_to_variants.setdefault(phase_name, []).append(variant_name)

		parents = extract_parents(params)
		for parent in parents:
			edges.append((parent, variant_name))

		outputs = load_yaml(params_path.parent / "outputs.yaml")
		created_at = params.get("created_at")
		if created_at is None:
			provenance = params.get("provenance")
			if isinstance(provenance, dict):
				created_at = provenance.get("created_at")

		variant_info[variant_name] = {
			"phase": phase_name,
			"params": extract_display_params(params, max_value_len=max_value_len),
			"duration_s": compute_duration_seconds(created_at, outputs),
		}

	ordered_phase_to_variants: dict[str, list[str]] = {}
	for phase in sorted(phase_to_variants.keys(), key=phase_sort_key):
		ordered_phase_to_variants[phase] = sorted(phase_to_variants[phase], key=variant_sort_key)

	return ordered_phase_to_variants, edges, known_variants, variant_info


def build_node_labels(
	known_variants: set[str],
	variant_info: dict[str, dict[str, Any]],
	show_params: bool,
	show_duration: bool,
	max_param_lines: int,
	label_mode: str,
) -> dict[str, str]:
	labels: dict[str, str] = {}
	for variant in known_variants:
		info = variant_info.get(variant, {})
		if label_mode == "variant-only":
			labels[variant] = variant
			continue
		lines = [variant]

		if show_params:
			params = info.get("params")
			phase = info.get("phase") if isinstance(info, dict) else None
			if isinstance(params, list):
				flat_params: list[str] = []
				for item in params:
					if isinstance(item, tuple) and len(item) == 2:
						k, v = item
						flat_params.append(f"{k}={v}")

				# Compacta informacion: 2 parametros por linea para reducir altura total.
				pairs_per_line = 2
				rendered_lines = 0
				consumed_params = 0
				for i in range(0, len(flat_params), pairs_per_line):
					if rendered_lines >= max_param_lines:
						break
					chunk = flat_params[i : i + pairs_per_line]
					lines.append(" | ".join(chunk))
					rendered_lines += 1
					consumed_params += len(chunk)

				remaining = len(flat_params) - consumed_params
				if remaining > 0 and phase != "f08_sysval":
					lines.append(f"... +{remaining} params")

		if show_duration:
			duration = info.get("duration_s")
			if isinstance(duration, (int, float)) and math.isfinite(float(duration)):
				lines.append(f"time_s={float(duration):.3f}")
			else:
				lines.append("time_s=NA")

		labels[variant] = "\n".join(lines)
	return labels


def node_id(variant: str) -> str:
	return f"n_{re.sub(r'[^A-Za-z0-9_]', '_', variant)}"


def mermaid_escape_label(text: str) -> str:
	return text.replace('"', "'").replace("\n", "<br/>")


def mermaid_rich_label(text: str) -> str:
	parts = text.split("\n")
	if not parts:
		return ""
	head = parts[0].replace('"', "'")
	tail = [p.replace('"', "'") for p in parts[1:]]
	first = f"<b><span style='font-size:16px'>{head}</span></b>"
	if not tail:
		return first
	return first + "<br/>" + "<br/>".join(tail)


def drawio_rich_label(text: str) -> str:
	parts = text.split("\n")
	if not parts:
		return ""
	head = html.escape(parts[0])
	tail = [html.escape(p) for p in parts[1:]]
	body = "".join(f"<div>{line}</div>" for line in tail)
	return (
		"<div>"
		f"<div><b><span style='font-size:14px'>{head}</span></b></div>"
		f"{body}"
		"</div>"
	)


def wrap_label_text(text: str, width: int) -> str:
	if width <= 0:
		return text
	wrapped_lines: list[str] = []
	for raw_line in text.split("\n"):
		if not raw_line:
			wrapped_lines.append("")
			continue
		parts = textwrap.wrap(
			raw_line,
			width=width,
			break_long_words=True,
			break_on_hyphens=False,
		)
		wrapped_lines.extend(parts or [raw_line])
	return "\n".join(wrapped_lines)


def is_uniform_height_phase(phase_name: str | None) -> bool:
	if not isinstance(phase_name, str):
		return False
	return phase_name in {
		"f03_windows",
		"f04_targets",
		"f05_modeling",
		"f06_quant",
		"f07_modval",
		"f08_sysval",
	}


def to_mermaid(
	phase_to_variants: dict[str, list[str]],
	edges: list[tuple[str, str]],
	known_variants: set[str],
	node_labels: dict[str, str],
) -> str:
	lines: list[str] = ["flowchart LR"]
	lines.append("  classDef hub fill:transparent,stroke:transparent,color:transparent;")
	lines.append("  classDef ghost fill:transparent,stroke:transparent,color:transparent;")
	palette = ["#e41a1c", "#377eb8", "#4daf4a", "#000000", "#984ea3", "#a65628", "#f781bf", "#999999"]
	phase_ids: list[str] = []
	row_ids: list[str] = []
	max_phase_rows = max((len(v) for v in phase_to_variants.values()), default=0)

	f07_variants = set(phase_to_variants.get("f07_modval", []))
	f08_variants = set(phase_to_variants.get("f08_sysval", []))
	f08_color: dict[str, str] = {}
	for i, v in enumerate(sorted(f08_variants)):
		f08_color[v] = palette[i % len(palette)]

	deferred_links: list[tuple[str, str | None]] = []

	# Nodos por fase en subgraphs para una lectura visual limpia.
	for phase in phase_to_variants:
		phase_ids.append(phase)
		lines.append(f"  subgraph {phase}[ ]")
		lines.append("    direction TB")
		if phase == "f07_modval":
			for variant in phase_to_variants[phase]:
				lines.append(f"    r_{node_id(variant)}(( )):::hub")
		if phase == "f08_sysval":
			variant_count = len(phase_to_variants[phase])
			missing_slots = max(0, max_phase_rows - variant_count)
			top_slots = missing_slots // 2
			bottom_slots = missing_slots - top_slots
			for idx in range(top_slots):
				lines.append(f"    pad_top_{idx}(( )):::ghost")
		for variant in phase_to_variants[phase]:
			label = mermaid_rich_label(node_labels.get(variant, variant))
			if phase == "f08_sysval":
				row_id = f"row_{node_id(variant)}"
				row_ids.append(row_id)
				lines.append(f"    subgraph {row_id}[ ]")
				lines.append("      direction LR")
				lines.append(f"      j_{node_id(variant)}(( )):::ghost")
				lines.append(f"      h_{node_id(variant)}(( )):::hub")
				lines.append(f'      {node_id(variant)}["{label}"]')
				lines.append(f"      r_{node_id(variant)}(( )):::ghost")
				lines.append("    end")
				deferred_links.append((f"h_{node_id(variant)} --> {node_id(variant)}", None))
				deferred_links.append((f"{node_id(variant)} --> r_{node_id(variant)}", None))
			else:
				lines.append(f"    l_{node_id(variant)}(( )):::ghost")
				lines.append(f"    r_{node_id(variant)}(( )):::ghost")
				lines.append(f'    {node_id(variant)}["{label}"]')
				# Todas las variantes usan anclas L/R para forzar salida lateral por la derecha.
				deferred_links.append((f"l_{node_id(variant)} --> {node_id(variant)}", None))
				deferred_links.append((f"{node_id(variant)} --> r_{node_id(variant)}", None))
		if phase == "f08_sysval":
			for idx in range(bottom_slots):
				lines.append(f"    pad_bottom_{idx}(( )):::ghost")
		lines.append("  end")

	missing_parents = sorted({p for p, _ in edges if p not in known_variants})
	if missing_parents:
		lines.append("  subgraph missing[parents no encontrados]")
		lines.append("    direction TB")
		for parent in missing_parents:
			label = mermaid_escape_label(node_labels.get(parent, parent))
			lines.append(f'    {node_id(parent)}["{label}"]')
		lines.append("  end")

	jh_added: set[str] = set()
	for parent, child in edges:
		src = f"r_{node_id(parent)}" if parent in known_variants else node_id(parent)
		if child in known_variants:
			child_phase = phase_to_variants.get("f08_sysval", [])
			dst = node_id(child) if child in child_phase else f"l_{node_id(child)}"
		else:
			dst = node_id(child)
		if parent in f07_variants and child in f08_variants:
			# Enlaces a F08 con nodo intermedio para abrir distancia entre forks y joins.
			color = f08_color.get(child)
			deferred_links.append((f"{src} --> j_{node_id(child)}", color))
			key = f"{child}"
			if key not in jh_added:
				deferred_links.append((f"j_{node_id(child)} --> h_{node_id(child)}", color))
				jh_added.add(key)
		else:
			deferred_links.append((f"{src} --> {dst}", None))

	styled_indices: list[tuple[int, str]] = []
	for idx, (link_line, color) in enumerate(deferred_links):
		lines.append(f"  {link_line}")
		if color:
			styled_indices.append((idx, color))

	for idx, color in styled_indices:
		lines.append(f"  linkStyle {idx} stroke:{color},stroke-width:2.6px,opacity:0.95;")

	# Oculta visualmente las cajas de fase y de fila; solo quedan visibles las variantes.
	for phase_id in phase_ids:
		lines.append(f"  style {phase_id} fill:transparent,stroke:transparent;")
	for row_id in row_ids:
		lines.append(f"  style {row_id} fill:transparent,stroke:transparent;")

	return "\n".join(lines) + "\n"


def write_outputs(executions_root: Path, mermaid_text: str, output_stem: str) -> tuple[Path, Path]:
	mmd_path = executions_root / f"{output_stem}.mmd"
	md_path = executions_root / f"{output_stem}.md"

	mmd_path.write_text(mermaid_text, encoding="utf-8")
	md_path.write_text(
		"```mermaid\n"
		f"{mermaid_text}"
		"```\n",
		encoding="utf-8",
	)
	return mmd_path, md_path


def to_drawio_xml(
	phase_to_variants: dict[str, list[str]],
	edges: list[tuple[str, str]],
	known_variants: set[str],
	node_labels: dict[str, str],
	variant_info: dict[str, dict[str, Any]],
	compact_layout: bool,
) -> str:
	missing_parents = sorted({p for p, _ in edges if p not in known_variants})
	all_nodes = sorted(known_variants | set(missing_parents))
	for p in missing_parents:
		node_labels.setdefault(p, p)

	# Layout sencillo por columnas (fases) para edición manual posterior en draw.io.
	phase_x_start = 40 if not missing_parents else 280
	phase_dx = 190 if compact_layout else 235
	phase_extra_gap_after_f07 = 95 if compact_layout else 140
	header_y = 20
	node_y_start = 65 if compact_layout else 80
	node_w = 170 if compact_layout else 240
	node_gap = 12 if compact_layout else 20
	node_h_uniform = 58 if compact_layout else 170

	phase_x: dict[str, int] = {}
	f08_variants = sorted(phase_to_variants.get("f08_sysval", []))
	palette = ["#e41a1c", "#377eb8", "#4daf4a", "#000000", "#984ea3", "#a65628", "#f781bf", "#999999"]
	f08_color: dict[str, str] = {v: palette[i % len(palette)] for i, v in enumerate(f08_variants)}
	phase_of: dict[str, str] = {}
	for phase_name, variants in phase_to_variants.items():
		for variant in variants:
			phase_of[variant] = phase_name

	for idx, phase in enumerate(phase_to_variants.keys()):
		base_x = phase_x_start + idx * phase_dx
		if phase == "f08_sysval":
			base_x += phase_extra_gap_after_f07
		phase_x[phase] = base_x

	node_pos: dict[str, tuple[int, int]] = {}

	column_bottoms: list[int] = []

	for phase, variants in phase_to_variants.items():
		x = phase_x[phase]
		y = node_y_start
		for i, variant in enumerate(variants):
			_ = i
			node_h = node_h_uniform
			node_pos[variant] = (x, y)
			y += node_h + node_gap
		column_bottoms.append(y)

	missing_bottom = node_y_start
	for i, parent in enumerate(missing_parents):
		_ = i
		lines_count = node_labels.get(parent, parent).count("\n") + 1
		node_h = max(38, 14 * lines_count + 16)
		node_pos[parent] = (40, missing_bottom)
		missing_bottom += node_h + node_gap

	if missing_parents:
		column_bottoms.append(missing_bottom)

	canvas_w = phase_x_start + max(1, len(phase_to_variants)) * phase_dx + phase_extra_gap_after_f07 + 220
	canvas_h = (max(column_bottoms) if column_bottoms else 400) + 80

	parts: list[str] = []
	parts.append('<?xml version="1.0" encoding="UTF-8"?>')
	parts.append('<mxfile host="app.diagrams.net" modified="2026-03-26T00:00:00.000Z" agent="GitHub Copilot" version="24.7.17" type="device">')
	parts.append('  <diagram id="variants-lineage" name="Variants Lineage">')
	parts.append(
		f'    <mxGraphModel dx="{canvas_w}" dy="{canvas_h}" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{canvas_w}" pageHeight="{canvas_h}" math="0" shadow="0">'
	)
	parts.append('      <root>')
	parts.append('        <mxCell id="0"/>')
	parts.append('        <mxCell id="1" parent="0"/>')

	cell_id = 2

	# Encabezado columna para missing parents.
	if missing_parents:
		parts.append(
			f'        <mxCell id="{cell_id}" value="parents externos" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#f8cecc;strokeColor=#b85450;fontStyle=1;" vertex="1" parent="1">'
		)
		parts.append(
			'          <mxGeometry x="20" y="20" width="170" height="34" as="geometry"/>'
		)
		parts.append('        </mxCell>')
		cell_id += 1

	# Sin encabezados de fase: la alineacion vertical por columnas ya comunica la estructura.

	node_to_cell_id: dict[str, int] = {}
	for node in all_nodes:
		x, y = node_pos[node]
		is_missing = node in missing_parents
		label = wrap_label_text(node_labels.get(node, node), width=28)
		phase_name = variant_info.get(node, {}).get("phase") if node in variant_info else None
		lines_count = label.count("\n") + 1
		if compact_layout:
			node_h = node_h_uniform
		elif is_uniform_height_phase(phase_name):
			node_h = node_h_uniform
		else:
			node_h = max(38, 14 * lines_count + 16)
		xml_label = drawio_rich_label(label)
		style = (
			"rounded=1;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;"
			if is_missing
			else "rounded=1;whiteSpace=wrap;html=1;fillColor=#f1f3f4;strokeColor=#666666;"
		)
		parts.append(
			f'        <mxCell id="{cell_id}" value="{xml_label}" style="{style}" vertex="1" parent="1">'
		)
		parts.append(
			f'          <mxGeometry x="{x}" y="{y}" width="{node_w}" height="{node_h}" as="geometry"/>'
		)
		parts.append('        </mxCell>')
		node_to_cell_id[node] = cell_id
		cell_id += 1

	for parent, child in edges:
		source = node_to_cell_id.get(parent)
		target = node_to_cell_id.get(child)
		if source is None or target is None:
			continue
		is_f07_to_f08 = phase_of.get(parent) == "f07_modval" and phase_of.get(child) == "f08_sysval"
		stroke = f08_color.get(child, "#000000") if is_f07_to_f08 else "#000000"
		width = "2.2" if is_f07_to_f08 else "1.2"
		parts.append(
			f'        <mxCell id="{cell_id}" value="" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=block;endFill=1;strokeColor={stroke};strokeWidth={width};" edge="1" parent="1" source="{source}" target="{target}">'
		)
		parts.append('          <mxGeometry relative="1" as="geometry"/>')
		parts.append('        </mxCell>')
		cell_id += 1

	parts.append('      </root>')
	parts.append('    </mxGraphModel>')
	parts.append('  </diagram>')
	parts.append('</mxfile>')
	return "\n".join(parts) + "\n"


def write_drawio_output(executions_root: Path, drawio_xml: str, output_stem: str) -> Path:
	drawio_path = executions_root / f"{output_stem}.drawio"
	drawio_path.write_text(drawio_xml, encoding="utf-8")
	return drawio_path


def write_jpg_output(
	executions_root: Path,
	output_stem: str,
	phase_to_variants: dict[str, list[str]],
	edges: list[tuple[str, str]],
	variant_info: dict[str, dict[str, Any]],
	node_labels: dict[str, str],
	dpi: int,
	compact_layout: bool,
) -> Path:
	try:
		import matplotlib.pyplot as plt
		from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
	except Exception as exc:  # pragma: no cover - depende del entorno
		raise RuntimeError("No se pudo importar matplotlib para exportar JPG") from exc

	phase_names = list(phase_to_variants.keys())
	phase_x: dict[str, float] = {}
	phase_extra_gap_after_f07_jpg = 0.45 if compact_layout else 0.7
	phase_step_jpg = 1.05 if compact_layout else 1.45
	x = 0.0
	for phase in phase_names:
		if phase == "f08_sysval":
			x += phase_extra_gap_after_f07_jpg
		phase_x[phase] = x
		x += phase_step_jpg

	f08_variants = sorted(phase_to_variants.get("f08_sysval", []))
	palette = ["#e41a1c", "#377eb8", "#4daf4a", "#000000", "#984ea3", "#a65628", "#f781bf", "#999999"]
	f08_color: dict[str, str] = {v: palette[i % len(palette)] for i, v in enumerate(f08_variants)}

	node_geom: dict[str, tuple[float, float, float, float]] = {}
	y_min = 0.0
	y_max = 0.0

	for phase in phase_names:
		variants = phase_to_variants[phase]
		uniform_node_h = 0.48 if compact_layout else 1.55
		spacing = (uniform_node_h + 0.14) if compact_layout else (uniform_node_h + 0.28)
		for i, variant in enumerate(variants):
			label = wrap_label_text(node_labels.get(variant, variant), width=28)
			lines_count = label.count("\n") + 1
			node_w = 0.60 if compact_layout else 0.92
			if compact_layout:
				node_h = uniform_node_h
			elif is_uniform_height_phase(phase):
				node_h = uniform_node_h
			else:
				node_h = max(0.42, 0.22 + 0.10 * lines_count)
			xc = phase_x[phase]
			yc = -i * spacing
			node_geom[variant] = (xc, yc, node_w, node_h)
			y_min = min(y_min, yc - node_h / 2)
			y_max = max(y_max, yc + node_h / 2)

	x_min = -0.8
	x_max = max(phase_x.values()) + 0.8 if phase_x else 3.0
	fig_w = max(12.0 if compact_layout else 18.0, (x_max - x_min) * (1.7 if compact_layout else 2.2))
	fig_h = max(5.8 if compact_layout else 8.0, (y_max - y_min) * (1.0 if compact_layout else 1.2) + (1.2 if compact_layout else 2.0))
	fig, ax = plt.subplots(figsize=(fig_w, fig_h))

	phase_of: dict[str, str] = {}
	for phase, variants in phase_to_variants.items():
		for v in variants:
			phase_of[v] = phase

	# Flechas primero para que queden detrás de cajas.
	for parent, child in edges:
		if parent not in node_geom or child not in node_geom:
			continue
		sx, sy, sw, sh = node_geom[parent]
		tx, ty, tw, th = node_geom[child]

		if phase_of.get(parent) == "f07_modval" and phase_of.get(child) == "f08_sysval":
			start = (sx + sw / 2, sy)
			end = (tx - tw / 2, ty)
		elif tx >= sx:
			start = (sx + sw / 2, sy)
			end = (tx - tw / 2, ty)
		else:
			start = (sx - sw / 2, sy)
			end = (tx + tw / 2, ty)

		is_f07_to_f08 = phase_of.get(parent) == "f07_modval" and phase_of.get(child) == "f08_sysval"
		arrow_color = f08_color.get(child, "#000000") if is_f07_to_f08 else "#000000"
		arrow_width = 1.6 if is_f07_to_f08 else 0.8
		arrow_alpha = 0.95 if is_f07_to_f08 else 0.8

		arrow = FancyArrowPatch(
			start,
			end,
			arrowstyle="-|>",
			mutation_scale=9,
			linewidth=arrow_width,
			color=arrow_color,
			alpha=arrow_alpha,
		)
		ax.add_patch(arrow)

	# Sin encabezados de fase para reducir ruido visual.

	for variant, (xc, yc, node_w, node_h) in node_geom.items():
		x0 = xc - node_w / 2
		y0 = yc - node_h / 2
		box = FancyBboxPatch(
			(x0, y0),
			node_w,
			node_h,
			boxstyle="round,pad=0.03,rounding_size=0.03",
			facecolor="#f1f3f4",
			edgecolor="#666666",
			linewidth=0.9,
		)
		ax.add_patch(box)

		label = wrap_label_text(node_labels.get(variant, variant), width=28)
		lines = label.split("\n")
		name = lines[0]
		rest = "\n".join(lines[1:])

		ax.text(
			xc,
			y0 + node_h - 0.08,
			name,
			ha="center",
			va="top",
			fontsize=7.4 if compact_layout else 8.7,
			fontweight="bold",
		)
		if rest:
			ax.text(
				xc,
				y0 + node_h - 0.24,
				rest,
				ha="center",
				va="top",
				fontsize=6.1 if compact_layout else 6.8,
			)

	ax.set_xlim(x_min, x_max)
	ax.set_ylim(y_min - 0.4, y_max + 0.9)
	ax.axis("off")

	jpg_path = executions_root / f"{output_stem}.jpg"
	fig.savefig(jpg_path, dpi=max(120, dpi), format="jpg", bbox_inches="tight")
	plt.close(fig)
	return jpg_path


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Genera diagramas Mermaid y draw.io de fases/variantes y relaciones parent."
	)
	parser.add_argument(
		"--executions-root",
		required=True,
		help="Ruta a la carpeta de ejecuciones (ej. executions, executions-linux, executions3).",
	)
	parser.add_argument(
		"--output-stem",
		default="variants_lineage",
		help="Prefijo de archivos de salida sin extensión (default: variants_lineage).",
	)
	parser.add_argument(
		"--show-params",
		action="store_true",
		help="Añade en cada nodo los parámetros del variant (excluye variant/parent/parents).",
	)
	parser.add_argument(
		"--show-duration",
		action="store_true",
		help="Añade en cada nodo el tiempo de ejecución en segundos (time_s).",
	)
	parser.add_argument(
		"--label-mode",
		choices=["full", "variant-only"],
		default="full",
		help="Modo de etiqueta: full (actual) o variant-only (solo nombre de variante).",
	)
	parser.add_argument(
		"--max-param-lines",
		type=int,
		default=8,
		help="Máximo de líneas de parámetros por variante cuando --show-params está activo.",
	)
	parser.add_argument(
		"--max-param-value-len",
		type=int,
		default=70,
		help="Longitud máxima por valor de parámetro antes de truncar con ...",
	)
	parser.add_argument(
		"--lineage-source",
		choices=["index", "tree"],
		default="index",
		help=(
			"Fuente para extraer parentesco: "
			"index=usa metadata.yaml + params.yaml; "
			"tree=escanea params.yaml dentro del arbol dado."
		),
	)
	parser.add_argument(
		"--export-jpg",
		action="store_true",
		help="Exporta también una imagen JPG del grafo.",
	)
	parser.add_argument(
		"--jpg-dpi",
		type=int,
		default=220,
		help="Resolución de salida para JPG (dpi).",
	)
	parser.add_argument(
		"--compact-layout",
		action="store_true",
		help="Usa cajas uniformes más pequeñas y menor separación para reducir tamaño final.",
	)
	return parser.parse_args()


def main() -> int:
	args = parse_args()
	executions_root = Path(args.executions_root).expanduser().resolve()

	if not executions_root.exists() or not executions_root.is_dir():
		raise SystemExit(f"No existe la carpeta de ejecuciones: {executions_root}")

	phase_to_variants, edges, known_variants, variant_info = build_graph(
		executions_root,
		max_value_len=max(20, args.max_param_value_len),
		lineage_source=args.lineage_source,
	)
	node_labels = build_node_labels(
		known_variants,
		variant_info,
		show_params=args.show_params,
		show_duration=args.show_duration,
		max_param_lines=max(1, args.max_param_lines),
		label_mode=args.label_mode,
	)
	mermaid_text = to_mermaid(phase_to_variants, edges, known_variants, node_labels)
	mmd_path, md_path = write_outputs(executions_root, mermaid_text, args.output_stem)
	drawio_xml = to_drawio_xml(
		phase_to_variants,
		edges,
		known_variants,
		node_labels,
		variant_info,
		compact_layout=args.compact_layout,
	)
	drawio_path = write_drawio_output(executions_root, drawio_xml, args.output_stem)
	jpg_path: Path | None = None
	if args.export_jpg:
		jpg_path = write_jpg_output(
			executions_root=executions_root,
			output_stem=args.output_stem,
			phase_to_variants=phase_to_variants,
			edges=edges,
			variant_info=variant_info,
			node_labels=node_labels,
			dpi=args.jpg_dpi,
			compact_layout=args.compact_layout,
		)

	print(f"Diagrama generado: {mmd_path}")
	print(f"Vista Markdown:   {md_path}")
	print(f"Archivo draw.io:  {drawio_path}")
	if jpg_path is not None:
		print(f"Archivo JPG:      {jpg_path}")
	print(
		"Opciones: "
		f"show_params={'on' if args.show_params else 'off'}, "
		f"show_duration={'on' if args.show_duration else 'off'}, "
		f"label_mode={args.label_mode}, "
		f"lineage_source={args.lineage_source}, "
		f"compact_layout={'on' if args.compact_layout else 'off'}, "
		f"export_jpg={'on' if args.export_jpg else 'off'}"
	)
	print(f"Fases: {len(phase_to_variants)} | Variantes: {len(known_variants)} | Enlaces: {len(edges)}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
