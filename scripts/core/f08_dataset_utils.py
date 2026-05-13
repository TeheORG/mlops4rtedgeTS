"""
F08 — Dataset utilities (shared inference + per-model evaluation)

Responsabilidad:
- Construir dataset único de ventanas para inferencia en edge
- Generar clave estable de ventana (window_key)
- Deduplicar ventanas
- Preparar datasets para evaluación por modelo
"""

from pathlib import Path
from typing import List, Tuple

import pandas as pd

from scripts.runtime_analysis.window_fingerprint import (
    normalize_window,
    window_fingerprint,
)


def compute_window_key(window) -> str:
    """
    Genera clave estable de ventana equivalente al fingerprint F07/edge.

    Se devuelve como string para mantener compatibilidad con el contrato
    de columna window_key usado en merges/tablas.
    """
    return str(window_fingerprint(window))


# ============================================================
# BUILD UNIQUE INFERENCE DATASET
# ============================================================

def build_unique_windows_dataset(
    dataset_path: Path,
    max_rows: int = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    A partir de un dataset etiquetado:
    - genera columna window_key
    - deduplica ventanas
    - devuelve:
        df_unique: ventanas únicas
        df_full: dataset original con window_key
    """

    df = pd.read_parquet(dataset_path)

    if max_rows:
        df = df.head(max_rows)

    # Generar clave
    df["window_key"] = df["OW_events"].apply(compute_window_key)

    # Dataset único
    df_unique = (
        df[["window_key", "OW_events"]]
        .drop_duplicates(subset=["window_key"])
        .reset_index(drop=True)
    )

    return df_unique, df


def save_unique_windows_csv(df_unique: pd.DataFrame, output_path: Path):
    """
    Guarda dataset único en CSV para F082 → edge runtime
    """
    df_unique.to_csv(output_path, index=False)


# ============================================================
# BUILD INFERENCE PAYLOAD
# ============================================================

def build_inference_windows_list(df_unique: pd.DataFrame) -> List[List]:
    """
    Convierte dataset único en lista de ventanas listas para enviar a runtime
    """
    return df_unique["OW_events"].apply(normalize_window).tolist()


# ============================================================
# PREPARE EVALUATION DATASET (PER MODEL)
# ============================================================

def prepare_evaluation_dataset(
    dataset_path: Path,
    max_rows: int = None,
) -> pd.DataFrame:
    """
    Carga dataset etiquetado y añade window_key.
    Se usará en F084.
    """

    df = pd.read_parquet(dataset_path)

    if max_rows:
        df = df.head(max_rows)

    df["window_key"] = df["OW_events"].apply(compute_window_key)

    return df


# ============================================================
# MERGE PREDICTIONS (PER MODEL)
# ============================================================

def merge_predictions_with_labels(
    df_eval: pd.DataFrame,
    df_predictions: pd.DataFrame,
    prediction_name: str,
) -> pd.DataFrame:
    """
    Cruza predicciones con dataset etiquetado.

    df_predictions esperado:
        window_key | prediction_name | y_pred
    """

    model_preds = df_predictions[
        df_predictions["prediction_name"] == prediction_name
    ][["window_key", "y_pred"]]

    merged = df_eval.merge(model_preds, on="window_key", how="left")

    return merged


# ============================================================
# METRICS (PER MODEL)
# ============================================================

def compute_confusion_metrics(df: pd.DataFrame):
    """
    Calcula TP, TN, FP, FN + métricas básicas
    """

    valid = df[df["y_pred"].notna()].copy()
    valid["y_pred"] = valid["y_pred"].astype(int)

    tp = ((valid["label"] == 1) & (valid["y_pred"] == 1)).sum()
    tn = ((valid["label"] == 0) & (valid["y_pred"] == 0)).sum()
    fp = ((valid["label"] == 0) & (valid["y_pred"] == 1)).sum()
    fn = ((valid["label"] == 1) & (valid["y_pred"] == 0)).sum()

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )

    return {
        "tp": int(tp),
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }