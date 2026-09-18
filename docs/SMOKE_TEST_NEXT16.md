# Smoke-test — upgrade Next.js 14 → 16 (painel AtentBot)

Escrito para: quem faz o deploy/valida o painel em staging antes de subir em produção.

Objetivo: confirmar que o upgrade para o Next 16.3.5 (commit `e291829`) não
quebrou nada em runtime. O build e a CSP já foram validados em build nativo; o
que falta é exercitar os **fluxos autenticados com o backend real** — que não deu
para testar no ambiente de desenvolvimento. Marque cada item; qualquer ❌ é
bloqueador para produção.

Pré-requisito: subir a stack (ou só o serviço `admin`) apontando para um
agent-service real, com `CSP_ENFORCE` **ainda em `false`** (report-only).

---

## 1. Build e boot
- [ ] A imagem do `admin` builda no CI/nó (Next 16, `output: standalone`).
- [ ] Container sobe rodando `node server.js` (standalone) — **não** `next start`.
- [ ] `GET /` (landing) responde 200.
- [ ] Sem erros de boot no log do container (`docker service logs atentbot_admin`).

## 2. CSP (ainda em report-only)
- [ ] Abrir o painel logado e olhar o **console do navegador**: anotar toda
      violação `Content-Security-Policy` reportada.
- [ ] Confirmar que **não há** violação que bloquearia recurso essencial
      (script do Next, fontes do Google, imagens de `paratec.com.br`, `/media`).
- [ ] `curl -sI https://<staging>/login | grep -i content-security` mostra o
      header `content-security-policy-report-only`.
- [ ] Se o console ficou limpo → definir `CSP_ENFORCE=true`, redeploy, e repetir
      um passe rápido pelas telas principais (nada deve quebrar).

## 3. Autenticação e sessão
- [ ] **Login** com credenciais válidas → entra no painel; cookie
      `atentbot_session` setado (HttpOnly, Secure, SameSite=Lax).
- [ ] **Rota protegida sem cookie** (ex.: abrir `/painel` numa aba anônima) →
      redireciona para `/login?next=/painel`.
- [ ] **Logout** limpa o cookie e volta a barrar as rotas protegidas.
- [ ] **Lockout**: 8 tentativas de senha errada seguidas → a 9ª responde **423**
      (aguardar/depois liberar). (backend, mas passa pelo proxy do painel).
- [ ] `/agent/chat` continua **404** pelo painel (bloqueio do middleware).

## 4. Proxy same-origin (rewrites — área sensível do Next 16)
- [ ] Chamadas do painel a `/agent/*` (ex.: `/auth/me`, `/conversas`) retornam
      200 e os dados certos (o rewrite para o agent-service funciona).
- [ ] `/api/v1/*` (se você usa a API pública pelo mesmo domínio) responde.
- [ ] Nenhuma resposta de `/agent/*` veio com header/corpo trocado (o Next 16
      mexeu em rewrites; conferir que o proxy está íntegro).

## 5. Tempo real (SSE)
- [ ] Abrir uma conversa em `/conversas/<id>` e enviar uma mensagem de teste
      pelo WhatsApp/simulação → a mensagem **aparece sozinha** (sem F5) via SSE.
- [ ] O stream reconecta após ficar minutos aberto (keep-alive a cada ~20s).
- [ ] Abrir muitas abas de stream do mesmo tenant → acima do teto responde 429
      (cap de SSE) sem derrubar o serviço.

## 6. next/image (Image Optimizer — CVE que o 16 corrige)
- [ ] Imagens do catálogo (de `paratec.com.br`) carregam nas telas de
      catálogo/produtos.
- [ ] Banners de promoção (em `/media`) carregam.
- [ ] `GET /_next/image?url=...` responde 200 para uma imagem válida e **não**
      aceita host fora de `remotePatterns` (paratec.com.br).

## 7. Mutações / formulários
- [ ] Criar/editar um registro simples (ex.: vendedor, agente, webhook) salva e
      reflete na tela.
- [ ] Upload de banner de promoção: imagem válida (JPG/PNG/WEBP) sobe; um arquivo
      não-imagem é **recusado** (magic bytes); acima de 5 MB → 413.
- [ ] Upload de CSV de catálogo / documento RAG respeita o teto (413 acima do
      limite) e importa um arquivo válido.
- [ ] Exportar um CSV (clientes/fila) e abrir no Excel/LibreOffice: um campo que
      começa com `=`/`+`/`@` aparece como **texto** (prefixo `'`), não executa.

## 8. Billing / onboarding (fluxos completos)
- [ ] Cadastro → e-mail de verificação → verificação de WhatsApp → checkout
      Stripe → volta em `/checkout/sucesso` e libera o painel.
- [ ] Webhook do Stripe (`/agent/billing/webhook`) processa e a assinatura fica
      ativa (testar com evento de teste do Stripe CLI, se disponível).

## 9. Regressão geral rápida
- [ ] Passar por todas as telas do menu lateral logado — nenhuma tela em branco
      nem erro de hidratação no console (o Next 16 mudou hidratação/caching).
- [ ] Tema claro/escuro alterna (o `<script>` do tema com nonce roda).
- [ ] Navegação SPA entre páginas sem recarregar quebrado.

---

## Rollback
Se algo travar em produção: reverter para a imagem anterior do `admin`
(`ADMIN_IMAGE` com a tag do commit pré-`e291829`) no Portainer. O upgrade é só
no serviço `admin`; o `agent-service` não muda.

## Notas do upgrade (para contexto)
- Única mudança de código: `RootLayout` virou async e usa `await headers()`
  (headers() ficou assíncrono no Next 15+).
- Node 20-alpine e `output: standalone` já atendem o Next 16.
- Ganho: `npm audit` = 0 vulnerabilidades (fecha DoS do Image Optimizer,
  smuggling em rewrites, DoS de RSC e a transitiva postcss).
