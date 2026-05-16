# Implantando a API QuantumFinance Credit Score no Azure

## Contexto

Este documento descreve como implantar a API de score de crédito do QuantumFinance no **Azure Container Apps** via CI/CD no GitHub Actions, e como expor a UI Streamlit no **Streamlit Community Cloud**. O projeto possui uma FastAPI pronta para produção em [src/api/main.py](src/api/main.py) com autenticação JWT, rate limiting e um modelo XGBoost servido via MLflow registry (`mlruns.db` + `mlruns/`). O pipeline de CI (GitHub Actions) roda lint/pytest/feast-plan; este guia adiciona o passo de CD. O alvo é o Azure Container Apps porque escala a zero — ideal para um POC.

> **Nota sobre artefatos do modelo**: os arquivos `mlruns/` e `mlruns.db` estão versionados no repositório intencionalmente, para que o build da imagem Docker possa embarcá-los. Veja a seção **Pré-requisitos** abaixo.

---

## Pré-requisitos

Antes de seguir as fases abaixo, garanta que:

1. **Os artefatos do modelo MLflow estão no repositório.** Verifique com:
   ```bash
   git ls-files mlruns/ mlruns.db | head
   ```
   Se a saída estiver vazia, force o add (eles normalmente estão em `.gitignore`):
   ```bash
   git add -f mlruns/ mlruns.db
   git commit -m "chore: version model artifacts for Docker build"
   ```
   Sem isso, o `COPY mlruns/` no Dockerfile falha com `failed to compute cache key: "/mlruns": not found`.

2. **Você tem o Docker Desktop em execução** localmente (necessário para Fase 1.5 e Fase 2 Passo 5).

3. **Você tem o Azure CLI instalado** (`brew install azure-cli`) e uma assinatura Azure ativa para a Fase 2.

---

## Fase 1 — Preparar o Repositório (local, executar uma vez)

### Passo 1: Criar `requirements-api.txt`

Crie [requirements-api.txt](requirements-api.txt) apenas com as dependências de runtime de inferência (sem `streamlit`, `feast`, `evidently`):
```
pandas==2.3.0
scikit-learn==1.4.2
xgboost==2.1.0
mlflow==2.16.0
fastapi==0.109.0
uvicorn==0.34.0
slowapi==0.1.9
PyJWT==2.8.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.6
python-dotenv==1.0.1
httpx==0.27.2
```

### Passo 2: Criar `Dockerfile`

Crie [Dockerfile](Dockerfile) na raiz do projeto. Multi-stage para manter a imagem final enxuta:

```dockerfile
# syntax=docker/dockerfile:1

FROM python:3.10-slim AS builder
WORKDIR /build
COPY requirements-api.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements-api.txt

FROM python:3.10-slim
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
WORKDIR /app
COPY --from=builder /install /usr/local
COPY src/ ./src/
COPY mlruns/ ./mlruns/
COPY mlruns.db ./mlruns.db
RUN chown -R appuser:appgroup /app
USER appuser

ENV PYTHONPATH=/app
ENV MLFLOW_TRACKING_URI=sqlite:////app/mlruns.db
ENV MODEL_NAME=XGBoost_Transaction_Score

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Observações importantes:
- `PYTHONPATH=/app` permite que `uvicorn src.api.main:app` resolva os imports; o `sys.path.insert` em [src/api/main.py](src/api/main.py#L11) então adiciona `/app/src` ao path para que os imports internos (`from api.auth`, `from model.inference`) resolvam corretamente.
- `MLFLOW_TRACKING_URI=sqlite:////app/mlruns.db` — quatro barras = `sqlite://` + caminho absoluto `/app/mlruns.db`.
- `--start-period=60s` dá tempo ao container de fazer cold start antes que as health probes falhem.
- `ENV` e secrets (`API_SECRET_KEY`, `VALID_PARTNERS`) **não** ficam na imagem intencionalmente — são injetados em runtime.

### Passo 3: Criar `.dockerignore`

Crie [.dockerignore](.dockerignore) para excluir código não-API do contexto de build:
```
.git/
.github/
.venv/
.env
.env.example
.actrc
__pycache__/
**/__pycache__/
*.py[cod]
tests/
.pytest_cache/
.vscode/
.claude/
src/app/
src/data/
src/model/train.py
src/model/drift.py
data/
feature_repo/
README.md
notebooks/
setup.sh
requirements.txt
```

### Passo 4: Atualizar `.github/workflows/ci_cd.yml`

Adicione um job `deploy` em [.github/workflows/ci_cd.yml](.github/workflows/ci_cd.yml). O job `build_and_test` existente fica inalterado. Adicione depois dele:

```yaml
  deploy:
    runs-on: ubuntu-latest
    needs: build_and_test
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'

    steps:
    - name: Check out repository
      uses: actions/checkout@v3

    - name: Log in to Azure
      uses: azure/login@v2
      with:
        creds: ${{ secrets.AZURE_CREDENTIALS }}

    - name: Log in to Azure Container Registry
      run: az acr login --name quantumfinanceacr

    - name: Build and push Docker image
      run: |
        docker build \
          -t quantumfinanceacr.azurecr.io/creditscoreapi:${{ github.sha }} \
          -t quantumfinanceacr.azurecr.io/creditscoreapi:latest \
          .
        docker push quantumfinanceacr.azurecr.io/creditscoreapi:${{ github.sha }}
        docker push quantumfinanceacr.azurecr.io/creditscoreapi:latest

    - name: Deploy to Azure Container Apps
      run: |
        az containerapp update \
          --name quantumfinance-api \
          --resource-group quantumfinance-rg \
          --image quantumfinanceacr.azurecr.io/creditscoreapi:${{ github.sha }}

    - name: Verify deployment
      run: |
        sleep 30
        APP_URL=$(az containerapp show \
          --name quantumfinance-api \
          --resource-group quantumfinance-rg \
          --query properties.configuration.ingress.fqdn -o tsv)
        echo "Deployed to: https://$APP_URL"
        STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
          -X POST "https://$APP_URL/token" \
          -d "username=probe&password=probe" --max-time 15)
        if [ "$STATUS" = "401" ] || [ "$STATUS" = "200" ]; then
          echo "API is up (HTTP $STATUS)"
        else
          echo "Deployment check failed with status $STATUS"
          exit 1
        fi
```

A verificação usa `/token` com credenciais inválidas (espera `401`) em vez de `/health` (que retorna `503` até o modelo carregar) — mais confiável durante cold starts.

---

## Fase 1.5 — Validar o Dockerfile Localmente (recomendado antes da Fase 2)

Faça um smoke test (teste de fumaça) da imagem no seu laptop antes de subir para o ACR. Isso pega bugs do Dockerfile sem queimar recursos no Azure.

> Nota: Faça o build nativo (sem `--platform`) para iteração local mais rápida. O cross-build de Apple Silicon → linux/amd64 só é necessário quando se vai publicar no Azure.

### Passo 1: Construir a imagem

A partir da raiz do projeto:
```bash
docker build -t creditscoreapi:local .
```

Esperado: 3–5 minutos no primeiro build (download da imagem base do Python + instalação via pip). Imagem final ~500 MB.

### Passo 2: Rodar o container

> **Substitua** `seu_usuario:sua_senha` por credenciais reais antes de executar — o valor é passado diretamente para o container e usado para autenticar no `/token`.

```bash
docker run --rm -d \
  --name creditscoreapi-test \
  -p 8000:8000 \
  -e ENV=production \
  -e API_SECRET_KEY="$(openssl rand -hex 32)" \
  -e VALID_PARTNERS="seu_usuario:sua_senha" \
  -e TOKEN_EXPIRE_MIN=60 \
  creditscoreapi:local

# Acompanhar logs em outro terminal (opcional)
docker logs -f creditscoreapi-test
```

Você deve ver a saída do uvicorn: `Uvicorn running on http://0.0.0.0:8000`.

### Passo 3: Bater nos endpoints

**3a. Token (não precisa do modelo — caminho rápido):**
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/token \
  -d "username=seu_usuario&password=sua_senha" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
echo "Token: $TOKEN"
```
Esperado: uma string JWT. Se receber `{"detail":"Usuário ou senha incorretos"}`, sua variável `VALID_PARTNERS` não chegou ao container.

**3b. Health (dispara o load do modelo via MLflow na primeira chamada — pode levar 2–3s):**
```bash
curl -i http://localhost:8000/health
```
Esperado: `HTTP/1.1 200 OK` + `{"status":"ok"}`. Se 503, verifique os logs procurando erro de load do MLflow — provavelmente paths de `mlruns/` ou `mlruns.db` na imagem.

**3c. Predict (fim a fim — auth + inferência do modelo):**
```bash
curl -s -X POST http://localhost:8000/predict \
  -H "Authorization: Bearer $TOKEN" \
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
  }' | python3 -m json.tool
```
Esperado: JSON com `score_predito`, `score_probabilidade`, `score_level`, `risco_interpretavel`. Os valores serão determinísticos para essa entrada exata.

### Passo 4: Parar e limpar
```bash
docker stop creditscoreapi-test
# (a flag --rm já remove o container quando ele para)

# Opcional: remover a imagem quando terminar
docker rmi creditscoreapi:local
```

### Modos de falha comuns

| Sintoma | Causa provável | Solução |
|---------|----------------|---------|
| `COPY mlruns/` falha durante o build | Pré-requisito não atendido: artefatos do modelo não estão no repo | Veja a seção **Pré-requisitos** no topo deste documento |
| Container sai imediatamente | Erro de import | `docker logs creditscoreapi-test` — geralmente é uma dependência faltando em `requirements-api.txt` |
| `/health` → 503 | MLflow não acha o modelo | Verifique nos logs a URI exata do MLflow; confirme `MLFLOW_TRACKING_URI=sqlite:////app/mlruns.db` (4 barras) |
| `/predict` → 500 | Mismatch de features | Os logs mostram o que o modelo XGBoost esperava vs. o que foi enviado |
| `RuntimeError: API_SECRET_KEY must be set` | `ENV=production` sem chave forte | O `openssl rand -hex 32` no Passo 2 resolve isso; confirme que a env var está sendo passada |

Quando os três testes de endpoint passarem localmente, a imagem está boa. Avance para a Fase 2 (que reconstrói com `--platform linux/amd64` para o Azure).

---

## Fase 2 — Provisionar a Infraestrutura no Azure (uma vez, terminal local)

Execute uma vez antes do primeiro push de CI/CD. Requer Azure CLI (`brew install azure-cli`).

```bash
# 1. Login
az login
az account set --subscription "<YOUR_SUBSCRIPTION_ID>"

# 2. Resource group
az group create --name quantumfinance-rg --location eastus

# 3. Container Registry (Basic ~$5/mês)
az acr create \
  --resource-group quantumfinance-rg \
  --name quantumfinanceacr \
  --sku Basic \
  --admin-enabled true

# 4. Pegar credenciais do ACR
ACR_USERNAME=$(az acr credential show --name quantumfinanceacr --query username -o tsv)
ACR_PASSWORD=$(az acr credential show --name quantumfinanceacr --query "passwords[0].value" -o tsv)

# 5. Build e push da imagem inicial manualmente (para que o Container App possa ser criado)
# IMPORTANTE: --platform linux/amd64 é obrigatório no Apple Silicon (M1/M2/M3).
# O Azure Container Apps só aceita imagens linux/amd64.
az acr login --name quantumfinanceacr
docker buildx build --platform linux/amd64 \
  -t quantumfinanceacr.azurecr.io/creditscoreapi:latest \
  --push .

# 6. Container Apps environment
az containerapp env create \
  --name quantumfinance-env \
  --resource-group quantumfinance-rg \
  --location eastus

# 7. Criar o Container App (primeiro deploy)
API_SECRET_KEY=$(openssl rand -hex 32)

az containerapp create \
  --name quantumfinance-api \
  --resource-group quantumfinance-rg \
  --environment quantumfinance-env \
  --image quantumfinanceacr.azurecr.io/creditscoreapi:latest \
  --registry-server quantumfinanceacr.azurecr.io \
  --registry-username $ACR_USERNAME \
  --registry-password $ACR_PASSWORD \
  --target-port 8000 \
  --ingress external \
  --min-replicas 0 \
  --max-replicas 3 \
  --cpu 0.5 --memory 1.0Gi \
  --env-vars \
    "ENV=production" \
    "MLFLOW_TRACKING_URI=sqlite:////app/mlruns.db" \
    "MODEL_NAME=XGBoost_Transaction_Score" \
    "TOKEN_EXPIRE_MIN=60" \
    "API_SECRET_KEY=secretref:api-secret-key" \
    "VALID_PARTNERS=secretref:valid-partners" \
  --secrets \
    "api-secret-key=$API_SECRET_KEY" \
    "valid-partners=seu_usuario:sua_senha"

# 8. Criar o service principal para o GitHub Actions
RESOURCE_GROUP_ID=$(az group show --name quantumfinance-rg --query id -o tsv)
az ad sp create-for-rbac \
  --name quantumfinance-github-sp \
  --role contributor \
  --scopes $RESOURCE_GROUP_ID \
  --sdk-auth
# Copie o JSON completo da saída — esse vira o AZURE_CREDENTIALS no GitHub Secrets
```

---

## Fase 3 — Configurar GitHub Secrets (uma vez, UI do GitHub)

Vá em: repo do GitHub → **Settings → Secrets and variables → Actions → New repository secret**

| Secret | Valor |
|--------|-------|
| `AZURE_CREDENTIALS` | JSON completo de `az ad sp create-for-rbac --sdk-auth` acima |

`API_SECRET_KEY` e `VALID_PARTNERS` ficam como secrets do Azure Container Apps (definidos no Passo 7 acima) — **não** precisam estar no GitHub Secrets.

---

## Fase 4 — Fluxo Contínuo de CD

Depois que a infraestrutura estiver provisionada, todo `git push` para `main`:
1. **Job CI** — lint, pytest, feast plan (inalterado)
2. **Job CD** — builda a imagem Docker (com os artefatos do modelo embarcados), publica no ACR, atualiza o Container App com a imagem taggeada pelo SHA

Pegue a URL pública (live) a qualquer momento:
```bash
az containerapp show --name quantumfinance-api --resource-group quantumfinance-rg \
  --query properties.configuration.ingress.fqdn -o tsv
```

---

## Fase 5 — Verificar o Deploy no Azure

Depois da Fase 2 (provisionamento inicial) ou após qualquer execução do CD, confirme que a API está saudável no Azure. Ordene as verificações de infraestrutura → app → fim a fim.

### Passo 1: Confirmar que os recursos existem
```bash
# Resource group
az group show --name quantumfinance-rg --query "{name:name, state:properties.provisioningState}" -o table

# Container Registry + tags da imagem
az acr repository list --name quantumfinanceacr -o table
az acr repository show-tags --name quantumfinanceacr --repository creditscoreapi -o table

# Container Apps environment
az containerapp env show --name quantumfinance-env --resource-group quantumfinance-rg \
  --query "{name:name, state:properties.provisioningState}" -o table
```
Esperado: `Succeeded` em tudo; o repo `creditscoreapi` lista `latest` mais as imagens taggeadas pelo SHA.

### Passo 2: Confirmar que o Container App está rodando a imagem certa
```bash
az containerapp show --name quantumfinance-api --resource-group quantumfinance-rg \
  --query "{provisioning:properties.provisioningState, runStatus:properties.runningStatus, image:properties.template.containers[0].image, replicas:properties.template.scale}" \
  -o json
```
Esperado: `provisioning=Succeeded`, `runStatus=Running` (ou `Idle` se escalou a zero), e a imagem corresponde ao SHA que você acabou de publicar.

### Passo 3: Inspecionar a revisão mais recente
```bash
az containerapp revision list --name quantumfinance-api --resource-group quantumfinance-rg \
  --query "[].{name:name, active:properties.active, replicas:properties.replicas, healthState:properties.healthState, created:properties.createdTime}" \
  -o table
```
Esperado: a revisão mais nova com `active=true` e `healthState=Healthy`. Se `healthState=Unhealthy`, pule para o Passo 6 (logs).

### Passo 4: Smoke test dos endpoints públicos
```bash
APP_URL=$(az containerapp show --name quantumfinance-api --resource-group quantumfinance-rg \
  --query properties.configuration.ingress.fqdn -o tsv)
echo "URL pública: https://$APP_URL"

# 4a. Token (usa o secret VALID_PARTNERS)
TOKEN=$(curl -s -X POST "https://$APP_URL/token" \
  -d "username=seu_usuario&password=sua_senha" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
echo "Token (primeiros 40 chars): ${TOKEN:0:40}..."

# 4b. Health (dispara o load do modelo via MLflow na primeira chamada — pode levar 2–3s após cold start)
curl -i "https://$APP_URL/health"

# 4c. Predict (fim a fim)
curl -s -X POST "https://$APP_URL/predict" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"renda": 4500.0, "idade": 42.0, "etnia": 0, "sexo": 1, "casapropria": 1, "outrasrendas": 0, "estadocivil": 1, "escolaridade": 2}' \
  | python3 -m json.tool
```
Esperado:
- `/token` → string JWT
- `/health` → `200` + `{"status":"ok"}`
- `/predict` → JSON com `score_predito`, `score_probabilidade`, `score_level`, `risco_interpretavel` (para o payload de exemplo acima, espere algo como `0`, `≈ 0.0191`, `Baixo`, `Aprovado`)

### Passo 5: Verificar o pipeline de CD do GitHub Actions
Depois do primeiro push para `main`:
- Repo do GitHub → aba **Actions** → execução mais recente do workflow
- Os dois jobs `build_and_test` e `deploy` devem estar verdes
- O passo `Verify deployment` no final do `deploy` faz a probe em `/token` — a linha de log deve dizer `API is up (HTTP 401)` ou `(HTTP 200)`

### Passo 6: Ler logs quando algo der errado

**Tail ao vivo (mais útil):**
```bash
az containerapp logs show --name quantumfinance-api --resource-group quantumfinance-rg --follow
```

**Últimas N linhas:**
```bash
az containerapp logs show --name quantumfinance-api --resource-group quantumfinance-rg --tail 100
```

**Revisão específica:**
```bash
az containerapp logs show --name quantumfinance-api --resource-group quantumfinance-rg \
  --revision <revision-name> --tail 200
```

**Eventos de sistema / triggers de restart:**
```bash
az containerapp revision show --name quantumfinance-api --resource-group quantumfinance-rg \
  --revision <revision-name> --query "properties.{health:healthState, errors:provisioningError}"
```

### Passo 7: Tabela de triagem rápida

| Sintoma | Causa provável | Onde olhar / como corrigir |
|---------|----------------|----------------------------|
| `az containerapp show` → `runStatus=Failed` | Erro de pull da imagem ou crash do container | `az containerapp logs show ... --tail 200`; confirme que as credenciais do ACR foram aplicadas |
| `/token` → `401 incorrect credentials` | Secret `VALID_PARTNERS` errado | `az containerapp secret show --name quantumfinance-api --resource-group quantumfinance-rg --secret-name valid-partners` |
| `/health` → `503 Modelo indisponível` | Artefato do modelo não está na imagem, ou path errado | Os logs vão mostrar o erro do MLflow; confirme que `mlruns/` foi commitado e que `MLFLOW_TRACKING_URI=sqlite:////app/mlruns.db` está setado |
| `/predict` → `429 Too Many Requests` | Rate limit atingido (5/min/IP) | Esperado — espere 60s e tente de novo |
| `/predict` → `500 Erro interno` | Mismatch de schema de feature ou problema no load do modelo | Os logs vão mostrar o traceback |
| Primeira request após ociosidade leva 10–20s | Cold start (réplicas escalaram a zero) | Esperado; requests subsequentes são rápidas. Use `--min-replicas 1` se for inaceitável |
| `RuntimeError: API_SECRET_KEY must be set` nos logs | Secret `api-secret-key` do Container App estava vazio | `az containerapp secret set --name quantumfinance-api --resource-group quantumfinance-rg --secrets "api-secret-key=$(openssl rand -hex 32)"` e depois reinicie a revisão |

### Passo 8: Script único de verificação de saúde

Para reverificar repetidamente, segue um bloco que dá pra colar:

```bash
APP_URL=$(az containerapp show --name quantumfinance-api --resource-group quantumfinance-rg --query properties.configuration.ingress.fqdn -o tsv)
echo "URL: https://$APP_URL"
echo -n "Health: "; curl -s -o /dev/null -w "%{http_code}\n" "https://$APP_URL/health"
TOKEN=$(curl -s -X POST "https://$APP_URL/token" -d "username=seu_usuario&password=sua_senha" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('access_token',''))")
[ -n "$TOKEN" ] && echo "Token: OK" || echo "Token: FAIL"
echo -n "Predict: "; curl -s -o /dev/null -w "%{http_code}\n" -X POST "https://$APP_URL/predict" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"renda": 4500.0, "idade": 42.0, "etnia": 0, "sexo": 1, "casapropria": 1, "outrasrendas": 0, "estadocivil": 1, "escolaridade": 2}'
```
Os três devem imprimir `200` (ou 200/200/200). Se `/predict` retornar `429`, você bateu no rate limit — espere um minuto.

---

## Fase 6 — Implantar a UI Streamlit no Streamlit Community Cloud

A [src/app/streamlit_app.py](src/app/streamlit_app.py) existente é uma UI completa que lê `API_URL` do ambiente, autentica via `/token` e chama `/predict`. Implantamos como está no Streamlit Cloud (gratuito) e apontamos para a API no Azure.

> Por que não precisa mexer com CORS: o Streamlit Cloud roda o script Python server-side. As chamadas `requests.post(...)` saem do runtime do Streamlit Cloud para o Azure — o navegador só vê a UI renderizada. CORS não se aplica.

### Passo 1: Adicionar um requirements específico para Streamlit

O [requirements.txt](requirements.txt) atual não lista `requests` (o streamlit_app importa, mas só funciona localmente porque é dependência transitiva do `mlflow`). O Streamlit Cloud precisa do próprio arquivo enxuto para não instalar xgboost/mlflow/feast.

Crie [src/app/requirements.txt](src/app/requirements.txt) com:
```
streamlit==1.41.0
requests==2.32.3
python-dotenv==1.0.1
```

O Streamlit Cloud detecta automaticamente um `requirements.txt` ao lado do script principal.

### Passo 2: Subir as mudanças
```bash
git add src/app/requirements.txt
git commit -m "feat(streamlit): add requirements.txt for Streamlit Cloud deploy"
git push origin main
```

### Passo 3: Implantar em share.streamlit.io

1. Acesse https://share.streamlit.io e entre com o GitHub
2. Clique em **Create app** → **Deploy a public app from GitHub**
3. Preencha:
   - **Repository**: `<seu-usuario-github>/quantumfinance_credit_score`
   - **Branch**: `main`
   - **Main file path**: `src/app/streamlit_app.py`
   - **App URL** (subdomínio customizado, opcional): `quantumfinance-creditscore` → URL resultante `https://quantumfinance-creditscore.streamlit.app`
4. Abra **Advanced settings** → **Secrets** e cole:
   ```toml
   API_URL = "https://<your-app-fqdn-from-azure>"
   ```
   Pegue o FQDN com:
   ```bash
   az containerapp show --name quantumfinance-api --resource-group quantumfinance-rg \
     --query properties.configuration.ingress.fqdn -o tsv
   ```
   Fica algo como `quantumfinance-api.<aleatorio>.eastus.azurecontainerapps.io`. Use a URL completa com `https://` e sem barra final.
5. Clique em **Deploy**. O primeiro boot leva 2–3 minutos (Streamlit Cloud instala as dependências).

### Passo 4: Testar fim a fim pela UI Streamlit

1. Abra `https://quantumfinance-creditscore.streamlit.app`
2. Sidebar → digite credenciais que batem com o secret `valid-partners` do Azure (substitua `seu_usuario` / `sua_senha` pelos valores reais que você usou no Passo 7 da Fase 2)
3. Clique em **Autenticar e Gerar Token** → esperado "Autenticado via JWT!"
4. Formulário → mantenha os valores padrão → clique em **Consultar Score**
5. Esperado: para os valores padrão do formulário, "Aprovado" em verde com métricas `Score Predito=0`, `Probabilidade ≈ 1.91%`, `Nível de Risco=Baixo`. Outros valores de entrada produzem outras saídas — o importante é que a chamada complete sem erro.

### Passo 5: Como o `API_URL` chega ao app rodando

`os.getenv("API_URL")` em [src/app/streamlit_app.py:8](src/app/streamlit_app.py#L8) lê do ambiente do processo. O Streamlit Cloud automaticamente promove qualquer chave que você colocar em **Secrets** tanto para `st.secrets["API_URL"]` quanto para `os.environ["API_URL"]` — então o código existente funciona sem alteração.

Se um dia quiser usar `st.secrets` explicitamente (um pouco mais seguro, dá erro claro se faltar), mude a linha 8 para:
```python
API_URL = st.secrets.get("API_URL", os.getenv("API_URL"))
```
Opcional, não é obrigatório para esse deploy.

### Passo 6: Modos de falha comuns

| Sintoma na UI Streamlit | Causa provável | Solução |
|--------------------------|----------------|---------|
| "Erro ao conectar com a API." ao clicar no token | `API_URL` faltando ou errado | Streamlit Cloud → Manage app → Secrets — verifique se a URL tem `https://` e sem barra final |
| "Falha na autenticação." | Credenciais não batem com `valid-partners` no Azure | `az containerapp secret show --name quantumfinance-api --resource-group quantumfinance-rg --secret-name valid-partners` |
| Primeira request após ociosidade muito lenta | Cold start do Container App no Azure (escalou a zero) | Esperado — espere 10–15s. Para eliminar, use `--min-replicas 1` no Container App |
| `Erro 429` | Rate limit (5/min/IP do egress do Streamlit Cloud) | Espere 60s. Um único usuário Streamlit normalmente não bate nisso |
| `ModuleNotFoundError: No module named 'requests'` nos logs do Streamlit | Passo 1 não foi feito | Confirme que `src/app/requirements.txt` existe e foi pushado |
| App preso em "Your app is in the oven" | Erro de build no Streamlit Cloud | Clique em "Manage app" → veja os logs no rodapé |

### Passo 7: Atualizações depois do deploy

O Streamlit Cloud redeploya automaticamente em todo push para `main` (mesmo gatilho do CD do Azure). Sem passo extra.

Se você só mudou a UI Streamlit e não quer redeployar a API, dá para:
- Pushar uma mudança vazia em `src/app/streamlit_app.py` apenas — o Streamlit Cloud rebuilda; o CD do Azure também roda mas acaba publicando uma imagem idêntica
- Usar uma branch separada para trabalho só de UI e implantar o Streamlit Cloud a partir dessa branch

Para um POC, o mais simples: manter uma branch só e aceitar o rebuild redundante da API.

### Opcional: travar o acesso à API somente para o Streamlit Cloud

Para um POC público, JWT + rate limiting é suficiente. Se quiser controle mais rígido depois:
- **Mais fácil**: rotacionar `API_SECRET_KEY` e `valid-partners` periodicamente (`az containerapp secret set ...`)
- **Mais rígido**: adicionar verificação de `X-API-Key` (segredo compartilhado) em [src/api/main.py](src/api/main.py) e guardar o mesmo valor nos Secrets do Streamlit Cloud e nos secrets do Container Apps — fora de escopo por agora

---

## Estimativa de Custo

| Serviço | SKU | ~Mensal |
|---------|-----|---------|
| Azure Container Registry | Basic | $5 |
| Azure Container Apps | Consumption, escala a zero | $0–$3 |
| **Total** | | **~$5–$8** |

---

## Observações Importantes

- **SQLite + múltiplas réplicas**: seguro para serving read-only do modelo. `mlflow.load_model` só lê do registry. Não escreva no registry de dentro do container.
- **Cold start**: com `min-replicas 0`, a primeira request após ociosidade leva ~10–15s (start do container) + lazy load do modelo. Aceitável para um POC. Use `--min-replicas 1` se quiser sempre quente (~$20/mês a mais).
- **Atualização do modelo**: re-treinar localmente, recommitar `mlruns/` e `mlruns.db`, push para `main` — o CD cuida do resto.
