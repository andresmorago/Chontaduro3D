"use client";

import { useEffect, useState } from "react";
import { useAvisos } from "@/components/ui/Avisos";
import { Boton } from "@/components/ui/Boton";
import { Entrada } from "@/components/ui/Campo";
import { Hoja } from "@/components/ui/Hoja";
import { CampoClave } from "@/components/panel/CampoClave";
import { api } from "@/lib/api";
import { motivoClaveDebil } from "@/lib/clave";
import { mensajeDe } from "@/lib/hooks";
import type { UsuarioAdmin } from "@/lib/types";

interface Props {
  usuario: UsuarioAdmin | null;
  onCerrar: () => void;
  onCambio: () => void;
}

/** Gestionar a una persona: nombre, restablecer su contraseña y activar/desactivar su acceso. */
export function UsuarioGestionHoja({ usuario, onCerrar, onCambio }: Props) {
  const { mostrar } = useAvisos();
  const [nombre, setNombre] = useState("");
  const [clave, setClave] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [confirmar, setConfirmar] = useState(false);

  useEffect(() => {
    setNombre(usuario?.nombre ?? "");
    setClave("");
    setError(null);
    setConfirmar(false);
  }, [usuario]);

  async function accion(clave_: string, fn: () => Promise<void>) {
    setOcupado(clave_);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(mensajeDe(e));
    } finally {
      setOcupado(null);
    }
  }

  if (!usuario) return <Hoja abierta={false} onCerrar={onCerrar} titulo="">{null}</Hoja>;
  const u = usuario;

  return (
    <Hoja abierta onCerrar={onCerrar} titulo={u.nombre || u.email} descripcion={`${u.email}${u.es_yo ? " · eres tú" : ""}${u.activo ? "" : " · desactivado"}`}>
      {error && <p className="alerta" role="alert">{error}</p>}

      <section style={{ display: "grid", gap: "var(--space-sm)" }}>
        <h3>Nombre</h3>
        <Entrada etiqueta="Nombre" value={nombre} maxLength={80} onChange={(e) => setNombre(e.target.value)} />
        <Boton variante="secondary" pequeno cargando={ocupado === "nombre"} disabled={!nombre.trim() || nombre.trim() === (u.nombre ?? "")} onClick={() => accion("nombre", async () => { await api.usuarios.actualizar(u.id, { nombre: nombre.trim() }); mostrar("Nombre actualizado."); onCambio(); })}>
          Guardar nombre
        </Boton>
      </section>

      {u.es_yo ? (
        <p className="muted">Tu contraseña la cambias en <strong>Mi cuenta</strong>, arriba en esta misma página.</p>
      ) : (
        <>
          <section style={{ display: "grid", gap: "var(--space-sm)" }}>
            <h3>Restablecer contraseña</h3>
            <p className="muted">Cierra todas sus sesiones abiertas y le da una contraseña nueva.</p>
            <CampoClave etiqueta="Contraseña nueva" valor={clave} onCambio={setClave} generar />
            <Boton variante="accent" pequeno cargando={ocupado === "clave"} disabled={!clave} onClick={() => {
              const debil = motivoClaveDebil(clave);
              if (debil) return setError(debil);
              void accion("clave", async () => { await api.usuarios.restablecer(u.id, clave); mostrar("Contraseña restablecida. Sus sesiones se cerraron."); setClave(""); onCambio(); });
            }}>
              Restablecer contraseña
            </Boton>
          </section>

          <section style={{ display: "grid", gap: "var(--space-sm)" }}>
            <h3>Acceso</h3>
            {u.activo ? (
              confirmar ? (
                <div style={{ display: "flex", gap: "var(--space-xs)", flexWrap: "wrap" }}>
                  <Boton variante="danger" pequeno cargando={ocupado === "estado"} onClick={() => accion("estado", async () => { await api.usuarios.actualizar(u.id, { activo: false }); mostrar("Usuario desactivado: ya no puede entrar."); onCambio(); onCerrar(); })}>Sí, desactivar</Boton>
                  <Boton variante="ghost" pequeno onClick={() => setConfirmar(false)}>No</Boton>
                </div>
              ) : (
                <>
                  <p className="muted">Desactivar corta su acceso de inmediato; sus registros se conservan.</p>
                  <Boton variante="danger" pequeno onClick={() => setConfirmar(true)}>Desactivar usuario</Boton>
                </>
              )
            ) : (
              <Boton variante="secondary" pequeno cargando={ocupado === "estado"} onClick={() => accion("estado", async () => { await api.usuarios.actualizar(u.id, { activo: true }); mostrar("Usuario activado."); onCambio(); onCerrar(); })}>Activar usuario</Boton>
            )}
          </section>
        </>
      )}
    </Hoja>
  );
}
