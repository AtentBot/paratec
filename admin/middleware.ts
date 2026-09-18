import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Rotas do PAINEL: exigem sessão (cookie). A validade real é checada no backend
// (/auth/me); aqui só barramos quem nem cookie tem, redirecionando ao /login.
// Onboarding (também exige sessão): o <AccountGate/> do painel manda para
// /verificar-whatsapp (código) e depois /ativar (escolha de plano + cartão).
const PROTEGIDAS = [
  "/verificar-whatsapp", "/ativar", "/painel", "/conversas", "/clientes", "/equipe", "/orcamentos", "/catalogo",
  "/fila", "/promocoes", "/conhecimento", "/relatorios", "/agentes",
  "/configuracoes", "/assinatura", "/suporte", "/admin", "/conta", "/integracoes",
];

// Content-Security-Policy com nonce por requisição. O Next 14 injeta o nonce
// nos <script> que ele gera quando encontra o nonce no header de CSP da
// REQUISIÇÃO; o script inline do tema lê o nonce via headers() no layout.
// Origens externas usadas: Google Fonts (css + arquivos) e imagens do catálogo
// (paratec.com.br). Sem Stripe.js/analytics no cliente.
function buildCsp(nonce: string): string {
  return [
    `default-src 'self'`,
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'`,
    `style-src 'self' 'unsafe-inline' https://fonts.googleapis.com`,
    `font-src 'self' https://fonts.gstatic.com data:`,
    `img-src 'self' data: https://paratec.com.br`,
    `connect-src 'self'`,
    `frame-ancestors 'none'`,
    `base-uri 'self'`,
    `form-action 'self'`,
    `object-src 'none'`,
  ].join("; ");
}

function newNonce(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

// Report-Only por padrão: a CSP é publicada e reporta violações no console do
// navegador SEM bloquear nada — rollout seguro. Depois de validar que o painel
// não acusa violação real, ligue o enforcement definindo CSP_ENFORCE=true (aí o
// header vira o `Content-Security-Policy` que de fato bloqueia).
const CSP_ENFORCE = process.env.CSP_ENFORCE === "true";

// Responde já com a CSP aplicada (e o nonce disponível ao SSR via x-nonce).
function comCsp(req: NextRequest): NextResponse {
  const nonce = newNonce();
  const csp = buildCsp(nonce);
  const requestHeaders = new Headers(req.headers);
  requestHeaders.set("x-nonce", nonce);
  // O Next só injeta o nonce nos scripts se enxergar a CSP no header da
  // requisição — vale mesmo em report-only, para o nonce já ficar coerente.
  requestHeaders.set("content-security-policy", csp);
  const res = NextResponse.next({ request: { headers: requestHeaders } });
  const header = CSP_ENFORCE
    ? "content-security-policy"
    : "content-security-policy-report-only";
  res.headers.set(header, csp);
  return res;
}

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Proxy /agent/*: bloqueia publicamente o /chat (endpoint sem auth, usado só
  // pelo n8n via rede interna). Os demais /agent/* passam (a autorização é do
  // backend: endpoints operacionais exigem sessão; /auth e /billing/webhook são
  // públicos por design). Respostas de proxy não recebem a CSP das páginas.
  if (pathname === "/agent/chat" || pathname.startsWith("/agent/chat/")) {
    return new NextResponse("Not found", { status: 404 });
  }
  if (pathname.startsWith("/agent/")) return NextResponse.next();

  const protegida = PROTEGIDAS.some((p) => pathname === p || pathname.startsWith(p + "/"));
  if (protegida && !req.cookies.has("atentbot_session")) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }

  // Página HTML servida por nós -> aplica a CSP com nonce.
  return comCsp(req);
}

export const config = {
  // Roda em tudo, exceto estáticos e /media. Inclui /agent p/ bloquear /agent/chat.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|media).*)"],
};
