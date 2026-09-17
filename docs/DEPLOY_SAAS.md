# Deploy da virada SaaS (AtentBot) — runbook

Passo a passo para colocar no ar o AtentBot multi-tenant (auth próprio + Stripe),
mantendo a Paratec (tenant #1) funcionando o tempo todo. Contexto e decisões:
`~/.claude/plans/joyful-zooming-sphinx.md`.

Ordem recomendada: **1) Stripe → 2) envs → 3) migração → 4) owner → 5) deploy dos
serviços → 6) remover Authentik → 7) verificação**.

---

## 1. Stripe (modo teste primeiro, depois live)

1. **Produtos e preços** (Dashboard → Products). Crie 3 produtos com um **preço
   recorrente mensal (BRL)** cada e copie os **Price IDs** (`price_...`):
   - Essencial — R$ 690/mês
   - Profissional — R$ 1.690/mês
   - Escala — R$ 3.900/mês
   > NÃO configure trial no preço (o checkout é sem trial por design).
   > Esses são só os preços iniciais. Depois do go-live, **altere o preço pela
   > central admin → Planos e preços** (`/admin/planos`), nunca direto no Stripe:
   > o sistema cria o novo Price (mesmo produto e lookup_key), arquiva o antigo,
   > grava o price vigente na tabela `plans` (as envs `STRIPE_PRICE_*` ficam só
   > como fallback) e, se você marcar a opção, migra as assinaturas atuais sem
   > proração. O site (landing, /precos) e o painel leem o valor da API.
2. **Chaves** (Developers → API keys): copie a **Secret key** (`sk_...`) e a
   **Publishable key** (`pk_...`).
3. **Webhook** (Developers → Webhooks → Add endpoint):
   - URL: `https://<host-da-api>/billing/webhook`
     (se o agente não é público, exponha só essa rota, ou aponte para o proxy
     `https://app.atentbot.com/agent/billing/webhook`).
   - Eventos: `checkout.session.completed`, `customer.subscription.created`,
     `customer.subscription.updated`, `customer.subscription.deleted`,
     `invoice.paid`, `invoice.payment_failed`.
   - Copie o **Signing secret** (`whsec_...`).

Teste local do webhook (opcional): `stripe listen --forward-to
localhost:8000/billing/webhook` e `stripe trigger checkout.session.completed`.

---

## 1b. Cobrança automática dos extras (Stripe Billing Meters) — opcional

O consumo (indexação + conversas) é sempre **medido e mostrado** no painel. Para
**cobrar automaticamente** na fatura, ligue os medidores do Stripe:

1. **Meters** (Dashboard → Billing → Meters, ou API `billing.Meter`). Crie dois,
   com agregação **sum** sobre o campo `value`:
   - indexação → `event_name`: `atentbot_indexacao`
   - conversa → `event_name`: `atentbot_conversa`
2. **Preços metered** (um por meter, recorrente mensal, moeda BRL). O código
   reporta `value = tokens`, então use **`unit_amount_decimal`** (centavos por
   token) casando com as tarifas do serviço:
   - indexação: R$ 0,02 / 1.000 tokens → `unit_amount_decimal = "0.002"`
   - conversa: R$ 0,20 / 1.000 tokens → `unit_amount_decimal = "0.02"`
   > Mantenha essas tarifas iguais às `USAGE_PRECO_POR_1K_TOKENS_*` (a estimativa
   > do painel usa as do serviço; a cobrança usa as do Stripe).
3. **Envs** (ver `.env.docker.example`): `STRIPE_METER_INDEXACAO`,
   `STRIPE_METER_CONVERSA`, `STRIPE_PRICE_METER_INDEXACAO`,
   `STRIPE_PRICE_METER_CONVERSA`. Preenchidos os quatro (com `STRIPE_SECRET_KEY`),
   `metered_enabled` liga: o painel passa a marcar "Cobrado na fatura" e o
   consumo é reportado ao Stripe em tempo real.
4. **Checkout:** novas assinaturas já entram com os itens metered (plano base +
   2 itens de consumo). **Assinaturas já existentes** NÃO ganham os itens
   retroativamente — rode o utilitário (idempotente, dry-run por padrão):
   `cd agent-service && .venv/bin/python backfill_metered.py` (depois `--apply`).
5. Redeploy o agent-service com as envs. O reporte é best-effort: se o Stripe
   falhar, o consumo continua medido no banco (nada trava o atendimento).

Enquanto os envs ficarem vazios, o comportamento é o atual (medir e mostrar).

## 2. Variáveis de ambiente (agent-service)

Adicione (ver `.env.docker.example`):

```
STRIPE_SECRET_KEY=sk_...
STRIPE_PUBLISHABLE_KEY=pk_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ESSENCIAL=price_...
STRIPE_PRICE_PROFISSIONAL=price_...
STRIPE_PRICE_ESCALA=price_...
BILLING_SUCCESS_URL=https://app.atentbot.com/checkout/sucesso
BILLING_CANCEL_URL=https://app.atentbot.com/checkout/cancelado
PAST_DUE_GRACE_DAYS=3
SESSION_COOKIE_SECURE=true
SESSION_TTL_DAYS=30
DEFAULT_TENANT_SLUG=paratec
PANEL_URL=https://app.atentbot.com
```

> Billing vazio (`STRIPE_SECRET_KEY=`) = enforcement liberado (útil só em dev).
> Com as chaves setadas, tenants sem assinatura ativa recebem 402 e o bot silencia
> — a Paratec é protegida pela assinatura "cortesia" semeada no schema.

Frontend: garanta que o cookie de sessão chega ao backend (o `admin` já faz proxy
same-origin `/agent/*`, então funciona sem CORS). Se algum dia a API for cross-origin,
ajuste `CORS_ORIGINS` e use `credentials: 'include'`.

---

## 3. Migração de schema (deliberada, off-peak)

Faça **backup** e rode o runner (aplica `db/schema_ops.sql`: novas tabelas,
`tenant_id` + backfill, PKs compostas, seeds da Paratec):

```
PGHOST=... PGUSER=... PGPASSWORD=... PGDATABASE=paratec bash scripts/backup_db.sh
PGHOST=... PGUSER=... PGPASSWORD=... PGDATABASE=paratec bash scripts/migrate_saas.sh
```

Ele mostra o tamanho das tabelas (o backfill de `messages`/`events` grandes é o
trecho mais lento), pede confirmação e verifica o resultado ao final. Como é
idempotente, os startups seguintes do serviço apenas revalidam.

> No Swarm com deploy rolling, o código antigo e o novo convivem: as colunas
> `tenant_id` têm DEFAULT transitório = id da Paratec, então inserts do código
> antigo continuam válidos durante a janela.

---

## 4. Criar o usuário owner da Paratec

Sem o Authentik, o login é da aplicação. Crie o owner uma vez:

```
cd agent-service
.venv/bin/python seed_owner.py --slug paratec \
  --email voce@paratec.com --senha 'TroqueEstaSenha123' --nome 'Seu Nome'
```

(No container: `docker exec <container> python seed_owner.py --slug paratec ...`.)

**Equipe Dew (central admin):** promova os usuários da equipe a staff (acesso
cross-tenant à central `/admin`):

```
cd agent-service
.venv/bin/python make_staff.py --email suporte@dewconsultoria.com.br
```

---

## 5. Deploy dos serviços

- **agent-service:** rebuild da imagem (novas deps `stripe`, `argon2-cffi` no
  `requirements.txt`) e `docker service update --image ... --force paratec-agent`
  (preservando o volume `agent_media` e os envs — ver notas em
  [[paratec-agent-service]]).
- **admin:** rebuild (`npm run build` já validado, 22 rotas) e
  `docker service update --image ... paratec-admin`.

---

## 6. Remover o Authentik

O painel agora autentica sozinho (cookie de sessão). No Traefik/Swarm, remova do
serviço `paratec-admin`: o middleware `authentik` (forwardauth) e o router
`paratec-outpost`. O `/auth/me` substituiu o antigo `/whoami` (Authentik headers).

Domínios sugeridos: `atentbot.com` (marketing/auth) e `app.atentbot.com` (painel)
— pode ser o mesmo app Next roteando por path (landing em `/`, painel em `/painel`).

---

## 7. n8n / WhatsApp

O `/chat` resolve o tenant pela **instância** (tabela `instances`). As instâncias
existentes foram semeadas para a Paratec na migração. Ao conectar um número novo
pelo painel (`/configuracoes`), o mapeamento é registrado automaticamente. O corpo
do `/chat` do fluxo n8n já envia `instancia` (feito antes) — nada a mudar para a
Paratec. Só registre novas instâncias antes de onboardar um 2º tenant, senão elas
caem no fallback (Paratec).

---

## 8. Verificação (checklist)

- [ ] `GET /health` 200 com contagem de produtos.
- [ ] Cadastro novo em `atentbot.com/cadastro` → checkout (cartão de teste
      `4242 4242 4242 4242`) → cobra na hora → `/checkout/sucesso` vira `ativa`.
- [ ] Painel do tenant novo abre isolado (0 conversas/produtos).
- [ ] `/assinatura`: cancelar → mantém acesso até `current_period_end`; reativar desfaz.
- [ ] `invoice.payment_failed` (Stripe CLI) → status `past_due` → bloqueio após a carência.
- [ ] Regressão Paratec: login do owner, dashboard/conversas/catálogo com os dados
      de sempre, bot respondendo pelo n8n.
- [ ] Isolamento: dados da Paratec não aparecem em outro tenant (e vice-versa).
- [ ] Testes: `bash scripts/dev_test.sh` (inclui `tests/test_isolation.py`).

---

## 9. Pendência de segurança (pré-requisito)

Rotacionar os segredos que estavam em `projeto.txt` (Docker/GitHub/Hetzner/
Portainer/Postgres/Gemini) **antes** de expor o billing publicamente.

---

## 10. Rollback

- Schema: restaure `backup_pre_saas.sql` (as mudanças são aditivas + swaps de PK;
  o backup é o caminho seguro de volta).
- Código: `docker service update --rollback` nos serviços.
- Billing: `STRIPE_SECRET_KEY=` desliga o enforcement sem derrubar o resto.
