# config.py

BASE_DIR = "executions"
DST_HTML_DIR = "executions"
OUTPUT_FILENAME = "pipeline_lineage.html"

# f01_explore  f03_windows  f05_modeling  f07_modval  pipeline_lineage.html
# f02_events   f04_targets  f06_quant     f08_sysval

PHASES = [
    {"name": "f01_explore",  "parent_keys": [], "metadata": ["metadata.yml"]},
    {"name": "f02_events",   "parent_keys": ["parent"], "metadata": ["metadata.yml"]},
    {"name": "f03_windows",  "parent_keys": ["parameters","parent_variant"], "metadata": ["metadata.yml"]},
    {"name": "f04_targets",  "parent_keys": ["parameters","parent_variant"], "metadata": ["metadata.yml"]},
    {"name": "f05_modeling", "parent_keys": ["parameters","parent_variant"], "metadata": ["metadata.yml"]},
    {"name": "f06_quant",    "parent_keys": ["parameters","parent_variant"], "metadata": ["metadata.yml"]},
    {"name": "f07_modval",   "parent_keys": ["parameters","parent_variant"], "metadata": ["metadata.yml"]},
    {"name": "f08_sysval",   "parent_keys": ["parameters","parent_variant"], "metadata": ["metadata.yml"]},
]

PHASE_COLORS = {
    "f01_explore":           {"bg": "#E3F2FD", "border": "#90CAF9", "text": "#1565C0"},
    "f02_events":   {"bg": "#E8F5E9", "border": "#A5D6A7", "text": "#2E7D32"},
    "f03_windows":  {"bg": "#FFF3E0", "border": "#FFCC80", "text": "#EF6C00"},
    "f04_targets": {"bg": "#F3E5F5", "border": "#CE93D8", "text": "#6A1B9A"},
    "f05_modeling":          {"bg": "#FFEBEE", "border": "#EF9A9A", "text": "#C62828"},
    "f06_quant":         {"bg": "#E0F7FA", "border": "#80DEEA", "text": "#006064"},
    "f07_modval":         {"bg": "#ECEFF1", "border": "#B0BEC5", "text": "#37474F"},
    "f08_sysval":       {"bg": "#F9FBE7", "border": "#E6EE9C", "text": "#827717"},
    "default":              {"bg": "#FFFFFF", "border": "#CCCCCC", "text": "#333333"}
}

CSS_STYLES = """
    /* Reseteamos el body para que no genere scroll extra */
    body { 
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
        background-color: #f8f9fa; 
        margin: 0; 
        padding: 0; 
        overflow: hidden; /* Oculta el scrollbar general de la ventana */
        height: 100vh;
        width: 100vw;
    }

    /* El contenedor es el único que hace scroll */
    .pipeline-container { 
        display: flex; 
        flex-direction: row; 
        gap: 80px; 
        overflow: auto; /* Único scrollbar aquí */
        padding: 40px; 
        box-sizing: border-box;
        height: 100%;
        align-items: flex-start; 
    }
    
    .phase-column { 
        display: flex; 
        flex-direction: column; 
        gap: 18px; 
        min-width: 220px; 
        flex-shrink: 0; /* EVITA QUE LAS CAJAS SE APLASTEN O DESAPAREZCAN */
        background: #fff; 
        padding: 15px; 
        border-radius: 10px; 
        box-shadow: 0 2px 4px rgba(0,0,0,0.05); 
        border-top: 4px solid #dee2e6;
        position: relative;
        z-index: 1;
    }
    
    .phase-title { text-align: center; color: #343a40; font-size: 1rem; margin-bottom: 10px; border-bottom: 2px solid #e9ecef; padding-bottom: 10px; text-transform: uppercase; font-weight: bold; }
    
    .variant-card {
        border-width: 2px; border-style: solid; border-radius: 8px; 
        /* CLAVE: Relleno mínimo arriba (6px), derecha (4px) y abajo (6px). Mantenemos 12px a la izq para el texto */
        padding: 6px 4px 6px 26px; 
        cursor: pointer; transition: all 0.2s ease; font-weight: 600;
        position: relative; z-index: 2; 
        display: flex;
        flex-direction: column;
        gap: 10px;
        text-align: left;
        height: max-content; 
    }

    .variant-card:hover { transform: translateY(-3px); box-shadow: 0 6px 12px rgba(0,0,0,0.1); filter: brightness(0.95); }

    .variant-card-head {
        display: flex;
        align-items: center; /* Alinea los iconos con el texto de forma centrada */
        justify-content: space-between;
        gap: 10px;
        width: 100%;
        min-height: 1.5rem;
    }

    .variant-id {
        font-size: 0.95rem;
        line-height: 1.2;
        word-break: break-word;
        flex: 1; /* Permite al texto empujar los iconos a la derecha */
    }

    .variant-card-state-row {
        display: flex;
        width: 100%;
        justify-content: center;
    }


    .variant-card-statuses {
        display: flex;
        flex-wrap: nowrap;
        gap: 4px; /* Reducido para coincidir con el stack */
        align-items: center;
        justify-content: space-between;
        width: 100%;
    }

    .variant-card-state-stack {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 2px; /* Pegados entre sí verticalmente */
        flex: 0 0 auto;
        /* Ancho ajustado: 2 iconos de 1.4rem + 2px de separación */
        width: calc(2.8rem + 2px); 
    }

    .status-badge {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 0;
        /* Tamaño intermedio: llenan el espacio porque ya no hay padding que los estorbe */
        width: 1.4rem; 
        height: 1.4rem; 
        border-radius: 50%;
        padding: 0;
        font-size: 0.9rem; 
        line-height: 1;
        font-weight: 800;
        border: 1px solid transparent;
        white-space: nowrap;
        flex: 0 0 1.4rem; 
        box-sizing: border-box;
    }

    .lifecycle-badge {
        width: 100%; 
        border-radius: 0.7rem; /* Mitad de la altura (1.4rem) para hacer la píldora perfecta */
        flex: 1 1 auto;
    }

    .lifecycle-badge.lifecycle-variant-created { background: #FFFFFF; color: #1565C0; border-color: #90CAF9; }
    .lifecycle-badge.lifecycle-execution-running { background: #fff8e1; color: #8d6e63; border-color: #ffcc80; }
    .lifecycle-badge.lifecycle-execution-completed { background: #e8f5e9; color: #2E7D32; border-color: #A5D6A7; }
    .lifecycle-badge.lifecycle-execution-failed { background: #ffebee; color: #C62828; border-color: #EF9A9A; }
    .lifecycle-badge.lifecycle-none { background: #f5f5f5; color: #616161; border-color: #e0e0e0; }

    .verified-badge.verified-none { background: #ffffff; color: #546e7a; border-color: #cfd8dc; }
    .verified-badge.verified-false { background: #ffebee; color: #C62828; border-color: #EF9A9A; }
    .verified-badge.verified-true { background: #e8f5e9; color: #2E7D32; border-color: #A5D6A7; }

    .registred-badge.registred-none { background: #ffffff; color: #546e7a; border-color: #cfd8dc; }
    .registred-badge.registred-false { background: #ffebee; color: #C62828; border-color: #EF9A9A; }
    .registred-badge.registred-true { background: #e8f5e9; color: #2E7D32; border-color: #A5D6A7; }
    
    #config-panel {
        position: fixed; top: 0; right: -450px; width: 400px; height: 100vh; background: white;
        box-shadow: -4px 0 15px rgba(0,0,0,0.1); transition: right 0.3s ease; padding: 20px; overflow-y: auto; z-index: 10;
        box-sizing: border-box;
    }
    #config-panel.open { right: 0; }
    .close-btn { cursor: pointer; color: red; float: right; font-weight: bold; }
    pre { background: #f1f3f5; padding: 10px; border-radius: 5px; overflow-x: auto; font-size: 0.85rem; }
"""