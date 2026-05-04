import os
from dotenv import load_dotenv

load_dotenv()

# MLflow Tracking & Registry
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI")
EXPERIMENT_NAME = os.getenv("EXPERIMENT_NAME")
MODEL_NAME = os.getenv("MODEL_NAME")
MIN_ROC_AUC_THRESHOLD = float(os.getenv("MIN_ROC_AUC", "0.75"))

# API Security (JWT) — set API_SECRET_KEY env var in production; never use the default below
SECRET_KEY = os.getenv("API_SECRET_KEY", "dev-insecure-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("TOKEN_EXPIRE_MIN", "60"))

if os.getenv("ENV", "development") == "production" and SECRET_KEY == "dev-insecure-secret-change-in-production":
    raise RuntimeError("API_SECRET_KEY must be set to a strong value in production.")

# Diretórios de Dados
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_RAW_PATH = os.path.join(BASE_DIR, "data", "raw")
DATA_PROCESSED_PATH = os.path.join(BASE_DIR, "data", "processed")
DRIFT_REPORTS_PATH = os.path.join(BASE_DIR, "data", "drift_reports")
MLFLOW_DB_PATH = os.path.join(BASE_DIR, "mlruns.db")
FEATURE_REPO_PATH = os.path.join(BASE_DIR, "feature_repo")
PARQUET_PATH = os.path.join(DATA_PROCESSED_PATH, "transaction_features.parquet")

# Fonte de dados brutos
DATA_RAW_URL = os.getenv("DATA_RAW_URL")

# Features servidas pelo Feast (nomes conforme CSV: BaseDefault01.csv)
FEATURE_REFS = [
    "customer_transaction_stats:renda",
    "customer_transaction_stats:idade",
    "customer_transaction_stats:etnia",
    "customer_transaction_stats:sexo",
    "customer_transaction_stats:casapropria",
    "customer_transaction_stats:outrasrendas",
    "customer_transaction_stats:estadocivil",
    "customer_transaction_stats:escolaridade",
]
TARGET_COLUMN = "default"
