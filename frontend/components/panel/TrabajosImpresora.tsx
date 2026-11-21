"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAvisos } from "@/components/ui/Avisos";
import { Boton } from "@/components/ui/Boton";
import { Segmentado } from "@/components/ui/Segmentado";
import { api } from "@/lib/api";
import { fechaCorta, fechaHora, hora } from "@/lib/format";
import { mensajeDe, useCargar } from "@/lib/hooks";
import { resumenConsumo } from "@/lib/impresora";
import { gramos, tiempoLargo } from "@/lib/produccion";
import type { TrabajoImpresora } from "@/lib/types";

interface Props {
  /** Trabajo cuyos datos están cargados en el formulario del lote. */
  usandoId: string | null;
  onUsar: (t: TrabajoImpresora) => void;
  /** Cambia cuando hay que recargar (p. ej. tras guardar el lote). */
  refrescar: number;
}

function Muestras({ t }: { t: TrabajoImpresora }) {
  const colores = t.filamentos.filter((f) => f.color);
  if (colores.length === 0) return null;
  return (
    <span className="muestras" aria-label={`Filamentos: ${t.filamentos.map((f) => `${f.tipo} ${gramos(f.gramos)}`).join(", ")}`}>
      {colores.map((f, i) => <span key={i} className="muestras__color" style={{ background: f.color ?? undefined }} />)}
    </span>
  );
}

/** Qué pasó con el filamento del trabajo en Spoolman; si falta una decisión, lleva a resolverla. */
function EstadoSpoolman({ t }: { t: TrabajoImpresora }) {
  const r = resumenConsumo(t.consumos);
  if (!r) return null;
  const clase = r.clase === "ok" ? "etiqueta--ok" : r.clase === "aviso" ? "etiqueta--aviso" : "etiqueta--tenue";
  return r.clase === "aviso" ? (
    <Link className={`etiqueta ${clase}`} href="/panel/administracion/impresora#spoolman">{r.texto}</Link>
  ) : (
    <span className={`etiqueta ${clase}`}>{r.texto}</span>
  );
}

/** Trabajos que la impresora ya hizo. La persona elige cuáles son producciones (los trae al formulario
 *  del lote con sus gramos y tiempo) y cuáles no (se ignoran). */
export function TrabajosImpresora({ usandoId, onUsar, refrescar }: Props) {
  const { mostrar } = useAvisos();
  const [vista, setVista] = useState<"pendiente" | "importado" | "ignorado" | "todos">("pendiente");
  const lista = useCargar(() => api.impresora.trabajos(vista, vista === "todos" ? 200 : 50));
  const [ocupado, setOcupado] = useState<string | null>(null);

  useEffect(() => {
    void lista.recargar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vista, refrescar]);

  // Un trabajo nuevo aparece solo, sin recargar la página.
  useEffect(() => {
    const id = setInterval(() => {
      if (!document.hidden) void lista.recargar();
    }, 20000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vista]);

  async function cambiar(t: TrabajoImpresora, accion: "ignorar" | "restaurar") {
    setOcupado(t.id);
    try {
      await api.impresora[accion](t.id);
      mostrar(accion === "ignorar" ? "Trabajo ignorado. Lo encuentras en «Ignorados»." : "Trabajo devuelto a la lista.");
      await lista.recargar();
    } catch (e) {
      mostrar(mensajeDe(e), { tipo: "error" });
    } finally {
      setOcupado(null);
    }
  }

  const trabajos = lista.datos ?? [];
  return (
    <section className="seccion seccion--trabajos" aria-labelledby="t-trabajos-imp">
      <h2 id="t-trabajos-imp">Trabajos de la impresora</h2>
      <p className="muted">Lo que la impresora fue haciendo. Importa los que son producción para traer sus gramos y su tiempo; ignora el resto (pruebas, fallos).</p>
      <Segmentado rejilla etiqueta="Qué trabajos ver" valor={vista} opciones={[{ valor: "pendiente", etiqueta: "Por revisar" }, { valor: "importado", etiqueta: "Importados" }, { valor: "ignorado", etiqueta: "Ignorados" }, { valor: "todos", etiqueta: "Todos" }]} onCambio={setVista} />
      {lista.error && <p className="alerta" role="alert">{lista.error}</p>}
      {lista.cargando ? (
        <p className="muted" role="status">Cargando…</p>
      ) : trabajos.length === 0 ? (
        <div className="vacio">
          <p>{vista === "pendiente" ? "No hay trabajos por revisar. Cuando la impresora termine uno, aparece aquí." : vista === "importado" ? "Todavía no has importado trabajos como producción." : vista === "ignorado" ? "No hay trabajos ignorados." : "La impresora aún no ha registrado trabajos."}</p>
        </div>
      ) : (
        <div className="tabla-caja">
          <table className="tabla-datos tabla-trab">
            <caption className="visually-hidden">Trabajos de la impresora</caption>
            <thead>
              <tr>
                <th scope="col">Trabajo</th>
                <th scope="col" className="c-num c-mov-no">Tiempo</th>
                <th scope="col" className="c-num c-mov-no">Gramos</th>
                <th scope="col" className="c-mov-no">Filamentos</th>
                <th scope="col">Estado</th>
                <th scope="col" className="c-acc"><span className="visually-hidden">Acciones</span></th>
              </tr>
            </thead>
            <tbody>
              {trabajos.map((t) => {
                const enCurso = t.estado === "en_curso";
                const aqui = usandoId === t.id;
                const tiempo = t.minutos != null ? `${tiempoLargo(t.minutos)} (${t.minutos_origen})` : "sin tiempo";
                const peso = t.gramos_total != null ? `${gramos(t.gramos_total)} (estimado)` : "sin gramos";
                return (
                  <tr key={t.id} data-aviso={aqui}>
                    <th scope="row" className="t-nombre">
                      {t.nombre}
                      <span className="t-sec c-mov-no num">{fechaCorta(t.fecha)}</span>
                      {t.estado === "interrumpido" && <span className="t-sec">Se cortó antes de terminar: gramos del archivo completo, ajústalos si hace falta.</span>}
                      <span className="t-sec t-sec--fila num">
                        <span>{fechaHora(t.inicio_en)}{t.fin_en ? ` → ${hora(t.fin_en)}` : ""}</span>
                        {t.desde && <span className="etiqueta etiqueta--tenue">{t.desde === "web" ? "Bambu Studio / web" : "Desde la impresora"}</span>}
                        {t.gestion === "importado" && <span className="etiqueta etiqueta--ok">Importado</span>}
                        {t.gestion === "ignorado" && vista === "todos" && <span className="etiqueta etiqueta--tenue">Ignorado</span>}
                      </span>
                      <span className="t-sec"><EstadoSpoolman t={t} /></span>
                      <span className="t-meta num">{fechaCorta(t.fecha)} · {tiempo} · {peso} <Muestras t={t} /></span>
                    </th>
                    <td className="c-num c-mov-no num">
                      {t.minutos != null ? tiempoLargo(t.minutos) : "—"}
                      {t.minutos != null && <span className="t-sec">{t.minutos_origen}</span>}
                    </td>
                    <td className="c-num c-mov-no num">
                      {t.gramos_total != null ? gramos(t.gramos_total) : "—"}
                      {t.gramos_total != null && <span className="t-sec">estimado</span>}
                    </td>
                    <td className="c-mov-no"><Muestras t={t} /></td>
                    <td className="c-fin">
                      {enCurso ? (
                        <span className="etiqueta etiqueta--aviso">Imprimiendo · {t.progreso} %</span>
                      ) : t.estado === "interrumpido" ? (
                        <span className="etiqueta etiqueta--aviso">{t.origen === "nube" || t.progreso === 0 ? "Interrumpido" : `Interrumpido al ${t.progreso} %`}</span>
                      ) : (
                        <span className="etiqueta etiqueta--ok">Terminado</span>
                      )}
                    </td>
                    <td className="c-acc c-ancho">
                      {!enCurso && t.gestion !== "importado" && (
                        <div className="t-acciones">
                          {t.gestion === "pendiente" ? (
                            <>
                              <Boton variante="accent" pequeno disabled={aqui} onClick={() => onUsar(t)} aria-label={`Importar el trabajo ${t.nombre} como producción`}>{aqui ? "En el lote" : "Importar"}</Boton>
                              <Boton variante="ghost" pequeno cargando={ocupado === t.id} onClick={() => void cambiar(t, "ignorar")} aria-label={`Ignorar el trabajo ${t.nombre}`}>Ignorar</Boton>
                            </>
                          ) : (
                            <Boton variante="secondary" pequeno cargando={ocupado === t.id} onClick={() => void cambiar(t, "restaurar")} aria-label={`Restaurar el trabajo ${t.nombre}`}>Restaurar</Boton>
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
