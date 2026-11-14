"use client";

import { useState, type FormEvent } from "react";
import { useAvisos } from "@/components/ui/Avisos";
import { Boton } from "@/components/ui/Boton";
import { AdminPestanas } from "@/components/panel/AdminPestanas";
import { CampoClave } from "@/components/panel/CampoClave";
import { UsuarioGestionHoja } from "@/components/panel/UsuarioGestionHoja";
import { UsuarioNuevoHoja } from "@/components/panel/UsuarioNuevoHoja";
import { api } from "@/lib/api";
import { motivoClaveDebil } from "@/lib/clave";
import { fechaHora } from "@/lib/format";
import { mensajeDe, useCargar } from "@/lib/hooks";
import type { UsuarioAdmin } from "@/lib/types";

export default function Administracion() {
  const { mostrar } = useAvisos();
  const usuarios = useCargar(api.usuarios.listar);
  const [nuevo, setNuevo] = useState(false);
  const [gestion, setGestion] = useState<UsuarioAdmin | null>(null);

  const [actual, setActual] = useState("");
  const [nueva, setNueva] = useState("");
  const [repetir, setRepetir] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [cambiando, setCambiando] = useState(false);

  async function cambiar(e: FormEvent) {
    e.preventDefault();
    const debil = motivoClaveDebil(nueva);
    if (debil) return setError(debil);
    if (nueva !== repetir) return setError("Las dos contraseñas nuevas no coinciden.");
    setCambiando(true);
    setError(null);
    try {
      await api.usuarios.cambiarMia(actual, nueva);
      mostrar("Contraseña cambiada. Se cerraron tus sesiones en otros equipos.");
      setActual("");
      setNueva("");
      setRepetir("");
    } catch (err) {
      setError(mensajeDe(err));
    } finally {
      setCambiando(false);
    }
  }

  const lista = usuarios.datos ?? [];
  const gestionActual = gestion ? (lista.find((u) => u.id === gestion.id) ?? gestion) : null;

  return (
    <>
      <div className="pagina-cab">
        <h1>Administración</h1>
        <p className="lead">Quién puede entrar al panel y cómo cuidar tu contraseña.</p>
        <AdminPestanas />
      </div>

      <div className="dos-paneles dos-paneles--iguales">
      <section className="seccion" aria-labelledby="t-cuenta">
        <h2 id="t-cuenta">Mi cuenta</h2>
        <form className="tarjeta bloque-clave" onSubmit={cambiar}>
          <h3>Cambiar mi contraseña</h3>
          {error && <p className="alerta" role="alert">{error}</p>}
          <CampoClave etiqueta="Contraseña actual" valor={actual} onCambio={setActual} autoComplete="current-password" />
          <CampoClave etiqueta="Contraseña nueva" valor={nueva} onCambio={setNueva} ayuda="Mínimo 10 caracteres, no solo números." />
          <CampoClave etiqueta="Repite la contraseña nueva" valor={repetir} onCambio={setRepetir} />
          <p className="muted" style={{ fontSize: "var(--text-sm)" }}>Al cambiarla se cierran tus sesiones en otros equipos; en este sigues dentro.</p>
          <Boton variante="accent" type="submit" cargando={cambiando} disabled={!actual || !nueva || !repetir}>Cambiar contraseña</Boton>
        </form>
      </section>

      <section className="seccion" aria-labelledby="t-usuarios">
        <h2 id="t-usuarios">Usuarios</h2>
        <div><Boton variante="accent" onClick={() => setNuevo(true)}>Nuevo usuario</Boton></div>
        {usuarios.error && <p className="alerta" role="alert">{usuarios.error}</p>}
        {usuarios.cargando ? (
          <p className="muted" role="status">Cargando…</p>
        ) : (
          <div className="lista">
            {lista.map((u) => (
              <button key={u.id} type="button" className="fila fila--sin-foto" onClick={() => setGestion(u)} style={!u.activo ? { opacity: 0.65 } : undefined}>
                <span className="fila__titulo">
                  <span className="fila__nombre">{u.nombre || u.email}</span>
                  <span className="fila__meta">{u.email} · desde {fechaHora(u.creado_en)}</span>
                </span>
                <span className="fila__fin">
                  {u.es_yo && <span className="etiqueta etiqueta--ok">Tú</span>}
                  {!u.activo && <span className="etiqueta etiqueta--tenue">Desactivado</span>}
                  <span className="fila__meta">Gestionar</span>
                </span>
              </button>
            ))}
          </div>
        )}
        <p className="muted" style={{ fontSize: "var(--text-sm)" }}>Por ahora todos los usuarios tienen el mismo acceso (sin roles).</p>
      </section>
      </div>

      <UsuarioNuevoHoja abierta={nuevo} onCerrar={() => setNuevo(false)} onCreado={() => void usuarios.recargar()} />
      <UsuarioGestionHoja usuario={gestionActual} onCerrar={() => setGestion(null)} onCambio={() => void usuarios.recargar()} />
    </>
  );
}
