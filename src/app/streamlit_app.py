import os
import streamlit as st
import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("API_URL")

st.title("POC - QuantumFinance API de Crédito")

# 1. Fluxo de Autenticação
st.sidebar.header("Credenciais do Parceiro")
username = st.sidebar.text_input("Usuário")
password = st.sidebar.text_input("Senha", type="password")

if "jwt_token" not in st.session_state:
    st.session_state["jwt_token"] = None

if st.sidebar.button("Autenticar e Gerar Token"):
    try:
        res = requests.post(
            f"{API_URL}/token",
            data={"username": username, "password": password},
            timeout=10,
        )
        if res.status_code == 200:
            st.session_state["jwt_token"] = res.json()["access_token"]
            st.sidebar.success("Autenticado via JWT!")
        else:
            st.sidebar.error("Falha na autenticação.")
    except requests.exceptions.RequestException:
        st.sidebar.error("Erro ao conectar com a API.")

# 2. Fluxo de Inferência
st.header("Analisador de Risco de Crédito")
with st.form("score_form"):
    c1, c2 = st.columns(2)
    renda        = c1.number_input("Renda Mensal (R$)",        min_value=0.0,   max_value=50000.0, value=4500.0)
    idade        = c2.number_input("Idade (anos)",              min_value=0.0,   max_value=120.0,   value=42.0)
    etnia        = c1.number_input("Etnia (código)",            min_value=0,     max_value=10,      value=0)
    sexo         = c2.selectbox("Sexo", options=[0, 1], format_func=lambda x: "Feminino" if x == 0 else "Masculino")
    casapropria  = c1.selectbox("Casa Própria", options=[0, 1], format_func=lambda x: "Não" if x == 0 else "Sim")
    outrasrendas = c2.selectbox("Outras Rendas", options=[0, 1], format_func=lambda x: "Não" if x == 0 else "Sim")
    estadocivil  = c1.number_input("Estado Civil (código)",     min_value=0,     max_value=10,      value=1)
    escolaridade = c2.number_input("Escolaridade (0–3)",        min_value=0,     max_value=3,       value=2)

    submit = st.form_submit_button("Consultar Score")

if submit:
    if not st.session_state["jwt_token"]:
        st.warning("Gere o token JWT na barra lateral primeiro.")
    else:
        payload = {
            "renda":        renda,
            "idade":        idade,
            "etnia":        etnia,
            "sexo":         sexo,
            "casapropria":  casapropria,
            "outrasrendas": outrasrendas,
            "estadocivil":  estadocivil,
            "escolaridade": escolaridade,
        }
        headers = {"Authorization": f"Bearer {st.session_state['jwt_token']}"}

        try:
            with st.spinner("Processando..."):
                response = requests.post(
                    f"{API_URL}/predict",
                    json=payload,
                    headers=headers,
                    timeout=10,
                )

            if response.status_code == 200:
                data = response.json()
                if data["score_predito"] == 1:
                    st.error(f"**{data['risco_interpretavel']}**")
                else:
                    st.success(f"**{data['risco_interpretavel']}**")

                col1, col2, col3 = st.columns(3)
                col1.metric("Score Predito", data["score_predito"])
                col2.metric("Probabilidade", f"{data['score_probabilidade']:.2%}")
                col3.metric("Nível de Risco", data["score_level"])
            elif response.status_code == 429:
                st.error("Erro 429: Limite de requisições excedido. Aguarde 1 minuto.")
            else:
                st.error(f"Erro {response.status_code}: Falha ao processar a predição.")
        except requests.exceptions.RequestException:
            st.error("Erro ao conectar com a API.")
