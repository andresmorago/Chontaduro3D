"use client";

import { useEffect, useState } from "react";
import { Boton } from "@/components/ui/Boton";
import { Contador } from "@/components/ui/Contador";
import { Foto } from "@/components/ui/Foto";
import { Hoja } from "@/components/ui/Hoja";
import { MAX_CANTIDAD } from "@/lib/carrito";
import { encuadreDe } from "@/lib/foto";
import { dinero } from "@/lib/format";
import type { ArticuloPublico } from "@/lib/types";

interface Props {
  articulo: ArticuloPublico | null;
  onCerrar: () => void;
  /** Suma al pedido (el carrito del catálogo). */
  onAgregar: (articulo: ArticuloPublico, color: string, cantidad: number) => void;
  /** El carrito ya tiene el máximo de renglones distintos. */
  carritoLleno: boolean;
}

/** Ficha ampliada: foto grande (la del color elegido, si la tiene), descripción, precio, color y cantidad.
 *  «Agregar al pedido» lo suma al carrito: se pueden agregar varios artículos y colores antes de enviar. */
export function DetalleHoja({ articulo, onCerrar, onAgregar, carritoLleno }: Props) {
  const [color, setColor] = useState("");
  const [cantidad, setCantidad] = useState(1);

  useEffect(() => {
    // Cada vez que se abre para otro artículo, empieza limpio (si tiene un solo color, ya viene elegido).
    setColor(articulo?.colores.length === 1 ? (articulo.colores[0]?.nombre ?? "") : "");
    setCantidad(1);
  }, [articulo?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const colorElegido = articulo?.colores.find((c) => c.nombre === color) ?? null;
  const hayColores = (articulo?.colores.length ?? 0) > 0;
  const falta = hayColores && !color;
  // Misma foto y encuadre que en la tarjeta; si el color elegido tiene foto propia, se muestra esa.
  const fotoFicha = colorElegido?.imagen_url ? { url: colorElegido.imagen_url, enc: encuadreDe(colorElegido) } : { url: articulo?.imagen_url ?? null, enc: articulo ? encuadreDe(articulo) : undefined };
  // «Disponible» del color elegido; sin color elegido, el del artículo.
  const hayEste = colorElegido ? colorElegido.disponible : (articulo?.disponible ?? false);

  return (
    <Hoja
      abierta={articulo !== null}
      onCerrar={onCerrar}
      titulo={articulo?.nombre ?? ""}
      descripcion={articulo?.codigo}
      pie={
        <Boton
          variante="accent"
          disabled={falta || carritoLleno}
          onClick={() => {
            if (articulo) onAgregar(articulo, color, cantidad);
          }}
        >
          Agregar al pedido
        </Boton>
      }
    >
      {articulo && (
        <div className="detalle">
          <Foto url={fotoFicha.url} codigo={articulo.codigo} nombre={articulo.nombre} clase="detalle__foto" enc={fotoFicha.enc} />
          <div className="detalle__precio">
            <span className="articulo__precio">{dinero(articulo.precio)}</span>
            <span className={`etiqueta ${hayEste ? "etiqueta--ok" : "etiqueta--tenue"}`}>{hayEste ? "Disponible" : "Sobre pedido"}</span>
          </div>
          {articulo.descripcion ? <p className="detalle__desc">{articulo.descripcion}</p> : <p className="muted">Este artículo aún no tiene descripción.</p>}
          <p className="field__hint">{hayEste ? "Disponible = listo para entregar." : "Sobre pedido = lo imprimimos cuando lo pides."}</p>
          {hayColores && (
            <div className="field">
              <span className="field__label" id="etq-color">
                Elige un color{color && <>: <strong>{color}</strong></>}
              </span>
              <div className="colores-elegir" role="radiogroup" aria-labelledby="etq-color">
                {articulo.colores.map((c) => (
                  <button key={c.id} type="button" role="radio" aria-checked={color === c.nombre} className="color-op" onClick={() => setColor(c.nombre)}>
                    <span className="color-op__muestra" style={{ background: c.hex }} aria-hidden="true" />
                    <span className="color-op__nombre">{c.nombre}</span>
                  </button>
                ))}
              </div>
              {falta && <p className="field__hint">Elige un color para agregarlo al pedido.</p>}
            </div>
          )}
          <div className="field">
            <span className="field__label" id="etq-cantidad">
              ¿Cuántos quieres?
            </span>
            <div className="detalle__cantidad">
              <Contador editable valor={cantidad} onCambio={setCantidad} min={1} max={MAX_CANTIDAD} etiqueta={`${articulo.nombre}${color ? `, ${color}` : ""}`} />
              <strong className="num">{dinero(articulo.precio * cantidad)}</strong>
            </div>
          </div>
          {carritoLleno && <p className="alerta" role="status">Tu pedido ya tiene el máximo de artículos distintos (20). Envíalo y haz otro.</p>}
        </div>
      )}
    </Hoja>
  );
}
