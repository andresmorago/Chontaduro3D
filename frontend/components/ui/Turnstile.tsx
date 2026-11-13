"use client";

import { useEffect, useRef, useState } from "react";

// Cloudflare Turnstile (el «reCAPTCHA» de Cloudflare). El widget solo entrega un token de un solo uso;
// quien lo valida es el servidor. Sin `sitekey` (apagado en el servidor) no se muestra nada.

interface ApiTurnstile {
  render: (el: HTMLElement, opciones: Record<string, unknown>) => string;
  remove: (id: string) => void;
}
declare global {
  interface Window {
    turnstile?: ApiTurnstile;
  }
}

const SRC = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
let cargando: Promise<void> | null = null;

function cargarScript(): Promise<void> {
  cargando ??= new Promise<void>((ok, fallo) => {
    if (window.turnstile) return ok();
    const s = document.createElement("script");
    s.src = SRC;
    s.async = true;
    s.defer = true;
    s.onload = () => ok();
    s.onerror = () => {
      cargando = null; // permite reintentar más tarde
      fallo(new Error("No cargó Turnstile"));
    };
    document.head.appendChild(s);
  });
  return cargando;
}

interface Props {
  sitekey: string;
  /** Recibe el token cuando la persona pasa la verificación, o null si venció o falló. */
  onToken: (token: string | null) => void;
  /** Cambiar este número reinicia el widget (el token es de un solo uso). */
  reinicio?: number;
}

export function Turnstile({ sitekey, onToken, reinicio = 0 }: Props) {
  const caja = useRef<HTMLDivElement>(null);
  const alToken = useRef(onToken);
  alToken.current = onToken;
  const [fallo, setFallo] = useState(false);

  useEffect(() => {
    if (!sitekey) return;
    let vivo = true;
    let id: string | null = null;
    setFallo(false);
    cargarScript()
      .then(() => {
        if (!vivo || !caja.current || !window.turnstile) return;
        id = window.turnstile.render(caja.current, {
          sitekey,
          language: "es",
          theme: "light",
          // Invisible salvo que haga falta interacción: la mayoría de la gente nunca ve el widget.
          appearance: "interaction-only",
          callback: (t: string) => alToken.current(t),
          "expired-callback": () => alToken.current(null),
          "error-callback": () => {
            alToken.current(null);
            setFallo(true);
          },
        });
      })
      .catch(() => {
        alToken.current(null);
        if (vivo) setFallo(true);
      });
    return () => {
      vivo = false;
      if (id && window.turnstile) window.turnstile.remove(id);
    };
  }, [sitekey, reinicio]);

  if (!sitekey) return null;
  return (
    <div className="turnstile">
      <div ref={caja} />
      {fallo && (
        <p className="field__error" role="alert">
          No se pudo cargar la verificación. Revisa tu conexión o desactiva el bloqueador de anuncios y recarga la página.
        </p>
      )}
    </div>
  );
}
