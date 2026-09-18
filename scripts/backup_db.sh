#!/usr/bin/env bash
# Backup do Postgres (pg_dump) — rode ANTES da migração SaaS (scripts/migrate_saas.sh).
#
# Conexão: usa as variáveis padrão do Postgres (PGHOST/PGPORT/PGDATABASE/PGUSER/
# PGPASSWORD) OU $DATABASE_URL. Gera um arquivo comprimido, com timestamp.
#
#   PGHOST=pg.atentbot.com PGUSER=postgres PGPASSWORD=... PGDATABASE=paratec \
#     bash scripts/backup_db.sh [pasta-destino]
set -euo pipefail

DEST="${1:-.}"
mkdir -p "$DEST"
STAMP="$(date +%Y%m%d-%H%M%S)"
DB="${PGDATABASE:-paratec}"
OUT="$DEST/backup_${DB}_${STAMP}.sql.gz"

command -v pg_dump >/dev/null || { echo "pg_dump não encontrado (instale o postgresql-client)" >&2; exit 1; }

echo "==> gerando backup de '${DATABASE_URL:-$DB}' em $OUT"
if [ "${DATABASE_URL:-}" != "" ]; then
  pg_dump --no-owner --no-privileges "$DATABASE_URL" | gzip > "$OUT"
else
  pg_dump --no-owner --no-privileges | gzip > "$OUT"
fi

SIZE="$(du -h "$OUT" | cut -f1)"
echo "==> OK — $OUT ($SIZE)"
echo "    Restaurar:  gunzip -c '$OUT' | psql \"\$DATABASE_URL\""
