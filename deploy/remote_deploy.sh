#!/usr/bin/env bash
# Deploy no nó Swarm (Hetzner): faz checkout do commit, builda a(s) imagem(ns) e
# atualiza o(s) serviço(s). Roda no NÓ — chamado pela pipeline
# (.github/workflows/deploy.yml) via SSH, e também serve para deploy manual:
#
#   bash deploy/remote_deploy.sh <sha> <agent|admin|both>
#
# Variáveis (opcionais; têm default):
#   DEPLOY_PATH    checkout do repo no nó                (default: /opt/paratec)
#   AGENT_SERVICE  nome do serviço Swarm do agente       (default: atentbot_agent-service)
#   ADMIN_SERVICE  nome do serviço Swarm do painel       (default: atentbot_admin)
set -euo pipefail

SHA="${1:?uso: remote_deploy.sh <sha> <agent|admin|both>}"
ALVO="${2:-both}"
REPO_DIR="${DEPLOY_PATH:-/opt/paratec}"
AGENT_SVC="${AGENT_SERVICE:-atentbot_agent-service}"
ADMIN_SVC="${ADMIN_SERVICE:-atentbot_admin}"

cd "$REPO_DIR"
git fetch --all --prune --quiet
git checkout -f "$SHA"

TAG="$(git rev-parse --short=7 HEAD)"
echo ">> deploy commit $TAG (alvo: $ALVO) em $REPO_DIR"

build_update_agent() {
  echo ">> build paratec/agent-service:$TAG (contexto = raiz)"
  docker build -f agent-service/Dockerfile -t "paratec/agent-service:$TAG" .
  echo ">> docker service update $AGENT_SVC"
  docker service update --image "paratec/agent-service:$TAG" \
    --update-order start-first --force "$AGENT_SVC"
}

build_update_admin() {
  echo ">> build paratec/admin:$TAG (contexto = admin/)"
  docker build -f admin/Dockerfile -t "paratec/admin:$TAG" admin
  echo ">> docker service update $ADMIN_SVC"
  docker service update --image "paratec/admin:$TAG" \
    --update-order start-first "$ADMIN_SVC"
}

case "$ALVO" in
  agent) build_update_agent ;;
  admin) build_update_admin ;;
  both)  build_update_agent; build_update_admin ;;
  *) echo "alvo inválido: '$ALVO' (use agent|admin|both)"; exit 2 ;;
esac

echo ">> deploy concluído: $TAG ($ALVO)"
