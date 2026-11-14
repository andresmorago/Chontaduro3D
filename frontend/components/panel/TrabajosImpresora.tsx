"use client";

import { useEffect, useState } from "react";
import { useAvisos } from "@/components/ui/Avisos";
import { Boton } from "@/components/ui/Boton";
import { Segmentado } from "@/components/ui/Segmentado";
import { api } from "@/lib/api";
import { fechaCorta } from "@/lib/format";
import { mensajeDe, useCargar } from "@/lib/hooks";
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

/** Trabajos que la impresora ya hizo. La persona elige cuáles son producciones (los trae al formulario
 *  del lote con sus gramos y tiempo) y cuáles no (se ignoran). */
export function TrabajosImpresora({ usandoId, onUsar, refrescar }: Props) {
  const { mostrar } = useAvisos();
  const [vista, setVista] = useState<"pendiente" | "ignorado">("pendiente");
  const lista = useCargar(() => api.impresora.trabajos(vista));
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
    <section className="seccion" aria-labelledby="t-trabajos-imp">
      <h2 id="t-trabajos-imp">Trabajos de la impresora</h2>
      <p className="muted">Lo que la impresora fue haciendo. Importa los que son producción para traer sus gramos y su tiempo; ignora el resto (pruebas, fallos).</p>
      <Segmentado etiqueta="Qué trabajos ver" valor={vista} opciones={[{ valor: "pendiente", etiqueta: "Por revisar" }, { valor: "ignorado", etiqueta: "Ignorados" }]} onCambio={setVista} />
      {lista.error && <p className="alerta" role="alert">{lista.error}</p>}
      {lista.cargando ? (
        <p className="muted" role="status">Cargando…</p>
      ) : trabajos.length === 0 ? (
        <div className="vacio">
          <p>{vista === "pendiente" ? "No hay trabajos por revisar. Cuando la impresora termine uno, aparece aquí." : "No hay trabajos ignorados."}</p>
        </div>
      ) : (
        <div className="lista trabajos">
          {trabajos.map((t) => {
            const enCurso = t.estado === "en_curso";
            const aqui = usandoId === t.id;
            return (
              <div key={t.id} className="trabajo">
                <div className="trabajo__cab">
                  <span className="trabajo__nombre">{t.nombre}</span>
                  {enCurso ? (
                    <span className="etiqueta etiqueta--aviso">Imprimiendo · {t.progreso} %</span>
                  ) : t.estado === "interrumpido" ? (
                    <span className="etiqueta etiqueta--aviso">Interrumpido al {t.progreso} %</span>
                  ) : (
                    <span className="etiqueta etiqueta--ok">Terminado</span>
                  )}
                </div>
                <div className="trabajo__meta num">
                  <span>{fechaCorta(t.fecha)}</span>
                  <span>{t.minutos != null ? `${tiempoLargo(t.minutos)} (${t.minutos_origen})` : "sin tiempo"}</span>
                  <span>{t.gramos_total != null ? `${gramos(t.gramos_total)} (estimado)` : "sin gramos"}</span>
                  <Muestras t={t} />
                </div>
                {t.estado === "interrumpido" && <p className="field__hint">Se cortó antes de terminar: los gramos son los del archivo completo; ajústalos si hace falta.</p>}
                {!enCurso && (
                  <div className="trabajo__acciones">
                    {vista === "pendiente" ? (
                      <>
                        <Boton variante="accent" pequeno disabled={aqui} onClick={() => onUsar(t)} aria-label={`Importar el trabajo ${t.nombre} como producción`}>{aqui ? "Cargado en el lote" : "Importar como producción"}</Boton>
                        <Boton variante="ghost" pequeno cargando={ocupado === t.id} onClick={() => void cambiar(t, "ignorar")} aria-label={`Ignorar el trabajo ${t.nombre}`}>Ignorar</Boton>
                      </>
                    ) : (
                      <Boton variante="secondary" pequeno cargando={ocupado === t.id} onClick={() => void cambiar(t, "restaurar")} aria-label={`Restaurar el trabajo ${t.nombre}`}>Restaurar</Boton>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
