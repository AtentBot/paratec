/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Imagem Docker enxuta (server.js + assets mínimos).
  output: "standalone",
  // Imagens do catálogo vêm do WordPress da Paratec.
  images: {
    remotePatterns: [{ protocol: "https", hostname: "paratec.com.br" }],
  },
  // Proxy same-origin: o navegador chama /agent/*, o servidor Next encaminha
  // para o agent-service interno (mantém o agente privado e funciona atrás do
  // login/Authentik, sem CORS nem subdomínio de API público).
  async rewrites() {
    const target = process.env.AGENT_INTERNAL_URL || "http://paratec-agent:8000";
    return [
      { source: "/agent/:path*", destination: `${target}/:path*` },
      // API pública de integrações (chave por tenant): https://<dominio>/api/v1/...
      { source: "/api/v1/:path*", destination: `${target}/v1/:path*` },
    ];
  },
};

export default nextConfig;
