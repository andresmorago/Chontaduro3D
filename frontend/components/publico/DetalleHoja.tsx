"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Boton } from "@/components/ui/Boton";
import { Entrada } from "@/components/ui/Campo";
import { Contador } from "@/components/ui/Contador";
import { Foto } from "@/components/ui/Foto";
import { Hoja } from "@/components/ui/Hoja";
import { Turnstile } from "@/components/ui/Turnstile";
import { ErrorApi, api } from "@/lib/api";
import { encuadreDe } from "@/lib/foto";
import { dinero } from "@/lib/format";
import type { ArticuloPublico } from "@/lib/types";

interface Props {
  articulo: ArticuloPublico | null;
  sitekey: string;
  onCerrar: () => void;
}

/** Ficha ampliada del artículo (foto grande, descripción, precio, colores) y, de ahí, el pedido
 *  en tres datos. Un pedido no toca el inventario. */
export function DetalleHoja({ articulo, sitekey, onCerrar }: Props) {
  const [paso, setPaso] = useState<"detalle" | "pedido">("detalle");
  const [color, setColor] = useState("");
  const [nombre, setNombre] = useState("");
  const [whatsapp, setWhatsapp] = useState("");
  const [cantidad, setCantidad] = useState(1);
  const [trampa, setTrampa] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [reinicio, setReinicio] = useState(0);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hecho, setHecho] = useState<string | null>(null);

  useEffect(() => {
    // Cada vez que se abre para otro artículo, empieza limpio (conserva nombre y contacto).
    setPaso("detalle");
    setColor(articulo?.colores.length === 1 ? (articulo.colores[0]?.nombre ?? "") : "");
    setCantidad(1);
    setError(null);
    setHecho(null);
    setToken(null);
  }, [articulo?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function enviar(e: FormEvent) {
    e.preventDefault();
    if (!articulo) return;
    if (sitekey && !token) {
      setError("Completa la verificación antes de enviar el pedido.");
      return;
    }
    setEnviando(true);
    setError(null);
    try {
      const r = await api.publico.pedir({ articulo_id: articulo.id, nombre: nombre.trim(), whatsapp: whatsapp.trim(), cantidad, color, sitio_web: trampa, turnstile: token ?? "" });
      setHecho(r.mensaje);
    } catch (err) {
      setError(err instanceof ErrorApi ? err.message : "No se pudo enviar el pedido.");
    } finally {
      setEnviando(false);
      // El token es de un solo uso: tras cada intento se pide uno nuevo.
      setToken(null);
      setReinicio((n) => n + 1);
    }
  }

  const colorElegidoPre = articulo?.colores.find((c) => c.nombre === color);
  const hayColores = (articulo?.colores.length ?? 0) > 0;
  // «Disponible» del color elegido (si hay colores y se eligió uno); si no, el del artículo.
  const hayEste = colorElegidoPre ? colorElegidoPre.disponible : (articulo?.disponible ?? false);
  // Misma foto y encuadre que en la tarjeta; si el color elegido tiene foto propia, se muestra esa.
  const colorElegido = articulo?.colores.find((c) => c.nombre === color);
  const fotoFicha = colorElegido?.imagen_url ? { url: colorElegido.imagen_url, enc: encuadreDe(colorElegido) } : { url: articulo?.imagen_url ?? null, enc: articulo ? encuadreDe(articulo) : undefined };
  const falta = hayColores && !color;
  const total = articulo ? articulo.precio * cantidad : 0;
  const enPedido = paso === "pedido" && !hecho;

  return (
    <Hoja
      abierta={articulo !== null}
      onCerrar={onCerrar}
      titulo={hecho ? "Pedido enviado" : enPedido ? "Hacer un pedido" : (articulo?.nombre ?? "")}
      descripcion={articulo ? (enPedido ? `${articulo.codigo} · ${articulo.nombre}` : articulo.codigo) : undefined}
      pie={
        hecho ? (
          <Boton variante="primary" onClick={onCerrar}>
            Listo
          </Boton>
        ) : enPedido ? (
          <>
            <Boton variante="secondary" onClick={() => setPaso("detalle")}>
              Volver
            </Boton>
            <Boton variante="accent" type="submit" form="form-pedido" cargando={enviando} disabled={Boolean(sitekey) && !token}>
              Enviar pedido
            </Boton>
          </>
        ) : (
          <Boton variante="accent" disabled={falta} onClick={() => setPaso("pedido")} aria-label={articulo ? `Pedir ${articulo.nombre}` : "Pedir"}>
            Pedir
          </Boton>
        )
      }
    >
      {!articulo ? null : hecho ? (
        <div style={{ display: "grid", gap: "var(--space-sm)" }}>
          <p className="lead">{hecho}</p>
          <p className="muted">Un pedido no es una compra: lo confirmamos contigo antes de imprimir o entregar.</p>
        </div>
      ) : enPedido ? (
        <form id="form-pedido" onSubmit={enviar} style={{ display: "grid", gap: "var(--space-md)" }}>
          {error && (
            <p className="alerta" role="alert">
              {error}
            </p>
          )}
          {hayColores && (
            <p className="resumen-color">
              <span className="muted">Color</span>
              <span className="color-chip">
                <span className="color-chip__muestra" style={{ background: articulo.colores.find((c) => c.nombre === color)?.hex }} aria-hidden="true" />
                <strong>{color}</strong>
              </span>
            </p>
          )}
          <Entrada etiqueta="Tu nombre" name="nombre" autoComplete="name" required minLength={2} maxLength={80} value={nombre} onChange={(e) => setNombre(e.target.value)} />
          <Entrada etiqueta="Tu WhatsApp" name="whatsapp" type="tel" inputMode="tel" autoComplete="tel" required minLength={7} maxLength={20} placeholder="300 123 4567" ayuda="Te escribimos por aquí para confirmar." value={whatsapp} onChange={(e) => setWhatsapp(e.target.value)} />
          <div className="field">
            <span className="field__label" id="etq-cantidad">
              ¿Cuántos quieres?
            </span>
            <Contador valor={cantidad} onCambio={setCantidad} min={1} max={99} etiqueta={articulo.nombre} />
          </div>
          <p className="num" style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-md)" }}>
            <span className="muted">Total estimado</span>
            <strong>{dinero(total)}</strong>
          </p>
          <Turnstile sitekey={sitekey} onToken={setToken} reinicio={reinicio} />
          {/* Trampa para robots: una persona nunca ve ni llena este campo. */}
          <div className="trampa" aria-hidden="true">
            <label>
              No llenar este campo
              <input tabIndex={-1} autoComplete="off" name="sitio_web" value={trampa} onChange={(e) => setTrampa(e.target.value)} />
            </label>
          </div>
        </form>
      ) : (
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
                  <button key={c.nombre} type="button" role="radio" aria-checked={color === c.nombre} className="color-op" onClick={() => setColor(c.nombre)}>
                    <span className="color-op__muestra" style={{ background: c.hex }} aria-hidden="true" />
                    <span className="color-op__nombre">{c.nombre}</span>
                  </button>
                ))}
              </div>
              {falta && <p className="field__hint">Elige un color para poder pedir.</p>}
            </div>
          )}
        </div>
      )}
    </Hoja>
  );
}
