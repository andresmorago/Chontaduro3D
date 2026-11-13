"use client";

import { useState } from "react";
import { useAvisos } from "@/components/ui/Avisos";
import { Icono } from "@/components/ui/Icono";
import { usePanel } from "@/components/panel/PanelShell";
import { api } from "@/lib/api";
import { enlaceWhatsapp, hace } from "@/lib/format";
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
        <p className="lead">Solicitudes del catálogo. No descuentan inventario: cuando concretes la venta, regístrala en Vender.</p>
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
        <div style={{ display: "grid", gap: "var(--space-md)" }}>
          {visibles.map((p) => (
            <article key={p.id} className={`pedido${p.estado === "nuevo" ? " pedido--nuevo" : ""}`}>
              <div className="pedido__cab">
                <div>
                  <h3 style={{ fontSize: "var(--text-lg)" }}>{p.nombre}</h3>
                  <p className="muted">{p.cantidad} × {p.articulo} <span className="code">({p.codigo})</span></p>
                </div>
                <p className="muted num">{hace(p.creado_en)}</p>
              </div>
              <div className="pedido__acciones">
                <a className="btn btn--accent btn--small" target="_blank" rel="noopener noreferrer" href={enlaceWhatsapp(p.whatsapp, `Hola ${p.nombre}, te escribimos por tu pedido de ${p.cantidad} × ${p.articulo}.`)} onClick={() => p.estado === "nuevo" && void cambiar(p, "contactado")}>
                  <Icono nombre="whatsapp" tamano={18} /> Escribir por WhatsApp
                </a>
                <span className="muted num">{p.whatsapp}</span>
              </div>
              <div className="segmentado" role="group" aria-label={`Estado del pedido de ${p.nombre}`}>
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
