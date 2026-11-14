"use client";

import { useState, type FormEvent } from "react";
import { Boton } from "@/components/ui/Boton";
import { Entrada } from "@/components/ui/Campo";
import { Contador } from "@/components/ui/Contador";
import { Foto } from "@/components/ui/Foto";
import { Hoja } from "@/components/ui/Hoja";
import { Turnstile } from "@/components/ui/Turnstile";
import { ErrorApi, api } from "@/lib/api";
import { MAX_CANTIDAD, type LineaCarrito } from "@/lib/carrito";
import { encuadreDe } from "@/lib/foto";
import { dinero } from "@/lib/format";

interface Props {
  abierta: boolean;
  lineas: LineaCarrito[];
  total: number;
  piezas: number;
  sitekey: string;
  onCerrar: () => void;
  onCambiar: (articuloId: string, color: string, cantidad: number) => void;
  /** El pedido se envió: el carrito se vacía. */
  onEnviado: () => void;
}

/** Mi pedido: los artículos elegidos (cantidad editable o quitar) y los tres datos para enviarlo. Un
 *  pedido es una solicitud: no toca el inventario; lo confirmamos por WhatsApp. */
export function CarritoHoja({ abierta, lineas, total, piezas, sitekey, onCerrar, onCambiar, onEnviado }: Props) {
  const [nombre, setNombre] = useState("");
  const [whatsapp, setWhatsapp] = useState("");
  const [trampa, setTrampa] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [reinicio, setReinicio] = useState(0);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hecho, setHecho] = useState<string | null>(null);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    if (lineas.length === 0) return;
    if (sitekey && !token) {
      setError("Completa la verificación antes de enviar el pedido.");
      return;
    }
    setEnviando(true);
    setError(null);
    try {
      const r = await api.publico.pedir({
        nombre: nombre.trim(),
        whatsapp: whatsapp.trim(),
        items: lineas.map((l) => ({ articulo_id: l.articuloId, cantidad: l.cantidad, color: l.color })),
        sitio_web: trampa,
        turnstile: token ?? "",
      });
      setHecho(r.mensaje);
      onEnviado();
    } catch (err) {
      setError(err instanceof ErrorApi ? err.message : "No se pudo enviar el pedido.");
    } finally {
      setEnviando(false);
      // El token es de un solo uso: tras cada intento se pide uno nuevo.
      setToken(null);
      setReinicio((n) => n + 1);
    }
  }

  function cerrar() {
    setHecho(null);
    setError(null);
    onCerrar();
  }

  const vacio = lineas.length === 0 && !hecho;

  return (
    <Hoja
      abierta={abierta}
      onCerrar={cerrar}
      titulo={hecho ? "Pedido enviado" : "Mi pedido"}
      descripcion={hecho ? undefined : vacio ? undefined : `${piezas === 1 ? "1 pieza" : `${piezas} piezas`} · ${lineas.length === 1 ? "1 artículo" : `${lineas.length} artículos`}`}
      pie={
        hecho ? (
          <Boton variante="primary" onClick={cerrar}>
            Listo
          </Boton>
        ) : vacio ? (
          <Boton variante="primary" onClick={cerrar}>
            Seguir mirando
          </Boton>
        ) : (
          <>
            <Boton variante="secondary" onClick={cerrar}>
              Seguir mirando
            </Boton>
            <Boton variante="accent" type="submit" form="form-pedido" cargando={enviando} disabled={Boolean(sitekey) && !token}>
              Enviar pedido
            </Boton>
          </>
        )
      }
    >
      {hecho ? (
        <div style={{ display: "grid", gap: "var(--space-sm)" }}>
          <p className="lead">{hecho}</p>
          <p className="muted">Un pedido no es una compra: lo confirmamos contigo antes de imprimir o entregar.</p>
        </div>
      ) : vacio ? (
        <p className="muted">Todavía no agregaste nada. Toca un artículo y pulsa «Agregar al pedido».</p>
      ) : (
        <form id="form-pedido" onSubmit={enviar} style={{ display: "grid", gap: "var(--space-md)" }}>
          {error && (
            <p className="alerta" role="alert">
              {error}
            </p>
          )}
          <ul className="carrito">
            {lineas.map((l) => (
              <li key={`${l.articuloId}|${l.color}`} className="carrito__linea">
                <Foto url={l.colorInfo?.imagen_url ?? l.articulo.imagen_url} codigo={l.articulo.codigo} nombre="" clase="carrito__foto" enc={l.colorInfo?.imagen_url ? encuadreDe(l.colorInfo) : encuadreDe(l.articulo)} />
                <div className="carrito__datos">
                  <strong className="carrito__nombre">{l.articulo.nombre}</strong>
                  {l.colorInfo && (
                    <span className="carrito__color">
                      <span className="muestra-mini" style={{ background: l.colorInfo.hex }} aria-hidden="true" />
                      {l.color}
                    </span>
                  )}
                  <span className="muted num">{dinero(l.articulo.precio)} c/u</span>
                </div>
                <div className="carrito__cantidad">
                  <Contador editable valor={l.cantidad} min={0} max={MAX_CANTIDAD} onCambio={(n) => onCambiar(l.articuloId, l.color, n)} etiqueta={`${l.articulo.nombre}${l.color ? `, ${l.color}` : ""}`} />
                  <strong className="num">{dinero(l.articulo.precio * l.cantidad)}</strong>
                  <button type="button" className="enlace" onClick={() => onCambiar(l.articuloId, l.color, 0)} aria-label={`Quitar ${l.articulo.nombre}${l.color ? ` (${l.color})` : ""} del pedido`}>
                    Quitar
                  </button>
                </div>
              </li>
            ))}
          </ul>
          <p className="num carrito__total">
            <span className="muted">Total estimado</span>
            <strong>{dinero(total)}</strong>
          </p>
          <Entrada etiqueta="Tu nombre" name="nombre" autoComplete="name" required minLength={2} maxLength={80} value={nombre} onChange={(e) => setNombre(e.target.value)} />
          <Entrada etiqueta="Tu WhatsApp" name="whatsapp" type="tel" inputMode="tel" autoComplete="tel" required minLength={7} maxLength={20} placeholder="300 123 4567" ayuda="Te escribimos por aquí para confirmar." value={whatsapp} onChange={(e) => setWhatsapp(e.target.value)} />
          <Turnstile sitekey={sitekey} onToken={setToken} reinicio={reinicio} />
          {/* Trampa para robots: una persona nunca ve ni llena este campo. */}
          <div className="trampa" aria-hidden="true">
            <label>
              No llenar este campo
              <input tabIndex={-1} autoComplete="off" name="sitio_web" value={trampa} onChange={(e) => setTrampa(e.target.value)} />
            </label>
          </div>
        </form>
      )}
    </Hoja>
  );
}
