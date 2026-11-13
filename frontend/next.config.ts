import type { NextConfig } from "next";

// Un solo origen: el navegador habla con `/api/*` y Next lo reenvía al backend
// por la red interna de Compose. Sin CORS, sin `api.<dominio>`, y las cookies de
// sesión son del mismo origen. (La CSP con nonce vive en middleware.ts.)
const API_INTERNA = process.env.API_INTERNAL_URL ?? "http://backend:8000";

const nextConfig: NextConfig = {
  // El contenedor monta el código por volumen; se sondea por si los eventos no cruzan.
  webpack: (config) => {
    config.watchOptions = { poll: 1000, aggregateTimeout: 300 };
    return config;
  },
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_INTERNA}/api/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "Permissions-Policy", value: "geolocation=(), camera=(), microphone=()" },
          { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
          { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
        ],
      },
    ];
  },
};

export default nextConfig;
