# scripts/core/mlflow_register.py
import os, yaml, pathlib, sys
import mlflow
from mlflow.tracking import MlflowClient

def main():
    variant    = os.environ.get("VARIANT")
    phase      = os.environ.get("PHASE5", "f05_modeling")
    mlflow_uri = os.environ.get("MLFLOW_URI", "")

    if not variant:
        print("[ERROR] VARIANT env var is required")
        sys.exit(1)

    if mlflow_uri:
        mlflow.set_tracking_uri(mlflow_uri)

    client = MlflowClient()

    outs_path = pathlib.Path(f"executions/{phase}/{variant}/outputs.yaml")
    data = yaml.safe_load(outs_path.read_text()) if outs_path.exists() else None
    if data is None:
        print(f"[ERROR] outputs.yaml not found at {outs_path}")
        sys.exit(1)

    reg = data.get("mlflow_registration") if isinstance(data, dict) else None
    if not reg:
        print("[WARN] No 'mlflow_registration' block in outputs.yaml - skipping")
        sys.exit(0)

    experiment_name = reg.get("experiment_name") or f"F05_{variant}"
    metrics   = reg.get("metrics", {})
    params    = reg.get("params", {})
    artifacts = reg.get("artifacts", [])

    exp = client.get_experiment_by_name(experiment_name)
    if exp is None:
        try:
            exp_id = client.create_experiment(experiment_name)
            print(f"[INFO] Experiment created: {experiment_name} (id={exp_id})")
        except Exception as exc:
            print(f"[ERROR] Could not create experiment '{experiment_name}': {exc}")
            sys.exit(1)
    else:
        exp_id = exp.experiment_id
        print(f"[INFO] Using existing experiment: {experiment_name} (id={exp_id})")

    with mlflow.start_run(experiment_id=exp_id) as run:
        run_id = run.info.run_id
        for k, v in params.items():
            mlflow.log_param(k, v)
        for k, v in metrics.items():
            mlflow.log_metric(k, float(v))
        for a in artifacts:
            if os.path.exists(a):
                mlflow.log_artifact(a)

    data["mlflow"] = {
        "run_id": run_id,
        "experiment_id": exp_id,
        "experiment_name": experiment_name,
    }
    outs_path.write_text(yaml.safe_dump(data, sort_keys=False))
    print(f"[OK] MLflow run created: {run_id} (experiment: {experiment_name})")

if __name__ == "__main__":
    main()
