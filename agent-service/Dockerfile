# Build a partir da RAIZ do repo (contexto .) para incluir db/schema_ops.sql,
# aplicado no startup pelo agent-service. Ver docker-compose.yml.
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY agent-service/requirements.txt .
RUN pip install -r requirements.txt

COPY agent-service/app ./app
COPY db ./db

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
