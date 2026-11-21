"use client";

import { useEffect, useState } from "react";
import { useAvisos } from "@/components/ui/Avisos";
import { Boton } from "@/components/ui/Boton";
import { Entrada } from "@/components/ui/Campo";
import { Contador } from "@/components/ui/Contador";
import { Hoja } from "@/components/ui/Hoja";
import { FilamentoTiempo } from "@/components/panel/FilamentoTiempo";
import { api } from "@/lib/api";
import { clave, partirClave } from "@/lib/lineas";
import { fechaCorta, hoyISO, restarDias } from "@/lib/format";
import { mensajeDe } from "@/lib/hooks";
import { aExtra, loteDesde, type EstadoLote } from "@/lib/produccion";
import type { Articulo, BobinaSpoolman, Parametros, Produccion } from "@/lib/types";

interface Props {
  /** El lote a corregir; `null` = cerrada. */
  lote: Produccion | null;
  articulos: Articulo[];
  parametros: Parametros | null;
  /** Bobinas de Spoolman (`null` = Spoolman no conectado). */
  bobinas?: BobinaSpoolman[] | null;
  onCerrar: () => void;
  onGuardado: () => void;
  onAbrirParametros: () => void;
}

/** Corrige un lote ya guardado: piezas, fecha, filamento, tiempo y nota. El inventario se ajusta
 *  solo por la diferencia. */
export function LoteEditarHoja({ lote, articulos, parametros, bobinas = null, onCerrar, onGuardado, onAbrirParametros }: Props) {
  const { mostrar } = useAvisos();
  const [estado, setEstado] = useState<EstadoLote | null>(null);
  const [cantidades, setCantidades] = useState<Record<string, number>>({});
  const [nota, setNota] = useState("");
  const [agregar, setAgregar] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hoy = hoyISO();

  useEffect(() => {
    if (!lote) return;
    setEstado(loteDesde(lote));
    setCantidades(Object.fromEntries(lote.items.map((i) => [clave(i.articulo_id, i.color_id), i.cantidad])));
    setNota(lote.nota ?? "");
    setAgregar("");
    setError(null);
  }, [lote]);

  if (!lote || !estado) return <Hoja abierta={false} onCerrar={onCerrar} titulo="Editar lote">{null}</Hoja>;

  // Cada línea es un (artículo, color). Un artículo archivado después de producirse puede seguir en su
  // lote: su nombre viene del propio lote.
  const rotulo = (nombre: string, color: string | null) => (color ? `${nombre} · ${color}` : nombre);
  const nombres = new Map<string, string>([
    ...lote.items.map((i): [string, string] => [clave(i.articulo_id, i.color_id), rotulo(i.nombre, i.color)]),
    ...articulos.flatMap((a): [string, string][] => (a.colores.length > 0 ? a.colores.map((c): [string, string] => [clave(a.id, c.id), rotulo(a.nombre, c.nombre)]) : [[clave(a.id, null), a.nombre]])),
  ]);
  const lineas = Object.entries(cantidades).filter(([, n]) => n > 0);
  const unidades = lineas.reduce((s, [, n]) => s + n, 0);
  // Lo que se puede agregar: cada artículo sin colores, y cada color de los que los tienen.
  const disponibles = articulos
    .flatMap((a) => (a.colores.length > 0 ? a.colores.map((c) => ({ k: clave(a.id, c.id), texto: `${a.codigo} · ${a.nombre} · ${c.nombre}` })) : [{ k: clave(a.id, null), texto: `${a.codigo} · ${a.nombre}` }]))
    .filter((o) => !((cantidades[o.k] ?? 0) > 0));
  const antes = lote.items.reduce((s, i) => s + i.cantidad, 0);

  async function guardar() {
    if (lineas.length === 0) return setError("El lote necesita al menos una pieza.");
    const conv = aExtra(estado!);
    if ("error" in conv) return setError(conv.error);
    setGuardando(true);
    setError(null);
    try {
      await api.produccion.modificar(lote!.id, lineas.map(([k, cantidad]) => { const { articuloId, colorId } = partirClave(k); return { articulo_id: articuloId, ...(colorId ? { color_id: colorId } : {}), cantidad }; }), nota.trim() || undefined, conv.extra);
      mostrar("Lote corregido. El inventario se ajustó por la diferencia.");
      onGuardado();
      onCerrar();
    } catch (e) {
      setError(mensajeDe(e));
    } finally {
      setGuardando(false);
    }
  }

  return (
    <Hoja
      abierta
      onCerrar={onCerrar}
      titulo="Editar lote"
      descripcion={`Del ${fechaCorta(lote.fecha)} · ${antes === 1 ? "1 pieza" : `${antes} piezas`}`}
      pie={
        <>
          <Boton variante="secondary" onClick={onCerrar}>Cancelar</Boton>
          <Boton variante="accent" cargando={guardando} onClick={guardar}>Guardar cambios</Boton>
        </>
      }
    >
      <div style={{ display: "grid", gap: "var(--space-md)" }}>
        {error && <p className="alerta" role="alert">{error}</p>}

        <section aria-label="Piezas del lote" style={{ display: "grid", gap: "var(--space-sm)" }}>
          <h3 style={{ fontSize: "var(--text-md)" }}>Piezas del lote</h3>
          {lineas.length === 0 && <p className="muted">Sin piezas: agrega al menos un artículo.</p>}
          {lineas.map(([k, n]) => (
            <div key={k} className="linea">
              <span className="linea__nombre">{nombres.get(k) ?? "Artículo"}</span>
              <Contador editable valor={n} min={0} max={10000} etiqueta={nombres.get(k) ?? "artículo"} onCambio={(v) => setCantidades((m) => ({ ...m, [k]: v }))} />
            </div>
          ))}
          {disponibles.length > 0 && (
            <label className="field">
              <span className="field__label">Agregar otro artículo</span>
              <select className="input" value={agregar} onChange={(e) => { const k = e.target.value; setAgregar(""); if (k) setCantidades((m) => ({ ...m, [k]: 1 })); }}>
                <option value="">Elegir…</option>
                {disponibles.map((o) => <option key={o.k} value={o.k}>{o.texto}</option>)}
              </select>
            </label>
          )}
          <p className="field__hint">Total: <strong>{unidades === 1 ? "1 pieza" : `${unidades} piezas`}</strong>. Al guardar, el inventario cambia solo por la diferencia con lo que ya estaba guardado.</p>
        </section>

        <div className="cuando">
          <label className="field">
            <span className="field__label">Fecha de producción</span>
            <input className="input num" type="date" value={estado.fecha} max={hoy} min={restarDias(hoy, 5 * 366)} onChange={(e) => setEstado({ ...estado, fecha: e.target.value })} />
          </label>
          <label className="check">
            <input type="checkbox" checked={estado.sumar} onChange={(e) => setEstado({ ...estado, sumar: e.target.checked })} />
            Suma al inventario actual
          </label>
          {estado.sumar !== lote.afecta_inventario && (
            <p className="field__hint">{estado.sumar ? "Estas piezas se SUMARÁN al stock de hoy." : "Estas piezas se RESTARÁN del stock de hoy y el lote quedará solo en el historial."}</p>
          )}
        </div>

        <FilamentoTiempo valor={estado} onCambio={setEstado} parametros={parametros} onAbrirParametros={onAbrirParametros} bobinas={bobinas} />
        <Entrada etiqueta="Nota (opcional)" value={nota} maxLength={300} onChange={(e) => setNota(e.target.value)} />
      </div>
    </Hoja>
  );
}
