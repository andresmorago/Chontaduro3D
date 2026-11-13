"use client";

import { useState } from "react";
import { Boton } from "@/components/ui/Boton";
import { useAvisos } from "@/components/ui/Avisos";
import { Contador } from "@/components/ui/Contador";
import { Entrada } from "@/components/ui/Campo";
import { Segmentado } from "@/components/ui/Segmentado";
import { Selector } from "@/components/panel/Selector";
import { api } from "@/lib/api";
import { dinero, hora } from "@/lib/format";
import { mensajeDe, useCargar } from "@/lib/hooks";
import type { Articulo, MetodoPago, Venta } from "@/lib/types";

interface Linea {
  cantidad: number;
  precio: number | null; // null = precio de la lista
}

const METODOS = [
  { valor: "efectivo", etiqueta: "Efectivo" },
  { valor: "transferencia", etiqueta: "Transferencia" },
  { valor: "otro", etiqueta: "Otro" },
] as const;

export default function Vender() {
  const { mostrar } = useAvisos();
  const articulos = useCargar(() => api.articulos.listar());
  const ventas = useCargar(api.ventas.deHoy);
  const [lineas, setLineas] = useState<Record<string, Linea>>({});
  const [metodo, setMetodo] = useState<MetodoPago>("efectivo");
  const [cliente, setCliente] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [aAnular, setAAnular] = useState<string | null>(null);

  const lista = articulos.datos ?? [];
  const porId = new Map(lista.map((a) => [a.id, a]));
  const items = Object.entries(lineas).filter(([id, l]) => l.cantidad > 0 && porId.has(id));
  const precioDe = (a: Articulo, l: Linea) => l.precio ?? a.precio_venta;
  const total = items.reduce((s, [id, l]) => s + precioDe(porId.get(id)!, l) * l.cantidad, 0);
  const piezas = items.reduce((s, [, l]) => s + l.cantidad, 0);

  function tocar(a: Articulo) {
    const actual = lineas[a.id]?.cantidad ?? 0;
    if (actual + 1 > a.stock) {
      mostrar(`De ${a.nombre} solo quedan ${a.stock}.`, { tipo: "error" });
      return;
    }
    setLineas((m) => ({ ...m, [a.id]: { cantidad: actual + 1, precio: m[a.id]?.precio ?? null } }));
  }

  function poner(id: string, cantidad: number) {
    setLineas((m) => {
      const { [id]: _quitada, ...resto } = m;
      void _quitada;
      return cantidad <= 0 ? resto : { ...m, [id]: { cantidad, precio: m[id]?.precio ?? null } };
    });
  }

  async function deshacer(id: string) {
    try {
      await api.ventas.anular(id);
      mostrar("Venta anulada. Las piezas volvieron al inventario.");
      await Promise.all([articulos.recargar(), ventas.recargar()]);
    } catch (e) {
      mostrar(mensajeDe(e), { tipo: "error" });
    }
  }

  async function registrar() {
    if (items.length === 0) return;
    setEnviando(true);
    try {
      const v = await api.ventas.registrar({
        metodo_pago: metodo,
        cliente: cliente.trim() || undefined,
        items: items.map(([id, l]) => ({ articulo_id: id, cantidad: l.cantidad, ...(l.precio !== null ? { precio_unitario: l.precio } : {}) })),
      });
      setLineas({});
      setCliente("");
      mostrar(`Venta registrada · ${dinero(v.total)}`, { accion: { etiqueta: "Deshacer", alPulsar: () => deshacer(v.id) } });
      await Promise.all([articulos.recargar(), ventas.recargar()]);
    } catch (e) {
      mostrar(mensajeDe(e), { tipo: "error" });
      void articulos.recargar(); // el stock pudo cambiar: se muestra el real
    } finally {
      setEnviando(false);
    }
  }

  async function anular(v: Venta) {
    setAAnular(null);
    try {
      await api.ventas.anular(v.id);
      mostrar("Venta anulada. Las piezas volvieron al inventario.");
      await Promise.all([articulos.recargar(), ventas.recargar()]);
    } catch (e) {
      mostrar(mensajeDe(e), { tipo: "error" });
    }
  }

  const delDia = (ventas.datos ?? []).filter((v) => !v.anulada);
  const totalDia = delDia.reduce((s, v) => s + v.total, 0);

  return (
    <>
      <div className="pagina-cab">
        <h1>Vender</h1>
        <p className="lead">Toca los artículos que se vendieron. Al registrar, salen del inventario.</p>
      </div>

      {articulos.error && <p className="alerta" role="alert">{articulos.error}</p>}
      {articulos.cargando ? (
        <p className="muted" role="status">Cargando artículos…</p>
      ) : lista.length === 0 ? (
        <div className="vacio">
          <h2 style={{ fontSize: "var(--text-title)" }}>Aún no hay artículos</h2>
          <p>Crea tu primer artículo para poder registrar ventas.</p>
          <a className="btn btn--primary" href="/panel/articulos">Crear artículo</a>
        </div>
      ) : (
        <div className="venta-grid">
          <Selector articulos={lista} cantidades={Object.fromEntries(items.map(([id, l]) => [id, l.cantidad]))} onTocar={tocar} exigirStock mostrarPrecio />

          <section className="ticket" id="ticket" aria-labelledby="t-ticket">
            <h2 id="t-ticket" style={{ fontSize: "var(--text-title)" }}>Esta venta</h2>
            {items.length === 0 ? (
              <p className="ticket__vacio">Toca un artículo para agregarlo.</p>
            ) : (
              <div className="ticket__lineas">
                {items.map(([id, l]) => {
                  const a = porId.get(id)!;
                  const precio = precioDe(a, l);
                  return (
                    <div key={id} className="linea">
                      <span className="linea__nombre">{a.nombre}</span>
                      <Contador chico valor={l.cantidad} min={0} max={a.stock} onCambio={(n) => poner(id, n)} etiqueta={a.nombre} />
                      <label className="linea__precio">
                        Precio c/u
                        <input className="input num" type="number" inputMode="numeric" min={0} step={100} value={precio} onChange={(e) => setLineas((m) => ({ ...m, [id]: { cantidad: l.cantidad, precio: e.target.value === "" ? null : Math.max(0, Number(e.target.value)) } }))} />
                      </label>
                      <span className="linea__subtotal">{dinero(precio * l.cantidad)}</span>
                    </div>
                  );
                })}
              </div>
            )}
            <div className="ticket__total">
              <span className="muted">{piezas === 1 ? "1 pieza" : `${piezas} piezas`}</span>
              <strong>{dinero(total)}</strong>
            </div>
            <Segmentado etiqueta="Forma de pago" valor={metodo} opciones={[...METODOS]} onCambio={setMetodo} />
            <Entrada etiqueta="Cliente (opcional)" value={cliente} maxLength={120} onChange={(e) => setCliente(e.target.value)} autoComplete="off" />
            <Boton variante="accent" bloque cargando={enviando} disabled={items.length === 0} onClick={registrar}>
              Registrar venta
            </Boton>
          </section>
        </div>
      )}

      {items.length > 0 && (
        <div className="barra-cobro">
          <strong>{dinero(total)}</strong>
          <Boton variante="primary" onClick={() => document.getElementById("ticket")?.scrollIntoView({ block: "start" })}>
            Revisar y cobrar
          </Boton>
        </div>
      )}

      <section className="seccion" aria-labelledby="t-hoy">
        <h2 id="t-hoy">Ventas de hoy {delDia.length > 0 && <span className="muted num">· {delDia.length} · {dinero(totalDia)}</span>}</h2>
        {ventas.error && <p className="alerta" role="alert">{ventas.error}</p>}
        {(ventas.datos ?? []).length === 0 ? (
          <div className="vacio"><p>Todavía no registraste ventas hoy.</p></div>
        ) : (
          <div className="lista">
            {(ventas.datos ?? []).map((v) => (
              <div key={v.id} className="fila fila--sin-foto" style={v.anulada ? { color: "var(--color-muted)" } : undefined}>
                <span className="fila__titulo">
                  <span className="fila__nombre" style={v.anulada ? { textDecoration: "line-through" } : undefined}>
                    {v.items.map((i) => `${i.cantidad} × ${i.nombre}`).join(", ")}
                  </span>
                  <span className="fila__meta">
                    {hora(v.creado_en)} · {v.metodo_pago}{v.cliente ? ` · ${v.cliente}` : ""}{v.anulada ? " · anulada" : ""}
                  </span>
                </span>
                <span className="fila__fin">
                  <span className="num" style={{ fontWeight: 700 }}>{dinero(v.total)}</span>
                  {!v.anulada &&
                    (aAnular === v.id ? (
                      <span style={{ display: "flex", gap: "var(--space-xs)" }}>
                        <Boton pequeno variante="danger" onClick={() => anular(v)}>Sí, anular</Boton>
                        <Boton pequeno variante="ghost" onClick={() => setAAnular(null)}>No</Boton>
                      </span>
                    ) : (
                      <Boton pequeno variante="ghost" onClick={() => setAAnular(v.id)}>Anular</Boton>
                    ))}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>
    </>
  );
}
