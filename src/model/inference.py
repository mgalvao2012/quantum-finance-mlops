import sys
import os
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


class InferenceEngine:
    def __init__(self):
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        model_uri = f"models:/{MODEL_NAME}/Production"
        self.model = mlflow.xgboost.load_model(model_uri)

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
