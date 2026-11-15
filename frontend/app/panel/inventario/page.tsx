"use client";

import { Fragment, useState, type FormEvent } from "react";
import { useAvisos } from "@/components/ui/Avisos";
import { Boton } from "@/components/ui/Boton";
import { Entrada } from "@/components/ui/Campo";
import { Foto } from "@/components/ui/Foto";
import { Hoja } from "@/components/ui/Hoja";
import { api } from "@/lib/api";
import { encuadreDe } from "@/lib/foto";
import { fechaHora } from "@/lib/format";
import { mensajeDe, useCargar } from "@/lib/hooks";
import type { Articulo, Movimiento } from "@/lib/types";

const TIPOS: Record<Movimiento["tipo"], string> = { produccion: "Producción", venta: "Venta", ajuste: "Ajuste", anulacion: "Venta anulada" };

function Detalle({ articulo, onCambio, onCerrar }: { articulo: Articulo | null; onCambio: () => void; onCerrar: () => void }) {
  const { mostrar } = useAvisos();
  const mov = useCargar(() => (articulo ? api.inventario.movimientos(articulo.id) : Promise.resolve([] as Movimiento[])));
  const [cantidad, setCantidad] = useState("");
  const [nota, setNota] = useState("");
  // En un artículo con colores el ajuste se hace sobre uno de ellos (o sobre el «sin color asignado»).
  const [colorId, setColorId] = useState("");
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
    if (articulo.colores.length > 0 && colorId === "" ) {
      setError("Elige a qué color corresponde el ajuste.");
      return;
    }
    if (colorId === "__sin_color") {
      if (n > 0) return setError("Al stock «sin color asignado» solo se le puede restar: súmalo al color que corresponda.");
    }
    setEnviando(true);
    setError(null);
    try {
      const a = await api.inventario.ajustar(articulo.id, n, nota.trim(), colorId && colorId !== "__sin_color" ? colorId : undefined);
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
        {articulo && articulo.colores.length > 0 && (
          <label className="field">
            <span className="field__label">Color</span>
            <select className="input" value={colorId} onChange={(e) => setColorId(e.target.value)} required>
              <option value="">Elegir color…</option>
              {articulo.colores.map((c) => (
                <option key={c.id} value={c.id}>{c.nombre} (hay {articulo.stock_colores.find((s) => s.color_id === c.id)?.stock ?? 0})</option>
              ))}
              {(articulo.stock_colores.find((s) => s.color_id === null)?.stock ?? 0) > 0 && (
                <option value="__sin_color">Sin color asignado (hay {articulo.stock_colores.find((s) => s.color_id === null)?.stock})</option>
              )}
            </select>
            <span className="field__hint">Para pasar piezas «sin color asignado» a un color: resta aquí y suma en el color.</span>
          </label>
        )}
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
                  {TIPOS[m.tipo]}{m.color ? ` · ${m.color}` : ""}
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
        <div className="tabla-caja">
          <table className="tabla-datos">
            <caption className="visually-hidden">Existencias por artículo y color</caption>
            <thead>
              <tr>
                <th scope="col" className="c-foto"><span className="visually-hidden">Foto</span></th>
                <th scope="col" className="c-cod">Código</th>
                <th scope="col">Artículo</th>
                <th scope="col" className="c-num c-mov-no">Mínimo</th>
                <th scope="col" className="c-num">Stock</th>
              </tr>
            </thead>
            <tbody>
              {lista.map((a) => {
                const bajo = a.stock <= a.stock_minimo;
                const colores = a.stock_colores;
                return (
                  <Fragment key={a.id}>
                    <tr className={`t-cab t-clic${colores.length > 0 ? " t-con-sub" : ""}`} data-aviso={bajo} onClick={() => setAbierto(a.id)}>
                      <td className="c-foto"><span className="t-foto"><Foto url={a.imagen_url} codigo="" nombre={a.nombre} enc={encuadreDe(a)} /></span></td>
                      <td className="c-cod code">{a.codigo}</td>
                      <th scope="row" className="t-nombre">
                        <button type="button" className="t-enlace" onClick={(e) => { e.stopPropagation(); setAbierto(a.id); }} aria-label={`${a.nombre}: ver y corregir el conteo`}>{a.nombre}</button>
                        <span className="t-meta num">{a.stock_minimo > 0 ? `Mínimo ${a.stock_minimo}` : "Sin mínimo"}</span>
                      </th>
                      <td className="c-num c-mov-no num">{a.stock_minimo > 0 ? a.stock_minimo : "—"}</td>
                      <td className="c-num c-fin">
                        <span className="t-estado">
                          {bajo && <span className="etiqueta etiqueta--aviso">{a.stock === 0 ? "Agotado" : "Poco"}</span>}
                          <span className={`stock-num ${a.stock === 0 ? "stock-num--cero" : bajo ? "stock-num--bajo" : ""}`}>{a.stock}</span>
                        </span>
                      </td>
                    </tr>
                    {colores.map((s) => (
                      <tr key={s.color_id ?? "sin-color"} className="t-sub t-clic" data-cero={s.stock === 0} onClick={() => setAbierto(a.id)}>
                        <td className="c-foto" />
                        <td className="c-cod" />
                        <th scope="row" className="t-nombre">
                          <span className="muestra-mini" style={s.hex ? { background: s.hex } : undefined} aria-hidden="true" /> {s.nombre ?? "Sin color asignado"}
                        </th>
                        <td className="c-mov-no" />
                        <td className="c-num c-fin num">{s.stock}</td>
                      </tr>
                    ))}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <Detalle key={abierto ?? "ninguno"} articulo={elegido} onCambio={recargar} onCerrar={() => setAbierto(null)} />
    </>
  );
}
