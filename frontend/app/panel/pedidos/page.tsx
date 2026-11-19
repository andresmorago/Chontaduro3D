"use client";

import Link from "next/link";
import { Fragment, useState } from "react";
import { useAvisos } from "@/components/ui/Avisos";
import { Icono } from "@/components/ui/Icono";
import { usePanel } from "@/components/panel/PanelShell";
import { api } from "@/lib/api";
import { dinero, enlaceWhatsapp, hace } from "@/lib/format";
import { mensajeDe, useCargar } from "@/lib/hooks";
import type { DemandaArticulo, EstadoPedido, Pedido } from "@/lib/types";

const ESTADOS: { valor: EstadoPedido; etiqueta: string }[] = [
  { valor: "nuevo", etiqueta: "Nuevo" },
  { valor: "contactado", etiqueta: "Contactado" },
  { valor: "cerrado", etiqueta: "Cerrado" },
  { valor: "descartado", etiqueta: "Descartado" },
];

export default function Pedidos() {
  const { mostrar } = useAvisos();
  const { refrescarNuevos } = usePanel();
  const [filtro, setFiltro] = useState<"abiertos" | "todos">("abiertos");
  const [vista, setVista] = useState<"pedidos" | "producir">("pedidos");
  const { datos, error, cargando, recargar } = useCargar(() => api.pedidos.listar());
  const demanda = useCargar(() => api.pedidos.demanda());
  const todos = datos ?? [];
  const [q, setQ] = useState("");
  const abiertos = todos.filter((p) => p.estado === "nuevo" || p.estado === "contactado");
  const texto = q.trim().toLowerCase();
  const visibles = (filtro === "todos" ? todos : abiertos).filter((p) => !texto || `${p.nombre} ${p.items.map((i) => `${i.articulo} ${i.color ?? ""} ${i.codigo}`).join(" ")}`.toLowerCase().includes(texto));

  async function cambiar(p: Pedido, estado: EstadoPedido) {
    try {
      await api.pedidos.cambiarEstado(p.id, estado);
      await Promise.all([recargar(), demanda.recargar()]);
      refrescarNuevos();
    } catch (e) {
      mostrar(mensajeDe(e), { tipo: "error" });
    }
  }

  return (
    <>
      <div className="pagina-cab">
        <h1>Pedidos</h1>
        <p className="lead">Solicitudes del catálogo. No descuentan inventario: cuando concretes la venta, atiéndela desde aquí o en Vender, y el pedido se cierra con ella.</p>
      </div>
      <div className="barra-tabla">
        <div className="filtros" role="group" aria-label="Vista">
          <button type="button" className="chip" aria-pressed={vista === "pedidos"} onClick={() => setVista("pedidos")}>Por pedido</button>
          <button type="button" className="chip" aria-pressed={vista === "producir"} onClick={() => setVista("producir")}>Por producir <span className="chip__n num">{(demanda.datos ?? []).filter((d) => d.faltan > 0).length}</span></button>
        </div>
      </div>
      {vista === "producir" ? (
        <PorProducir lista={demanda.datos ?? []} cargando={demanda.cargando} error={demanda.error} />
      ) : (
      <>
      <div className="barra-tabla">
        <div className="filtros" role="group" aria-label="Filtrar pedidos">
          <button type="button" className="chip" aria-pressed={filtro === "abiertos"} onClick={() => setFiltro("abiertos")}>Por atender <span className="chip__n num">{abiertos.length}</span></button>
          <button type="button" className="chip" aria-pressed={filtro === "todos"} onClick={() => setFiltro("todos")}>Todos <span className="chip__n num">{todos.length}</span></button>
        </div>
        {todos.length > 6 && (
          <div className="buscador-panel">
            <label className="visually-hidden" htmlFor="filtro-pedidos">Buscar pedido</label>
            <input id="filtro-pedidos" className="input" type="search" placeholder="Buscar por cliente o artículo" value={q} onChange={(e) => setQ(e.target.value)} autoComplete="off" />
          </div>
        )}
      </div>
      {error && <p className="alerta" role="alert">{error}</p>}
      {cargando ? (
        <p className="muted" role="status">Cargando…</p>
      ) : visibles.length === 0 ? (
        <div className="vacio">
          <h2 style={{ fontSize: "var(--text-title)" }}>{q ? "Ningún pedido coincide" : filtro === "abiertos" ? "No hay pedidos por atender" : "Aún no hay pedidos"}</h2>
          <p>{q ? "Prueba con otro nombre o artículo." : "Cuando alguien pida algo desde el catálogo público, aparece aquí."}</p>
        </div>
      ) : (
        <div className="tabla-caja">
          <table className="tabla-datos tabla-ped">
            <caption className="visually-hidden">Pedidos del catálogo con sus artículos</caption>
            <thead>
              <tr>
                <th scope="col">Cliente</th>
                <th scope="col" className="c-mov-no">Recibido</th>
                <th scope="col" className="c-num c-mov-no">Piezas</th>
                <th scope="col" className="c-num c-mov-no">Total</th>
                <th scope="col">Estado</th>
                <th scope="col" className="c-acc"><span className="visually-hidden">Acciones</span></th>
              </tr>
            </thead>
            <tbody>
              {visibles.map((p) => {
                const abierto = p.estado === "nuevo" || p.estado === "contactado";
                const anuladas = p.ventas.filter((v) => v.anulada).length;
                return (
                  <Fragment key={p.id}>
                    <tr className="t-cab t-con-sub" data-aviso={p.estado === "nuevo"}>
                      <th scope="row" className="t-nombre">
                        {p.nombre}
                        <span className="t-sec num">{p.whatsapp}</span>
                        <span className="t-meta num">{hace(p.creado_en)} · {p.piezas === 1 ? "1 pieza" : `${p.piezas} piezas`} · {dinero(p.total_estimado)}{p.ventas.length > 0 ? ` · vendido ${dinero(p.total_vendido)}` : ""}</span>
                      </th>
                      <td className="c-mov-no num">{hace(p.creado_en)}</td>
                      <td className="c-num c-mov-no num">{p.piezas}</td>
                      <td className="c-num c-mov-no num">
                        <strong>{dinero(p.total_estimado)}</strong>
                        {p.ventas.length > 0 && <span className="t-sec">{p.total_vendido > 0 ? `Vendido ${dinero(p.total_vendido)}` : "Sin ventas vigentes"}{anuladas > 0 ? ` · ${anuladas} anulada${anuladas === 1 ? "" : "s"}` : ""}</span>}
                      </td>
                      <td className="c-fin">
                        <label className="t-estado">
                          <span className="visually-hidden">Estado del pedido de {p.nombre}</span>
                          <select className={`t-select t-select--${p.estado}`} value={p.estado} onChange={(e) => void cambiar(p, e.target.value as EstadoPedido)}>
                            {ESTADOS.map((e) => <option key={e.valor} value={e.valor}>{e.etiqueta}</option>)}
                          </select>
                        </label>
                      </td>
                      <td className="c-acc c-ancho">
                        <div className="t-acciones">
                          {abierto && <Link className="btn btn--primary btn--small" href={`/panel/vender?pedido=${p.id}`}>Atender con una venta</Link>}
                          <a className="btn btn--accent btn--small" target="_blank" rel="noopener noreferrer" aria-label={`Escribir por WhatsApp a ${p.nombre}`} href={enlaceWhatsapp(p.whatsapp, `Hola ${p.nombre}, te escribimos por tu pedido: ${p.items.map((i) => `${i.cantidad} × ${i.articulo}${i.color ? ` (${i.color})` : ""}`).join(", ")}.`)} onClick={() => p.estado === "nuevo" && void cambiar(p, "contactado")}>
                            <Icono nombre="whatsapp" tamano={18} /> WhatsApp
                          </a>
                        </div>
                      </td>
                    </tr>
                    {p.items.map((i) => (
                      <tr key={`${p.id}|${i.articulo_id}|${i.color ?? ""}`} className="t-sub">
                        <th scope="row" className="t-nombre">{i.articulo}{i.color ? ` · ${i.color}` : ""} <span className="code muted sin-corte">({i.codigo})</span></th>
                        <td className="c-mov-no" />
                        <td className="c-num c-mov-no num">{i.cantidad}</td>
                        <td className="c-num c-mov-no num">{dinero(i.subtotal)}</td>
                        <td className="c-fin num"><span className="t-solo-movil">{i.cantidad} {i.cantidad === 1 ? "ud" : "uds"} · {dinero(i.subtotal)}</span></td>
                        <td className="c-mov-no" />
                      </tr>
                    ))}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      </>
      )}
    </>
  );
}

/** Lo que piden los pedidos por atender, agrupado por artículo: cuánto falta producir. */
function PorProducir({ lista, cargando, error }: { lista: DemandaArticulo[]; cargando: boolean; error: string | null }) {
  const piezas = lista.reduce((n, d) => n + d.faltan, 0);
  const porProducir = lista.filter((d) => d.faltan > 0).length;
  if (error) return <p className="alerta" role="alert">{error}</p>;
  if (cargando) return <p className="muted" role="status">Cargando…</p>;
  if (lista.length === 0) {
    return (
      <div className="vacio">
        <h2 style={{ fontSize: "var(--text-title)" }}>No hay pedidos por atender</h2>
        <p>Cuando haya pedidos nuevos o contactados, aquí verás cuánto producir de cada artículo.</p>
      </div>
    );
  }
  return (
    <>
      <p className="lead" role="status">
        {piezas === 0
          ? "El inventario cubre todos los pedidos por atender."
          : `Faltan ${piezas} ${piezas === 1 ? "pieza" : "piezas"} de ${porProducir} ${porProducir === 1 ? "artículo" : "artículos"} para cubrir los pedidos por atender.`}{" "}
        Lo ya vendido a un pedido no cuenta.{piezas > 0 && <> <Link href="/panel/produccion">Ir a Producción</Link></>}
      </p>
      <div className="tabla-caja">
        <table className="tabla-datos tabla-ped">
          <caption className="visually-hidden">Demanda de los pedidos por atender, por artículo</caption>
          <thead>
            <tr>
              <th scope="col">Artículo</th>
              <th scope="col" className="c-num c-mov-no">Pedidos</th>
              <th scope="col" className="c-num c-mov-no">Piden</th>
              <th scope="col" className="c-num c-mov-no">En stock</th>
              <th scope="col" className="c-num">Producir</th>
            </tr>
          </thead>
          <tbody>
            {lista.map((d) => (
              <Fragment key={d.articulo_id}>
                <tr className={`t-cab${d.colores.length > 0 ? " t-con-sub" : ""}`} data-aviso={d.faltan > 0}>
                  <th scope="row" className="t-nombre">
                    {d.articulo} <span className="code muted sin-corte">({d.codigo})</span>
                    <span className="t-meta num">{d.pedidos === 1 ? "1 pedido" : `${d.pedidos} pedidos`} · piden {d.pendiente} · stock {d.stock}</span>
                  </th>
                  <td className="c-num c-mov-no num">{d.pedidos}</td>
                  <td className="c-num c-mov-no num">{d.pendiente}</td>
                  <td className="c-num c-mov-no num">{d.stock}</td>
                  <td className="c-num num"><strong>{d.faltan > 0 ? d.faltan : "Cubierto"}</strong></td>
                </tr>
                {d.colores.map((c) => (
                  <tr key={`${d.articulo_id}|${c.color ?? ""}`} className="t-sub" data-cero={c.faltan === 0}>
                    <th scope="row" className="t-nombre">{c.color ?? "Sin color asignado"}</th>
                    <td className="c-mov-no" />
                    <td className="c-num c-mov-no num">{c.pendiente}</td>
                    <td className="c-num c-mov-no num">{c.stock}</td>
                    <td className="c-num num">
                      {c.faltan > 0 ? c.faltan : "Cubierto"}
                      <span className="t-solo-movil t-sec">piden {c.pendiente} · stock {c.stock}</span>
                    </td>
                  </tr>
                ))}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
