# API QuantumFinance Credit Score — Documentação

> **Versão:** 1.0
> **Modelo servido:** `XGBoost_Transaction_Score` (estágio `Production` no MLflow Registry)
> **Autenticação:** OAuth2 Password Flow + JWT Bearer (HS256)
> **Throttling:** 5 requisições/minuto/IP no `/predict`

---

## Sumário

1. [Visão Geral](#visão-geral)
2. [Base URLs](#base-urls)
3. [Fluxo de Uso](#fluxo-de-uso)
4. [Autenticação](#autenticação)
5. [Endpoint `GET /health`](#endpoint-get-health)
6. [Endpoint `POST /token`](#endpoint-post-token)
7. [Endpoint `POST /predict`](#endpoint-post-predict)
8. [Throttling (Rate Limiting)](#throttling-rate-limiting)
9. [Schemas de Entrada e Saída](#schemas-de-entrada-e-saída)
10. [Códigos de Status HTTP](#códigos-de-status-http)
11. [Troubleshooting e FAQ](#troubleshooting-e-faq)
12. [Documentação Interativa (Swagger)](#documentação-interativa-swagger)

---

## Visão Geral

A API QuantumFinance Credit Score expõe um modelo XGBoost binário de avaliação de risco de crédito para parceiros autorizados. Dado um conjunto de 8 features socioeconômicas de um cliente, a API retorna:

- **Classe binária** (`0` = aprovado, `1` = risco detectado)
- **Probabilidade** de inadimplência (`0.0`–`1.0`)
- **Nível de risco** semântico (`Baixo`, `Médio`, `Alto`)
- **Classificação interpretável** (`Aprovado` ou `Risco Detectado`)

A API é **stateless**: cada parceiro autentica uma vez via `/token`, recebe um JWT, e usa esse JWT para chamar `/predict` quantas vezes precisar (respeitando o rate limit) até o token expirar.

---

## Base URLs

| Ambiente | URL |
|----------|-----|
| Local (uvicorn) | `http://localhost:8000` |
| Local (Docker) | `http://localhost:8000` |
| Azure (produção) | `https://<seu-app>.<região>.azurecontainerapps.io` |

A URL do ambiente Azure pode ser obtida com:
```bash
az containerapp show --name quantumfinance-api --resource-group quantumfinance-rg \
  --query properties.configuration.ingress.fqdn -o tsv
```

> Todos os exemplos abaixo usam `http://localhost:8000`. Para chamar o ambiente Azure, troque por `https://<seu-fqdn>`.

---

## Fluxo de Uso

```
┌─────────────────────────────────────────────────────────────┐
│  1. Cliente chama POST /token com username + password       │
│     ──► API retorna { access_token: "eyJ...", token_type }  │
│                                                             │
│  2. Cliente armazena o token e o usa por até 60 minutos     │
│                                                             │
│  3. Cliente chama POST /predict com:                        │
│     - Header: Authorization: Bearer <token>                 │
│     - Body JSON: 8 features do cliente                      │
│     ──► API retorna o score                                 │
│                                                             │
│  4. Quando o token expira (HTTP 401 "Token expirado"),      │
│     volte ao passo 1 para gerar um novo                     │
└─────────────────────────────────────────────────────────────┘
```

Opcional (mas recomendado para integrações automatizadas): chame `GET /health` antes do primeiro `/predict` para confirmar que o modelo está carregado.

---

## Autenticação

### Modelo

- **Padrão:** OAuth2 Password Flow (RFC 6749)
- **Token:** JWT (RFC 7519), assinado com **HS256**
- **Tempo de vida:** 60 minutos por padrão (configurável via `TOKEN_EXPIRE_MIN`)
- **Header de uso:** `Authorization: Bearer <access_token>`

### Como obter credenciais

Cada parceiro recebe um par `usuário:senha` previamente cadastrado. As credenciais são armazenadas como **secrets do Azure Container Apps** (env var `VALID_PARTNERS` no formato `user1:senha1,user2:senha2`).

> **Importante:** as credenciais nunca trafegam fora do request inicial em `POST /token`. Após isso, todo o tráfego usa apenas o JWT.

### Estrutura do JWT

Decodificado, o token contém:

```json
{
  "sub": "seu_usuario",
  "exp": 1726588800
}
```

O campo `sub` identifica o parceiro; `exp` é o timestamp Unix da expiração. A assinatura é verificada em cada chamada protegida.

---

## Endpoint `GET /health`

Verifica se a API está operacional e se o modelo está carregado em memória.

| Atributo | Valor |
|----------|-------|
| Método | `GET` |
| Caminho | `/health` |
| Autenticação | Não exigida |
| Rate limit | Não aplicável |

### Exemplo de request

```bash
curl http://localhost:8000/health
```

### Resposta `200 OK`

```json
{
  "status": "ok"
}
```

### Resposta `503 Service Unavailable`

```json
{
  "detail": "Modelo indisponível"
}
```

Significa que a API está rodando, mas o `InferenceEngine` não conseguiu carregar o modelo do MLflow Registry. Veja [Troubleshooting](#troubleshooting-e-faq) → "Por que `/health` retorna 503?".

---

## Endpoint `POST /token`

Autentica um parceiro e retorna um JWT Bearer.

| Atributo | Valor |
|----------|-------|
| Método | `POST` |
| Caminho | `/token` |
| Content-Type | `application/x-www-form-urlencoded` |
| Autenticação | Credenciais no body (form fields) |
| Rate limit | Não aplicável |

### Body (form-encoded)

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `username` | string | sim | Identificador do parceiro |
| `password` | string | sim | Senha do parceiro |

### Exemplo de request

```bash
curl -X POST http://localhost:8000/token \
  -d "username=seu_usuario&password=sua_senha"
```

### Resposta `200 OK`

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJwYXJ0bmVyX2EiLCJleHAiOjE3MjY1ODg4MDB9.k3X...",
  "token_type": "bearer"
}
```

### Resposta `401 Unauthorized`

```json
{
  "detail": "Usuário ou senha incorretos"
}
```

Causas: usuário não cadastrado, senha errada, ou `VALID_PARTNERS` mal formatada no servidor.

### Resposta `422 Unprocessable Entity`

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "username"],
      "msg": "Field required",
      "input": null
    }
  ]
}
```

Acontece quando `username` ou `password` não foi enviado no body.

---

## Endpoint `POST /predict`

Retorna o score de risco de crédito para um cliente.

| Atributo | Valor |
|----------|-------|
| Método | `POST` |
| Caminho | `/predict` |
| Content-Type | `application/json` |
| Autenticação | **Obrigatória** — `Authorization: Bearer <token>` |
| Rate limit | **5 requisições/minuto/IP** |

### Headers

| Header | Valor | Obrigatório |
|--------|-------|-------------|
| `Authorization` | `Bearer <access_token>` | sim |
| `Content-Type` | `application/json` | sim |

### Body (JSON)

Veja a tabela completa de campos em [Schemas de Entrada e Saída](#schemas-de-entrada-e-saída). Todos os campos são obrigatórios.

### Exemplo de request

```bash
curl -X POST http://localhost:8000/predict \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6..." \
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

### Resposta `200 OK`

```json
{
  "score_predito": 0,
  "score_probabilidade": 0.0191,
  "score_level": "Baixo",
  "risco_interpretavel": "Aprovado"
}
```

### Resposta `401 Unauthorized` — token ausente

Quando o header `Authorization` não foi enviado:

```json
{
  "detail": "Not authenticated"
}
```

### Resposta `401 Unauthorized` — token inválido

Quando o token está malformado ou tem assinatura inválida:

```json
{
  "detail": "Credenciais inválidas"
}
```

### Resposta `401 Unauthorized` — token expirado

```json
{
  "detail": "Token expirado"
}
```

### Resposta `401 Unauthorized` — payload do token inválido

```json
{
  "detail": "Token inválido"
}
```

Acontece quando o token foi assinado corretamente, mas a claim `sub` está ausente.

### Resposta `422 Unprocessable Entity`

Falha de validação do payload (campo ausente, tipo errado, ou valor < 0):

```json
{
  "detail": [
    {
      "type": "greater_than_equal",
      "loc": ["body", "renda"],
      "msg": "Input should be greater than or equal to 0",
      "input": -100.0,
      "ctx": {"ge": 0.0}
    }
  ]
}
```

Outro exemplo — campo obrigatório ausente:

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "idade"],
      "msg": "Field required",
      "input": {"renda": 4500.0}
    }
  ]
}
```

### Resposta `429 Too Many Requests`

Disparada quando o IP origem ultrapassa **5 requisições por minuto** no `/predict`:

```json
{
  "error": "Rate limit exceeded: 5 per 1 minute"
}
```

A resposta inclui um header `Retry-After` indicando quantos segundos aguardar antes da próxima tentativa.

### Resposta `500 Internal Server Error`

```json
{
  "detail": "Erro interno ao processar a predição."
}
```

Indica falha na inferência (ex: schema do modelo divergente do payload, modelo corrompido). O traceback completo é registrado nos logs do servidor — **nunca** retornado ao cliente por motivos de segurança.

### Resposta `503 Service Unavailable`

Mesmo formato do `/health` quando o modelo não carregou:

```json
{
  "detail": "Modelo indisponível"
}
```

---

## Throttling (Rate Limiting)

| Endpoint | Limite | Escopo |
|----------|--------|--------|
| `GET /health` | Sem limite | — |
| `POST /token` | Sem limite | — |
| `POST /predict` | **5 req/min** | Por IP de origem |

Implementação: [SlowAPI](https://slowapi.readthedocs.io/) com `key_func=get_remote_address`. O contador é uma janela deslizante de 60 segundos, mantida em memória do processo (não compartilhada entre réplicas).

> **Atenção:** num cenário com múltiplas réplicas no Azure Container Apps, o limite efetivo é `5 × N` requisições/minuto/IP, onde `N` é o número de réplicas ativas. Com `min-replicas=0`, normalmente há apenas uma réplica.

Ao exceder o limite, a API responde `429` e bloqueia o IP por até 60 segundos. **Não há fila** — requisições rejeitadas precisam ser retentadas pelo cliente.

---

## Schemas de Entrada e Saída

### Entrada — `TransactionInputSchema`

Definido em [src/api/schemas.py](src/api/schemas.py).

| Campo | Tipo | Restrição | Descrição |
|-------|------|-----------|-----------|
| `renda` | `float` | `≥ 0.0` | Renda mensal do cliente (R$) |
| `idade` | `float` | `≥ 0.0` | Idade do cliente (anos) |
| `etnia` | `int` | `≥ 0` | Etnia (codificada numericamente) |
| `sexo` | `int` | `≥ 0` | Sexo: `0` = feminino, `1` = masculino |
| `casapropria` | `int` | `≥ 0` | Possui casa própria: `0` = não, `1` = sim |
| `outrasrendas` | `int` | `≥ 0` | Possui outras fontes de renda: `0` = não, `1` = sim |
| `estadocivil` | `int` | `≥ 0` | Estado civil (codificado numericamente) |
| `escolaridade` | `int` | `≥ 0` | Nível de escolaridade (`0`–`3`) |

Todos os 8 campos são **obrigatórios**. Valores fora do tipo ou `< 0` resultam em `HTTP 422`.

### Saída — `ScoreOutputSchema`

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `score_predito` | `int` | Classe binária: `0` = Aprovado, `1` = Risco Detectado |
| `score_probabilidade` | `float` | Probabilidade de inadimplência no intervalo `[0.0, 1.0]`, com 4 casas decimais |
| `score_level` | `str` | Nível de risco: `Baixo` (< 30%), `Médio` (30%–60%), `Alto` (> 60%) |
| `risco_interpretavel` | `str` | Classificação semântica: `Aprovado` ou `Risco Detectado` |

> A regra de negócio para o `score_level` está em [src/model/inference.py](src/model/inference.py) na função `_score_level`.

---

## Códigos de Status HTTP

| Status | Endpoint | Significado |
|--------|----------|-------------|
| `200 OK` | todos | Requisição processada com sucesso |
| `401 Unauthorized` | `/token` | Credenciais inválidas |
| `401 Unauthorized` | `/predict` | Token ausente, expirado, malformado, ou com claim `sub` inválida |
| `422 Unprocessable Entity` | `/token` | `username` ou `password` ausente |
| `422 Unprocessable Entity` | `/predict` | Payload com campo ausente, tipo errado, ou valor `< 0` |
| `429 Too Many Requests` | `/predict` | Limite de 5 req/min/IP excedido |
| `500 Internal Server Error` | `/predict` | Falha na inferência (logs do servidor têm o traceback) |
| `503 Service Unavailable` | `/health`, `/predict` | Modelo não carregado pelo `InferenceEngine` |

---

## Troubleshooting e FAQ

### 1. Recebi `401 Unauthorized` mesmo enviando o token. O que verificar?

Em ordem de probabilidade:

1. **Header mal formatado.** Deve ser exatamente `Authorization: Bearer <token>` — note o espaço entre `Bearer` e o token, e que `Bearer` começa com B maiúsculo.
2. **Token expirado.** Tokens expiram após 60 minutos. Se o `detail` da resposta for `"Token expirado"`, gere um novo via `POST /token`.
3. **Token de outro ambiente.** Tokens emitidos pelo ambiente local **não funcionam** no Azure (cada ambiente tem seu próprio `API_SECRET_KEY`). Confirme que você obteve o token na mesma URL onde está chamando `/predict`.
4. **Token truncado.** JWTs são longos (~200 caracteres). Se ele foi copiado parcialmente do log de outra ferramenta, regenere.
5. **Claim `sub` ausente.** Se o `detail` for `"Token inválido"`, o token foi assinado mas a claim `sub` está vazia — não deveria acontecer com `/token`, indica adulteração.

### 2. Recebi `429 Too Many Requests` logo depois de autenticar — por quê?

O rate limit do `/predict` é **5 req/min por IP**, independente do token. Se outro cliente atrás do mesmo NAT/proxy já consumiu o limite, sua requisição será bloqueada mesmo no primeiro uso do seu token.

**Soluções:**
- Aguarde 60 segundos e tente novamente
- Em integrações automatizadas, implemente backoff exponencial respeitando o header `Retry-After` da resposta
- Se o cenário exigir taxa maior, contate o time da QuantumFinance para revisar o limite

### 3. Por que `/health` está retornando `503`?

O endpoint `/health` retorna `503` quando o `InferenceEngine` não conseguiu carregar o modelo. Causas mais comuns:

| Cenário | Como diagnosticar | Solução |
|---------|-------------------|---------|
| Não há versão `Production` no MLflow Registry | Rodar `python -c "import mlflow; mlflow.set_tracking_uri('sqlite:///mlruns.db'); print([(v.version, v.current_stage) for v in mlflow.MlflowClient().search_model_versions(\"name='XGBoost_Transaction_Score'\")])"` | Rodar `python src/model/train.py` para gerar e promover um modelo |
| Arquivos `mlruns/` ausentes do container | `az containerapp logs show ... --tail 100` mostra `OSError: No such file or directory` | Garantir que `git ls-files mlruns/ \| head` lista arquivos antes do build |
| `MLFLOW_TRACKING_URI` apontando pro lugar errado | Logs mostram path SQLite errado | No Azure, deve ser `sqlite:////app/mlruns.db` (4 barras = path absoluto) |
| Modelo corrompido | Logs mostram traceback de `xgb.Booster.load_model` | Re-treinar |

### 4. Como atualizo o modelo que está sendo servido?

A API consome **automaticamente** a última versão promovida para `Production` no MLflow Registry. Para atualizar:

1. Re-treine localmente: `python src/model/train.py`
   - Se `ROC-AUC ≥ 0.75` e sem drift, a nova versão é promovida e a anterior arquivada
2. Commite os artefatos atualizados: `git add -f mlruns/ mlruns.db && git commit -m "chore: update model artifacts"`
3. Push para `main` — o pipeline CI/CD reconstrói a imagem Docker e atualiza o Azure Container App

A próxima requisição em `/predict` (ou no `/health` em uma réplica nova) já carregará o modelo atualizado.

### 5. Posso reutilizar o mesmo token entre requisições?

**Sim — é o uso esperado.** O JWT é stateless: cada chamada a `/predict` valida a assinatura e a expiração no servidor sem consultar nenhum estado compartilhado. Para uma sessão de até 60 minutos, **autentique uma vez e reutilize o token**. Não chame `/token` antes de cada `/predict` — isso é desnecessário e pode interferir no seu fluxo.

### 6. Recebi `422 Unprocessable Entity`. Como descubro qual campo está errado?

A resposta `422` traz um array `detail` onde cada item descreve um problema específico:

- `loc`: caminho do campo (`["body", "renda"]` = campo `renda` no body)
- `type`: tipo do erro (`missing`, `int_parsing`, `greater_than_equal`, `float_parsing`)
- `msg`: descrição em inglês
- `input`: valor recebido (útil para depurar coerção de tipos)

Erros comuns:

| `type` | Significado | Exemplo |
|--------|-------------|---------|
| `missing` | Campo obrigatório ausente | Faltou `idade` no body |
| `greater_than_equal` | Valor `< 0` | `renda: -100` |
| `int_parsing` | Tipo errado (string em vez de int) | `sexo: "M"` |
| `float_parsing` | Tipo errado (string em vez de float) | `renda: "4500"` |

Confirme que **todos os 8 campos** estão presentes, com tipos corretos e valores ≥ 0.

### 7. O Swagger UI mostra meu token, é seguro deixar aberto?

Em ambiente de desenvolvimento, `/docs` está exposto e armazena o token na sessão do navegador (memória, não localStorage). Para produção:

- Não compartilhe a tela do Swagger com o token autenticado
- Tokens vivem 60 minutos por padrão — feche a aba após o uso
- Se desconfia de exposição, gere um novo token: o antigo continua válido até expirar (não há logout server-side), mas você pode rotacionar `API_SECRET_KEY` para invalidar todos os tokens emitidos

### 8. A primeira requisição depois de algum tempo demora muito. É normal?

Sim. O Azure Container App está configurado com `min-replicas=0`, ou seja, **escala a zero** quando ocioso. A primeira requisição após inatividade dispara um cold start:

- ~10–15s para o container subir
- ~2–3s para carregar o modelo XGBoost via MLflow

Requisições subsequentes são rápidas (<200ms). Para eliminar o cold start, configure `--min-replicas 1` (custo aproximado adicional: ~$20/mês).

### 9. Recebi `500 Internal Server Error`. O que fazer?

`500` indica falha não tratada na inferência. O servidor já registrou o traceback completo nos logs. **Como cliente, você não consegue diagnosticar pelo response** — o `detail` é genérico de propósito (não vazar stack trace é boa prática de segurança).

Procedimento:

1. Confirme que seu payload está dentro do schema esperado (não devolveu `422`)
2. Tente o mesmo payload depois de alguns segundos — pode ter sido um problema transitório
3. Se persistir, contate o time de operações com:
   - Timestamp aproximado da requisição
   - Payload usado (sem dados sensíveis)
   - Headers (sem o token completo — só os primeiros 10 caracteres)

### 10. Como sei qual versão do modelo está sendo servida?

Hoje a API não expõe um endpoint de metadata da versão. Para descobrir:

- **Olhar o registry localmente:**
  ```bash
  python -c "import mlflow; mlflow.set_tracking_uri('sqlite:///mlruns.db'); \
    print([(v.version, v.current_stage, v.run_id) for v in \
      mlflow.MlflowClient().get_latest_versions('XGBoost_Transaction_Score', stages=['Production'])])"
  ```
- **Olhar a UI do MLflow:** `mlflow ui --backend-store-uri sqlite:///mlruns.db` → http://localhost:5000

Para integrações automatizadas que precisam validar versão, abra um pedido de feature — uma rota futura `GET /model/version` retornaria essas informações.

---

## Documentação Interativa (Swagger)

Toda a especificação acima também está disponível em formato OpenAPI 3 navegável:

| Recurso | URL |
|---------|-----|
| Swagger UI | `http://localhost:8000/docs` |
| ReDoc | `http://localhost:8000/redoc` |
| OpenAPI JSON | `http://localhost:8000/openapi.json` |

O Swagger UI permite:
- Autenticar com o botão **Authorize** no topo direito (chama `/token` automaticamente)
- Testar `/predict` com payloads de exemplo via **Try it out**
- Copiar o `curl` equivalente de cada chamada

> **Nota sobre versões:** este documento descreve a API em sua versão atual. Mudanças futuras (novos endpoints, novos campos no schema) serão registradas em changelog separado e refletidas na resposta do `/openapi.json`.
