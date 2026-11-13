"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Boton } from "@/components/ui/Boton";
import { Entrada } from "@/components/ui/Campo";
import { Contador } from "@/components/ui/Contador";
import { Hoja } from "@/components/ui/Hoja";
import { ErrorApi, api } from "@/lib/api";
import { dinero } from "@/lib/format";
import type { ArticuloPublico } from "@/lib/types";

interface Props {
  articulo: ArticuloPublico | null;
  onCerrar: () => void;
}

/** Pedido en tres datos: quién eres, cómo te escribimos y cuántos quieres. No toca el inventario. */
export function PedidoHoja({ articulo, onCerrar }: Props) {
  const [nombre, setNombre] = useState("");
  const [whatsapp, setWhatsapp] = useState("");
  const [cantidad, setCantidad] = useState(1);
  const [trampa, setTrampa] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hecho, setHecho] = useState<string | null>(null);

  useEffect(() => {
    // Cada vez que se abre para otro artículo, el formulario empieza limpio (conserva nombre y contacto).
    setCantidad(1);
    setError(null);
    setHecho(null);
  }, [articulo?.id]);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    if (!articulo) return;
    setEnviando(true);
    setError(null);
    try {
      const r = await api.publico.pedir({ articulo_id: articulo.id, nombre: nombre.trim(), whatsapp: whatsapp.trim(), cantidad, sitio_web: trampa });
      setHecho(r.mensaje);
    } catch (err) {
      setError(err instanceof ErrorApi ? err.message : "No se pudo enviar el pedido.");
    } finally {
      setEnviando(false);
    }
  }

  const total = articulo ? articulo.precio * cantidad : 0;

  return (
    <Hoja
      abierta={articulo !== null}
      onCerrar={onCerrar}
      titulo={hecho ? "Pedido enviado" : "Hacer un pedido"}
      descripcion={articulo ? `${articulo.codigo} · ${articulo.nombre}` : undefined}
      pie={
        hecho ? (
          <Boton variante="primary" onClick={onCerrar}>
            Listo
          </Boton>
        ) : (
          <>
            <Boton variante="secondary" onClick={onCerrar}>
              Cancelar
            </Boton>
            <Boton variante="accent" type="submit" form="form-pedido" cargando={enviando}>
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
      ) : (
        <form id="form-pedido" onSubmit={enviar} style={{ display: "grid", gap: "var(--space-md)" }} noValidate={false}>
          {error && (
            <p className="alerta" role="alert">
              {error}
            </p>
          )}
          <Entrada etiqueta="Tu nombre" name="nombre" autoComplete="name" required minLength={2} maxLength={80} value={nombre} onChange={(e) => setNombre(e.target.value)} />
          <Entrada etiqueta="Tu WhatsApp" name="whatsapp" type="tel" inputMode="tel" autoComplete="tel" required minLength={7} maxLength={20} placeholder="300 123 4567" ayuda="Te escribimos por aquí para confirmar." value={whatsapp} onChange={(e) => setWhatsapp(e.target.value)} />
          <div className="field">
            <span className="field__label" id="etq-cantidad">
              ¿Cuántos quieres?
            </span>
            <Contador valor={cantidad} onCambio={setCantidad} min={1} max={99} etiqueta={articulo?.nombre ?? "artículo"} />
          </div>
          {articulo && (
            <p className="num" style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-md)" }}>
              <span className="muted">Total estimado</span>
              <strong>{dinero(total)}</strong>
            </p>
          )}
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
