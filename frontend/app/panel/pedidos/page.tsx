"use client";

import Link from "next/link";
import { useState } from "react";
import { useAvisos } from "@/components/ui/Avisos";
import { Icono } from "@/components/ui/Icono";
import { usePanel } from "@/components/panel/PanelShell";
import { api } from "@/lib/api";
import { dinero, enlaceWhatsapp, hace } from "@/lib/format";
import { mensajeDe, useCargar } from "@/lib/hooks";
import type { EstadoPedido, Pedido } from "@/lib/types";

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
  const { datos, error, cargando, recargar } = useCargar(() => api.pedidos.listar());
  const todos = datos ?? [];
  const visibles = filtro === "todos" ? todos : todos.filter((p) => p.estado === "nuevo" || p.estado === "contactado");

  async function cambiar(p: Pedido, estado: EstadoPedido) {
    try {
      await api.pedidos.cambiarEstado(p.id, estado);
      await recargar();
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
      <div className="filtros" role="group" aria-label="Filtrar pedidos" style={{ marginBottom: "var(--space-md)" }}>
        <button type="button" className="etiqueta" style={{ minHeight: 40, padding: "0 var(--space-md)", background: filtro === "abiertos" ? "var(--color-ink)" : undefined, color: filtro === "abiertos" ? "var(--color-paper)" : undefined }} aria-pressed={filtro === "abiertos"} onClick={() => setFiltro("abiertos")}>Por atender</button>
        <button type="button" className="etiqueta" style={{ minHeight: 40, padding: "0 var(--space-md)", background: filtro === "todos" ? "var(--color-ink)" : undefined, color: filtro === "todos" ? "var(--color-paper)" : undefined }} aria-pressed={filtro === "todos"} onClick={() => setFiltro("todos")}>Todos</button>
      </div>
      {error && <p className="alerta" role="alert">{error}</p>}
      {cargando ? (
        <p className="muted" role="status">Cargando…</p>
      ) : visibles.length === 0 ? (
        <div className="vacio">
          <h2 style={{ fontSize: "var(--text-title)" }}>{filtro === "abiertos" ? "No hay pedidos por atender" : "Aún no hay pedidos"}</h2>
          <p>Cuando alguien pida algo desde el catálogo público, aparece aquí.</p>
        </div>
      ) : (
        <div className="pedidos-grid">
          {visibles.map((p) => (
            <article key={p.id} className={`pedido${p.estado === "nuevo" ? " pedido--nuevo" : ""}`}>
              <div className="pedido__cab">
                <div>
                  <h3 style={{ fontSize: "var(--text-lg)" }}>{p.nombre}</h3>
                  <p className="muted num"><span className="sin-corte">{p.piezas === 1 ? "1 pieza" : `${p.piezas} piezas`}</span> · <span className="sin-corte">{dinero(p.total_estimado)}</span> <span className="muted">(a precios de hoy)</span></p>
                </div>
                <p className="muted num">{hace(p.creado_en)}</p>
              </div>
              <ul className="pedido__items">
                {p.items.map((i) => (
                  <li key={`${i.articulo_id}|${i.color ?? ""}`}>
                    <span className="pedido__nombre"><strong className="num sin-corte">{i.cantidad} ×</strong> {i.articulo}{i.color ? ` · ${i.color}` : ""} <span className="code muted sin-corte">({i.codigo})</span></span>
                    <span className="num muted pedido__precio">{dinero(i.subtotal)}</span>
                  </li>
                ))}
              </ul>
              {p.ventas.length > 0 && (
                <p className="muted pedido__ventas">
                  {p.total_vendido > 0 ? <>Vendido: <strong className="num sin-corte">{dinero(p.total_vendido)}</strong></> : "Sin ventas vigentes"}
                  {p.ventas.some((v) => v.anulada) && ` · ${p.ventas.filter((v) => v.anulada).length === 1 ? "1 venta anulada" : `${p.ventas.filter((v) => v.anulada).length} ventas anuladas`}`}
                </p>
              )}
              <div className="pedido__acciones">
                {(p.estado === "nuevo" || p.estado === "contactado") && (
                  <Link className="btn btn--primary btn--small" href={`/panel/vender?pedido=${p.id}`}>Atender con una venta</Link>
                )}
                <a className="btn btn--accent btn--small" target="_blank" rel="noopener noreferrer" href={enlaceWhatsapp(p.whatsapp, `Hola ${p.nombre}, te escribimos por tu pedido: ${p.items.map((i) => `${i.cantidad} × ${i.articulo}${i.color ? ` (${i.color})` : ""}`).join(", ")}.`)} onClick={() => p.estado === "nuevo" && void cambiar(p, "contactado")}>
                  <Icono nombre="whatsapp" tamano={18} /> Escribir por WhatsApp
                </a>
                <span className="muted num">{p.whatsapp}</span>
              </div>
              <div className="segmentado segmentado--rejilla" role="group" aria-label={`Estado del pedido de ${p.nombre}`}>
                {ESTADOS.map((e) => (
                  <button key={e.valor} type="button" className="segmentado__op" aria-pressed={p.estado === e.valor} onClick={() => p.estado !== e.valor && void cambiar(p, e.valor)}>{e.etiqueta}</button>
                ))}
              </div>
            </article>
          ))}
        </div>
      )}
    </>
  );
}
