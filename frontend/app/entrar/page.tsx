"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { Boton } from "@/components/ui/Boton";
import { Entrada } from "@/components/ui/Campo";
import { Turnstile } from "@/components/ui/Turnstile";
import { ErrorApi, api } from "@/lib/api";

export default function Entrar() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [sitekey, setSitekey] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [reinicio, setReinicio] = useState(0);

  useEffect(() => {
    api.publico.config().then((c) => setSitekey(c.turnstile_sitekey)).catch(() => {});
  }, []);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    if (sitekey && !token) {
      setError("Completa la verificación para continuar.");
      return;
    }
    setEnviando(true);
    setError(null);
    try {
      await api.auth.entrar(email.trim(), password, token ?? "");
      window.location.assign("/panel");
    } catch (err) {
      setError(err instanceof ErrorApi ? err.message : "No se pudo entrar.");
      setEnviando(false);
      setToken(null); // el token es de un solo uso
      setReinicio((n) => n + 1);
    }
  }

  return (
    <main id="contenido" className="entrar">
      <div className="entrar__tarjeta">
        <div>
          <p className="code muted">Acceso del negocio</p>
          <h1>Entrar</h1>
        </div>
        <form onSubmit={enviar}>
          {error && (
            <p className="alerta" role="alert">
              {error}
            </p>
          )}
          <Entrada etiqueta="Correo" type="email" name="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
          <Entrada etiqueta="Contraseña" type="password" name="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          <Turnstile sitekey={sitekey} onToken={setToken} reinicio={reinicio} />
          <Boton variante="primary" bloque type="submit" cargando={enviando} disabled={Boolean(sitekey) && !token}>
            Entrar
          </Boton>
        </form>
        <Link href="/">← Volver al catálogo</Link>
      </div>
    </main>
  );
}
