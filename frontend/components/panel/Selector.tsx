"use client";

import { useMemo, useState } from "react";
import { dinero } from "@/lib/format";
import type { Articulo } from "@/lib/types";

interface Props {
  articulos: Articulo[];
  cantidades: Record<string, number>;
  onTocar: (a: Articulo) => void;
  /** En ventas: deshabilita lo que no tiene stock. En producción: todo se puede tocar. */
  exigirStock?: boolean;
  mostrarPrecio?: boolean;
}

const sinTildes = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

/** Rejilla de fichas: un toque suma una unidad. */
export function Selector({ articulos, cantidades, onTocar, exigirStock, mostrarPrecio }: Props) {
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
          const n = cantidades[a.id] ?? 0;
          const sinStock = exigirStock && a.stock <= 0;
          return (
            <button key={a.id} type="button" className="ficha" data-en-ticket={n > 0} disabled={sinStock} onClick={() => onTocar(a)} aria-label={`${a.nombre}${n ? `, ${n} en la lista` : ""}`}>
              {n > 0 && (
                <span className="ficha__cant" aria-hidden="true">
                  {n}
                </span>
              )}
              <span className="code ficha__codigo">{a.codigo}</span>
              <span className="ficha__nombre">{a.nombre}</span>
              <span className="ficha__meta num">
                {mostrarPrecio ? `${dinero(a.precio_venta)} · ` : ""}
                {sinStock ? "Sin stock" : `Stock ${a.stock}`}
              </span>
            </button>
          );
        })}
        {visibles.length === 0 && <p className="muted">No hay artículos que coincidan.</p>}
      </div>
    </div>
  );
}
