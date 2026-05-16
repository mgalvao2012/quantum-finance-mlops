# QuantumFinance — Sistema de Credit Score com MLOps

> Trabalho Final — MBA em Data Science & IA | FIAP  
> Disciplina: Machine Learning Engineering

> 📘 **Implantação em produção**: para subir esta API ao Azure (Container Apps) e a UI ao Streamlit Community Cloud via CI/CD, consulte **[DeployToAzure.md](DeployToAzure.md)**.

---

## Sumário

1. [Visão Geral](#visão-geral)
2. [Arquitetura](#arquitetura)
3. [Estrutura de Diretórios](#estrutura-de-diretórios)
4. [Dependências](#dependências)
5. [Configuração do Ambiente](#configuração-do-ambiente)
6. [Variáveis de Ambiente](#variáveis-de-ambiente)
7. [Ingestão de Dados](#ingestão-de-dados)
8. [Pipeline de Treinamento](#pipeline-de-treinamento)
9. [API de Inferência](#api-de-inferência)
10. [Interface Web (Streamlit)](#interface-web-streamlit)
11. [Feature Store (Feast)](#feature-store-feast)
12. [Detecção de Data Drift (Evidently)](#detecção-de-data-drift-evidently)
13. [Rastreamento de Experimentos (MLflow)](#rastreamento-de-experimentos-mlflow)
14. [Testes](#testes)
15. [CI/CD](#cicd)
16. [Implantação no Azure](#implantação-no-azure)
17. [Segurança](#segurança)
18. [Decisões de Design](#decisões-de-design)

---

## Visão Geral

O **QuantumFinance Credit Score** é uma prova de conceito (POC) de um sistema completo de **avaliação de risco de crédito** construído com práticas de MLOps. O sistema integra:

- **Ingestão** de dados brutos com normalização para o schema do Feature Store
- Treinamento automatizado de um modelo **XGBoost** com detecção de *data drift* antes de cada ciclo
- **Registro e promoção automática** do modelo via MLflow Model Registry
- **API REST** (FastAPI) com autenticação JWT e *rate limiting* por IP
- **Interface web** (Streamlit) para consulta interativa de scores
- **Feature Store** (Feast) integrado ao pipeline de treinamento via `get_historical_features()`
- **Pipeline CI/CD** (GitHub Actions) com linting, testes e validação de features

O modelo classifica clientes em dois grupos:

| `score_predito` | Interpretação |
|---|---|
| `0` | Aprovado — baixo risco de inadimplência |
| `1` | Risco Detectado — alto risco de inadimplência |

---

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────┐
│                        DADOS & FEATURES                         │
│                                                                 │
│  CSV (GCS) ──► ingest.py ──► Parquet ──► Feast Offline Store    │
│                                                │                │
│                                                ▼                │
│                              train.py ──► get_historical_       │
│                                 │         features()            │
│                                 │              │                │
│                          Drift Detection       │                │
│                                 │              ▼                │
│                                 └──────► XGBoost.fit()          │
│                                                │                │
│                                          MLflow Registry        │
└────────────────────────────────────────────────│────────────────┘
                                                 │
                                          modelo "Production"
                                                 │
┌────────────────────────────────────────────────▼────────────────┐
│                        SERVIÇO DE INFERÊNCIA                    │
│                                                                 │
│  POST /token ──► JWT Bearer Token                               │
│                       │                                         │
│  POST /predict ◄───── │ ──► InferenceEngine ──► score_predito   │
│  (rate limit: 5/min)  │                                         │
│  GET  /health         │                                         │
└───────────────────────│─────────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────────┐
│                       INTERFACE WEB                             │
│                                                                 │
│  Streamlit App ──► Autenticação ──► Formulário ──► Resultado    │
└─────────────────────────────────────────────────────────────────┘
```

### Fluxo completo

```
1. Ingestão
   CSV (GCS) ──► ingest.py ──► data/processed/transaction_features.parquet

2. Inicialização do Feature Store
   feast apply  ──► registry.db + online_store.db

3. Treinamento
   Parquet ──► get_historical_features() ──► detect_data_drift()
          ──► XGBClassifier.fit() ──► mlflow.log_metrics()
          ──► mlflow.register_model() ──► transition_to_stage("Production")

4. Inferência
   Cliente ──► POST /token ──► JWT
   JWT + features ──► POST /predict ──► InferenceEngine.predict()
                  ──► {"score_predito": 0|1, "risco_interpretavel": "..."}
```

---

## Estrutura de Diretórios

```
quantumfinance_credit_score/
│
├── .github/
│   └── workflows/
│       └── ci_cd.yml               # Pipeline CI/CD (GitHub Actions)
│
├── data/
│   ├── drift_reports/              # Relatórios HTML do Evidently (gerados em runtime)
│   ├── processed/                  # Parquet gerado pela ingestão (fonte do Feast)
│   └── raw/                        # Dados brutos (excluídos do git)
│
├── feature_repo/
│   ├── feature_store.yaml          # Configuração do Feast (projeto, registry, stores)
│   └── feature_views.py            # Definição de entidade e feature views
│
├── src/
│   ├── api/
│   │   ├── auth.py                 # Geração e verificação de JWT
│   │   ├── main.py                 # Aplicação FastAPI (endpoints, rate limiting)
│   │   └── schemas.py              # Schemas Pydantic de entrada e saída
│   │
│   ├── app/
│   │   ├── requirements.txt        # Dependências enxutas para Streamlit Community Cloud
│   │   └── streamlit_app.py        # Interface web para consulta de scores
│   │
│   ├── data/
│   │   └── ingest.py               # Ingestão: baixa CSV, normaliza e salva Parquet
│   │
│   ├── model/
│   │   ├── drift.py                # Módulo de detecção de data drift (Evidently)
│   │   ├── inference.py            # Motor de inferência (carrega modelo do MLflow)
│   │   └── train.py                # Pipeline de treinamento e promoção de modelo
│   │
│   └── config.py                   # Configuração centralizada via variáveis de ambiente
│
├── tests/
│   └── test_api.py                 # Testes de integração da API (pytest)
│
├── Dockerfile                      # Build multi-stage da imagem da API (deploy no Azure)
├── .dockerignore                   # Exclusões do contexto de build Docker
├── requirements.txt                # Dependências Python fixadas por versão (ambiente completo)
├── requirements-api.txt            # Dependências apenas de runtime de inferência (imagem Docker)
├── setup.sh                        # Script de configuração completa do ambiente
├── DeployToAzure.md                # Guia completo de implantação no Azure + Streamlit Cloud
└── README.md                       # Este arquivo
```

---

## Dependências

| Biblioteca | Versão | Finalidade |
|---|---|---|
| `pandas` | 2.3.0 | Manipulação de dados |
| `scikit-learn` | 1.4.2 | Divisão de dados, métricas |
| `xgboost` | 2.1.0 | Modelo de classificação binária |
| `mlflow` | 2.16.0 | Rastreamento de experimentos e Model Registry |
| `fastapi` | 0.109.0 | Framework da API REST |
| `uvicorn` | 0.34.0 | Servidor ASGI para a API |
| `slowapi` | 0.1.9 | Rate limiting por IP |
| `PyJWT` | 2.8.0 | Geração e verificação de tokens JWT |
| `passlib[bcrypt]` | 1.7.4 | Utilitários de criptografia |
| `python-multipart` | 0.0.6 | Suporte a formulários OAuth2 |
| `streamlit` | 1.41.0 | Interface web interativa |
| `feast` | 0.50.0 | Feature Store |
| `evidently` | 0.5.0 | Detecção de data drift e qualidade de dados |

**Python requerido:** 3.10+

---

## Configuração do Ambiente

### Opção 1 — Script automático (recomendado)

```bash
bash setup.sh
source .venv/bin/activate
```

O script executa automaticamente todas as etapas:
1. Cria o virtualenv e instala as dependências
2. Baixa os dados brutos e gera o Parquet (`src/data/ingest.py`)
3. Inicializa o Feature Store (`feast apply`)
4. Executa o treinamento inicial (`src/model/train.py`)

### Opção 2 — Manual

```bash
# 1. Criar e ativar o virtualenv
python -m venv .venv
source .venv/bin/activate          # Linux/macOS
# .venv\Scripts\activate           # Windows

# 2. Instalar dependências
pip install --upgrade pip
pip install -r requirements.txt

# 3. Ingerir dados e gerar o Parquet
python src/data/ingest.py

# 4. Inicializar o Feature Store
cd feature_repo && feast apply && cd ..

# 5. Treinar o modelo
python src/model/train.py
```

---

## Variáveis de Ambiente

Todas as configurações possuem valores padrão para desenvolvimento local. **Em produção, as variáveis marcadas como obrigatórias devem ser definidas.**

| Variável | Padrão (dev) | Obrigatória em prod | Descrição |
|---|---|---|---|
| `API_SECRET_KEY` | `quantum_finance_super_secret_key_mock` | **Sim** | Chave secreta para assinatura dos tokens JWT |
| `ENV` | `development` | **Sim** | Defina como `production` para ativar validações de segurança |
| `VALID_PARTNERS` | `partner_a:password123` | **Sim** | Credenciais dos parceiros no formato `user:senha,user2:senha2` |
| `MLFLOW_TRACKING_URI` | `sqlite:////<raiz>/mlruns.db` | Não | URI do servidor MLflow |
| `EXPERIMENT_NAME` | `QuantumFinance_Credit_Score_Alternativo` | Não | Nome do experimento no MLflow |
| `MODEL_NAME` | `XGBoost_Transaction_Score` | Não | Nome do modelo no MLflow Registry |
| `MIN_ROC_AUC` | `0.75` | Não | Limiar mínimo de ROC-AUC para promoção do modelo |
| `TOKEN_EXPIRE_MIN` | `60` | Não | Tempo de expiração do JWT em minutos |
| `API_URL` | `http://localhost:8000` | Não | URL da API usada pelo Streamlit |
| `DATA_RAW_URL` | URL pública do GCS | Não | URL do CSV de dados brutos |

> **Atenção:** Se `ENV=production` e `API_SECRET_KEY` for o valor padrão, a aplicação recusará iniciar com `RuntimeError`.

Exemplo de arquivo `.env` para desenvolvimento:

```dotenv
ENV=development
API_SECRET_KEY=troque_por_uma_chave_forte_aqui
VALID_PARTNERS=user:password
TOKEN_EXPIRE_MIN=60
MLFLOW_TRACKING_URI=sqlite:///mlruns.db
EXPERIMENT_NAME=QuantumFinance_Credit_Score_Alternativo
MODEL_NAME=XGBoost_Transaction_Score
MIN_ROC_AUC=0.75
DATA_RAW_URL=https://storage.googleapis.com/ds-publico/IA/BaseDefault01.csv
API_URL=http://localhost:8000
```

---

## Ingestão de Dados

**Arquivo:** [src/data/ingest.py](src/data/ingest.py)

### Execução

```bash
python src/data/ingest.py
```

### O que faz

1. Baixa o CSV de `DATA_RAW_URL` (Google Cloud Storage por padrão)
2. Adiciona coluna `customer_id` (índice sequencial) se ausente
3. Adiciona coluna `event_timestamp` com o timestamp atual em UTC (exigido pelo Feast)
4. Descarta a coluna `nome` (sem valor preditivo)
5. Salva o resultado como Parquet em `data/processed/transaction_features.parquet`

Este Parquet é a **fonte de dados do Feast Offline Store** e deve existir antes de `feast apply` e antes de cada ciclo de re-treinamento.

### Dataset: BaseDefault01.csv

| Coluna | Tipo | Descrição |
|---|---|---|
| `renda` | float | Renda mensal do cliente (R$) |
| `idade` | float | Idade do cliente (anos) |
| `etnia` | int | Etnia (codificada numericamente) |
| `sexo` | int | Sexo (0=feminino, 1=masculino) |
| `casapropria` | int | Possui casa própria (0=não, 1=sim) |
| `outrasrendas` | int | Possui outras fontes de renda (0=não, 1=sim) |
| `estadocivil` | int | Estado civil (codificado numericamente) |
| `escolaridade` | int | Nível de escolaridade (0–3) |
| `default` | int | **Target** — inadimplência (0=não, 1=sim) |

---

## Pipeline de Treinamento

**Arquivo:** [src/model/train.py](src/model/train.py)

### Pré-requisito

O Parquet e o Feature Store devem estar inicializados antes do primeiro treinamento (feito automaticamente pelo `setup.sh`).

### Execução

```bash
python src/model/train.py
```

### Etapas do pipeline

```
1. Carregamento via Feast Offline Store
   └─► FeatureStore.get_historical_features(entity_df, features=FEATURE_REFS)
   └─► Retorna DataFrame com as 8 features + coluna default

2. Preparação para Drift Detection
   └─► Divide o dataset em referência (50%) e lote atual (50%)

3. Detecção de Data Drift
   └─► Executa detect_data_drift() com Evidently DataDriftPreset
   └─► Gera relatório HTML em data/drift_reports/drift_report.html
   └─► Emite alerta se drift for detectado

4. Treinamento do modelo
   └─► Separação de features (8 colunas) e target (default)
   └─► Divisão treino/teste: 80% / 20% com stratify=y
   └─► XGBClassifier: objective=binary:logistic, max_depth=3, learning_rate=0.05

5. Avaliação e registro no MLflow
   └─► Calcula ROC-AUC no conjunto de teste
   └─► Loga métricas: test_roc_auc, data_drift_detected
   └─► Registra o modelo com assinatura de entrada/saída inferida

6. Promoção automática (condicional)
   └─► Condição: ROC-AUC >= 0.75 E sem drift detectado
   └─► Promove versão para o estágio "Production"
   └─► Arquiva versões anteriores automaticamente
```

### Critério de promoção

| Condição | Resultado |
|---|---|
| ROC-AUC ≥ 0.75 **e** sem drift | Modelo promovido para `Production` |
| ROC-AUC < 0.75 **ou** drift detectado | Modelo registrado, mas **não** promovido |

---

## API de Inferência

**Arquivo:** [src/api/main.py](src/api/main.py)

### Inicialização

```bash
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```

A documentação interativa (Swagger UI) fica disponível em `http://localhost:8000/docs`.

### Autenticação no Swagger UI

1. Clique em **Authorize** (cadeado) no topo direito da página
2. Preencha `username` e `password` e clique em **Authorize**
3. O Swagger chama `/token` automaticamente, obtém o JWT e o injeta em todas as requisições subsequentes

### Endpoints

#### `GET /health`

Verifica se a API está operacional e se o modelo está carregado.

```bash
curl http://localhost:8000/health
```

| Status | Significado |
|---|---|
| `200 OK` | API saudável, modelo disponível |
| `503 Service Unavailable` | Modelo não carregado (MLflow indisponível) |

**Resposta 200:**
```json
{ "status": "ok" }
```

---

#### `POST /token`

Autentica um parceiro e retorna um token JWT Bearer.

```bash
curl -X POST http://localhost:8000/token \
  -d "username=partner_a&password=password123"
```

**Resposta 200:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

| Status | Significado |
|---|---|
| `200 OK` | Token gerado com sucesso |
| `401 Unauthorized` | Usuário ou senha incorretos |

---

#### `POST /predict`

Retorna o score de risco de crédito para um cliente.

**Requer:** `Authorization: Bearer <token>`  
**Rate limit:** 5 requisições por minuto por IP

```bash
curl -X POST http://localhost:8000/predict \
  -H "Authorization: Bearer <seu_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "renda": 4500.0,
    "idade": 42.0,
    "etnia": 0,
    "sexo": 1,
    "casapropria": 1,
    "outrasrendas": 0,
    "estadocivil": 1,
    "escolaridade": 2
  }'
```

**Schema de entrada:**

| Campo | Tipo | Restrição | Descrição |
|---|---|---|---|
| `renda` | `float` | ≥ 0.0 | Renda mensal do cliente (R$) |
| `idade` | `float` | ≥ 0.0 | Idade do cliente (anos) |
| `etnia` | `int` | ≥ 0 | Etnia (codificada numericamente) |
| `sexo` | `int` | ≥ 0 | Sexo (0=feminino, 1=masculino) |
| `casapropria` | `int` | ≥ 0 | Possui casa própria (0=não, 1=sim) |
| `outrasrendas` | `int` | ≥ 0 | Possui outras fontes de renda (0=não, 1=sim) |
| `estadocivil` | `int` | ≥ 0 | Estado civil (codificado numericamente) |
| `escolaridade` | `int` | ≥ 0 | Nível de escolaridade (0–3) |

**Resposta 200:**
```json
{
  "score_predito": 0,
  "score_probabilidade": 0.0191,
  "score_level": "Baixo",
  "risco_interpretavel": "Aprovado"
}
```

| Campo | Tipo | Descrição |
|---|---|---|
| `score_predito` | `int` | Classe binária: `0` = Aprovado, `1` = Risco Detectado |
| `score_probabilidade` | `float` | Probabilidade de inadimplência (0.0–1.0) |
| `score_level` | `str` | Nível de risco: `Baixo` (< 30%), `Médio` (30–60%), `Alto` (> 60%) |
| `risco_interpretavel` | `str` | Classificação semântica: `Aprovado` ou `Risco Detectado` |

| Status | Significado |
|---|---|
| `200 OK` | Predição realizada |
| `401 Unauthorized` | Token ausente ou inválido |
| `422 Unprocessable Entity` | Payload com campos inválidos ou ausentes |
| `429 Too Many Requests` | Limite de 5 req/min excedido |
| `500 Internal Server Error` | Falha interna na inferência |
| `503 Service Unavailable` | Modelo não disponível |

---

## Interface Web (Streamlit)

**Arquivo:** [src/app/streamlit_app.py](src/app/streamlit_app.py)

### Execução

```bash
streamlit run src/app/streamlit_app.py
```

A interface abre automaticamente em `http://localhost:8501`.

### Fluxo de uso

1. **Autenticação** — informe usuário e senha na barra lateral e clique em "Autenticar e Gerar Token". O JWT é armazenado na sessão.
2. **Consulta** — preencha os campos do formulário com os dados do cliente. Campos binários (`sexo`, `casapropria`, `outrasrendas`) usam seletores de opção para melhor usabilidade.
3. **Resultado** — o score é exibido com destaque visual (fundo verde para aprovado, fundo vermelho para risco).

A URL da API é configurável via variável de ambiente `API_URL` (padrão: `http://localhost:8000`).

### Deploy no Streamlit Community Cloud

A UI também pode ser publicada gratuitamente em [share.streamlit.io](https://share.streamlit.io) apontando para a API hospedada no Azure. O arquivo [src/app/requirements.txt](src/app/requirements.txt) já está pronto para esse deploy (dependências enxutas, sem `xgboost`/`mlflow`/`feast`). O passo a passo está na **Fase 6** de [DeployToAzure.md](DeployToAzure.md).

---

## Feature Store (Feast)

**Diretório:** [feature_repo/](feature_repo/)

O projeto utiliza **Feast** com integração real ao pipeline de treinamento via `get_historical_features()`.

### Configuração ([feature_store.yaml](feature_repo/feature_store.yaml))

```yaml
project: quantumfinance_credit
provider: local
offline_store:
  type: file          # Parquet local
online_store:
  type: sqlite        # SQLite local
```

### Feature View definida

**Nome:** `customer_transaction_stats`  
**Entidade:** `customer_id` (Int64)  
**TTL:** 30 dias  
**Fonte:** `data/processed/transaction_features.parquet`

| Feature | Tipo Feast | Descrição |
|---|---|---|
| `renda` | `Float32` | Renda mensal do cliente (R$) |
| `idade` | `Float32` | Idade do cliente (anos) |
| `etnia` | `Int64` | Etnia (codificada numericamente) |
| `sexo` | `Int64` | Sexo (0=feminino, 1=masculino) |
| `casapropria` | `Int64` | Possui casa própria (0=não, 1=sim) |
| `outrasrendas` | `Int64` | Outras fontes de renda (0=não, 1=sim) |
| `estadocivil` | `Int64` | Estado civil (codificado numericamente) |
| `escolaridade` | `Int64` | Nível de escolaridade (0–3) |

### Integração com o treinamento

O `train.py` consome as features diretamente do Feast Offline Store:

```python
store = FeatureStore(repo_path=FEATURE_REPO_PATH)
training_df = store.get_historical_features(
    entity_df=entity_df,   # customer_id + event_timestamp + default
    features=FEATURE_REFS, # lista definida em config.py
).to_df()
```

### Comandos úteis

```bash
cd feature_repo

# Visualizar mudanças antes de aplicar
feast plan

# Aplicar definições ao registry e stores
feast apply

# Materializar features para o online store
feast materialize-incremental $(date -u +"%Y-%m-%dT%H:%M:%S")
```

> **Nota:** O `feast apply` precisa que o Parquet já exista em `data/processed/`. Execute `python src/data/ingest.py` antes se o arquivo não estiver presente.

---

## Detecção de Data Drift (Evidently)

**Arquivo:** [src/model/drift.py](src/model/drift.py)

### Funcionamento

A função `detect_data_drift(reference_data, current_data, report_path)`:

1. Compara o lote de dados atual contra uma base de referência histórica usando o preset `DataDriftPreset` do Evidently
2. Gera um relatório visual interativo em HTML no caminho especificado (padrão: `data/drift_reports/drift_report.html`)
3. Retorna `True` se drift significativo foi detectado no dataset como um todo, `False` caso contrário

### Integração com o treinamento

O pipeline de treinamento (`train.py`) chama `detect_data_drift()` **antes** de iniciar o treinamento, passando apenas as 8 colunas de feature (sem target):

- Se drift for detectado → emite alerta e treina com ressalvas; modelo **não é promovido** automaticamente
- Se não houver drift → treinamento prossegue normalmente; promoção condicionada ao ROC-AUC

### Relatório HTML

```bash
# Abrir o relatório gerado após um ciclo de treinamento
open data/drift_reports/drift_report.html
```

---

## Rastreamento de Experimentos (MLflow)

**URI padrão:** `sqlite:///<raiz_do_projeto>/mlruns.db`

### Iniciar a UI do MLflow

```bash
mlflow ui --backend-store-uri sqlite:///mlruns.db
```

Acesse em `http://localhost:5000`.

### O que é rastreado por experimento

| Métrica | Descrição |
|---|---|
| `test_roc_auc` | ROC-AUC no conjunto de teste |
| `data_drift_detected` | `1` se drift foi detectado, `0` caso contrário |

### Model Registry

O modelo é registrado com o nome `XGBoost_Transaction_Score`. O estágio de cada versão segue o ciclo:

```
None ──► Staging (implícito ao registrar) ──► Production ──► Archived
```

A promoção automática para `Production` e o arquivamento das versões anteriores são gerenciados pelo próprio `train.py` via `MlflowClient`.

---

## Testes

**Arquivo:** [tests/test_api.py](tests/test_api.py)

### Execução

```bash
pytest tests/ -v
```

### Casos de teste

| Teste | Descrição |
|---|---|
| `test_health_check` | Verifica que `/health` retorna `200` (modelo carregado) ou `503` (modelo ausente) |
| `test_generate_token_success` | Autenticação válida retorna status `200` e `access_token` no corpo |
| `test_generate_token_failure` | Senha incorreta retorna status `401` |
| `test_predict_without_token` | Requisição sem JWT retorna `401` |
| `test_predict_with_invalid_payload` | Payload com tipo inválido retorna `422` |

> Os testes de `/predict` com modelo real dependem de um modelo registrado no MLflow. Em ambientes de CI sem MLflow configurado, o `InferenceEngine` falha ao inicializar e o `/health` retorna `503`, comportamento já coberto pelo teste `test_health_check`.

---

## CI/CD

**Arquivo:** [.github/workflows/ci_cd.yml](.github/workflows/ci_cd.yml)

O pipeline é acionado em **push** ou **pull request** para a branch `main`.

### Job `build_and_test` (executado em todo push e PR)

```
1. Checkout do repositório
2. Configurar Python 3.10
3. Instalar dependências (requirements.txt + pytest + flake8)
4. Linting com flake8 (erros críticos: E9, F63, F7, F82)
5. Execução dos testes com pytest
6. Validação do Feature Store (feast plan)
```

### Job `deploy` (executado apenas em push para `main`)

```
7.  Login no Azure (via service principal armazenado em GitHub Secrets)
8.  Login no Azure Container Registry
9.  Build da imagem Docker e push para o ACR (tags: latest + SHA do commit)
10. Update do Azure Container App com a nova imagem
11. Smoke test do endpoint /token (espera HTTP 401 com credenciais inválidas)
```

Configuração do secret `AZURE_CREDENTIALS` e provisionamento dos recursos no Azure: ver [DeployToAzure.md](DeployToAzure.md).

### Executar o pipeline localmente

```bash
# Linting (análise estática no código-fonte para identificar erros de sintaxe, erros em potencial, problemas de estilo e formatação)
flake8 src/ tests/ --count --select=E9,F63,F7,F82 --show-source --statistics

# Flags
Flag  What it catches
E9    Syntax errors, invalid escape sequences, I/O errors
F63   Invalid assert or raise statements 
F7    Syntax errors detected by pyflakes 
F82   Undefined names (NameError at runtime) 

# Resultado esperado
-> 0 → código está ok, sem erros críticos
-> Outro resultado → Existem erros reais que causarão falhas em tempo de execução

# Testes
.venv/bin/pytest tests/ -v

# Validação do Feast
cd feature_repo && feast plan
```

---

## Implantação no Azure

O projeto inclui uma esteira completa para implantar a API no **Azure Container Apps** e a UI no **Streamlit Community Cloud**, com CI/CD automático no GitHub Actions.

### Artefatos relevantes

| Arquivo | Função |
|---|---|
| [Dockerfile](Dockerfile) | Build multi-stage da imagem da API (Python 3.10-slim, modelo MLflow embarcado) |
| [.dockerignore](.dockerignore) | Exclui código de treino, testes e dados do contexto de build |
| [requirements-api.txt](requirements-api.txt) | Dependências apenas de runtime de inferência (sem `streamlit`/`feast`/`evidently`) |
| [src/app/requirements.txt](src/app/requirements.txt) | Dependências enxutas para o deploy no Streamlit Community Cloud |
| [.github/workflows/ci_cd.yml](.github/workflows/ci_cd.yml) | Job `deploy` que builda, publica no ACR e atualiza o Container App |

**Para o passo a passo completo** — provisionamento de infraestrutura no Azure, configuração de secrets no GitHub, validação local da imagem Docker, deploy do Streamlit e troubleshooting — consulte **[DeployToAzure.md](DeployToAzure.md)**.

### Resumo do fluxo

```
git push origin main
    │
    ▼
GitHub Actions
    │
    ├─► build_and_test  (lint + pytest + feast plan)
    │
    └─► deploy          (Docker build → push para ACR → update do Container App)
                                │
                                ▼
                  Azure Container Apps (escala a zero)
                                │
                                ▼
              https://<fqdn>.azurecontainerapps.io
                                │
                                ▼
                Streamlit Cloud (UI consome a API)
```

---

## Segurança

### Autenticação

- Todos os endpoints de inferência exigem um **token JWT Bearer** válido obtido via `POST /token`
- Tokens expiram após 60 minutos (configurável via `TOKEN_EXPIRE_MIN`)
- O algoritmo de assinatura é **HS256**

### Rate Limiting

- O endpoint `POST /predict` aceita no máximo **5 requisições por minuto por IP**
- Exceder o limite retorna `HTTP 429 Too Many Requests`

### Boas práticas implementadas

- Chave secreta JWT lida exclusivamente de variável de ambiente (`API_SECRET_KEY`)
- Credenciais de parceiros configuráveis via `VALID_PARTNERS` (sem hardcode em produção)
- Exceções internas são logadas no servidor e **nunca** expostas na resposta HTTP
- Validação de presença de `API_SECRET_KEY` forte ao iniciar em `ENV=production`
- Inputs do usuário validados pelo Pydantic antes de chegarem ao modelo

### Recomendações para produção

- **Implantação completa documentada em [DeployToAzure.md](DeployToAzure.md)** — provisionamento de infraestrutura, secrets e CI/CD para Azure Container Apps
- Substituir o dicionário `VALID_PARTNERS` por um serviço de identidade (OAuth2, LDAP, Keycloak)
- Armazenar `API_SECRET_KEY` em um cofre de segredos (AWS Secrets Manager, HashiCorp Vault, Azure Key Vault)
- Habilitar HTTPS via proxy reverso (nginx, Traefik) — no Azure Container Apps já é provido nativamente pelo `ingress external`
- Adicionar logs de auditoria para todas as predições realizadas

---

## Decisões de Design

### Por que XGBoost?

XGBoost oferece excelente desempenho em dados tabulares com variáveis socioeconômicas, resiste bem a outliers e produz previsões interpretáveis via importância de features — características essenciais para sistemas de crédito.

### Por que MLflow para registro do modelo?

O MLflow Model Registry fornece controle de versão, rastreabilidade de experimentos e a abstração de "estágios" (Production/Archived) necessária para o fluxo de promoção automática com base em métricas.

### Por que Evidently para drift detection?

O Evidently gera relatórios HTML ricos em visualizações com uma API simples. O preset `DataDriftPreset` cobre análise estatística de todas as features em uma única chamada, adequado para a escala desta POC.

### Por que FastAPI + SlowAPI?

FastAPI fornece validação automática de schema via Pydantic, documentação OpenAPI integrada e performance assíncrona. O SlowAPI adiciona rate limiting sem overhead de infraestrutura adicional.

### Por que configuração centralizada em `config.py`?

Todos os módulos (`train.py`, `inference.py`, `auth.py`) importam constantes de um único arquivo, eliminando divergências entre valores duplicados. As variáveis de ambiente permitem sobrescrever qualquer configuração sem alterar código.

### Por que `stratify=y` no train_test_split?

O dataset de crédito é desbalanceado (mais inadimplentes do que adimplentes). Sem estratificação, o split aleatório pode colocar apenas uma classe no conjunto de teste, tornando o ROC-AUC indefinido. O `stratify=y` garante que a proporção de classes seja mantida em ambos os conjuntos.

### Por que retornar `score_probabilidade` e `score_level` além da classe binária?

A classe binária (`0`/`1`) sozinha esconde a confiança do modelo. Dois clientes podem ambos receber `score_predito=1`, mas um com 51% de probabilidade e outro com 92% — decisões de negócio diferentes. O `score_level` traduz esse gradiente para uma linguagem operacional (`Baixo` / `Médio` / `Alto`) sem exigir que o consumidor da API interprete valores decimais.
