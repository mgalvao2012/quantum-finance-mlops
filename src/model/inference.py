import sys
import os
import glob
import pandas as pd
import mlflow
import mlflow.xgboost

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MLFLOW_TRACKING_URI, MODEL_NAME


def _score_level(probability: float) -> str:
    if probability < 0.3:
        return "Baixo"
    if probability < 0.6:
        return "Médio"
    return "Alto"


def _resolve_model_path() -> str:
    """Return a path mlflow.xgboost.load_model can read.

    Resolution order:
    1. MODEL_PATH env var (explicit override)
    2. Registry → run_id → local artifacts dir (honra a promoção `Production`)
    3. Glob de mlruns/*/*/artifacts/model (bootstrap fallback)
    4. mlflow URI `models:/<NAME>/Production` (último recurso)
    """
    explicit = os.getenv("MODEL_PATH")
    if explicit:
        return explicit

    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    try:
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        client = mlflow.MlflowClient()
        versions = client.get_latest_versions(MODEL_NAME, stages=["Production"])
        if versions:
            v = versions[0]
            run = client.get_run(v.run_id)
            candidate = os.path.join(
                base_dir, "mlruns", run.info.experiment_id, v.run_id, "artifacts", "model"
            )
            if os.path.isdir(candidate):
                return candidate
    except Exception:
        pass

    matches = sorted(glob.glob(os.path.join(base_dir, "mlruns", "*", "*", "artifacts", "model")))
    if matches:
        return matches[-1]

    return f"models:/{MODEL_NAME}/Production"


class InferenceEngine:
    def __init__(self):
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        self.model = mlflow.xgboost.load_model(_resolve_model_path())

    def predict(self, input_data: dict) -> dict:
        df = pd.DataFrame([input_data])
        proba = float(self.model.predict_proba(df)[0, 1])
        label = int(proba >= 0.5)
        return {
            "score_predito": label,
            "score_probabilidade": round(proba, 4),
            "score_level": _score_level(proba),
            "risco_interpretavel": "Risco Detectado" if label == 1 else "Aprovado",
        }


engine = InferenceEngine()
