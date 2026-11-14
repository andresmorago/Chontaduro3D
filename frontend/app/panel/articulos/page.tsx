"use client";

import { useMemo, useState } from "react";
import { Boton } from "@/components/ui/Boton";
import { Foto } from "@/components/ui/Foto";
import { Icono } from "@/components/ui/Icono";
import { ArticuloHoja } from "@/components/panel/ArticuloHoja";
import { api } from "@/lib/api";
import { dinero } from "@/lib/format";
import { useCargar } from "@/lib/hooks";
import type { Articulo } from "@/lib/types";

const sinTildes = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

export default function Articulos() {
  const [archivados, setArchivados] = useState(false);
  const { datos, error, cargando, recargar } = useCargar(() => api.articulos.listar(archivados));
  const [objetivo, setObjetivo] = useState<Articulo | "nuevo" | null>(null);
  const [q, setQ] = useState("");

  const lista = useMemo(() => {
    const t = sinTildes(q.trim());
    const todos = datos ?? [];
    return t ? todos.filter((a) => sinTildes(`${a.nombre} ${a.codigo}`).includes(t)) : todos;
  }, [datos, q]);

  return (
    <>
      <div className="pagina-cab">
        <h1>Artículos</h1>
        <p className="lead">Tu lista maestra: nombre, foto, descripción y el precio que quieres cobrar. Puedes cambiar el precio cuando quieras.</p>
        <div className="pagina-cab__acciones">
          <Boton variante="accent" onClick={() => setObjetivo("nuevo")}><Icono nombre="mas" /> Nuevo artículo</Boton>
        </div>
      </div>

      {(datos ?? []).length > 6 && (
        <div className="buscador-panel" style={{ marginBottom: "var(--space-md)" }}>
          <label className="visually-hidden" htmlFor="q-articulos">Buscar artículo</label>
          <input id="q-articulos" className="input" type="search" placeholder="Buscar por nombre o código" value={q} onChange={(e) => setQ(e.target.value)} autoComplete="off" />
        </div>
      )}

      {error && <p className="alerta" role="alert">{error}</p>}
      {cargando ? (
        <p className="muted" role="status">Cargando…</p>
      ) : (datos ?? []).length === 0 ? (
        <div className="vacio">
          <h2 style={{ fontSize: "var(--text-title)" }}>Crea tu primer artículo</h2>
          <p>Cada artículo lleva nombre, una foto y el precio de venta. Después podrás registrar cuántos imprimes y cuántos vendes.</p>
          <Boton variante="accent" onClick={() => setObjetivo("nuevo")}>Nuevo artículo</Boton>
        </div>
      ) : lista.length === 0 ? (
        <div className="vacio"><p>Ningún artículo coincide con «{q}».</p></div>
      ) : (
        <div className="lista lista--tarjetas">
          {lista.map((a) => (
            <button key={a.id} type="button" className="fila" onClick={() => setObjetivo(a)} style={!a.activo ? { opacity: 0.6 } : undefined}>
              <span className="fila__foto"><Foto url={a.imagen_url} codigo="" nombre={a.nombre} /></span>
              <span className="fila__titulo">
                <span className="code muted">{a.codigo}</span>
                <span className="fila__nombre">{a.nombre}</span>
                <span className="fila__meta">
                  {!a.activo ? "Archivado" : a.publicado ? "En el catálogo" : "Oculto del catálogo"} · stock {a.stock}
                </span>
              </span>
              <span className="fila__fin">
                <span className="num" style={{ fontWeight: 700 }}>{dinero(a.precio_venta)}</span>
                <span className="fila__meta">Editar</span>
              </span>
            </button>
          ))}
        </div>
      )}

      <label className="check" style={{ marginTop: "var(--space-md)" }}>
        <input type="checkbox" checked={archivados} onChange={(e) => setArchivados(e.target.checked)} />
        Mostrar archivados
      </label>

      <ArticuloHoja objetivo={objetivo} onCerrar={() => setObjetivo(null)} onGuardado={recargar} />
    </>
  );
}
