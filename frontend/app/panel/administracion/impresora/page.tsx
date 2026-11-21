"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AdminPestanas } from "@/components/panel/AdminPestanas";
import { ControlesTermicos } from "@/components/panel/ControlesTermicos";
import { SpoolmanSeccion } from "@/components/panel/SpoolmanSeccion";
import { useAvisos } from "@/components/ui/Avisos";
import { Boton } from "@/components/ui/Boton";
import { api } from "@/lib/api";
import { hace } from "@/lib/format";
import { ETIQUETA_ESTADO, VELOCIDADES, grados, restante } from "@/lib/impresora";
import { mensajeDe, useCargar } from "@/lib/hooks";
import type { BandejaAms, ComandoImpresora } from "@/lib/types";

function Bandeja({ b, titulo }: { b: BandejaAms; titulo: string }) {
  return (
    <li className={`bandeja${b.en_uso ? " bandeja--uso" : ""}`}>
      <span className="bandeja__color" style={b.color ? { background: b.color } : undefined} aria-hidden="true" />
      <span className="bandeja__texto">
        <span className="bandeja__titulo">
          <strong>{titulo}</strong>
          {b.en_uso && <span className="etiqueta etiqueta--ok">En uso</span>}
        </span>
        <span className="muted">{b.vacia ? "Vacía" : `${b.marca ?? b.tipo ?? "Filamento"} · ${b.restante != null ? `${b.restante} %` : "sin medir"}`}</span>
      </span>
    </li>
  );
}

export default function Impresora() {
  const { mostrar } = useAvisos();
  const estado = useCargar(api.impresora.ver);
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [confirmarCancelar, setConfirmarCancelar] = useState(false);

  // El estado se refresca solo mientras la pestaña está a la vista.
  useEffect(() => {
    const id = setInterval(() => {
      if (!document.hidden) void estado.recargar();
    }, 3000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const info = estado.datos;
  const d = info?.datos ?? null;
  const maquina = d?.estado ?? "desconocido";
  const conectada = Boolean(info?.servicio_activo && info.conectada);
  const imprimiendo = maquina === "imprimiendo";
  const pausada = maquina === "pausada";
  const activa = imprimiendo || pausada || maquina === "preparando";

  async function ordenar(comando: ComandoImpresora, valor?: string, texto?: string) {
    setOcupado(comando);
    try {
      const orden = await api.impresora.ordenar(comando, valor);
      // La orden la envía el servicio: se espera su resultado unos segundos.
      let r = orden;
      for (let i = 0; i < 10 && r.estado === "pendiente"; i++) {
        await new Promise((ok) => setTimeout(ok, 700));
        r = await api.impresora.orden(orden.id);
      }
      if (r.estado === "enviado") mostrar(texto ?? "Orden enviada a la impresora.");
      else if (r.estado === "pendiente") mostrar("La orden sigue en cola; revisa en unos segundos.", { tipo: "error" });
      else mostrar(r.detalle ?? "La impresora no recibió la orden.", { tipo: "error" });
    } catch (e) {
      mostrar(mensajeDe(e), { tipo: "error" });
    } finally {
      setOcupado(null);
      setConfirmarCancelar(false);
      await estado.recargar();
    }
  }

  return (
    <>
      <div className="pagina-cab">
        <h1>Administración</h1>
        <p className="lead">Datos y controles de la impresora 3D.</p>
        <AdminPestanas />
      </div>

      {estado.error && <p className="alerta" role="alert">{estado.error}</p>}
      {!estado.cargando && info && !info.servicio_activo && (
        <p className="alerta" role="alert">El servicio de la impresora no está respondiendo, así que no hay datos ni controles. Revisa que esté corriendo (<code>make prod-impresora-logs</code>).</p>
      )}
      {!estado.cargando && info?.servicio_activo && !info.conectada && (
        <p className="alerta" role="alert">No se alcanza la impresora. Revisa que esté encendida y conectada a la red, o que la IP y el código de acceso sean los correctos en <Link href="/panel/administracion/conexion">Conexión</Link>; mientras tanto no se pueden enviar controles.</p>
      )}
      {d && d.error !== 0 && <p className="alerta" role="alert">La impresora reporta un error (código {d.error}). Míralo en su pantalla.</p>}
      {d && d.error === 0 && d.alertas > 0 && <p className="alerta" role="status">La impresora tiene {d.alertas === 1 ? "1 aviso" : `${d.alertas} avisos`} en su pantalla.</p>}

      <div className="dos-paneles dos-paneles--iguales">
      <section className="seccion" aria-labelledby="t-estado">
        <h2 id="t-estado">Estado</h2>
        {estado.cargando ? (
          <p className="muted" role="status">Cargando…</p>
        ) : (
          <div className="tarjeta impresora-estado">
            <div className="impresora-estado__cab">
              <span className={`etiqueta ${imprimiendo ? "etiqueta--ok" : pausada ? "etiqueta--aviso" : "etiqueta--tenue"}`}>{conectada ? ETIQUETA_ESTADO[maquina] : "Sin conexión"}</span>
              {info?.actualizado_en && <span className="muted">Actualizado {hace(info.actualizado_en)}</span>}
            </div>
            {d && conectada && (
              <>
                {d.trabajo && activa && <p className="impresora-estado__trabajo">{d.trabajo}</p>}
                {activa && (
                  <>
                    <div className="progreso" role="progressbar" aria-label="Progreso de la impresión" aria-valuemin={0} aria-valuemax={100} aria-valuenow={d.progreso ?? 0}>
                      <span style={{ width: `${d.progreso ?? 0}%` }} />
                    </div>
                    <p className="muted num">
                      {d.progreso ?? 0} %{d.capa != null && d.capas ? ` · capa ${d.capa} de ${d.capas}` : ""} · faltan {restante(d.restante_min)}
                    </p>
                  </>
                )}
                <dl className="impresora-datos">
                  <div><dt>Boquilla{d.boquilla_mm ? ` (${d.boquilla_mm} mm)` : ""}</dt><dd className="num">{grados(d.boquilla)}{d.boquilla_objetivo ? ` → ${grados(d.boquilla_objetivo)}` : ""}</dd></div>
                  <div><dt>Cama</dt><dd className="num">{grados(d.cama)}{d.cama_objetivo ? ` → ${grados(d.cama_objetivo)}` : ""}</dd></div>
                  <div><dt>Wi-Fi</dt><dd className="num">{d.wifi ?? "—"}</dd></div>
                  <div><dt>Ventilador pieza</dt><dd className="num">{d.ventilador_pieza != null ? `${d.ventilador_pieza} %` : "—"}</dd></div>
                  <div><dt>Ventilador auxiliar</dt><dd className="num">{d.ventilador_aux != null ? `${d.ventilador_aux} %` : "—"}</dd></div>
                  <div><dt>Velocidad</dt><dd>{VELOCIDADES.find((v) => v.valor === String(d.velocidad))?.etiqueta ?? "—"}</dd></div>
                </dl>
              </>
            )}
          </div>
        )}
      </section>

      <section className="seccion" aria-labelledby="t-controles">
        <h2 id="t-controles">Controles</h2>
        <div className="tarjeta impresora-controles">
          <div className="impresora-controles__fila">
            <Boton variante="secondary" disabled={!conectada || !imprimiendo} cargando={ocupado === "pausar"} onClick={() => void ordenar("pausar", undefined, "Impresión en pausa.")}>Pausar</Boton>
            <Boton variante="accent" disabled={!conectada || !pausada} cargando={ocupado === "reanudar"} onClick={() => void ordenar("reanudar", undefined, "Impresión reanudada.")}>Reanudar</Boton>
            <Boton variante="secondary" disabled={!conectada} cargando={ocupado === "luz"} onClick={() => void ordenar("luz", d?.luz === "on" ? "off" : "on", d?.luz === "on" ? "Luz apagada." : "Luz encendida.")}>
              {d?.luz === "on" ? "Apagar luz" : "Encender luz"}
            </Boton>
          </div>

          <ControlesTermicos datos={d} conectada={conectada} ocupado={ocupado} ordenar={(c, v, t) => ordenar(c, v, t)} />

          <div className="field">
            <span className="field__label" id="etq-vel">Velocidad de impresión</span>
            <div className="segmentado segmentado--rejilla" role="group" aria-labelledby="etq-vel">
              {VELOCIDADES.map((v) => (
                <button key={v.valor} type="button" className="segmentado__op" aria-pressed={String(d?.velocidad) === v.valor} disabled={!conectada || !(imprimiendo || pausada) || ocupado === "velocidad"} onClick={() => void ordenar("velocidad", v.valor, `Velocidad: ${v.etiqueta}.`)}>
                  {v.etiqueta}
                </button>
              ))}
            </div>
            {!(imprimiendo || pausada) && <p className="field__hint">La velocidad se cambia mientras hay una impresión en curso.</p>}
          </div>

          {activa && (
            <div className="impresora-cancelar">
              {confirmarCancelar ? (
                <>
                  <p><strong>¿Cancelar «{d?.trabajo ?? "esta impresión"}»?</strong> No se puede reanudar ni deshacer.</p>
                  <div className="impresora-controles__fila">
                    <Boton variante="danger" disabled={!conectada} cargando={ocupado === "cancelar"} onClick={() => void ordenar("cancelar", undefined, "Impresión cancelada.")}>Sí, cancelar</Boton>
                    <Boton variante="secondary" onClick={() => setConfirmarCancelar(false)}>No, seguir</Boton>
                  </div>
                </>
              ) : (
                <Boton variante="danger" pequeno disabled={!conectada} onClick={() => setConfirmarCancelar(true)}>Cancelar impresión…</Boton>
              )}
            </div>
          )}
        </div>
      </section>

      <SpoolmanSeccion
        impresora={{ estado: maquina, conectada, enExtrusor: d?.en_extrusor ?? null }}
        respaldo={
          d && conectada && (d.ams.length > 0 || d.externa) ? (
            <ul className="bandejas">
              {d.ams.map((b, i) => <Bandeja key={b.id} b={b} titulo={`Ranura ${i + 1}`} />)}
              {d.externa && <Bandeja b={d.externa} titulo="Externa" />}
            </ul>
          ) : (
            <p className="muted">Sin datos de filamento por ahora.</p>
          )
        }
      />

      <section className="seccion" aria-labelledby="t-trabajos">
        <h2 id="t-trabajos">Trabajos</h2>
        <div className="tarjeta bloque-clave">
          <p>
            {info && info.trabajos_pendientes > 0
              ? `Hay ${info.trabajos_pendientes === 1 ? "1 trabajo" : `${info.trabajos_pendientes} trabajos`} de la impresora por revisar.`
              : "No hay trabajos por revisar."}{" "}
            Elige cuáles son producciones para traer sus gramos y tiempos.
          </p>
          {info && (
            <p className={info.nube.estado === "requiere_login" || info.nube.estado === "error" ? "alerta" : "muted"} role={info.nube.estado === "requiere_login" || info.nube.estado === "error" ? "alert" : undefined}>
              <strong>Historial de Bambu Cloud:</strong>{" "}
              {info.nube.estado === "ok" && `sincronizado ${info.nube.sincronizada_en ? hace(info.nube.sincronizada_en) : ""}. Trae los trabajos de los últimos días.`}
              {info.nube.estado === "requiere_login" && <>el acceso venció. Vuelve a vincular tu cuenta en <Link href="/panel/administracion/conexion">Conexión</Link>.</>}
              {info.nube.estado === "error" && `no se pudo consultar (${info.nube.detalle ?? "error"}). Se reintenta solo.`}
              {(info.nube.estado === "sin_configurar" || info.nube.estado === null) && <>sin vincular. Vincula tu cuenta en <Link href="/panel/administracion/conexion">Conexión</Link> para traer los trabajos previos de Studio y Handy.</>}
            </p>
          )}
          <div><Link className="btn btn--accent" href="/panel/produccion">Ir a Producción</Link></div>
        </div>
      </section>
      </div>
    </>
  );
}
