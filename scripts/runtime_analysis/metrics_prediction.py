# scripts/runtime_analysis/metrics_prediction.py
# -*- coding: utf-8 -*-

"""
Runtime prediction metrics engine.

Provides:
    - compute_prediction_metrics()
    - compute_full_prediction_metrics()

Pure analytical module.
No CLI. No prints. No file writing.
"""

import pandas as pd


def compute_prediction_metrics(
    df: pd.DataFrame,
    fp_index_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute prediction metrics per model.

    fp_index_df must contain:
        - model_name
        - fingerprint
        - expected   (0/1)
    """
    results = []

    required_cols = {"model_name", "fingerprint", "expected"}
    if not required_cols.issubset(fp_index_df.columns):
        raise ValueError(
            "fp_index_df must contain columns: model_name, fingerprint, expected"
        )

    df_func = df[df["event_name"] == "FUNC_PRED_RESULT"].copy() if not df.empty else pd.DataFrame()
    if not df_func.empty:
        df_func["fingerprint"] = pd.to_numeric(df_func["fingerprint"], errors="coerce")
        df_func["predicted"] = pd.to_numeric(df_func["predicted"], errors="coerce")

    for model_name, g_fp in fp_index_df.groupby("model_name"):
        df_model_all = df[df["model_name"] == model_name] if not df.empty else pd.DataFrame()
        df_model_pred = df_func[df_func["model_name"] == model_name] if not df_func.empty else pd.DataFrame()

        n_pred_results = int((df_model_all["event_name"] == "FUNC_PRED_RESULT").sum()) if not df_model_all.empty else 0
        n_offload_results = int((df_model_all["event_name"] == "FUNC_OFFLOAD_RESULT").sum()) if not df_model_all.empty else 0
        n_urgent_results = int((df_model_all["event_name"] == "FUNC_URGENT_RESULT").sum()) if not df_model_all.empty else 0

        TP = FP = FN = TN = 0
        skipped = 0

        expected_map = dict(
            zip(
                g_fp["fingerprint"].astype(int),
                g_fp["expected"].astype(int),
            )
        )

        if not df_model_pred.empty:
            for _, row in df_model_pred.iterrows():
                fp = row["fingerprint"]
                pred = row["predicted"]

                if pd.isna(fp) or pd.isna(pred):
                    skipped += 1
                    continue

                fp = int(fp)
                pred = int(pred)

                if fp == 0:
                    skipped += 1
                    continue

                if fp not in expected_map:
                    skipped += 1
                    continue

                exp = int(expected_map[fp])

                if pred == 1 and exp == 1:
                    TP += 1
                elif pred == 1 and exp == 0:
                    FP += 1
                elif pred == 0 and exp == 1:
                    FN += 1
                elif pred == 0 and exp == 0:
                    TN += 1
                else:
                    skipped += 1

        N = TP + FP + FN + TN

        accuracy = (TP + TN) / N if N > 0 else None
        precision = TP / (TP + FP) if (TP + FP) > 0 else None
        recall = TP / (TP + FN) if (TP + FN) > 0 else None
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision is not None and recall is not None and (precision + recall) > 0
            else None
        )
        false_negative_rate = FN / (FN + TP) if (FN + TP) > 0 else None

        results.append({
            "model_name": str(model_name),
            "n_pred_results": n_pred_results,
            "n_offload_results": n_offload_results,
            "n_urgent_results": n_urgent_results,
            "N_total": int(N),
            "accuracy": float(accuracy) if accuracy is not None else None,
            "precision": float(precision) if precision is not None else None,
            "recall": float(recall) if recall is not None else None,
            "f1": float(f1) if f1 is not None else None,
            "TP": int(TP),
            "FP": int(FP),
            "FN": int(FN),
            "TN": int(TN),
            "false_negative_rate": float(false_negative_rate) if false_negative_rate is not None else None,
            "skipped_predictions": int(skipped),
        })

    return pd.DataFrame(results)


def compute_full_prediction_metrics(
    df: pd.DataFrame,
    fp_index_df: pd.DataFrame,
) -> pd.DataFrame:
    return compute_prediction_metrics(df, fp_index_df)