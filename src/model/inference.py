import sys
import os
import glob
import pandas as pd
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

    Order of resolution:
    1. MODEL_PATH env var (explicit override)
    2. Local artifact dir discovered by glob (portable across host/container)
    3. Fallback to the MLflow registry URI (only works when the registry's
       stored source path matches the current filesystem)
    """
    explicit = os.getenv("MODEL_PATH")
    if explicit:
        return explicit

    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
