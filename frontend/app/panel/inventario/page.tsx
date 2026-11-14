"use client";

import { useState, type FormEvent } from "react";
import { useAvisos } from "@/components/ui/Avisos";
import { Boton } from "@/components/ui/Boton";
import { Entrada } from "@/components/ui/Campo";
import { Foto } from "@/components/ui/Foto";
import { Hoja } from "@/components/ui/Hoja";
import { api } from "@/lib/api";
import { fechaHora } from "@/lib/format";
import { mensajeDe, useCargar } from "@/lib/hooks";
import type { Articulo, Movimiento } from "@/lib/types";

const TIPOS: Record<Movimiento["tipo"], string> = { produccion: "Producción", venta: "Venta", ajuste: "Ajuste", anulacion: "Venta anulada" };

function Detalle({ articulo, onCambio, onCerrar }: { articulo: Articulo | null; onCambio: () => void; onCerrar: () => void }) {
  const { mostrar } = useAvisos();
  const mov = useCargar(() => (articulo ? api.inventario.movimientos(articulo.id) : Promise.resolve([] as Movimiento[])));
  const [cantidad, setCantidad] = useState("");
  const [nota, setNota] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ajustar(e: FormEvent) {
    e.preventDefault();
    if (!articulo) return;
    const n = Number(cantidad);
    if (!Number.isInteger(n) || n === 0) {
      setError("Escribe una cantidad entera distinta de 0 (negativa para restar).");
      return;
    }
    setEnviando(true);
    setError(null);
    try {
      const a = await api.inventario.ajustar(articulo.id, n, nota.trim());
      mostrar(`Ajuste guardado. Ahora hay ${a.stock}.`);
      setCantidad("");
      setNota("");
      onCambio();
      await mov.recargar();
    } catch (err) {
      setError(mensajeDe(err));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Hoja abierta={articulo !== null} onCerrar={onCerrar} titulo={articulo?.nombre ?? ""} descripcion={articulo ? `${articulo.codigo} · hay ${articulo.stock}` : undefined}>
      <form onSubmit={ajustar} style={{ display: "grid", gap: "var(--space-md)" }}>
        <h3>Corregir el conteo</h3>
        <p className="muted">Úsalo si contaste y no coincide, o si una pieza se dañó. Suma con un número positivo y resta con uno negativo.</p>
        {error && <p className="alerta" role="alert">{error}</p>}
        <Entrada etiqueta="Cantidad (+ o −)" type="number" inputMode="numeric" step={1} value={cantidad} onChange={(e) => setCantidad(e.target.value)} placeholder="-2" />
        <Entrada etiqueta="Motivo" value={nota} minLength={3} maxLength={300} required onChange={(e) => setNota(e.target.value)} placeholder="Pieza rota al desmoldar" />
        <Boton variante="primary" type="submit" cargando={enviando}>Guardar ajuste</Boton>
      </form>
      <section style={{ display: "grid", gap: "var(--space-sm)" }}>
        <h3>Movimientos</h3>
        {(mov.datos ?? []).length === 0 ? (
          <p className="muted">Todavía no hay movimientos.</p>
        ) : (
          <ul className="kardex" style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {(mov.datos ?? []).map((m) => (
              <li key={m.id}>
                <span>
                  {TIPOS[m.tipo]}
                  <span className="muted"> · {fechaHora(m.creado_en)}{m.nota ? ` · ${m.nota}` : ""}</span>
                </span>
                <span className={m.cantidad > 0 ? "mov--mas" : "mov--menos"}>{m.cantidad > 0 ? `+${m.cantidad}` : m.cantidad}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </Hoja>
  );
}

export default function Inventario() {
  const { datos, error, cargando, recargar } = useCargar(api.inventario.existencias);
  const [abierto, setAbierto] = useState<string | null>(null);
  const lista = datos ?? [];
  const elegido = lista.find((a) => a.id === abierto) ?? null;
  const total = lista.reduce((s, a) => s + a.stock, 0);

  return (
    <>
      <div className="pagina-cab">
        <h1>Inventario</h1>
        <p className="lead">{cargando ? "Cargando…" : `${total} ${total === 1 ? "pieza" : "piezas"} en ${lista.length} ${lista.length === 1 ? "artículo" : "artículos"}.`}</p>
      </div>
      {error && <p className="alerta" role="alert">{error}</p>}
      {!cargando && lista.length === 0 ? (
        <div className="vacio">
          <h2 style={{ fontSize: "var(--text-title)" }}>Aún no hay artículos</h2>
          <p>El inventario se llena al registrar producción de tus artículos.</p>
          <a className="btn btn--primary" href="/panel/articulos">Crear artículo</a>
        </div>
      ) : (
        <div className="lista lista--multi">
          {lista.map((a) => {
            const bajo = a.stock <= a.stock_minimo;
            return (
              <button key={a.id} type="button" className={`fila${bajo ? " fila--aviso" : ""}`} onClick={() => setAbierto(a.id)}>
                <span className="fila__foto"><Foto url={a.imagen_url} codigo="" nombre={a.nombre} /></span>
                <span className="fila__titulo">
                  <span className="code muted">{a.codigo}</span>
                  <span className="fila__nombre">{a.nombre}</span>
                  {a.stock_minimo > 0 && <span className="fila__meta">mínimo {a.stock_minimo}</span>}
                </span>
                <span className="fila__fin">
                  <span className={`stock-num ${a.stock === 0 ? "stock-num--cero" : bajo ? "stock-num--bajo" : ""}`}>{a.stock}</span>
                  {bajo && <span className="etiqueta etiqueta--aviso">{a.stock === 0 ? "Agotado" : "Poco"}</span>}
                </span>
              </button>
            );
          })}
        </div>
      )}
      <Detalle key={abierto ?? "ninguno"} articulo={elegido} onCambio={recargar} onCerrar={() => setAbierto(null)} />
    </>
  );
}
