"use client";

import { useEffect } from "react";
import { AdminPestanas } from "@/components/panel/AdminPestanas";
import { ConexionImpresora } from "@/components/panel/ConexionImpresora";
import { ConexionNube } from "@/components/panel/ConexionNube";
import { api } from "@/lib/api";
import { useCargar } from "@/lib/hooks";

export default function Conexion() {
  const conexion = useCargar(api.impresora.conexion.ver);

  // El estado se refresca solo mientras la pestaña está a la vista.
  useEffect(() => {
    const id = setInterval(() => {
      if (!document.hidden) void conexion.recargar();
    }, 4000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const c = conexion.datos;
  return (
    <>
      <div className="pagina-cab">
        <h1>Administración</h1>
        <p className="lead">Conecta la impresora y tu cuenta de Bambu Lab desde aquí.</p>
        <AdminPestanas />
      </div>

      {conexion.error && <p className="alerta" role="alert">{conexion.error}</p>}
      {conexion.cargando && <p className="muted" role="status">Cargando…</p>}
      {c && (
        <div className="dos-paneles dos-paneles--iguales">
          <section className="seccion" aria-labelledby="t-impresora">
            <h2 id="t-impresora">Impresora</h2>
            <ConexionImpresora conexion={c} recargar={async () => { await conexion.recargar(); }} />
          </section>
          <section className="seccion" aria-labelledby="t-nube">
            <h2 id="t-nube">Historial de Bambu Cloud</h2>
            <ConexionNube conexion={c} recargar={async () => { await conexion.recargar(); }} />
          </section>
        </div>
      )}
    </>
  );
}
