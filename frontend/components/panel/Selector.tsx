"use client";

import { Fragment, useMemo, useState } from "react";
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

/** Los artículos como las filas de una tabla: todas miden lo mismo y las columnas se alinean (código, artículo,
 *  stock, precio y cantidad). Un artículo con colores lleva su fila de cabecera y, debajo, una fila por color con su
 *  propio contador. En un artículo sin colores, tocar la fila suma una unidad. En móvil cada fila pasa a dos líneas
 *  (nombre y datos a la izquierda, contador a la derecha). Estilos en panel.css («.tabla-art»). */
export function Selector({ articulos, cantidades, onCambiar, exigirStock, mostrarPrecio, incluirSinColor }: Props) {
  const [q, setQ] = useState("");
  const visibles = useMemo(() => {
    const t = sinTildes(q.trim());
    return t ? articulos.filter((a) => sinTildes(`${a.nombre} ${a.codigo}`).includes(t)) : articulos;
  }, [articulos, q]);

  return (
    <div style={{ display: "grid", gap: "var(--space-md)", alignContent: "start" }}>
      {articulos.length > 8 && (
        <div className="buscador-panel">
          <label className="visually-hidden" htmlFor="filtro-articulos">
            Filtrar artículos
          </label>
          <input id="filtro-articulos" className="input" type="search" placeholder="Buscar artículo" value={q} onChange={(e) => setQ(e.target.value)} autoComplete="off" />
        </div>
      )}
      <div className="selector">
        <table className="tabla-art">
          <caption className="visually-hidden">Artículos{exigirStock ? " con su stock" : ""}</caption>
          <thead>
            <tr>
              <th scope="col" className="c-cod">Código</th>
              <th scope="col" className="c-nom">Artículo</th>
              <th scope="col" className="c-num c-stock">Stock</th>
              {mostrarPrecio && <th scope="col" className="c-num c-precio">Precio</th>}
              <th scope="col" className="c-num c-cant">Cantidad</th>
            </tr>
          </thead>
          <tbody>
            {visibles.map((a) => {
              if (tieneColores(a)) {
                const filas = [
                  ...a.colores.map((c) => ({ id: c.id as string | null, nombre: c.nombre, hex: c.hex as string | null })),
                  ...(incluirSinColor && stockDe(a, null) > 0 ? [{ id: null, nombre: "Sin color asignado", hex: null }] : []),
                ];
                return (
                  <Fragment key={a.id}>
                    <tr className="art-cab">
                      <td className="c-cod code">{a.codigo}</td>
                      <th scope="row" className="c-nom">
                        {a.nombre}
                        <span className="art-meta num">{`${a.codigo}${mostrarPrecio ? ` · ${dinero(a.precio_venta)}` : ""} · Stock ${a.stock} · elige el color`}</span>
                      </th>
                      <td className="c-num c-stock num">{a.stock}</td>
                      {mostrarPrecio && <td className="c-num c-precio num">{dinero(a.precio_venta)}</td>}
                      <td className="c-num c-cant art-hint">Elige el color</td>
                    </tr>
                    {filas.map((f) => {
                      const n = cantidades[clave(a.id, f.id)] ?? 0;
                      const hay = stockDe(a, f.id);
                      return (
                        <tr key={f.id ?? "sin-color"} className="art-color" data-en-ticket={n > 0} data-sin-stock={Boolean(exigirStock) && hay <= 0}>
                          <td className="c-cod" />
                          <th scope="row" className="c-nom">
                            <span className="art-muestra" style={f.hex ? { background: f.hex } : undefined} aria-hidden="true" />
                            {f.nombre}
                            <span className="art-meta num">{exigirStock ? (hay > 0 ? `${hay} en stock` : "Sin stock") : `Stock ${hay}`}</span>
                          </th>
                          <td className="c-num c-stock num">{hay}</td>
                          {mostrarPrecio && <td className="c-precio" />}
                          <td className="c-num c-cant">
                            <Paso n={n} etiqueta={`${a.nombre}, ${f.nombre}`} onMenos={() => onCambiar(a, f.id, -1)} onMas={() => onCambiar(a, f.id, 1)} masDeshabilitado={Boolean(exigirStock) && n >= hay} />
                          </td>
                        </tr>
                      );
                    })}
                  </Fragment>
                );
              }
              const n = cantidades[clave(a.id, null)] ?? 0;
              const sinStock = Boolean(exigirStock) && a.stock <= 0;
              return (
                <tr key={a.id} className="art-fila" data-en-ticket={n > 0} data-sin-stock={sinStock} onClick={sinStock ? undefined : () => onCambiar(a, null, 1)}>
                  <td className="c-cod code">{a.codigo}</td>
                  <th scope="row" className="c-nom">
                    {a.nombre}
                    <span className="art-meta num">{`${a.codigo}${mostrarPrecio ? ` · ${dinero(a.precio_venta)}` : ""} · ${sinStock ? "Sin stock" : `Stock ${a.stock}`}`}</span>
                  </th>
                  <td className="c-num c-stock num">{a.stock}</td>
                  {mostrarPrecio && <td className="c-num c-precio num">{dinero(a.precio_venta)}</td>}
                  {/* El contador no debe sumar además la unidad del toque en la fila. */}
                  <td className="c-num c-cant" onClick={(e) => e.stopPropagation()}>
                    <Paso n={n} etiqueta={a.nombre} onMenos={() => onCambiar(a, null, -1)} onMas={() => onCambiar(a, null, 1)} masDeshabilitado={Boolean(exigirStock) && n >= a.stock} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {visibles.length === 0 && <p className="muted" style={{ padding: "var(--space-md)" }}>No hay artículos que coincidan.</p>}
      </div>
    </div>
  );
}
