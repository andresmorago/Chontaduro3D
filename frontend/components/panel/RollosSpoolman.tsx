"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useAvisos } from "@/components/ui/Avisos";
import { Boton } from "@/components/ui/Boton";
import { api } from "@/lib/api";
import { dinero } from "@/lib/format";
import { gramosTexto, muestra } from "@/lib/impresora";
import { mensajeDe, useCargar } from "@/lib/hooks";
import type { AlcanceTrabajo, BobinaSpoolman, EstadoAlcance, LineaAlcance } from "@/lib/types";

/** Cuánto queda del rollo (lo que informa Spoolman): la cifra, una barra fina y, si queda poco, un aviso. */
export function Restante({ b }: { b: BobinaSpoolman }) {
  if (b.restante_g == null) return <span className="muted">Sin peso en Spoolman</span>;
  const pct = b.inicial_g && b.inicial_g > 0 ? Math.max(0, Math.min(100, Math.round((b.restante_g / b.inicial_g) * 100))) : null;
  return (
    <span className={`restante${b.bajo ? " restante--bajo" : ""}`} title={pct != null ? `${pct} % del rollo` : undefined}>
      <span className="restante__cifra num">
        <strong>{gramosTexto(b.restante_g)}</strong>
        {b.inicial_g ? <span className="muted"> de {gramosTexto(b.inicial_g)}</span> : null}
      </span>
      {pct != null && (
        <span className="restante__barra" role="progressbar" aria-label="Lo que queda del rollo" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
          <span style={{ width: `${pct}%` }} />
        </span>
      )}
      {b.bajo && <span className="pildora pildora--aviso">Queda poco</span>}
    </span>
  );
}

/** Menú «Más»: acciones poco frecuentes de una fila, plegadas para que la fila no sea tan grande. */
export function MenuMas({ children }: { children: ReactNode }) {
  return (
    <details className="menu-mas">
      <summary className="btn btn--ghost btn--small" aria-label="Más acciones">Más ▾</summary>
      <div className="menu-mas__lista" onClick={(e) => { (e.currentTarget.parentElement as HTMLDetailsElement).open = false; }}>
        {children}
      </div>
    </details>
  );
}

const num = (t: string) => (t.trim() === "" ? undefined : Number(t.replace(",", ".")));

/** Corregir un rollo sin entrar a Spoolman: cuánto queda (pesado), su precio, o archivarlo cuando se terminó. */
export function EditarRollo({ b, alTerminar, alCerrar }: { b: BobinaSpoolman; alTerminar: () => Promise<void>; alCerrar: () => void }) {
  const { mostrar } = useAvisos();
  const [restante, setRestante] = useState(b.restante_g != null ? String(b.restante_g) : "");
  const [precio, setPrecio] = useState(b.precio != null ? String(b.precio) : "");
  const [ocupado, setOcupado] = useState(false);
  const [confirmar, setConfirmar] = useState(false);

  async function guardar() {
    const r = num(restante), p = num(precio);
    if ([r, p].some((n) => n !== undefined && (!Number.isFinite(n) || n < 0))) {
      mostrar("Revisa los números: deben ser positivos.", { tipo: "error" });
      return;
    }
    const cambios: { restante_g?: number; precio?: number } = {};
    if (r !== undefined && r !== b.restante_g) cambios.restante_g = r;
    if (p !== undefined && p !== b.precio) cambios.precio = p;
    if (Object.keys(cambios).length === 0) {
      alCerrar();
      return;
    }
    setOcupado(true);
    try {
      await api.spoolman.editarBobina(b.id, cambios);
      mostrar(`${b.nombre}: guardado en Spoolman.`);
      await alTerminar();
      alCerrar();
    } catch (e) {
      mostrar(mensajeDe(e), { tipo: "error" });
    } finally {
      setOcupado(false);
    }
  }

  async function archivar() {
    setOcupado(true);
    try {
      await api.spoolman.editarBobina(b.id, { archivar: true });
      mostrar(`${b.nombre}: archivado. Ya no sale en las listas.`);
      await alTerminar();
      alCerrar();
    } catch (e) {
      mostrar(mensajeDe(e), { tipo: "error" });
    } finally {
      setOcupado(false);
    }
  }

  return (
    <span className="spool-edicion spool-crear">
      <label className="spool-gramos">
        <span>Cuánto queda</span>
        <input className="input num" inputMode="decimal" value={restante} onChange={(e) => setRestante(e.target.value)} />
        <span aria-hidden="true">g</span>
      </label>
      <label className="spool-gramos">
        <span>Precio del rollo</span>
        <input className="input num" inputMode="decimal" placeholder="opcional" value={precio} onChange={(e) => setPrecio(e.target.value)} />
      </label>
      <Boton variante="accent" pequeno cargando={ocupado} onClick={() => void guardar()}>Guardar</Boton>
      <Boton variante="ghost" pequeno onClick={alCerrar}>Cancelar</Boton>
      {confirmar ? (
        <>
          <span className="aviso-linea">¿Rollo terminado? Sale de las listas; su chip se sigue reconociendo.</span>
          <Boton variante="danger" pequeno cargando={ocupado} onClick={() => void archivar()}>Sí, archivar</Boton>
          <Boton variante="ghost" pequeno onClick={() => setConfirmar(false)}>No</Boton>
        </>
      ) : (
        <Boton variante="secondary" pequeno onClick={() => setConfirmar(true)}>Archivar (se terminó)…</Boton>
      )}
      <span className="field__hint">«Cuánto queda» es el filamento sin el carrete (si pesas el rollo, réstale el carrete vacío). El precio sirve para el costo de cada lote.</span>
    </span>
  );
}

/** Los rollos que no están en el AMS (los de repuesto), con los más bajos primero. */
export function Repuestos({ alCambiar }: { alCambiar: () => Promise<void> }) {
  const lista = useCargar(api.spoolman.repuestos);
  const [editando, setEditando] = useState<number | null>(null);

  useEffect(() => {
    const id = setInterval(() => {
      if (!document.hidden && editando === null) void lista.recargar();
    }, 10000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editando]);

  const bobinas = lista.datos?.bobinas ?? [];
  const bajos = bobinas.filter((b) => b.bajo).length;
  return (
    <div className="spool-bloque">
      <h3 className="spool-sub">
        Rollos de repuesto
        {bobinas.length > 0 && <span className="etiqueta etiqueta--tenue">{bobinas.length}</span>}
        {bajos > 0 && <span className="etiqueta etiqueta--aviso">{bajos === 1 ? "1 con poco" : `${bajos} con poco`}</span>}
      </h3>
      <p className="field__hint">Rollos que no están en el AMS; primero los que quedan por debajo de {lista.datos?.umbral_g ?? 150} g.</p>
      {lista.error && <p className="alerta" role="alert">{lista.error}</p>}
      {lista.cargando ? (
        <p className="muted" role="status">Cargando…</p>
      ) : bobinas.length === 0 ? (
        <p className="muted">No hay rollos de repuesto: todos los que tienes en Spoolman están en el AMS.</p>
      ) : (
        <ul className="spool-ranuras">
          {bobinas.map((b) => (
            <li key={b.id} className="spool-ranura">
              <span className="bandeja__color" style={{ background: muestra(b.color) }} aria-hidden="true" />
              <div className="spool-ranura__texto">
                <strong className="spool-ranura__titulo">
                  {b.nombre} <span className="muted">· n.º {b.id}</span>
                </strong>
                {b.precio != null && <span className="spool-ranura__sub muted num">Precio {dinero(b.precio)}</span>}
              </div>
              <div className="spool-ranura__consumo"><Restante b={b} /></div>
              {editando !== b.id && (
                <div className="spool-ranura__acciones">
                  <Boton variante="secondary" pequeno onClick={() => setEditando(b.id)}>Ajustar</Boton>
                </div>
              )}
              {editando === b.id && (
                <div className="spool-ranura__extra">
                  <EditarRollo b={b} alCerrar={() => setEditando(null)} alTerminar={async () => { await Promise.all([lista.recargar(), alCambiar()]); }} />
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function mensajeAlcance(l: LineaAlcance): { texto: string; clase: string; detalle: string } {
  const falta = l.restante_g != null ? l.gramos - l.restante_g : 0;
  const sobra = l.restante_g != null ? l.restante_g - l.gramos : 0;
  const m: Record<EstadoAlcance, { texto: string; clase: string; detalle: string }> = {
    alcanza: { texto: "Alcanza", clase: "pildora--ok", detalle: `Quedan ${gramosTexto(l.restante_g)} y se necesitan ${gramosTexto(l.gramos)}.` },
    justo: { texto: `Va justo: sobran ${gramosTexto(sobra)}`, clase: "pildora--aviso", detalle: "Los gramos del archivo son estimados: ten otro rollo a la mano." },
    no_alcanza: { texto: `No alcanza: faltan ${gramosTexto(falta)}`, clase: "pildora--aviso", detalle: `Quedan ${gramosTexto(l.restante_g)} y se necesitan ${gramosTexto(l.gramos)}. Ten otro rollo a la mano.` },
    sin_bobina: { texto: "Sin bobina unida: no sé cuánto queda", clase: "", detalle: "Asocia una bobina de Spoolman a esta ranura." },
    sin_peso: { texto: "Spoolman no tiene su peso", clase: "", detalle: "Ajusta «cuánto queda» en esta bobina." },
    dudoso: { texto: "No sé en qué ranura va", clase: "", detalle: "Hay más de una ranura parecida." },
  };
  return m[l.estado];
}

/** Lo que el trabajo en curso necesita de UNA ranura: va dentro de su fila en «En la impresora ahora». */
export function DetalleAlcance({ l }: { l: LineaAlcance }) {
  const m = mensajeAlcance(l);
  return (
    <span className="spool-alcance-linea" title={m.detalle}>
      <span className="muted">Este trabajo usa {gramosTexto(l.gramos)}</span>
      <span className={`pildora ${m.clase}`}>{m.texto}</span>
    </span>
  );
}

/** Encabezado del trabajo en curso: qué se imprime, la alerta si algo no alcanza y lo que no se pudo ubicar en una ranura. */
export function AvisoAlcance({ a }: { a: AlcanceTrabajo | null }) {
  if (!a || !a.trabajo) return null;
  const sueltas = a.lineas.filter((l) => l.ranura == null);
  return (
    <div className="spool-trabajo">
      <p>
        Imprimiendo <strong>«{a.trabajo}»</strong>.{" "}
        {a.leyendo || a.lineas.length === 0 ? (
          <span className="muted" role="status">Leyendo el archivo para saber cuánto filamento necesita…</span>
        ) : (
          <span className="muted">Abajo, cada ranura dice si le alcanza.</span>
        )}
      </p>
      {a.alerta && (
        <p className="alerta" role="alert">
          Un rollo no alcanza para este trabajo. Cámbialo antes de que se acabe.
        </p>
      )}
      {sueltas.map((l, i) => (
        <p key={i} className="muted">
          {l.tipo ?? "Filamento"} · {gramosTexto(l.gramos)}: {mensajeAlcance(l).texto}
        </p>
      ))}
    </div>
  );
}
