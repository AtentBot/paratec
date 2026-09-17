import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Rotas do PAINEL: exigem sessão (cookie). A validade real é checada no backend
// (/auth/me); aqui só barramos quem nem cookie tem, redirecionando ao /login.
// A tela /assinatura fica protegida mas acessível a quem tem sessão sem plano
// ativo (o cookie existe), para o responsável conseguir assinar.
const PROTEGIDAS = [
  "/painel", "/conversas", "/clientes", "/equipe", "/orcamentos", "/catalogo",
  "/fila", "/promocoes", "/conhecimento", "/relatorios", "/agentes",
  "/configuracoes", "/assinatura", "/suporte", "/admin", "/conta", "/integracoes",
];

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Proxy /agent/*: bloqueia publicamente o /chat (endpoint sem auth, usado só
  // pelo n8n via rede interna). Os demais /agent/* passam (a autorização é do
  // backend: endpoints operacionais exigem sessão; /auth e /billing/webhook são
  // públicos por design).
  if (pathname === "/agent/chat" || pathname.startsWith("/agent/chat/")) {
    return new NextResponse("Not found", { status: 404 });
  }
  if (pathname.startsWith("/agent/")) return NextResponse.next();

  const protegida = PROTEGIDAS.some((p) => pathname === p || pathname.startsWith(p + "/"));
  if (!protegida) return NextResponse.next();

  if (!req.cookies.has("atentbot_session")) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  // Roda em tudo, exceto estáticos e /media. Inclui /agent p/ bloquear /agent/chat.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|media).*)"],
};
