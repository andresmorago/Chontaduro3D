"use client";

import { useEffect, useState } from "react";
import { Boton } from "@/components/ui/Boton";
import { useAvisos } from "@/components/ui/Avisos";
import { Contador } from "@/components/ui/Contador";
import { Entrada, Seleccion } from "@/components/ui/Campo";
import { Segmentado } from "@/components/ui/Segmentado";
import { Selector } from "@/components/panel/Selector";
import { api } from "@/lib/api";
import { clave, hexColor, nombreColor, partirClave, stockDe } from "@/lib/lineas";
import { dinero, hora } from "@/lib/format";
import { mensajeDe, useCargar } from "@/lib/hooks";
import { lineasDePedido, type LineaVenta as Linea } from "@/lib/pedidoAVenta";
import type { Articulo, MetodoPago, Venta } from "@/lib/types";

const METODOS = [
  { valor: "efectivo", etiqueta: "Efectivo" },
  { valor: "transferencia", etiqueta: "Transferencia" },
  { valor: "otro", etiqueta: "Otro" },
] as const;

export default function Vender() {
  const { mostrar } = useAvisos();
  const articulos = useCargar(() => api.articulos.listar());
  const ventas = useCargar(api.ventas.deHoy);
  const pedidos = useCargar(() => api.pedidos.listar());
  // Pedido que esta venta atiende (opcional). Llega por ?pedido= desde Pedidos → «Atender».
  const [pedidoId, setPedidoId] = useState("");
  const [cerrarPedido, setCerrarPedido] = useState(true);
  const [pedidoUrl, setPedidoUrl] = useState<string | null>(null);
  const [lineas, setLineas] = useState<Record<string, Linea>>({});
  const [metodo, setMetodo] = useState<MetodoPago>("efectivo");
  const [cliente, setCliente] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [aAnular, setAAnular] = useState<string | null>(null);

  const lista = articulos.datos ?? [];
  const porId = new Map(lista.map((a) => [a.id, a]));
  const abiertos = (pedidos.datos ?? []).filter((p) => p.estado === "nuevo" || p.estado === "contactado");
  const pedido = abiertos.find((p) => p.id === pedidoId) ?? null;
  // Cada línea es un (artículo, color): la clave las distingue (ver lib/lineas.ts).
  const items = Object.entries(lineas).filter(([k, l]) => l.cantidad > 0 && porId.has(partirClave(k).articuloId));
  const precioDe = (a: Articulo, l: Linea) => l.precio ?? a.precio_venta;
  const articuloDe = (k: string) => porId.get(partirClave(k).articuloId)!;
  const total = items.reduce((s, [k, l]) => s + precioDe(articuloDe(k), l) * l.cantidad, 0);
  const piezas = items.reduce((s, [, l]) => s + l.cantidad, 0);

  function poner(k: string, cantidad: number) {
    setLineas((m) => {
      const { [k]: _quitada, ...resto } = m;
      void _quitada;
      return cantidad <= 0 ? resto : { ...m, [k]: { cantidad, precio: m[k]?.precio ?? null } };
    });
  }

  function cambiar(a: Articulo, colorId: string | null, delta: number) {
    const k = clave(a.id, colorId);
    const nuevo = (lineas[k]?.cantidad ?? 0) + delta;
    const hay = stockDe(a, colorId);
    if (delta > 0 && nuevo > hay) {
      const color = nombreColor(a, colorId);
      mostrar(`De ${a.nombre}${color ? ` (${color})` : ""} solo quedan ${hay}.`, { tipo: "error" });
      return;
    }
    poner(k, nuevo);
  }

  /** Carga en la venta lo que pidió el cliente (con el color y lo que alcance del stock). */
  function cargarPedido(p: (typeof abiertos)[number]) {
    const { lineas: nuevas, avisos } = lineasDePedido(p, porId);
    setLineas(nuevas);
    if (!cliente.trim()) setCliente(p.nombre);
    if (avisos.length > 0) mostrar(avisos.join(" "), { tipo: "error", ms: 9000 });
  }

  function elegirPedido(id: string) {
    setPedidoId(id);
    const p = abiertos.find((x) => x.id === id);
    // Con la venta vacía se carga solo; si ya había líneas no se pisan (hay un botón para cargarlo).
    if (p && items.length === 0) cargarPedido(p);
  }

  // Llegada desde Pedidos → «Atender»: ?pedido=<id>. Se espera a tener artículos y pedidos cargados.
  useEffect(() => {
    setPedidoUrl(new URLSearchParams(window.location.search).get("pedido"));
  }, []);
  useEffect(() => {
    if (!pedidoUrl || articulos.cargando || pedidos.cargando) return;
    const p = abiertos.find((x) => x.id === pedidoUrl);
    setPedidoUrl(null);
    window.history.replaceState(null, "", "/panel/vender");
    if (!p) return mostrar("Ese pedido ya no está por atender.", { tipo: "error" });
    setPedidoId(p.id);
    cargarPedido(p);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pedidoUrl, articulos.cargando, pedidos.cargando]);

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
        ...(pedido ? { pedido_id: pedido.id, cerrar_pedido: cerrarPedido } : {}),
        items: items.map(([k, l]) => {
          const { articuloId, colorId } = partirClave(k);
          return { articulo_id: articuloId, ...(colorId ? { color_id: colorId } : {}), cantidad: l.cantidad, ...(l.precio !== null ? { precio_unitario: l.precio } : {}) };
        }),
      });
      const cerrado = Boolean(pedido && cerrarPedido);
      setLineas({});
      setCliente("");
      setPedidoId("");
      mostrar(`Venta registrada${cerrado ? " y pedido cerrado" : ""} · ${dinero(v.total)}`, { accion: { etiqueta: "Deshacer", alPulsar: () => deshacer(v.id) } });
      await Promise.all([articulos.recargar(), ventas.recargar(), pedidos.recargar()]);
    } catch (e) {
      mostrar(mensajeDe(e), { tipo: "error" });
      void articulos.recargar(); // el stock pudo cambiar: se muestra el real
      void pedidos.recargar(); // y el pedido pudo cerrarse o descartarse mientras tanto
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
          <Selector articulos={lista} cantidades={Object.fromEntries(items.map(([k, l]) => [k, l.cantidad]))} onCambiar={cambiar} exigirStock mostrarPrecio incluirSinColor />

          <section className="ticket" id="ticket" aria-labelledby="t-ticket">
            <h2 id="t-ticket" style={{ fontSize: "var(--text-title)" }}>Esta venta</h2>
            {items.length === 0 ? (
              <p className="ticket__vacio">Toca un artículo para agregarlo.</p>
            ) : (
              <div className="ticket__lineas">
                {items.map(([k, l]) => {
                  const a = articuloDe(k);
                  const { colorId } = partirClave(k);
                  const color = nombreColor(a, colorId) ?? (a.colores.length > 0 ? "Sin color asignado" : null);
                  const precio = precioDe(a, l);
                  return (
                    <div key={k} className="linea">
                      <span className="linea__nombre">
                        {a.nombre}
                        {color && (
                          <span className="linea__color">
                            <span className="muestra-mini" style={hexColor(a, colorId) ? { background: hexColor(a, colorId)! } : undefined} aria-hidden="true" />
                            {color}
                          </span>
                        )}
                      </span>
                      <Contador editable valor={l.cantidad} min={0} max={stockDe(a, colorId)} onCambio={(n) => poner(k, n)} etiqueta={`${a.nombre}${color ? `, ${color}` : ""}`} />
                      <label className="linea__precio">
                        Precio c/u
                        <input className="input num" type="number" inputMode="numeric" min={0} step={100} value={precio} onChange={(e) => setLineas((m) => ({ ...m, [k]: { cantidad: l.cantidad, precio: e.target.value === "" ? null : Math.max(0, Number(e.target.value)) } }))} />
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
            {abiertos.length > 0 && (
              <div className="ticket__pedido">
                <Seleccion etiqueta="Pedido que atiendes (opcional)" value={pedidoId} onChange={(e) => elegirPedido(e.target.value)}>
                  <option value="">Ninguno: venta suelta</option>
                  {abiertos.map((p) => (
                    <option key={p.id} value={p.id}>{p.nombre} · {dinero(p.total_estimado)}</option>
                  ))}
                </Seleccion>
                {pedido && (
                  <>
                    <label className="ticket__cerrar">
                      <input type="checkbox" checked={cerrarPedido} onChange={(e) => setCerrarPedido(e.target.checked)} />
                      <span>Cerrar el pedido al registrar la venta</span>
                    </label>
                    <Boton variante="secondary" pequeno onClick={() => cargarPedido(pedido)}>Cargar los artículos del pedido</Boton>
                  </>
                )}
              </div>
            )}
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
          <div className="tabla-caja">
            <table className="tabla-datos tabla-ventas">
              <caption className="visually-hidden">Ventas de hoy</caption>
              <thead>
                <tr>
                  <th scope="col" className="c-mov-no">Hora</th>
                  <th scope="col">Venta</th>
                  <th scope="col" className="c-mov-no">Cliente</th>
                  <th scope="col" className="c-mov-no">Pago</th>
                  <th scope="col" className="c-num">Total</th>
                  <th scope="col" className="c-acc"><span className="visually-hidden">Acciones</span></th>
                </tr>
              </thead>
              <tbody>
                {(ventas.datos ?? []).map((v) => (
                  <tr key={v.id} data-cero={v.anulada} className={v.anulada ? "t-anulada" : undefined}>
                    <td className="c-mov-no num">{hora(v.creado_en)}</td>
                    <th scope="row" className="t-nombre">
                      {v.items.map((i) => `${i.cantidad} × ${i.nombre}${i.color ? ` (${i.color})` : ""}`).join(", ")}
                      {v.pedido_nombre && <span className="t-sec">Pedido de {v.pedido_nombre}</span>}
                      <span className="t-meta num">{hora(v.creado_en)} · {v.metodo_pago}{v.cliente ? ` · ${v.cliente}` : ""}{v.anulada ? " · anulada" : ""}</span>
                    </th>
                    <td className="c-mov-no">{v.cliente ?? "—"}</td>
                    <td className="c-mov-no">{v.metodo_pago}{v.anulada && <span className="etiqueta etiqueta--tenue" style={{ marginLeft: "var(--space-xs)" }}>Anulada</span>}</td>
                    <td className="c-num c-fin num"><strong>{dinero(v.total)}</strong></td>
                    <td className="c-acc c-ancho">
                      {!v.anulada &&
                        (aAnular === v.id ? (
                          <span className="t-acciones">
                            <Boton pequeno variante="danger" onClick={() => anular(v)}>Sí, anular</Boton>
                            <Boton pequeno variante="ghost" onClick={() => setAAnular(null)}>No</Boton>
                          </span>
                        ) : (
                          <Boton pequeno variante="ghost" onClick={() => setAAnular(v.id)}>Anular</Boton>
                        ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
