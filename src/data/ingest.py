"""Ingestão de dados brutos: baixa o CSV público, normaliza para o schema do
Feast (adiciona event_timestamp e customer_id) e salva como Parquet em
data/processed/transaction_features.parquet.

Deve ser executado uma vez antes de `feast apply` e antes de cada ciclo de
re-treinamento que precise de dados frescos.

Uso:
    python src/data/ingest.py
"""
import sys
import os
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATA_RAW_URL, PARQUET_PATH, TARGET_COLUMN


def ingest() -> pd.DataFrame:
    print(f"Baixando dados de: {DATA_RAW_URL}")
    df = pd.read_csv(DATA_RAW_URL)

    # Garante coluna de entidade
    if "customer_id" not in df.columns:
        df.insert(0, "customer_id", range(len(df)))

    # Feast exige uma coluna de timestamp com timezone
    if "event_timestamp" not in df.columns:
        df["event_timestamp"] = pd.Timestamp("now", tz="UTC")

    # Descarta coluna de nome (sem valor preditivo)
    df = df.drop(columns=["nome"], errors="ignore")

    # Colunas a persistir: entidade + timestamp + features + target
    feature_cols = [
        "customer_id",
        "event_timestamp",
        "renda",
        "idade",
        "etnia",
        "sexo",
        "casapropria",
        "outrasrendas",
        "estadocivil",
        "escolaridade",
    ]
    if TARGET_COLUMN in df.columns:
        feature_cols.append(TARGET_COLUMN)

    available = [c for c in feature_cols if c in df.columns]
    df_out = df[available].copy()

    os.makedirs(os.path.dirname(PARQUET_PATH), exist_ok=True)
    df_out.to_parquet(PARQUET_PATH, index=False)
    print(f"Parquet salvo em: {PARQUET_PATH}  ({len(df_out)} linhas)")
    return df_out


if __name__ == "__main__":
    ingest()
