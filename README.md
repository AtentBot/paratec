# Paratec — Plataforma de Atendimento com IA

Plataforma que ajuda os vendedores da Paratec: uma malha de **multi-agentes**
que responde sobre produtos, atende pedidos, consulta entregas e emite 2ª via de
boletos, conversando com clientes via **WhatsApp**.

## Arquitetura (visão geral)

```
Cliente (WhatsApp)
   │
   ▼
Evolution API  ──►  N8N (orquestração de fluxo / integrações)
                       │
                       ▼
                 Serviço LangGraph (malha de agentes: produtos, pedidos,
                       │            entrega, boletos, ...)
                       ▼
                 Postgres (catálogo + base de conhecimento/RAG)
```

- **Orquestração híbrida**: N8N recebe/envia WhatsApp e faz integrações
  (boleto, entrega); chama o serviço **LangGraph** para o raciocínio dos agentes.
- **WhatsApp**: Evolution API (self-hosted).
- **Banco**: Postgres (`pg.atentbot.com`). RAG vetorial depende de **pgvector**
  (ainda não provisionado no servidor — ver "Pendências").
- **Infra**: Hetzner + Docker + Portainer.

## Estado atual — Catálogo (fonte de dados dos agentes)

Fonte: <https://paratec.com.br/produtos/> (WordPress; post type `produto`).
Descoberto que a **API REST do WP** expõe os 129 produtos; os dados técnicos
(SKU/material/dimensão/descrição) ficam no HTML de cada página.

Pipeline em `scraper/` (3 fases):

| Fase | Script | O que faz |
|------|--------|-----------|
| 1 | `scrape_index.py` | Enumera via REST + baixa/cacheia o HTML em `data/raw/` |
| 2 | `extract.py` | Parser heurístico → `data/products.json` (marca irregulares em `data/needs_llm.json`) |
| 2b | `extract_llm.py` *(pendente)* | Fallback LLM para páginas irregulares (extração híbrida) |
| 3 | `load_to_db.py` | Upsert idempotente no Postgres |

Modelo de dados: `products` (família) → `product_variants` (SKUs);
`categories` + `product_categories` (N:N). Ver `db/schema.sql`.

## Serviço de agentes (LangGraph)

`agent-service/` — API FastAPI que expõe a malha de agentes. Consulta o catálogo
no Postgres via ferramentas reais.

- `app/catalog.py` — consultas ao catálogo (busca, detalhe, por SKU, categorias)
- `app/tools.py` — ferramentas LangChain sobre o catálogo
- `app/agents.py` — grafo LangGraph (especialista de **produtos** completo;
  pedidos/entrega/boletos são pontos de extensão)
- `app/main.py` — endpoints `GET /health` e `POST /chat`

Contrato do `POST /chat` (o que o N8N chama):
```json
// request
{ "mensagem": "vocês têm captor Franklin?", "thread_id": "5511999998888" }
// response
{ "resposta": "Sim! Temos o Captor Franklin 1 Descida (PRT-101/103/105/121)..." }
```
`thread_id` = identificador da conversa (ex: número do WhatsApp) para manter histórico.

## Stack de execução (Docker)

`docker-compose.yml` sobe: **Evolution API** (WhatsApp) → **N8N** (fluxo) →
**agent-service** (agentes) + **Postgres** (pgvector) + **Redis**.

```bash
cp .env.docker.example .env.docker   # preencher segredos (NÃO commitar)
docker compose --env-file .env.docker up -d --build
```

Fluxo do WhatsApp (montado no N8N):
1. Evolution API recebe a mensagem do cliente e dispara um **webhook** para o N8N.
2. N8N extrai `mensagem` + número, chama `POST http://agent-service:8000/chat`.
3. N8N envia a `resposta` de volta pela Evolution API (`/message/sendText`).

Fluxo pronto para importar: **`n8n/paratec-whatsapp-flow.json`**
(N8N → Import from File). Após importar:
- Troque `REPLACE_WITH_EVOLUTION_API_KEY` no node "Responder (sendText)" pela
  chave da Evolution (ou use uma credencial Header Auth).
- Ative o workflow e copie a URL do Webhook.
- Na Evolution API, aponte o webhook da instância (evento `MESSAGES_UPSERT`)
  para essa URL: `http://n8n:5678/webhook/paratec-whatsapp`.

Malha de agentes (supervisor + especialistas), em `app/agents.py`:
`supervisor` roteia para `produtos` (completo), `pedidos`, `entrega`, `boletos`
(stubs que encaminham para humano — pontos de integração com ERP/logística/financeiro).

## Como rodar (catálogo)

```bash
cp .env.example .env          # preencher credenciais (NÃO commitar)
python3 -m venv .venv && .venv/bin/pip install -r scraper/requirements.txt

# Fase 1 (só stdlib, pode usar python3 direto)
python3 scraper/scrape_index.py
# Fase 2
python3 scraper/extract.py
# Fase 3 (aplica schema + carrega)
.venv/bin/python scraper/load_to_db.py --schema
```

## Segurança

- `projeto.txt` e `.env` estão no `.gitignore` — **nunca commitar segredos**.
- As credenciais que trafegaram em texto puro (Docker, GitHub PAT, root do
  Hetzner, Portainer, Postgres) **devem ser rotacionadas**.

## Pendências

- [x] Catálogo completo: 129 produtos / 293 variantes / 16 categorias no Postgres.
- [x] Serviço de agentes (LangGraph) — especialista de produtos + API `/chat`.
- [x] `docker-compose` da stack (Evolution + N8N + agent-service + Postgres + Redis).
- [x] **Tela administrativa** (`admin/`, Next.js): Dashboard, Conversas, Catálogo e Fila humana —
      **todas com dados reais** do agent-service (sem mocks). Rodar: `cd admin && npm install && npm run dev`.
- [x] **Persistência operacional** (`db/schema_ops.sql`): clientes, conversas, mensagens, eventos e fila.
      O `agent-service` grava durante o atendimento (checkpointer PostgresSaver) e expõe
      `/clientes`, `/conversas`, `/fila`, `/metrics/overview`. Schema aplicado no startup (idempotente).
- [x] **Cadastro de clientes via WhatsApp**: número novo é cadastrado (razão social, CNPJ,
      e-mail, contato) ANTES de liberar o catálogo — especialista `cadastro` + tools
      `verificar_cliente`/`cadastrar_cliente` (CNPJ/e-mail validados). Seção "Clientes" na adm.
- [x] **Testes** (`agent-service/tests/`, pytest): unitários + integração (pulam sem DB) + wiring HTTP.
- [x] **Verificação local** ponta-a-ponta: `bash scripts/dev_test.sh` (Postgres efêmero + catálogo real + smoke).
- [ ] **`GOOGLE_API_KEY`** (Gemini) para o agente responder (LLM). Camada de dados já validada.
- [ ] Subir a stack no Hetzner (Portainer) e montar o fluxo no N8N (webhook Evolution → `/chat` → sendText).
- [ ] Provisionar **pgvector** no Postgres de produção e aplicar `db/schema_vector.sql` (RAG).
- [ ] Especialistas adicionais: pedidos, entrega, 2ª via de boleto (extensão em `app/agents.py`).
- [ ] Fallback LLM de extração (`extract_llm.py`) — hoje desnecessário (heurística cobre 128/129).
- [ ] **Rotacionar todas as credenciais expostas.**
