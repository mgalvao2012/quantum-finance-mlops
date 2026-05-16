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
