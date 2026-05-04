import sys
import os
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from api.main import app
from dotenv import load_dotenv

load_dotenv()

# Le as credenciais dos parceiros autorizados a partir de variáveis de ambiente
_raw_partners = os.getenv("VALID_PARTNERS", "")
VALID_PARTNERS = dict(pair.split(":") for pair in _raw_partners.split(",") if ":" in pair) if _raw_partners else {}

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    # 200 quando modelo está carregado, 503 quando não está (e.g. em CI sem MLflow)
    assert response.status_code in [200, 503]


def test_generate_token_success():
    response = client.post("/token", data={"username": username, "password": password})
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert response.json()["token_type"] == "bearer"


def test_generate_token_failure():
    response = client.post("/token", data={"username": username, "password": "wrongpassword"})
    assert response.status_code == 401


def test_predict_without_token():
    payload = {
        "renda": 4500.0,
        "idade": 42.0,
        "etnia": 0,
        "sexo": 1,
        "casapropria": 1,
        "outrasrendas": 0,
        "estadocivil": 1,
        "escolaridade": 2,
    }
    response = client.post("/predict", json=payload)
    assert response.status_code == 401


def test_predict_with_invalid_payload():
    token_resp = client.post("/token", data={"username": username, "password": password})
    token = token_resp.json()["access_token"]

    bad_payload = {"renda": "alto"}
    response = client.post("/predict", json=bad_payload, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 422
