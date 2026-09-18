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
   - Essencial — R$ 99/mês
   - Profissional — R$ 249/mês
   - Escala — R$ 599/mês
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
     `invoice.paid`, `invoice.payment_failed`, `checkout.session.async_payment_succeeded`,
     `checkout.session.async_payment_failed` (pacotes pagos por Pix).
   - Copie o **Signing secret** (`whsec_...`).

Teste local do webhook (opcional): `stripe listen --forward-to
localhost:8000/billing/webhook` e `stripe trigger checkout.session.completed`.

---

## 1b. Cota de mensagens e pacotes avulsos

Cada plano inclui N respostas da IA por ciclo (`plans.mensagens_incluidas`:
1.000 / 3.000 / 10.000). Acima disso o cliente compra um **pacote avulso** em
Assinatura (pagamento único, pré-pago, válido até o fim do ciclo em que foi pago).
Sem saldo, a IA não é chamada: o cliente final recebe `COTA_ESGOTADA_MENSAGEM` e a
conversa vai para a fila humana. O dono da conta recebe e-mail em 80% e 100%.

- **Nada a criar no Stripe:** o preço do pacote vai inline no Checkout
  (`price_data`), a partir da tabela `message_packs` (editável em `/admin/planos`,
  junto com a cota de cada plano).
- **Webhook:** além dos eventos acima, assine
  `checkout.session.async_payment_succeeded` e
  `checkout.session.async_payment_failed` (Pix/boleto confirmam depois).
- **Pix:** ligue em Settings → Payment methods para aparecer no checkout do pacote.
- **Cortesia:** assinaturas sem `stripe_subscription_id` (ex.: Paratec) não têm
  limite. `COTA_MENSAGENS_ATIVA=false` desliga a cota para todos (emergência).
- A antiga cobrança por token (Billing Meters) foi removida; tokens seguem medidos
  em `usage_events` só como custo interno (`/admin/consumo`). Assinaturas antigas
  que tenham itens metered param de receber eventos, ou seja, cobram R$ 0 neles.

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
