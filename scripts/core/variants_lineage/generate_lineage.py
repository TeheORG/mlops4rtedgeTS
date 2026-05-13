# generate_html.py
import html
import os
import yaml
import json
import re
from config import BASE_DIR, PHASES, PHASE_COLORS, CSS_STYLES, DST_HTML_DIR, OUTPUT_FILENAME

VARIANT_ID_REGEX = re.compile(r"^v(?P<phase>\d)_(?P<seq>\d{4})$")

LIFECYCLE_STATE_ICONS = {
    # "VARIANT_CREATED": "🆕",
    "VARIANT_CREATED": "🇻",
    "EXECUTION_RUNNING": "⏳",
    "EXECUTION_COMPLETED": "✅",
    "EXECUTION_FAILED": "❌",
}

LIFECYCLE_STATE_LABELS = {
    "VARIANT_CREATED": "Created",
    "EXECUTION_RUNNING": "Running",
    "EXECUTION_COMPLETED": "Completed",
    "EXECUTION_FAILED": "Failed",
}


def _phase_code(phase_name):
    m = re.match(r"^f(\d{2})(?:_|$)", phase_name)
    return str(int(m.group(1))) if m else None


def _list_phase_variants(phase_name):
    phase_dir = os.path.join(BASE_DIR, phase_name)
    if not os.path.isdir(phase_dir):
        return []

    code = _phase_code(phase_name)
    variants = []
    for entry in sorted(os.listdir(phase_dir)):
        entry_path = os.path.join(phase_dir, entry)
        if not os.path.isdir(entry_path):
            continue
        m = VARIANT_ID_REGEX.fullmatch(entry)
        if not m:
            continue
        if code and m.group("phase") != code:
            continue
        variants.append(entry)
    return variants

def load_yaml(filepath):
    if not os.path.exists(filepath):
        return {}
    with open(filepath, 'r') as file:
        return yaml.safe_load(file) or {}


def _normalize_metadata_specs(metadata_specs):
    if not metadata_specs:
        return ["metadata.yaml"]
    if isinstance(metadata_specs, str):
        return [metadata_specs]
    if isinstance(metadata_specs, (list, tuple)):
        return [str(item) for item in metadata_specs if isinstance(item, str) and item.strip()]
    return ["metadata.yaml"]


def _candidate_metadata_paths(phase_name, variant_id, metadata_specs):
    candidates = []
    seen = set()
    for spec in _normalize_metadata_specs(metadata_specs):
        variant_dir = os.path.join(BASE_DIR, phase_name, variant_id)
        alt_paths = [os.path.join(variant_dir, spec)]
        if alt_paths[0].endswith(".yml"):
            alt_paths.append(alt_paths[0][:-4] + ".yaml")
        elif alt_paths[0].endswith(".yaml"):
            alt_paths.append(alt_paths[0][:-5] + ".yml")
        # Backward compatibility: also look for a shared phase-level file.
        phase_base = os.path.join(BASE_DIR, phase_name, spec)
        alt_paths.extend([phase_base])
        if phase_base.endswith(".yml"):
            alt_paths.append(phase_base[:-4] + ".yaml")
        elif phase_base.endswith(".yaml"):
            alt_paths.append(phase_base[:-5] + ".yml")
        for path in alt_paths:
            if path not in seen:
                seen.add(path)
                candidates.append(path)
    return candidates


def _load_phase_metadata(phase_name, variant_id, metadata_specs):
    candidates = _candidate_metadata_paths(phase_name, variant_id, metadata_specs)
    for path in candidates:
        if os.path.exists(path):
            return load_yaml(path), path
    return {}, candidates[0] if candidates else ""


def _state_slug(value):
    if value is None:
        return "none"
    return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-") or "none"


def _display_state(value):
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    return str(value)


def _lifecycle_state_text(lifecycle_state):
    label = LIFECYCLE_STATE_LABELS.get(lifecycle_state, _display_state(lifecycle_state).replace("_", " "))
    icon = LIFECYCLE_STATE_ICONS.get(lifecycle_state, "•")
    return icon, label


def _status_value_class(value):
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "none"


def _verified_badge(value):
    status_class = _status_value_class(value)
    icon = {"true": "✓", "false": "✗", "none": "Ｏ"}[status_class]
    return f'<span class="status-badge verified-badge verified-{status_class}" title="verified: {_display_state(value)}">{icon}</span>'


def _registred_badge(value):
    status_class = _status_value_class(value)
    return f'<span class="status-badge registred-badge registred-{status_class}" title="registred: {_display_state(value)}">R</span>'


def _lifecycle_badge(lifecycle_state):
    status_class = _state_slug(lifecycle_state)
    icon, label = _lifecycle_state_text(lifecycle_state)
    return f'<span class="status-badge lifecycle-badge lifecycle-{status_class}" title="lifecycle_state: {_display_state(lifecycle_state)}">{icon}</span>'


def _as_parent_path(parent_key_spec):
    """Normalize parent key spec to a YAML path list.

    Examples:
    - "parent" -> ["parent"]
    - ["parameters", "parents"] -> ["parameters", "parents"]
    """
    if isinstance(parent_key_spec, str):
        return [parent_key_spec]
    if isinstance(parent_key_spec, (list, tuple)) and all(isinstance(k, str) for k in parent_key_spec):
        return list(parent_key_spec)
    return []


def _normalize_parent_paths(parent_key_specs):
    """Return a list of candidate YAML paths for parent lookup.

    Supported input forms:
    - ["parent"]                          -> [["parent"]]
    - ["parent", "parents"]              -> [["parent", "parents"], ["parent"], ["parents"]]
    - ["parameters", "parents"]          -> [["parameters", "parents"], ["parameters"], ["parents"]]
    - [["parameters", "parents"], "parent"] -> [["parameters", "parents"], ["parent"]]
    """
    if not isinstance(parent_key_specs, (list, tuple)):
        return []

    paths = []

    # Ambiguous list[str]: could be one nested path OR multiple top-level keys.
    if all(isinstance(item, str) for item in parent_key_specs):
        if parent_key_specs:
            paths.append(list(parent_key_specs))
        paths.extend([[item] for item in parent_key_specs])
    else:
        for spec in parent_key_specs:
            path = _as_parent_path(spec)
            if path:
                paths.append(path)

    # Deduplicate paths while preserving order.
    unique_paths = []
    seen = set()
    for path in paths:
        key = tuple(path)
        if key not in seen:
            seen.add(key)
            unique_paths.append(path)
    return unique_paths


def _get_value_by_path(data, path):
    """Traverse a YAML dict using a path of keys, returning None on missing nodes."""
    current = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _extract_parents(params, parent_key_specs):
    """Extract parent ids from configured key specs with arbitrary YAML depth."""
    parents = []
    for path in _normalize_parent_paths(parent_key_specs):

        val = _get_value_by_path(params, path)
        if val is None:
            continue

        if isinstance(val, list):
            parents.extend(val)
        elif isinstance(val, dict):
            # Ignore map-like values (e.g., selecting "parameters" node itself).
            continue
        else:
            parents.append(val)

    # Keep order while removing duplicates and null-like values.
    clean = []
    seen = set()
    for p in parents:
        if p is None:
            continue
        p = str(p)
        if p not in seen:
            seen.add(p)
            clean.append(p)
    return clean

def build_html_dashboard():
    html_columns = []
    edges_js = []
    configs_data = {}

    for i, phase in enumerate(PHASES):
        phase_name = phase["name"]
        variant_ids = _list_phase_variants(phase_name)
        
        colors = PHASE_COLORS.get(phase_name, PHASE_COLORS["default"])
        
        column_html = f'<div class="phase-column" id="col_{phase_name}" style="border-top-color: {colors["border"]}">'
        column_html += f'<div class="phase-title">{phase_name}</div>'

        if variant_ids:
            for variant_id in variant_ids:
                node_id = f"{phase_name}_{variant_id}"
                
                card_style = f"background-color: {colors['bg']}; border-color: {colors['border']}; color: {colors['text']};"
                params_path = os.path.join(BASE_DIR, phase_name, variant_id, "params.yaml")
                params = load_yaml(params_path)
                metadata, metadata_path = _load_phase_metadata(phase_name, variant_id, phase.get("metadata", []))

                lifecycle_state = metadata.get("lifecycle_state")
                verified = metadata.get("verified", "none")
                registred = metadata.get("registred", "none")

                configs_data[node_id] = {
                    "params_path": params_path,
                    "metadata_path": metadata_path,
                    "params": params,
                    "metadata": metadata,
                }

                lifecycle_badge = _lifecycle_badge(lifecycle_state)
                verified_badge = _verified_badge(verified)
                registred_badge = _registred_badge(registred)

                column_html += f'''
                    <div class="variant-card" id="{node_id}" style="{card_style}" onclick="showConfig('{node_id}')" onmouseenter="highlightLines('{node_id}')" onmouseleave="resetLines()">
                        <div class="variant-card-head">
                            <div class="variant-id">{html.escape(variant_id)}</div>
                            <div class="variant-card-state-stack">
                                <div class="variant-card-state-row">
                                    {lifecycle_badge}
                                </div>
                                <div class="variant-card-statuses">
                                    {verified_badge}
                                    {registred_badge}
                                </div>
                            </div>
                        </div>
                    </div>
                '''

                parents = _extract_parents(params, phase.get("parent_keys", []))
                
                if parents and i > 0:
                    prev_phase_name = PHASES[i - 1]["name"]
                    for p in parents:
                        parent_node_id = f"{prev_phase_name}_{p}"
                        
                        # Guardamos el objeto línea junto con su origen y destino
                        edges_js.append(f"""
                            var startNode = document.getElementById('{parent_node_id}');
                            var endNode = document.getElementById('{node_id}');
                            if (startNode && endNode) {{
                                var line = new LeaderLine(startNode, endNode, {{ 
                                    color: '#adb5bd', 
                                    size: 2, 
                                    path: 'fluid', 
                                    startSocket: 'right', 
                                    endSocket: 'left'
                                }});
                                lines.push({{
                                    obj: line,
                                    source: '{parent_node_id}',
                                    target: '{node_id}'
                                }});
                            }}
                        """)
        
        column_html += '</div>'
        html_columns.append(column_html)

    html_template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>MLOps Pipeline Lineage</title>
        <style>{CSS_STYLES}</style>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/leader-line/1.0.7/leader-line.min.js"></script>
    </head>
    <body>
        <div class="pipeline-container" id="pipeline-container">
            {''.join(html_columns)}
        </div>

        <div id="config-panel">
            <span class="close-btn" onclick="closeConfig()">Cerrar ✕</span>
            <h2 id="config-title">Configuración</h2>
            <pre id="config-content">Selecciona una variante...</pre>
        </div>

        <script>
            let lines = [];
            const variantConfigs = {json.dumps(configs_data, ensure_ascii=False)};

            function showConfig(nodeId) {{
                document.getElementById('config-panel').classList.add('open');
                document.getElementById('config-title').innerText = "Variante: " + nodeId;
                document.getElementById('config-content').innerText = JSON.stringify(variantConfigs[nodeId], null, 2);
            }}

            function closeConfig() {{
                document.getElementById('config-panel').classList.remove('open');
            }}

            // Función auxiliar para encontrar todos los ancestros (padres, abuelos, etc.)
            function findAllAncestors(nodeId, visitedNodes) {{
                if (!visitedNodes) visitedNodes = new Set();
                if (visitedNodes.has(nodeId)) return [];
                visitedNodes.add(nodeId);
                
                let ancestors = [];
                lines.forEach(function(l) {{
                    if (l.target === nodeId && !visitedNodes.has(l.source)) {{
                        ancestors.push(l.source);
                        ancestors = ancestors.concat(findAllAncestors(l.source, visitedNodes));
                    }}
                }});
                return ancestors;
            }}

            // Función auxiliar para encontrar todos los descendientes (hijos, nietos, etc.)
            function findAllDescendants(nodeId, visitedNodes) {{
                if (!visitedNodes) visitedNodes = new Set();
                if (visitedNodes.has(nodeId)) return [];
                visitedNodes.add(nodeId);
                
                let descendants = [];
                lines.forEach(function(l) {{
                    if (l.source === nodeId && !visitedNodes.has(l.target)) {{
                        descendants.push(l.target);
                        descendants = descendants.concat(findAllDescendants(l.target, visitedNodes));
                    }}
                }});
                return descendants;
            }}

            // Función para resaltar líneas conectadas al nodo y su genealogía completa
            function highlightLines(nodeId) {{
                // Encontrar todos los ancestros y descendientes
                let ancestors = findAllAncestors(nodeId);
                let descendants = findAllDescendants(nodeId);
                let connectedNodes = new Set([nodeId, ...ancestors, ...descendants]);
                
                lines.forEach(function(l) {{
                    // Resaltar si la línea conecta nodos en la genealogía
                    if (connectedNodes.has(l.source) && connectedNodes.has(l.target)) {{
                        l.obj.color = '#ff5722'; // Naranja para resaltar
                        l.obj.size = 4;          // Más gruesa
                    }} else {{
                        l.obj.color = 'rgba(173, 181, 189, 0.1)'; // Transparente para ocultar
                    }}
                }});
            }}

            // Función para volver al estado original
            function resetLines() {{
                lines.forEach(function(l) {{
                    l.obj.color = '#adb5bd';
                    l.obj.size = 2;
                }});
            }}

            window.addEventListener('load', function() {{
                // Le damos 150ms al navegador para que dibuje el layout completo antes de trazar las líneas
                setTimeout(function() {{
                    {chr(10).join(edges_js)}
                }}, 150);
            }});

            // Listener de scroll ajustado usando requestAnimationFrame para mayor rendimiento
            document.getElementById('pipeline-container').addEventListener('scroll', function() {{
                window.requestAnimationFrame(function() {{
                    lines.forEach(function(l) {{
                        l.obj.position(); // Actualizado para llamar a .obj
                    }});
                }});
            }});

            window.addEventListener('resize', function() {{
                lines.forEach(function(l) {{
                    l.obj.position(); // Actualizado para llamar a .obj
                }});
            }});
        </script>
    </body>
    </html>
    """

    os.makedirs(DST_HTML_DIR, exist_ok=True)
    output_path = os.path.join(DST_HTML_DIR, OUTPUT_FILENAME)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_template)
    print(f"Dashboard generado: {output_path}")

if __name__ == "__main__":
    build_html_dashboard()