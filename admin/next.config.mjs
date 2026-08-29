/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Imagem Docker enxuta (server.js + assets mínimos).
  output: "standalone",
  // Imagens do catálogo vêm do WordPress da Paratec.
  images: {
    remotePatterns: [{ protocol: "https", hostname: "paratec.com.br" }],
  },
};

export default nextConfig;
