import re
from typing import List


FNV_OFFSET_BASIS = 2166136261
FNV_PRIME = 16777619


def normalize_window(window):
    """
    Convierte una ventana a una lista Python en formato estable.
    """
    if hasattr(window, "tolist"):
        return window.tolist()
    if isinstance(window, (list, tuple)):
        return list(window)
    if hasattr(window, "item"):
        return [window.item()]
    return [window]


def normalize_events_for_fingerprint(window) -> List[int]:
    """
    Normaliza una ventana para fingerprint compatible con firmware/F07.

    Reglas:
    - [] -> [0] (ventana vacia)
    - cada valor se interpreta como int; el enmascarado a uint8 se aplica en hash
    """
    values = normalize_window(window)
    if not values:
        return [0]
    return [int(v) for v in values]


def fnv1a_32(events: List[int]) -> int:
    """
    FNV-1a 32-bit compatible con events_mgr_fingerprint (firmware).
    """
    h = FNV_OFFSET_BASIS
    for e in events:
        h ^= int(e) & 0xFF
        h = (h * FNV_PRIME) & 0xFFFFFFFF
    return h


def window_fingerprint(window) -> int:
    """
    Calcula fingerprint FNV-1a 32-bit de una ventana.
    """
    return fnv1a_32(normalize_events_for_fingerprint(window))


def parse_events_cell(value, empty_as_zero: bool = True) -> List[int]:
    """
    Extrae enteros de una celda textual de eventos.

    Soporta formatos como "[57 60]", "[57, 60]" o "57 60".
    """
    text = "" if value is None else str(value).strip()
    if not text or text == "[]":
        return [0] if empty_as_zero else []

    nums = re.findall(r"-?\d+", text)
    if not nums:
        return [0] if empty_as_zero else []

    return [int(n) for n in nums]