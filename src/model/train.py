import sys
import os
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
import mlflow
from mlflow.tracking import MlflowClient
from mlflow.models.signature import infer_signature
from feast import FeatureStore

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    MLFLOW_TRACKING_URI, EXPERIMENT_NAME, MODEL_NAME,
    MIN_ROC_AUC_THRESHOLD, DRIFT_REPORTS_PATH,
    FEATURE_REPO_PATH, FEATURE_REFS, TARGET_COLUMN, PARQUET_PATH,
)
from model.drift import detect_data_drift


def load_features_from_store() -> pd.DataFrame:
    """Busca features do Feast Offline Store usando a entity_df do Parquet."""
    store = FeatureStore(repo_path=FEATURE_REPO_PATH)

    # Lê o Parquet completo para montar a entity_df com customer_id, timestamp e target
    raw = pd.read_parquet(PARQUET_PATH)
    entity_cols = ["customer_id", "event_timestamp"]
    if TARGET_COLUMN in raw.columns:
        entity_cols.append(TARGET_COLUMN)
    entity_df = raw[entity_cols]

    print("Buscando features do Feast Offline Store...")
    training_df = store.get_historical_features(
        entity_df=entity_df,
        features=FEATURE_REFS,
    ).to_df()

    return training_df


def main():
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT_NAME)
    client = MlflowClient()

    df = load_features_from_store()

    # Divisão em referência histórica e lote atual para Drift Detection
    reference_df = df.sample(frac=0.5, random_state=42)
    current_df = df.drop(reference_df.index)

    # 1. Drift Detection
    drift_report_path = os.path.join(DRIFT_REPORTS_PATH, "drift_report.html")
    os.makedirs(DRIFT_REPORTS_PATH, exist_ok=True)

    feature_cols = [r.split(":")[1] for r in FEATURE_REFS]
    is_drifting = detect_data_drift(
        reference_df[feature_cols],
        current_df[feature_cols],
        drift_report_path,
    )
    if is_drifting:
        print("ALERTA: Data Drift detectado! Verifique o relatório gerado. Treinamento prosseguirá com ressalvas.")

    # 2. Preparação de features e target
    X = current_df[feature_cols]
    y = current_df[TARGET_COLUMN] if TARGET_COLUMN in current_df.columns else pd.Series(0, index=X.index)

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    # 3. Treinamento e rastreamento no MLflow
    with mlflow.start_run() as run:
        params = {"objective": "binary:logistic", "eval_metric": "auc", "max_depth": 3, "learning_rate": 0.05}
        model = xgb.XGBClassifier(**params)
        model.fit(X_train, y_train)

        y_pred_proba = model.predict_proba(X_test)[:, 1]
        roc_auc = roc_auc_score(y_test, y_pred_proba)

        mlflow.log_metrics({"test_roc_auc": roc_auc, "data_drift_detected": int(is_drifting)})
        signature = infer_signature(X_train, model.predict(X_train))
        mlflow.xgboost.log_model(xgb_model=model, artifact_path="model", signature=signature)

        # 4. Promoção automática no Model Registry
        if roc_auc >= MIN_ROC_AUC_THRESHOLD and not is_drifting:
            model_uri = f"runs:/{run.info.run_id}/model"
            registered_model = mlflow.register_model(model_uri, MODEL_NAME)

            client.transition_model_version_stage(
                name=MODEL_NAME,
                version=registered_model.version,
                stage="Production",
                archive_existing_versions=True,
            )
            print(f"Versão {registered_model.version} promovida para Produção no Registry.")


if __name__ == "__main__":
    main()
