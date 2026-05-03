# feature_repo/feature_views.py
import os
from feast import FeatureView, Field, FileSource, Entity
from feast.types import Float32, Int64
from feast.value_type import ValueType
from datetime import timedelta

_PARQUET_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "processed", "transaction_features.parquet",
)

# Definição da Entidade principal
customer = Entity(name="customer_id", join_keys=["customer_id"], value_type=ValueType.INT64)

# Fonte de dados offline (Parquet processado pela ingestão)
transaction_stats_source = FileSource(
    path=_PARQUET_PATH,
    timestamp_field="event_timestamp"
)

# Feature View — colunas conforme BaseDefault01.csv
transaction_features = FeatureView(
    name="customer_transaction_stats",
    entities=[customer],
    ttl=timedelta(days=30),
    schema=[
        Field(name="renda",       dtype=Float32),
        Field(name="idade",       dtype=Float32),
        Field(name="etnia",       dtype=Int64),
        Field(name="sexo",        dtype=Int64),
        Field(name="casapropria", dtype=Int64),
        Field(name="outrasrendas",dtype=Int64),
        Field(name="estadocivil", dtype=Int64),
        Field(name="escolaridade",dtype=Int64),
    ],
    online=True,
    source=transaction_stats_source,
    tags={"team": "credit_risk"}
)
