// Worker de Cloudflare: da una dirección ESTABLE (*.workers.dev) a la app, que por dentro
// vive detrás de un quick tunnel (*.trycloudflare.com) cuya URL cambia al reiniciarse.
// `urlsync` vuelve a subir este Worker con el ORIGIN vigente cada vez que la URL cambia.
//
// Variables (las pone urlsync al subir el Worker):
//   ORIGIN        https://<algo>.trycloudflare.com
//   PROXY_SECRET  secreto compartido con la app (cabecera x-proxy-secret)

export default {
  async fetch(request, env) {
    if (!env.ORIGIN) return new Response("Servicio no disponible.", { status: 503 });

    const entrada = new URL(request.url);
    const destino = new URL(entrada.pathname + entrada.search, env.ORIGIN);

    const cabeceras = new Headers(request.headers);
    // Lo que manda el cliente nunca se cree: estas cabeceras las fija el Worker.
    for (const h of ["x-proxy-secret", "x-real-client-ip", "x-forwarded-host", "x-forwarded-proto", "x-forwarded-for"]) {
      cabeceras.delete(h);
    }
    cabeceras.set("x-forwarded-host", entrada.host);
    cabeceras.set("x-forwarded-proto", "https");
    const ip = request.headers.get("cf-connecting-ip");
    if (ip) cabeceras.set("x-real-client-ip", ip);
    if (env.PROXY_SECRET) cabeceras.set("x-proxy-secret", env.PROXY_SECRET);

    let respuesta;
    try {
      respuesta = await fetch(new Request(destino, {
        method: request.method,
        headers: cabeceras,
        body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
        redirect: "manual",
      }));
    } catch {
      return new Response("El servicio no responde en este momento. Inténtalo de nuevo en unos segundos.", {
        status: 502,
        headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" },
      });
    }

    // Las redirecciones que apuntan al túnel se reescriben a la dirección pública.
    const salida = new Response(respuesta.body, respuesta);
    const ubicacion = salida.headers.get("location");
    if (ubicacion?.startsWith(env.ORIGIN)) {
      salida.headers.set("location", entrada.origin + ubicacion.slice(env.ORIGIN.length));
    }
    return salida;
  },
};
