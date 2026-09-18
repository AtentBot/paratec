#!/usr/bin/env bash
# Migração SaaS multi-tenant (AtentBot) — aplica db/schema_ops.sql de forma
# DELIBERADA e controlada, em vez de depender só do startup do serviço.
#
# Por quê: o schema_ops.sql roda no startup do agent-service (idempotente), mas
# os swaps de PK compostas e o backfill de tenant_id podem travar tabelas
# grandes (messages/events) num Postgres COMPARTILHADO (Evolution/n8n). Rode
# isto uma vez, off-peak, com backup feito — depois os startups apenas revalidam.
#
# Conexão: usa as variáveis padrão do Postgres (PGHOST/PGPORT/PGDATABASE/
# PGUSER/PGPASSWORD) OU $DATABASE_URL. Ex.:
#   PGHOST=pg.atentbot.com PGUSER=postgres PGPASSWORD=... PGDATABASE=paratec \
#     bash scripts/migrate_saas.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCHEMA="$ROOT/db/schema_ops.sql"
[ -f "$SCHEMA" ] || { echo "não encontrei $SCHEMA" >&2; exit 1; }

# psql aceita a URL como 1º arg posicional, ou as variáveis PG* do ambiente.
PSQL=(psql -v ON_ERROR_STOP=1)
if [ "${DATABASE_URL:-}" != "" ]; then
  PSQL+=("$DATABASE_URL")
fi

q() { "${PSQL[@]}" -tAc "$1"; }

echo "==> alvo: ${DATABASE_URL:-${PGUSER:-postgres}@${PGHOST:-localhost}:${PGPORT:-5432}/${PGDATABASE:-paratec}}"
echo "==> testando conexão"
q "SELECT 1" >/dev/null

echo "==> pré-checagem (tamanho das tabelas que serão alteradas/backfilled)"
for t in messages events conversations customers queue_items; do
  n=$(q "SELECT count(*) FROM $t" 2>/dev/null || echo "n/d")
  printf "   %-14s %s linhas\n" "$t" "$n"
done
echo "   (tabelas grandes = backfill/UPDATE mais demorado; rode off-peak)"

cat <<'AVISO'

==> ATENÇÃO
    - Faça BACKUP do banco antes de prosseguir (pg_dump).
    - A migração é idempotente e guardada, mas altera PKs de customers e
      conversations e recria a FK de messages.
    - Não interrompa no meio.

AVISO
read -r -p "Confirmar e aplicar a migração agora? [digite 'sim'] " ok
[ "$ok" = "sim" ] || { echo "cancelado."; exit 0; }

echo "==> aplicando db/schema_ops.sql"
"${PSQL[@]}" -f "$SCHEMA"

echo "==> verificação pós-migração"
q "SELECT 'tenant paratec id=' || id FROM tenants WHERE slug='paratec'"
q "SELECT 'assinatura cortesia: ' || status FROM subscriptions s
     JOIN tenants t ON t.id=s.tenant_id WHERE t.slug='paratec'"
nulos=$(q "SELECT count(*) FROM conversations WHERE tenant_id IS NULL")
echo "   conversations com tenant_id nulo: $nulos (deve ser 0)"
pk=$(q "SELECT count(*) FROM pg_constraint
          WHERE conname='conversations_pkey' AND array_length(conkey,1)=2")
echo "   PK composta em conversations: $([ "$pk" = "1" ] && echo OK || echo PENDENTE)"

echo "==> concluído. Próximo: criar o owner (seed_owner.py) e setar as chaves Stripe."
