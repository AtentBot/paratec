import { headers } from "next/headers";
import { NextResponse } from "next/server";

// Lê a identidade injetada pelo Authentik (forward-auth) nos headers da requisição.
export async function GET() {
  const h = headers();
  const username = h.get("x-authentik-username");
  return NextResponse.json({
    username,
    name: h.get("x-authentik-name") || username,
    email: h.get("x-authentik-email"),
  });
}

export const dynamic = "force-dynamic";
