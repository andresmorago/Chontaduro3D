"use client";

import { useMemo, useState } from "react";
import { dinero } from "@/lib/format";
import { clave, stockDe, tieneColores } from "@/lib/lineas";
import type { Articulo } from "@/lib/types";

interface Props {
  articulos: Articulo[];
  /** Unidades elegidas por (artículo, color): la clave sale de `clave()` en lib/lineas.ts. */
  cantidades: Record<string, number>;
  /** Suma o resta unidades de un (artículo, color); `colorId` es null en un artículo sin colores. */
  onCambiar: (a: Articulo, colorId: string | null, delta: number) => void;
  /** En ventas: no deja pasar de lo que hay en inventario. En producción: sin tope. */
  exigirStock?: boolean;
  mostrarPrecio?: boolean;
  /** En ventas: ofrece también el stock «sin color asignado» (anterior a los colores). */
  incluirSinColor?: boolean;
}

const sinTildes = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

/** Menos / cantidad / más: la forma explícita de cambiar cuántas piezas son. */
function Paso({ n, etiqueta, onMenos, onMas, masDeshabilitado }: { n: number; etiqueta: string; onMenos: () => void; onMas: () => void; masDeshabilitado?: boolean }) {
  return (
    <span className="paso" role="group" aria-label={`Cantidad de ${etiqueta}`}>
      <button type="button" className="paso__btn" aria-label={`Quitar una unidad de ${etiqueta}`} disabled={n <= 0} onClick={onMenos}>
        −
      </button>
      <span className="paso__n num" aria-live="polite">
        {n}
      </span>
      <button type="button" className="paso__btn" aria-label={`Agregar una unidad de ${etiqueta}`} disabled={masDeshabilitado} onClick={onMas}>
        +
      </button>
    </span>
  );
}

/** Rejilla de fichas. Un artículo sin colores es una ficha: un toque suma una unidad y aparece su contador.
 *  Un artículo CON colores es una ficha con una fila por color, cada una con su propio contador (en escritorio todas las tarjetas miden lo mismo de ancho; ver panel-escritorio.css). */
export function Selector({ articulos, cantidades, onCambiar, exigirStock, mostrarPrecio, incluirSinColor }: Props) {
  const [q, setQ] = useState("");
  const visibles = useMemo(() => {
    const t = sinTildes(q.trim());
    return t ? articulos.filter((a) => sinTildes(`${a.nombre} ${a.codigo}`).includes(t)) : articulos;
  }, [articulos, q]);

  return (
    <div style={{ display: "grid", gap: "var(--space-md)" }}>
      {articulos.length > 8 && (
        <div className="buscador-panel">
          <label className="visually-hidden" htmlFor="filtro-articulos">
            Filtrar artículos
          </label>
          <input id="filtro-articulos" className="input" type="search" placeholder="Buscar artículo" value={q} onChange={(e) => setQ(e.target.value)} autoComplete="off" />
        </div>
      )}
      <div className="selector">
        {visibles.map((a) => {
          if (tieneColores(a)) {
            const filas = [
              ...a.colores.map((c) => ({ id: c.id as string | null, nombre: c.nombre, hex: c.hex as string | null })),
              ...(incluirSinColor && stockDe(a, null) > 0 ? [{ id: null, nombre: "Sin color asignado", hex: null }] : []),
            ];
            const total = filas.reduce((s, f) => s + (cantidades[clave(a.id, f.id)] ?? 0), 0);
            return (
              <div key={a.id} className="ficha-caja ficha-caja--colores">
                <div className="ficha ficha--colores" data-en-ticket={total > 0} role="group" aria-label={`${a.nombre}, por color`}>
                  <span className="code ficha__codigo">{a.codigo}</span>
                  <span className="ficha__nombre">{a.nombre}</span>
                  <span className="ficha__meta num">
                    {mostrarPrecio ? `${dinero(a.precio_venta)} · ` : ""}
                    {exigirStock ? `Stock ${a.stock}` : "Elige el color"}
                  </span>
                  <ul className="ficha__colores">
                    {filas.map((f) => {
                      const n = cantidades[clave(a.id, f.id)] ?? 0;
                      const hay = stockDe(a, f.id);
                      return (
                        <li key={f.id ?? "sin-color"} className="ficha__color">
                          <span className="ficha__muestra" style={f.hex ? { background: f.hex } : undefined} aria-hidden="true" />
                          <span className="ficha__color-nombre">
                            {f.nombre}
                            <span className="ficha__color-stock num">{exigirStock ? (hay > 0 ? `${hay} en stock` : "Sin stock") : `Stock ${hay}`}</span>
                          </span>
                          <Paso n={n} etiqueta={`${a.nombre}, ${f.nombre}`} onMenos={() => onCambiar(a, f.id, -1)} onMas={() => onCambiar(a, f.id, 1)} masDeshabilitado={Boolean(exigirStock) && n >= hay} />
                        </li>
                      );
                    })}
                  </ul>
                </div>
              </div>
            );
          }
          const n = cantidades[clave(a.id, null)] ?? 0;
          const sinStock = Boolean(exigirStock) && a.stock <= 0;
          return (
            <div key={a.id} className="ficha-caja">
              <button type="button" className="ficha" data-en-ticket={n > 0} disabled={sinStock} onClick={() => onCambiar(a, null, 1)} aria-label={`${a.nombre}${n ? `, ${n} en la lista` : ""}. Toca para sumar una unidad`}>
                {!sinStock && (
                  <span className="ficha__mas" aria-hidden="true">
                    +
                  </span>
                )}
                <span className="code ficha__codigo">{a.codigo}</span>
                <span className="ficha__nombre">{a.nombre}</span>
                <span className="ficha__meta num">
                  {mostrarPrecio ? `${dinero(a.precio_venta)} · ` : ""}
                  {sinStock ? "Sin stock" : `Stock ${a.stock}`}
                </span>
              </button>
              {/* Siempre presente: en escritorio todas las tarjetas tienen la misma estructura (y no saltan al elegir). En móvil solo aparece al elegir. */}
              <div className="ficha__paso" data-vacio={n === 0}>
                <Paso n={n} etiqueta={a.nombre} onMenos={() => onCambiar(a, null, -1)} onMas={() => onCambiar(a, null, 1)} masDeshabilitado={Boolean(exigirStock) && n >= a.stock} />
              </div>
            </div>
          );
        })}
        {visibles.length === 0 && <p className="muted">No hay artículos que coincidan.</p>}
      </div>
    </div>
  );
}
