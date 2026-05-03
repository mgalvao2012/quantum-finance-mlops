import sys
import os
import logging
from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.auth import Token, create_access_token, verify_token
from api.schemas import TransactionInputSchema, ScoreOutputSchema
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Le as credenciais dos parceiros autorizados a partir de variáveis de ambiente
_raw_partners = os.getenv("VALID_PARTNERS")
VALID_PARTNERS = dict(pair.split(":") for pair in _raw_partners.split(",") if ":" in pair)

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="QuantumFinance API - JWT Secured")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Lazy load engine to avoid failures in CI
_engine = None

def get_engine():
    global _engine
    if _engine is None:
        from model.inference import engine
        _engine = engine
    return _engine

@app.get("/health")
async def health_check():
    """Liveness probe para orquestradores e load balancers"""
    model_ready = engine.model is not None
    if not model_ready:
        raise HTTPException(status_code=503, detail="Modelo indisponível")
    return {"status": "ok"}


@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """Gera o JWT para parceiros autorizados"""
    if form_data.username in VALID_PARTNERS and form_data.password == VALID_PARTNERS[form_data.username]:
        access_token = create_access_token(data={"sub": form_data.username})
        return {"access_token": access_token, "token_type": "bearer"}
    raise HTTPException(status_code=401, detail="Usuário ou senha incorretos")


@app.post("/predict", response_model=ScoreOutputSchema)
@limiter.limit("5/minute")
async def predict_score(request: Request, payload: TransactionInputSchema, current_user: str = Depends(verify_token)):
    """Avaliação de risco de crédito protegida por JWT e SlowAPI"""
    try:
        result = engine.predict(payload.model_dump())
        return ScoreOutputSchema(**result)
    except Exception:
        logger.exception("Falha na inferência para usuário %s", current_user)
        raise HTTPException(status_code=500, detail="Erro interno ao processar a predição.")
