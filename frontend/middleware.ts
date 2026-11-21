import { NextResponse, type NextRequest } from "next/server";

// 1) Si hay PROXY_SHARED_SECRET, solo se sirve lo que traiga el secreto que añade el
//    Worker de Cloudflare: la URL directa del túnel deja de servir (403).
// 2) /panel exige una cookie de sesión (la validación real la hace la API).
// 3) CSP con nonce por petición: los scripts en línea de Next llevan el nonce y no
//    hace falta 'unsafe-inline' para scripts.

const SECRETO = process.env.PROXY_SHARED_SECRET ?? "";
const DESARROLLO = process.env.NODE_ENV !== "production";
// Un poco más que MAX_UPLOAD_MB (12 MB) del backend: el multipart añade unos KB.
const TOPE_CUERPO = 14 * 1024 * 1024;

function iguales(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

// Detrás del Worker, `req.url` trae el host del túnel; el público es el que el Worker
// manda en x-forwarded-host (solo se cree si la petición ya pasó la verificación del secreto).
function origenPublico(req: NextRequest): string {
  const host = SECRETO ? req.headers.get("x-forwarded-host") : null;
  if (host && /^[a-z0-9.-]+(:\d+)?$/i.test(host)) {
    return `${req.headers.get("x-forwarded-proto") === "http" ? "http" : "https"}://${host}`;
  }
  return req.nextUrl.origin;
}

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (pathname === "/healthz") return NextResponse.next();

  // En producción sin secreto compartido la URL directa del túnel serviría la app: falla cerrado.
  if (!SECRETO && !DESARROLLO) {
    return new NextResponse("Servicio mal configurado.", { status: 503 });
  }
  if (SECRETO && !iguales(req.headers.get("x-proxy-secret") ?? "", SECRETO)) {
    return new NextResponse("Acceso no permitido.", { status: 403 });
  }

  // Tope temprano al cuerpo (la subida de fotos admite 5 MB + multipart): evita proxificar al backend
  // una subida enorme que el backend cortaría de todos modos, y devuelve un 413 limpio.
  const largo = Number(req.headers.get("content-length") ?? "0");
  if (req.method !== "GET" && req.method !== "HEAD" && largo > TOPE_CUERPO) {
    return new NextResponse("El cuerpo de la petición es demasiado grande.", { status: 413 });
  }

  if (pathname.startsWith("/panel") && !req.cookies.has("mi_access") && !req.cookies.has("mi_refresh")) {
    return NextResponse.redirect(new URL("/entrar", origenPublico(req)));
  }

  const nonce = btoa(crypto.randomUUID());
  const csp = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic' https://challenges.cloudflare.com${DESARROLLO ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    "connect-src 'self'",
    "frame-src https://challenges.cloudflare.com",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "object-src 'none'",
    "form-action 'self'",
  ].join("; ");

  const cabeceras = new Headers(req.headers);
  cabeceras.set("x-nonce", nonce);
  cabeceras.set("Content-Security-Policy", csp);
  const res = NextResponse.next({ request: { headers: cabeceras } });
  res.headers.set("Content-Security-Policy", csp);
  return res;
}

export const config = {
  matcher: [{ source: "/((?!_next/static|_next/image|favicon.ico|icon.svg).*)" }],
};
