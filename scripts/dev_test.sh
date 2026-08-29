#!/usr/bin/env bash
# Verificação local ponta-a-ponta do agent-service (requer Docker rodando).
#
# Sobe um Postgres EFÊMERO, aplica os schemas (catálogo + operacional), carrega
# o catálogo real do cache (data/products.json), roda os testes de integração
# e faz um smoke dos endpoints da tela adm. Não usa o Postgres de produção nem
# precisa de GOOGLE_API_KEY (o LLM não é chamado aqui).
#
# Uso:  bash scripts/dev_test.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/agent-service/.venv/bin"
CONT="paratec-pg-test"
PORT="5544"

export PGHOST=localhost PGPORT="$PORT" PGDATABASE=paratec PGUSER=postgres PGPASSWORD=devtest

cleanup() { docker rm -f "$CONT" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "==> subindo Postgres efêmero ($CONT :$PORT)"
cleanup
docker run -d --name "$CONT" \
  -e POSTGRES_PASSWORD="$PGPASSWORD" -e POSTGRES_DB="$PGDATABASE" \
  -p "$PORT:5432" postgres:16-alpine >/dev/null

echo "==> aguardando o banco aceitar conexões"
for i in $(seq 1 30); do
  if docker exec "$CONT" pg_isready -U postgres >/dev/null 2>&1; then break; fi
  sleep 1
done

echo "==> aplicando schema do catálogo + carregando produtos (cache)"
"$VENV/python" "$ROOT/scraper/load_to_db.py" --schema

echo "==> testes (unitários + integração real contra o Postgres)"
( cd "$ROOT/agent-service" && "$VENV/python" -m pytest )

echo "==> subindo a API e fazendo smoke dos endpoints"
( cd "$ROOT/agent-service" && GOOGLE_API_KEY=dummy "$VENV/uvicorn" app.main:app --port 8010 >/tmp/paratec-api.log 2>&1 & )
API_PID=$!
for i in $(seq 1 30); do curl -sf http://localhost:8010/health >/dev/null 2>&1 && break; sleep 1; done

echo "--- /health";            curl -s http://localhost:8010/health; echo
echo "--- /catalog/stats";     curl -s http://localhost:8010/catalog/stats; echo
echo "--- /metrics/overview";  curl -s http://localhost:8010/metrics/overview; echo
echo "--- /conversas";         curl -s http://localhost:8010/conversas; echo
echo "--- /fila";              curl -s http://localhost:8010/fila; echo

kill "$API_PID" 2>/dev/null || true
echo "==> OK — pipeline real verificado (catálogo com dados; ops vazio até haver atendimentos)"
